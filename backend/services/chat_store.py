"""Chat history helpers: legacy ag_ui import and UI message conversion (tilt_ui-qzk0.1)."""

import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional, Sequence

from pydantic import TypeAdapter
from pydantic_ai.messages import (
    ModelMessage,
    ModelMessagesTypeAdapter,
    ModelRequest,
    ModelResponse,
    TextPart,
    UserPromptPart,
)
from pydantic_ai.ui.vercel_ai import VercelAIAdapter
from pydantic_ai.ui.vercel_ai.request_types import UIMessage

logger = logging.getLogger(__name__)

SDK_VERSION = 7  # matches the frontend's `ai` major; 6+ enables tool approval

_ui_list = TypeAdapter(list[UIMessage])


def to_ui_messages(messages: Sequence[ModelMessage], fallback_model: Optional[str] = None) -> list[dict]:
    """ModelMessages -> JSON UIMessages, consecutive assistant messages merged,
    assistant `metadata.model` set from the response that produced it."""
    ui = VercelAIAdapter.dump_messages(messages, sdk_version=SDK_VERSION)
    models = [m.model_name for m in messages if isinstance(m, ModelResponse)]
    n_assistant = sum(1 for m in ui if m.role == "assistant")
    # ponytail: 1:1 only when every response rendered parts; else use the last model name
    aligned = len(models) == n_assistant
    out: list[UIMessage] = []
    i = 0
    for m in ui:
        if m.role == "assistant":
            name = (models[i] if aligned else (models[-1] if models else None)) or fallback_model
            i += 1
            if name:
                m.metadata = {**(m.metadata if isinstance(m.metadata, dict) else {}), "model": name}
            if out and out[-1].role == "assistant":
                out[-1].parts.extend(m.parts)
                out[-1].metadata = m.metadata
                continue
        out.append(m)
    return _ui_list.dump_python(out, mode="json", by_alias=True, exclude_none=True)


def dump_history(messages: Sequence[ModelMessage]) -> str:
    return ModelMessagesTypeAdapter.dump_json(list(messages)).decode()


def load_history(raw: Optional[str]) -> list[ModelMessage]:
    return ModelMessagesTypeAdapter.validate_json(raw) if raw else []


def _legacy_to_model_messages(rows: list[tuple[str, str]]) -> list[ModelMessage]:
    """(role, content) rows of an ag_ui thread -> text-only history. Tool calls
    and results are dropped; adjacent same-role turns are merged."""
    out: list[ModelMessage] = []
    now = datetime.now(timezone.utc)
    for role, content in rows:
        if not content:
            continue
        if role == "user":
            if out and isinstance(out[-1], ModelRequest):
                out[-1].parts = [*out[-1].parts, UserPromptPart(content=content, timestamp=now)]
            else:
                out.append(ModelRequest(parts=[UserPromptPart(content=content, timestamp=now)]))
        elif role == "assistant":
            if out and isinstance(out[-1], ModelResponse):
                out[-1].parts = [TextPart(content=f"{out[-1].parts[0].content}\n\n{content}")]
            else:
                out.append(ModelResponse(parts=[TextPart(content=content)], timestamp=now))
    return out


def migrate_legacy_threads(conn) -> None:
    """Import ag_ui threads that have no chat_histories row (sync, for run_sync).

    Best effort, idempotent: user/assistant text only so old chats still open.
    """
    from sqlalchemy import inspect, text

    tables = inspect(conn).get_table_names()
    if "ag_ui_threads" not in tables or "chat_histories" not in tables:
        return
    threads = conn.execute(text(
        "SELECT id, user_id FROM ag_ui_threads WHERE id NOT IN (SELECT thread_id FROM chat_histories)"
    )).fetchall()
    if not threads:
        return
    by_thread = defaultdict(list)
    for tid, role, content in conn.execute(text(
        "SELECT thread_id, role, content FROM ag_ui_messages ORDER BY created_at, id"
    )):
        by_thread[tid].append((role, content))
    now = datetime.now(timezone.utc).isoformat()
    n = 0
    for tid, uid in threads:
        try:
            msgs = _legacy_to_model_messages(by_thread.get(tid, []))
            conn.execute(
                text("INSERT INTO chat_histories (thread_id, user_id, messages, message_count, updated_at) "
                     "VALUES (:t, :u, :m, :c, :ts)"),
                {"t": tid, "u": uid, "m": dump_history(msgs), "c": len(to_ui_messages(msgs)), "ts": now},
            )
            n += 1
        except Exception as e:  # one bad thread must not block startup
            logger.warning("Skipped legacy chat thread %s: %s", tid, e)
    logger.info("Imported %d legacy chat threads", n)
