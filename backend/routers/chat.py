"""Assistant chat on standard parts (tilt_ui-qzk0.1).

Pydantic AI runs the agent loop; VercelAIAdapter (sdk v7) streams the AI SDK
UI message stream that @ai-sdk/svelte's `Chat` consumes. History is held on
the server (chat_histories): the client sends only its newest message, so it
cannot forge tool outputs or approvals. An approval is accepted only for a
tool call still unanswered at the end of the stored history, runs with the
stored args, and once answered is no longer pending (no replay).

Replaced the old AG-UI router (removed in tilt_ui-qzk0.3).
"""

import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Annotated, Any, AsyncIterator, Optional

import anyio
import prompty
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, ValidationError
from pydantic_ai import Agent, DeferredToolRequests, RunContext, Tool, UsageLimits
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models import Model
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.models.openrouter import OpenRouterModel, OpenRouterModelSettings
from pydantic_ai.providers.ollama import OllamaProvider
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.providers.openrouter import OpenRouterProvider
from pydantic_ai.settings import ModelSettings
from pydantic_ai.ui._adapter import pending_tool_calls
from pydantic_ai.ui.vercel_ai import VercelAIAdapter
from pydantic_ai.ui.vercel_ai._event_stream import VercelAIEventStream
from pydantic_ai.ui.vercel_ai.response_types import BaseChunk, ErrorChunk, MessageMetadataChunk
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import AuthUser, require_auth
from backend.database import get_db
from backend.models import AgUiThread, ChatHistory, serialize_datetime_to_utc
from backend.routers.assistant import get_llm_config
from backend.services.chat_store import SDK_VERSION, conversation_text, dump_history, load_history, to_ui_messages
from backend.services.chat_support import (
    PROMPTS_DIR,
    _extract_memories_background,
    _get_lite_llm_config,
    _get_recipe_system_prompt,
)
from backend.services.hop_inventory_bulk import BulkHopItem, StaleStockError, bulk_update_hops
from backend.services.llm.config import DEFAULT_BASE_URLS, DEFAULT_MODELS, ENV_VAR_NAMES, LLMConfig, LLMProvider
from backend.services.llm.openrouter import resolve_openrouter_model
from backend.services.llm.tools import TOOL_DEFINITIONS, execute_tool
from backend.services.memory import format_memories_for_context, search_memories

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/chat", tags=["chat"])

ERROR_TEXT = "The assistant hit an error. Try again."
MAX_MODEL_REQUESTS = 15  # per run, same cap as the old agent loop
DENIED_TEXT = "The user did not approve this action."

# Providers reachable with the openai SDK (already installed with the openrouter extra)
OPENAI_COMPATIBLE_URLS: dict[str, Optional[str]] = {
    "openai": None,
    "deepseek": "https://api.deepseek.com",
    "groq": "https://api.groq.com/openai/v1",
    "google": "https://generativelanguage.googleapis.com/v1beta/openai/",
    "huggingface": "https://router.huggingface.co/v1",
}
# Cheap models for title summarisation (bare ids, no litellm prefixes)
FAST_TITLE_MODELS = {
    "openrouter": "anthropic/claude-haiku-4.5",
    "openai": "gpt-4o-mini",
    "google": "gemini-1.5-flash",
    "groq": "llama-3.1-8b-instant",
    "deepseek": "deepseek-chat",
    "local": "smollm2:360m",
    "hailo": "qwen2:1.5b",
}
LITE_TITLE_MODEL = "qwen2:1.5b"  # hailo-ollama

# Threads with a run in flight. A second run on the same thread gets 409.
# ponytail: in-process set, correct for the single-process Pi; use a DB lock if workers > 1
_active: set[str] = set()
_background: set[asyncio.Task] = set()  # keep refs so tasks are not garbage collected


# =============================================================================
# Model
# =============================================================================


class UnsupportedProvider(Exception):
    pass


def _ollama_model(name: str, base_url: str) -> Model:
    base = base_url.rstrip("/")
    return OpenAIChatModel(name, provider=OllamaProvider(base_url=base if base.endswith("/v1") else f"{base}/v1"))


def build_model(config: LLMConfig, model_name: Optional[str] = None) -> Model:
    """Pydantic AI model for the configured provider."""
    provider = config._provider_str()
    name = model_name or config.model or DEFAULT_MODELS[LLMProvider(provider)]
    key = config.api_key.get_secret_value() if config.api_key else os.environ.get(ENV_VAR_NAMES.get(provider, ""))
    if provider == "openrouter":
        return OpenRouterModel(name, provider=OpenRouterProvider(api_key=key))
    if provider in ("local", "hailo"):
        return _ollama_model(name, config.base_url or DEFAULT_BASE_URLS[LLMProvider(provider)])
    if provider in OPENAI_COMPATIBLE_URLS:
        return OpenAIChatModel(name, provider=OpenAIProvider(base_url=OPENAI_COMPATIBLE_URLS[provider], api_key=key))
    raise UnsupportedProvider(provider)


def model_settings(config: LLMConfig) -> ModelSettings:
    if config._provider_str() == "openrouter":
        # Reasoning models can spend the whole max_tokens budget thinking after
        # tool results and emit no text: cap reasoning at half (tilt_ui-atvb)
        return OpenRouterModelSettings(
            max_tokens=config.max_tokens,
            temperature=config.temperature,
            openrouter_reasoning={"max_tokens": config.max_tokens // 2},
        )
    return ModelSettings(max_tokens=config.max_tokens, temperature=config.temperature)


# =============================================================================
# Agent and tools
# =============================================================================


@dataclass
class ChatDeps:
    db: AsyncSession
    user_id: Optional[str]
    thread_id: str
    # approval-gated calls that already ran: tool_call_id -> (tool_name, result)
    executed: dict = field(default_factory=dict)


def _bridge(name: str, description: str, schema: dict) -> Tool:
    """A Pydantic AI tool that runs the existing execute_tool dispatcher.

    Schema validation is the library's job only for shape; execute_tool takes
    the raw args exactly as the ag_ui loop passed them.
    """

    async def run(ctx: RunContext[ChatDeps], **args: Any) -> dict:
        try:
            return await execute_tool(
                ctx.deps.db, name, args, thread_id=ctx.deps.thread_id, user_id=ctx.deps.user_id
            )
        except Exception as e:
            logger.exception("Chat tool %s failed", name)
            await ctx.deps.db.rollback()  # a failed statement must not poison later tools
            return {"error": f"{type(e).__name__}: {e}"}

    # sequential=True: every tool shares one AsyncSession, which cannot run concurrent statements
    return Tool.from_schema(run, name=name, description=description, json_schema=schema, takes_ctx=True, sequential=True)


# update_hop_inventory is the old preview + confirm-card tool; preview/apply below replace it
_REPLACED = {"update_hop_inventory"}
_bridged = [
    _bridge(t["function"]["name"], t["function"]["description"], t["function"]["parameters"])
    for t in TOOL_DEFINITIONS
    if t["function"]["name"] not in _REPLACED
]

agent = Agent(
    deps_type=ChatDeps,
    # A run can end waiting for the user to approve apply_hop_inventory
    output_type=[str, DeferredToolRequests],
    tools=_bridged,
)

HOP_INSTRUCTIONS = (
    "To change hop inventory from a list the user gives you: first call preview_hop_inventory with "
    "every item, summarise the plan briefly, ask whether to replace all existing hops or only add "
    "and update, then call apply_hop_inventory with the same items, that choice and the preview's "
    "stock_version. The app asks the user to approve before it runs."
)


@agent.tool(sequential=True)
async def preview_hop_inventory(ctx: RunContext[ChatDeps], items: list[BulkHopItem]) -> dict:
    """Preview updating hop inventory from a list of hop names and grams. Saves nothing.

    Names are matched to the hop library. Returns the plan for a full replace (stock
    lines marked replace_only are kept when only adding/updating) and the stock_version
    to pass to apply_hop_inventory.
    """
    return await bulk_update_hops(ctx.deps.db, ctx.deps.user_id, items, replace=True, dry_run=True)


@agent.tool(requires_approval=True, sequential=True)
async def apply_hop_inventory(
    ctx: RunContext[ChatDeps],
    items: list[BulkHopItem],
    replace: bool,
    expected_stock_version: Annotated[str, Field(min_length=1)],
) -> dict:
    """Save a hop inventory update the user approved. replace=True removes hops not in the list.

    expected_stock_version must be the stock_version from the latest preview.
    """
    try:
        result = await bulk_update_hops(
            ctx.deps.db, ctx.deps.user_id, items, replace=replace, dry_run=False,
            expected_stock_version=expected_stock_version,
        )
    except StaleStockError:
        result = {"error": "Hop inventory changed since the preview. Preview again before saving."}
    except ValueError as e:
        result = {"error": str(e)}
    # Remembered so the approval is consumed even if the run dies after this commit
    ctx.deps.executed[ctx.tool_call_id] = ("apply_hop_inventory", result)
    return result


# =============================================================================
# Adapter: fixed client error text, server-side logging
# =============================================================================


class ChatEventStream(VercelAIEventStream):
    async def on_error(self, error: Exception) -> AsyncIterator[BaseChunk]:
        logger.error("Chat run failed", exc_info=error)
        async for chunk in super().on_error(error):
            yield ErrorChunk(error_text=ERROR_TEXT) if isinstance(chunk, ErrorChunk) else chunk


@dataclass
class ChatAdapter(VercelAIAdapter):
    def build_event_stream(self):
        return ChatEventStream(
            self.run_input,
            accept=self.accept,
            sdk_version=self.sdk_version,
            server_message_id=self.server_message_id,
            manage_system_prompt=self.manage_system_prompt,
        )


# =============================================================================
# Helpers
# =============================================================================


def _text_of(message: dict) -> str:
    return "\n".join(p.get("text", "") for p in message.get("parts", []) if p.get("type") == "text").strip()


async def _owned_thread(db: AsyncSession, thread_id: str, user: AuthUser) -> Optional[AgUiThread]:
    return (await db.execute(
        select(AgUiThread).where(AgUiThread.id == thread_id, AgUiThread.user_id == user.user_id)
    )).scalar_one_or_none()


async def _thread_or_404(db: AsyncSession, thread_id: str, user: AuthUser) -> AgUiThread:
    thread = await _owned_thread(db, thread_id, user)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    return thread


async def _get_or_create_thread(db: AsyncSession, thread_id: str, user: AuthUser, first_text: str) -> AgUiThread:
    """The caller's thread; creates it for a new id. 404 when the id belongs to someone else."""
    thread = await _owned_thread(db, thread_id, user)
    if thread:
        return thread
    if (await db.execute(select(AgUiThread.id).where(AgUiThread.id == thread_id))).first():
        raise HTTPException(status_code=404, detail="Thread not found")
    title = snippet_title(first_text) if first_text else None
    thread = AgUiThread(id=thread_id, user_id=user.user_id, title=title)
    db.add(thread)
    await db.commit()
    return thread


async def _load(db: AsyncSession, thread_id: str) -> list[ModelMessage]:
    row = await db.get(ChatHistory, thread_id)
    return load_history(row.messages) if row else []


async def _save(db: AsyncSession, thread: AgUiThread, messages: list[ModelMessage]) -> None:
    row = await db.get(ChatHistory, thread.id)
    if not row:
        row = ChatHistory(thread_id=thread.id, user_id=thread.user_id)
        db.add(row)
    row.messages = dump_history(messages)
    row.message_count = len(to_ui_messages(messages))
    row.updated_at = thread.updated_at = datetime.now(timezone.utc)
    await db.commit()


async def _save_executed(
    db: AsyncSession, thread: AgUiThread, history: list[ModelMessage], executed: dict
) -> None:
    """Store the results of approval-gated calls that ran in a run that did not finish."""
    await db.rollback()  # the run may have died mid-transaction; the tool's own commit is already durable
    await db.refresh(thread)  # rollback expired it; reload asynchronously before _save reads its columns
    open_ids = {c.tool_call_id for c in pending_tool_calls(history)}
    parts = [
        ToolReturnPart(tool_name=name, tool_call_id=cid, content=result)
        for cid, (name, result) in executed.items() if cid in open_ids
    ]
    if parts:
        await _save(db, thread, [*history, ModelRequest(parts=parts)])


async def _instructions(db: AsyncSession, config: LLMConfig, user: AuthUser, query: str, context: Optional[dict]) -> str:
    text = await _get_recipe_system_prompt(db, None)
    text += "\n\n" + HOP_INSTRUCTIONS
    batch_id = (context or {}).get("batch_id")
    if isinstance(batch_id, int):
        text += f"\n\nThe user is currently viewing batch #{batch_id}; questions about 'this batch' mean it."
    if user.user_id and query:
        try:
            memories = await search_memories(query, user_id=user.user_id, llm_config=config, limit=5)
            if memory_context := format_memories_for_context(memories):
                text += f"\n\n{memory_context}"
        except Exception as e:
            logger.warning("Chat memory search failed: %s", e)
    return text


_conversation = conversation_text


def _spawn(coro) -> None:
    task = asyncio.create_task(coro)
    _background.add(task)
    task.add_done_callback(_background.discard)


# =============================================================================
# Title summarisation (cheap model, or the local lite
# LLM when ai_lite_enabled and hailo-ollama is running)
# =============================================================================


async def summarize_title(thread_id: str) -> Optional[str]:
    from backend.database import async_session_factory

    try:
        async with async_session_factory() as db:
            lite_enabled, hailo_url = await _get_lite_llm_config(db)
            config = await get_llm_config(db)
            if lite_enabled and hailo_url:
                model = _ollama_model(LITE_TITLE_MODEL, hailo_url)
                logger.info("Summarizing chat %s title with the local lite LLM", thread_id)
            elif config.is_configured():
                provider = config._provider_str()
                name = FAST_TITLE_MODELS.get(provider) or config.model
                if provider == "openrouter":
                    name = await resolve_openrouter_model(name)
                model = build_model(config, name)
            else:
                return None

            history = await _load(db, thread_id)
            lines = [f"{m['role']}: {m['content'][:200]}" for m in _conversation(history)[:4]]
            if not lines:
                return None
            rendered = prompty.prepare(
                prompty.load(str(PROMPTS_DIR / "title.prompty")), inputs={"conversation": "\n".join(lines)}
            )
            system = next(m["content"] for m in rendered if m["role"] == "system")
            user_msg = next(m["content"] for m in rendered if m["role"] == "user")
            result = await Agent(model, instructions=system).run(
                user_msg, model_settings=ModelSettings(temperature=0.3, max_tokens=60)
            )
            title = result.output.strip().strip("\"'").strip()
            if not title:
                return None
            if len(title) > 60:
                title = title[:57] + "..."
            thread = await db.get(AgUiThread, thread_id)
            if thread and not thread.title_locked:
                thread.title = title
                await db.commit()
            return title
    except Exception as e:
        logger.warning("Chat title summarization failed: %s", e)
        return None


# Legacy titles were message fragments ("**y in the library...", "(0 min) | 15 |").
_CONTENT_TITLE = re.compile(r"[\n\r|*#`>]|\]\(|^\s*[-+]\s")
_MD_STRIP = re.compile(r"[*_`#>|]+|\[([^\]]*)\]\([^)]*\)")


def looks_like_content(title: Optional[str]) -> bool:
    return bool(title) and (len(title) > 60 or bool(_CONTENT_TITLE.search(title)))


def snippet_title(text: str) -> Optional[str]:
    """First line-ish of a message as a plain title: no markdown, one line, <= 60 chars."""
    text = _MD_STRIP.sub(lambda m: m.group(1) or " ", text)
    text = " ".join(text.split()).strip(" -+.")
    if not text:
        return None
    return text if len(text) <= 60 else text[:57].rstrip() + "..."


async def retitle_legacy_threads() -> int:
    """One-time-ish background job (tilt_ui-qzk0.4): re-title unlocked threads whose title
    looks like message content. Uses the title summariser; with no model configured (or on
    failure) falls back to a cleaned snippet of the first user message. Idempotent: a
    retitled thread no longer matches, and title_locked threads are never touched."""
    from backend.database import async_session_factory

    try:
        async with async_session_factory() as db:
            rows = (await db.execute(select(AgUiThread.id, AgUiThread.title, AgUiThread.title_locked))).all()
        ids = [r.id for r in rows if not r.title_locked and looks_like_content(r.title)]
        done = 0
        for thread_id in ids:
            await summarize_title(thread_id)  # sets the title itself when it works; ignores locked
            async with async_session_factory() as db:
                thread = await db.get(AgUiThread, thread_id)
                if not thread or thread.title_locked or not looks_like_content(thread.title):
                    done += 1
                    continue
                first_user = next((m["content"] for m in _conversation(await _load(db, thread_id)) if m["role"] == "user"), "")
                if fallback := snippet_title(first_user or thread.title or ""):
                    thread.title = fallback
                    await db.commit()
                    done += 1
        if ids:
            logger.info("Re-titled %d/%d legacy chat threads", done, len(ids))
        return done
    except Exception:
        logger.exception("Legacy chat re-titling failed; will retry on next boot")
        return 0


# =============================================================================
# Endpoints
# =============================================================================


@router.post("")
async def run_chat(
    request: Request,
    user: AuthUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> Response:
    try:
        body = await request.json()
        thread_id = body["id"]
        message = body["message"]
        assert isinstance(thread_id, str) and 0 < len(thread_id) <= 100 and isinstance(message, dict)
    except Exception:
        raise HTTPException(status_code=422, detail="Body needs `id` and `message`")

    config = await get_llm_config(db)
    if not config.is_configured():
        raise HTTPException(status_code=400, detail="AI assistant is not configured. Enable it in Settings.")
    try:
        model = build_model(config)
    except UnsupportedProvider:
        raise HTTPException(status_code=400, detail=f"Provider '{config._provider_str()}' is not supported by chat.")

    run_input: dict[str, Any] = {
        "id": thread_id, "trigger": body.get("trigger") or "submit-message", "messages": [message],
    }
    if body.get("messageId"):
        run_input["messageId"] = body["messageId"]
    try:
        adapter = ChatAdapter(
            agent=agent,
            run_input=VercelAIAdapter.build_run_input(json.dumps(run_input).encode()),
            accept=request.headers.get("accept"),
            sdk_version=SDK_VERSION,
            manage_message_history="server",
        )
        approvals = adapter.deferred_tool_results
    except ValidationError:
        raise HTTPException(status_code=422, detail="Invalid message")

    user_text = _text_of(message) if message.get("role") == "user" else ""
    thread = await _get_or_create_thread(db, thread_id, user, user_text)  # 404 before any dispatch
    if thread_id in _active:
        raise HTTPException(status_code=409, detail="This chat already has a run in progress")
    _active.add(thread_id)  # released when the stream ends (or below on a rejected request)
    try:
        history = await _load(db, thread_id)

        pending = {c.tool_call_id: c for c in pending_tool_calls(history)}
        if approvals:
            # Only a call the server stored and has not yet answered can be approved
            if not set(approvals.approvals) <= set(pending):
                raise HTTPException(status_code=400, detail="Approval does not match a pending request")
        elif pending:
            # The user moved on instead of answering: close the open calls as denied
            history = [*history, ModelRequest(parts=[
                ToolReturnPart(tool_name=c.tool_name, tool_call_id=c.tool_call_id, content=DENIED_TEXT, outcome="denied")
                for c in pending.values()
            ])]

        deps = ChatDeps(db=db, user_id=user.user_id, thread_id=thread_id)
        first_exchange = not history
        instructions = await _instructions(db, config, user, user_text, body.get("context"))
        shown_model = config.model or DEFAULT_MODELS[LLMProvider(config._provider_str())]

        completed = False

        async def on_complete(result) -> AsyncIterator[BaseChunk]:
            nonlocal completed
            messages = result.all_messages()
            await _save(db, thread, messages)
            if user.user_id:
                _spawn(_extract_memories_background(_conversation(messages), user.user_id, config))
            if first_exchange:
                _spawn(summarize_title(thread_id))
            completed = True
            yield MessageMetadataChunk(message_metadata={"model": result.response.model_name or shown_model})

        async def guarded() -> AsyncIterator[BaseChunk]:
            stream = adapter.run_stream(
                message_history=history,
                deps=deps,
                model=model,
                model_settings=model_settings(config),
                usage_limits=UsageLimits(request_limit=MAX_MODEL_REQUESTS),
                instructions=instructions,
                on_complete=on_complete,
            )
            try:
                async for chunk in stream:
                    yield chunk
            finally:
                # Shielded: on client disconnect Starlette cancels this scope, which would
                # also cancel the recovery awaits. Bounded so a hung DB cannot hold the thread.
                with anyio.CancelScope(shield=True):
                    try:
                        if not completed and deps.executed:
                            # Run failed or was cancelled after a tool committed: store its
                            # result so the call is no longer pending and the UI shows the outcome.
                            with anyio.move_on_after(10):
                                await _save_executed(db, thread, history, deps.executed)
                    except Exception:
                        logger.exception("Could not persist executed tool results")
                    finally:
                        _active.discard(thread_id)  # only after persistence finished

        return adapter.streaming_response(guarded())
    except BaseException:
        _active.discard(thread_id)
        raise


@router.get("/status")
async def get_status(db: AsyncSession = Depends(get_db)) -> dict:
    config = await get_llm_config(db)
    provider = config._provider_str()
    # No client is built here: that needs credentials and would raise without them
    supported = provider in ("openrouter", "local", "hailo", *OPENAI_COMPATIBLE_URLS)
    return {
        "enabled": config.is_configured() and supported,
        "provider": provider,
        "model": config.model or DEFAULT_MODELS[LLMProvider(provider)],
    }


def _list_item(thread: AgUiThread, count: int) -> dict:
    return {
        "id": thread.id,
        "title": thread.title,
        "updated_at": serialize_datetime_to_utc(thread.updated_at),
        "message_count": count,
    }


@router.get("/threads")
async def list_threads(user: AuthUser = Depends(require_auth), db: AsyncSession = Depends(get_db)) -> list[dict]:
    rows = (await db.execute(
        select(AgUiThread, ChatHistory.message_count)
        .outerjoin(ChatHistory, ChatHistory.thread_id == AgUiThread.id)
        .where(AgUiThread.user_id == user.user_id)
        .order_by(AgUiThread.updated_at.desc())
    )).all()
    return [_list_item(t, c or 0) for t, c in rows]


@router.get("/threads/{thread_id}")
async def get_thread(thread_id: str, user: AuthUser = Depends(require_auth), db: AsyncSession = Depends(get_db)) -> dict:
    thread = await _thread_or_404(db, thread_id, user)
    return {
        "id": thread.id,
        "title": thread.title,
        "messages": to_ui_messages(await _load(db, thread_id)),
    }


class TitleBody(BaseModel):
    title: str = Field(min_length=1, max_length=200)


@router.patch("/threads/{thread_id}")
async def rename_thread(
    thread_id: str, body: TitleBody, user: AuthUser = Depends(require_auth), db: AsyncSession = Depends(get_db)
) -> dict:
    thread = await _thread_or_404(db, thread_id, user)
    thread.title = body.title.strip() or thread.title
    thread.title_locked = True  # a manual title is never overwritten by summarisation
    await db.commit()
    row = await db.get(ChatHistory, thread_id)
    return _list_item(thread, row.message_count if row else 0)


@router.delete("/threads/{thread_id}", status_code=204)
async def delete_thread(
    thread_id: str, user: AuthUser = Depends(require_auth), db: AsyncSession = Depends(get_db)
) -> Response:
    thread = await _thread_or_404(db, thread_id, user)
    await db.execute(delete(ChatHistory).where(ChatHistory.thread_id == thread_id))
    await db.delete(thread)
    await db.commit()
    return Response(status_code=204)
