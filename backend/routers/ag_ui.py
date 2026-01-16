"""AG-UI Protocol endpoints for streaming AI assistant.

This module implements the Agent-User Interaction Protocol (AG-UI)
for real-time streaming communication with the AI assistant.

Includes thread persistence for chat history and title summarization.
"""

import asyncio
import json
import logging
import os
import uuid
from typing import AsyncGenerator, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.database import get_db
from backend.routers.assistant import get_llm_config
from backend.services.llm import LLMService
from backend.services.llm.tools import TOOL_DEFINITIONS, execute_tool
from backend.models import (
    AgUiThread, AgUiMessage,
    AgUiThreadResponse, AgUiThreadListItem, AgUiMessageResponse
)

# Fast models per provider for title summarization (cheap, fast)
FAST_MODELS_BY_PROVIDER = {
    "anthropic": "claude-3-5-haiku-20241022",
    "openrouter": "openrouter/anthropic/claude-3-5-haiku-20241022",
    "openai": "gpt-4o-mini",
    "google": "gemini/gemini-1.5-flash",
    "groq": "groq/llama-3.1-8b-instant",
    "deepseek": "deepseek/deepseek-chat",
    "local": "ollama/phi3:mini",
}

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/ag-ui", tags=["ag-ui"])


# AG-UI Event Types
class AGUIEvent:
    """Base class for AG-UI events."""

    def __init__(self, event_type: str, **data):
        self.type = event_type
        self.timestamp = datetime.utcnow().isoformat() + "Z"
        self.data = data

    def to_sse(self) -> str:
        """Convert to Server-Sent Event format."""
        payload = {"type": self.type, "timestamp": self.timestamp, **self.data}
        return f"data: {json.dumps(payload)}\n\n"


# Request/Response models
class Message(BaseModel):
    """A chat message."""
    id: str
    role: str  # "user", "assistant", "system", "tool"
    content: str
    createdAt: Optional[str] = None
    toolCallId: Optional[str] = None  # For tool result messages


class ToolDefinition(BaseModel):
    """Tool definition for agent capabilities."""
    name: str
    description: str
    parameters: dict


class RunRequest(BaseModel):
    """Request body for agent run."""
    threadId: Optional[str] = None
    messages: list[Message]
    tools: Optional[list[ToolDefinition]] = None
    state: Optional[dict] = None
    metadata: Optional[dict] = None


async def get_llm_service(db: AsyncSession = Depends(get_db)) -> LLMService:
    """Dependency to get configured LLM service."""
    config = await get_llm_config(db)
    return LLMService(config)


async def generate_ag_ui_events(
    service: LLMService,
    request: RunRequest,
    db: AsyncSession,
) -> AsyncGenerator[str, None]:
    """Generate AG-UI events from LLM streaming response."""

    is_new_thread = request.threadId is None
    thread_id = request.threadId or str(uuid.uuid4())
    run_id = str(uuid.uuid4())

    # Create or get thread
    thread = await _get_or_create_thread(db, thread_id, request.messages)

    # Emit RUN_STARTED
    yield AGUIEvent(
        "RUN_STARTED",
        threadId=thread_id,
        runId=run_id,
    ).to_sse()

    # Check if service is configured
    if not service.config.is_configured():
        yield AGUIEvent(
            "RUN_ERROR",
            message="AI assistant is not configured. Enable it in Settings.",
            code="NOT_CONFIGURED",
        ).to_sse()
        return

    try:
        # If resuming thread, load previous messages from database
        llm_messages = []
        if not is_new_thread:
            # Load history from database
            db_messages = await _get_thread_messages(db, thread_id)
            for msg in db_messages:
                if msg.role in ("user", "assistant"):
                    llm_messages.append({"role": msg.role, "content": msg.content})

        # Add new messages from request (not already in DB)
        for m in request.messages:
            if m.role == "user":
                llm_messages.append({"role": m.role, "content": m.content})
                # Save user message to database
                await _save_message(db, thread_id, m.role, m.content)
            elif m.role == "tool" and m.toolCallId:
                llm_messages.append({
                    "role": "tool",
                    "tool_call_id": m.toolCallId,
                    "content": m.content
                })

        # Add system prompt for recipe assistant
        system_prompt = await _get_recipe_system_prompt(db, request.state)
        llm_messages.insert(0, {"role": "system", "content": system_prompt})

        # Run agent loop (handles tool calls) - collect final response
        final_response = ""
        async for event in _run_agent_loop(
            service, db, llm_messages, thread_id, run_id
        ):
            yield event
            # Capture final response content
            parsed = _parse_sse_event(event)
            if parsed and parsed.get("type") == "TEXT_MESSAGE_END":
                # Save accumulated content at end of message
                pass  # Content is accumulated in the loop

        # Save assistant response to database
        # We need to get the final content from the last iteration
        # This is handled inside _run_agent_loop now

        # Emit RUN_FINISHED
        yield AGUIEvent(
            "RUN_FINISHED",
            threadId=thread_id,
            runId=run_id,
        ).to_sse()

        # Trigger title summarization in background (don't block response)
        # Use a new session since the generator's session may close
        from backend.database import async_session_factory
        asyncio.create_task(_summarize_thread_background(thread_id))

    except Exception as e:
        logger.error(f"AG-UI streaming error: {e}")
        yield AGUIEvent(
            "RUN_ERROR",
            message=str(e),
            code="INTERNAL_ERROR",
        ).to_sse()


async def _summarize_thread_background(thread_id: str):
    """Background task to summarize thread title."""
    from backend.database import async_session_factory
    try:
        async with async_session_factory() as db:
            await _summarize_thread_title(db, thread_id)
    except Exception as e:
        logger.warning(f"Background title summarization failed: {e}")


def _parse_sse_event(sse: str) -> Optional[dict]:
    """Parse SSE event string back to dict."""
    if not sse.startswith("data: "):
        return None
    try:
        return json.loads(sse[6:].strip())
    except json.JSONDecodeError:
        return None


async def _get_or_create_thread(
    db: AsyncSession,
    thread_id: str,
    messages: list[Message]
) -> AgUiThread:
    """Get existing thread or create new one."""
    result = await db.execute(
        select(AgUiThread).where(AgUiThread.id == thread_id)
    )
    thread = result.scalar_one_or_none()

    if not thread:
        # Generate title from first user message
        title = None
        for m in messages:
            if m.role == "user" and m.content:
                title = m.content[:100]
                if len(m.content) > 100:
                    title += "..."
                break

        thread = AgUiThread(id=thread_id, title=title)
        db.add(thread)
        await db.commit()
        logger.info(f"Created new AG-UI thread: {thread_id}")
    else:
        # Update timestamp
        thread.updated_at = datetime.utcnow()
        await db.commit()

    return thread


async def _get_thread_messages(db: AsyncSession, thread_id: str) -> list[AgUiMessage]:
    """Get all messages for a thread."""
    result = await db.execute(
        select(AgUiMessage)
        .where(AgUiMessage.thread_id == thread_id)
        .order_by(AgUiMessage.created_at)
    )
    return list(result.scalars().all())


async def _save_message(
    db: AsyncSession,
    thread_id: str,
    role: str,
    content: str,
    tool_calls: Optional[list[dict]] = None
) -> AgUiMessage:
    """Save a message to the database."""
    message = AgUiMessage(
        thread_id=thread_id,
        role=role,
        content=content,
    )
    if tool_calls:
        message.tool_calls_data = tool_calls
    db.add(message)
    await db.commit()
    return message


async def _summarize_thread_title(
    db: AsyncSession,
    thread_id: str,
) -> Optional[str]:
    """Generate a concise title for a thread using a fast LLM.

    Called asynchronously after a run completes to update the thread title
    with a semantic summary instead of just the first message.
    """
    try:
        import litellm

        # Get LLM config to access API key and provider
        config = await get_llm_config(db)
        if not config.is_configured():
            logger.debug("LLM not configured, skipping title summarization")
            return None

        # Get thread messages
        messages = await _get_thread_messages(db, thread_id)
        if not messages:
            return None

        # Build context from messages (just first few)
        context_messages = []
        for msg in messages[:4]:  # First 4 messages max
            context_messages.append(f"{msg.role}: {msg.content[:200]}")
        context = "\n".join(context_messages)

        # Determine provider and fast model
        provider_str = config._provider_str()
        fast_model = FAST_MODELS_BY_PROVIDER.get(provider_str, "gpt-4o-mini")

        # Build kwargs for litellm
        kwargs = {
            "model": fast_model,
            "messages": [
                {
                    "role": "system",
                    "content": "Generate a 3-6 word title summarizing this conversation. "
                               "Be specific about the topic (e.g., beer style, brewing question). "
                               "Output ONLY the title, no quotes or punctuation."
                },
                {"role": "user", "content": context}
            ],
            "temperature": 0.3,
            "max_tokens": 30,
        }

        # Pass API key if configured (same approach as main LLM service)
        if config.api_key:
            kwargs["api_key"] = config.api_key.get_secret_value()

        # Add base URL for Ollama
        if provider_str == "local":
            kwargs["api_base"] = config.base_url or "http://localhost:11434"

        logger.info(f"Summarizing thread {thread_id} title with {fast_model}")
        response = await litellm.acompletion(**kwargs)

        title = response.choices[0].message.content.strip()
        # Clean up: remove quotes, limit length
        title = title.strip('"\'').strip()
        if len(title) > 60:
            title = title[:57] + "..."

        # Update thread title
        result = await db.execute(
            select(AgUiThread).where(AgUiThread.id == thread_id)
        )
        thread = result.scalar_one_or_none()
        if thread:
            thread.title = title
            await db.commit()
            logger.info(f"Updated thread {thread_id} title to: {title}")

        return title

    except Exception as e:
        logger.warning(f"Failed to summarize thread title: {e}")
        return None


async def _run_agent_loop(
    service: LLMService,
    db: AsyncSession,
    messages: list[dict],
    thread_id: str,
    run_id: str,
    max_iterations: int = 5
) -> AsyncGenerator[str, None]:
    """Run the agent loop, handling tool calls.

    This implements the agentic loop:
    1. Send messages to LLM with tools
    2. If LLM wants to call tools, execute them
    3. Add tool results to messages
    4. Continue until LLM produces final response
    """
    litellm = service._get_litellm()
    iteration = 0

    while iteration < max_iterations:
        iteration += 1
        message_id = str(uuid.uuid4())

        # Build kwargs for LLM call
        kwargs = {
            "model": service.config.effective_model,
            "messages": messages,
            "temperature": service.config.temperature,
            "max_tokens": service.config.max_tokens,
            "tools": TOOL_DEFINITIONS,
            "stream": True,
        }

        # Only pass explicit API key if configured
        api_key = service._get_api_key()
        if api_key:
            kwargs["api_key"] = api_key

        # Add base URL for Ollama
        if service.config._provider_str() == "local":
            kwargs["api_base"] = service.config.base_url or "http://localhost:11434"

        logger.info(f"AG-UI iteration {iteration}: sending to LLM with {len(TOOL_DEFINITIONS)} tools")

        # Call LLM with streaming
        response = await litellm.acompletion(**kwargs)

        # Collect the full response
        full_content = ""
        tool_calls = []
        current_tool_call = None

        async for chunk in response:
            delta = chunk.choices[0].delta if chunk.choices else None
            if not delta:
                continue

            # Handle text content
            if delta.content:
                if not full_content:
                    # First content chunk - emit TEXT_MESSAGE_START
                    yield AGUIEvent(
                        "TEXT_MESSAGE_START",
                        messageId=message_id,
                        role="assistant",
                    ).to_sse()

                full_content += delta.content
                yield AGUIEvent(
                    "TEXT_MESSAGE_CONTENT",
                    messageId=message_id,
                    delta=delta.content,
                ).to_sse()

            # Handle tool calls
            if delta.tool_calls:
                for tc in delta.tool_calls:
                    if tc.index is not None:
                        # Ensure we have enough slots
                        while len(tool_calls) <= tc.index:
                            tool_calls.append({
                                "id": None,
                                "name": "",
                                "arguments": ""
                            })
                        current_tool_call = tool_calls[tc.index]

                    if tc.id:
                        current_tool_call["id"] = tc.id
                    if tc.function:
                        if tc.function.name:
                            current_tool_call["name"] = tc.function.name
                        if tc.function.arguments:
                            current_tool_call["arguments"] += tc.function.arguments

        # End text message if we had content
        if full_content:
            yield AGUIEvent(
                "TEXT_MESSAGE_END",
                messageId=message_id,
            ).to_sse()

            # Check for recipe JSON in response
            recipe = _extract_recipe_json(full_content)
            if recipe:
                yield AGUIEvent(
                    "STATE_DELTA",
                    delta=[
                        {"op": "add", "path": "/recipe", "value": recipe},
                        {"op": "add", "path": "/hasRecipe", "value": True},
                    ],
                ).to_sse()

        # If no tool calls, we're done - save final assistant response
        if not tool_calls or not any(tc.get("id") for tc in tool_calls):
            logger.info("AG-UI: No tool calls, finishing")
            if full_content:
                await _save_message(db, thread_id, "assistant", full_content)
            break

        # Process tool calls
        logger.info(f"AG-UI: Processing {len(tool_calls)} tool calls")

        # Add assistant message with tool calls to history
        assistant_msg = {
            "role": "assistant",
            "content": full_content or None,
            "tool_calls": [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": tc["arguments"]
                    }
                }
                for tc in tool_calls
                if tc.get("id")
            ]
        }
        messages.append(assistant_msg)

        # Execute each tool call
        for tc in tool_calls:
            if not tc.get("id"):
                continue

            tool_call_id = tc["id"]
            tool_name = tc["name"]
            tool_args_str = tc["arguments"]

            # Emit TOOL_CALL_START
            yield AGUIEvent(
                "TOOL_CALL_START",
                toolCallId=tool_call_id,
                toolName=tool_name,
            ).to_sse()

            # Emit TOOL_CALL_ARGS
            yield AGUIEvent(
                "TOOL_CALL_ARGS",
                toolCallId=tool_call_id,
                delta=tool_args_str,
            ).to_sse()

            # Parse arguments and execute
            try:
                tool_args = json.loads(tool_args_str) if tool_args_str else {}
                result = await execute_tool(db, tool_name, tool_args)
                result_str = json.dumps(result)
            except json.JSONDecodeError as e:
                result_str = json.dumps({"error": f"Invalid arguments: {e}"})
            except Exception as e:
                logger.error(f"Tool execution error: {e}")
                result_str = json.dumps({"error": str(e)})

            # Emit TOOL_CALL_END
            yield AGUIEvent(
                "TOOL_CALL_END",
                toolCallId=tool_call_id,
            ).to_sse()

            # Emit TOOL_RESULT
            yield AGUIEvent(
                "TOOL_RESULT",
                toolCallId=tool_call_id,
                result=result_str,
            ).to_sse()

            # Add tool result to messages for next iteration
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": result_str
            })

    if iteration >= max_iterations:
        logger.warning(f"AG-UI: Hit max iterations ({max_iterations})")


async def _get_recipe_system_prompt(db: AsyncSession, state: Optional[dict] = None) -> str:
    """Get the system prompt for recipe assistant.

    Fetches brewing defaults from equipment inventory (fermenter capacity for batch size).
    Falls back to state values or defaults if no equipment configured.
    """
    from backend.models import Equipment

    # Try to get brewing defaults from equipment
    batch_size = 19  # Default
    efficiency = 72  # Default
    equipment_note = ""

    # Query for fermenters/all-in-one systems with capacity
    stmt = select(Equipment).where(
        Equipment.is_active == True,
        Equipment.type.in_(["fermenter", "all_in_one"]),
        Equipment.capacity_liters.is_not(None)
    ).order_by(
        # Prefer all_in_one, then by capacity
        Equipment.type.desc(),
        Equipment.capacity_liters.desc()
    )
    result = await db.execute(stmt)
    primary_equipment = result.scalars().first()

    if primary_equipment:
        # Use 85% of fermenter capacity as default batch size (leave headspace for krausen)
        batch_size = round(primary_equipment.capacity_liters * 0.85, 1)
        equipment_note = f" (based on {primary_equipment.name}: {primary_equipment.capacity_liters}L capacity)"
    elif state:
        # Fall back to state values if provided
        batch_size = state.get("batchSize", batch_size)
        efficiency = state.get("efficiency", efficiency)

    return f"""You are BrewSignal's AI Brewing Assistant, an expert homebrewer who helps create beer recipes.

## Your Tools
You have access to tools to search the BrewSignal database:
- **search_yeast**: Search 449+ yeast strains by name, producer, type, attenuation, or temperature range
- **search_styles**: Search 116 BJCP 2021 beer styles by name, category, or characteristics
- **get_yeast_by_id**: Get detailed info about a specific yeast by product ID
- **get_style_by_name**: Get complete BJCP guidelines for a specific style (use exact BJCP name like "American IPA")

**IMPORTANT**: Use these tools when discussing yeast or styles! Don't rely on memory - search the database for accurate, up-to-date information.

## Your Expertise
- Deep knowledge of BJCP beer styles and their characteristics
- Understanding of brewing ingredients: malts, hops, yeast, adjuncts
- Ability to calculate OG, FG, ABV, IBU, and SRM from ingredients
- Knowledge of fermentation temperatures and schedules
- Understanding of water chemistry basics

## Response Format
When asked to create or discuss a recipe, provide:
1. A brief description of the beer style and what makes it special
2. Target specifications (OG, FG, ABV, IBU, SRM)
3. Suggested ingredients with amounts for a standard batch
4. Brewing notes (mash temp, boil time, fermentation temp)

## When Generating a Final Recipe
When the user is ready to create the recipe, output a JSON block with this exact format:
```json
{{
  "name": "Recipe Name",
  "style": "BJCP Style Name",
  "type": "all-grain",
  "og": 1.050,
  "fg": 1.010,
  "abv": 5.2,
  "ibu": 35,
  "color_srm": 8,
  "batch_size_liters": {batch_size},
  "boil_time_minutes": 60,
  "efficiency_percent": {efficiency},
  "yeast_name": "Yeast Strain Name",
  "yeast_lab": "Manufacturer",
  "yeast_attenuation": 75,
  "yeast_temp_min": 18,
  "yeast_temp_max": 22,
  "notes": "Detailed brewing instructions"
}}
```

## Conversation Style
- Be friendly and enthusiastic about brewing
- Ask clarifying questions if the request is vague
- Offer alternatives when appropriate
- Explain the "why" behind suggestions
- Keep responses concise but informative

## Important Rules
- Always use metric units (liters, kg, grams, Celsius)
- User's batch size: {batch_size} liters
- User's brewhouse efficiency: {efficiency}%
- Calculate ABV from OG and FG: ABV = (OG - FG) × 131.25
- Only output JSON when the user confirms they want to save/create the recipe
- ALWAYS use tools to look up yeast and style information - your database has 449+ yeast strains!
"""


def _extract_recipe_json(text: str) -> Optional[dict]:
    """Extract recipe JSON from assistant response."""
    import re

    # Try to find JSON in code block
    json_match = re.search(r'```(?:json)?\s*\n({[\s\S]*?})\s*\n```', text)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass

    # Try to find raw JSON object
    json_match = re.search(r'({[\s\S]*?"name"[\s\S]*?"notes"[\s\S]*?})', text)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass

    return None


@router.post("/run")
async def run_agent(
    request: RunRequest,
    service: LLMService = Depends(get_llm_service),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """
    Run the AI agent with AG-UI protocol streaming.

    This endpoint streams AG-UI events as Server-Sent Events (SSE).
    The client should parse events in the format:

    data: {"type": "EVENT_TYPE", ...}

    Events emitted:
    - RUN_STARTED: Agent run has started
    - TEXT_MESSAGE_START: Beginning of assistant message
    - TEXT_MESSAGE_CONTENT: Streaming text chunk (delta)
    - TEXT_MESSAGE_END: End of assistant message
    - TOOL_CALL_START: Tool call initiated
    - TOOL_CALL_ARGS: Tool call arguments (streamed)
    - TOOL_CALL_END: Tool call completed
    - TOOL_RESULT: Tool execution result
    - STATE_DELTA: State updates (e.g., recipe extracted)
    - RUN_FINISHED: Agent run completed
    - RUN_ERROR: Error occurred
    """
    return StreamingResponse(
        generate_ag_ui_events(service, request, db),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


@router.get("/status")
async def get_status(service: LLMService = Depends(get_llm_service)) -> dict:
    """Get AG-UI service status."""
    status = service.get_status()
    return {
        "protocol": "ag-ui",
        "version": "1.0",
        "enabled": status.get("configured", False),
        "provider": status.get("provider"),
        "model": status.get("model"),
        "tools": [t["function"]["name"] for t in TOOL_DEFINITIONS],
    }


@router.get("/tools")
async def get_tools() -> dict:
    """Get available tools for the AI assistant."""
    return {
        "tools": [
            {
                "name": t["function"]["name"],
                "description": t["function"]["description"],
                "parameters": t["function"]["parameters"]
            }
            for t in TOOL_DEFINITIONS
        ]
    }


# =============================================================================
# Thread Management Endpoints
# =============================================================================

@router.get("/threads", response_model=list[AgUiThreadListItem])
async def list_threads(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    search: Optional[str] = Query(None, description="Search thread titles"),
    db: AsyncSession = Depends(get_db),
) -> list[AgUiThreadListItem]:
    """List all conversation threads."""
    query = select(AgUiThread)

    # Apply search filter if provided
    if search:
        query = query.where(AgUiThread.title.ilike(f"%{search}%"))

    # Order by most recent first
    query = query.order_by(AgUiThread.updated_at.desc())
    query = query.offset(offset).limit(limit)

    result = await db.execute(query)
    threads = result.scalars().all()

    # Get message counts
    response = []
    for thread in threads:
        count_result = await db.execute(
            select(func.count(AgUiMessage.id))
            .where(AgUiMessage.thread_id == thread.id)
        )
        message_count = count_result.scalar() or 0

        response.append(AgUiThreadListItem(
            id=thread.id,
            title=thread.title,
            created_at=thread.created_at,
            updated_at=thread.updated_at,
            message_count=message_count,
        ))

    return response


@router.get("/threads/{thread_id}", response_model=AgUiThreadResponse)
async def get_thread(
    thread_id: str,
    db: AsyncSession = Depends(get_db),
) -> AgUiThreadResponse:
    """Get a specific thread with all messages."""
    result = await db.execute(
        select(AgUiThread)
        .options(selectinload(AgUiThread.messages))
        .where(AgUiThread.id == thread_id)
    )
    thread = result.scalar_one_or_none()

    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    # Sort messages by created_at to ensure correct order
    sorted_messages = sorted(thread.messages, key=lambda m: m.created_at)

    return AgUiThreadResponse(
        id=thread.id,
        title=thread.title,
        created_at=thread.created_at,
        updated_at=thread.updated_at,
        messages=[
            AgUiMessageResponse(
                id=m.id,
                thread_id=m.thread_id,
                role=m.role,
                content=m.content,
                tool_calls=m.tool_calls_data,
                created_at=m.created_at,
            )
            for m in sorted_messages
        ],
        message_count=len(thread.messages),
    )


@router.delete("/threads/{thread_id}")
async def delete_thread(
    thread_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Delete a conversation thread and all its messages."""
    result = await db.execute(
        select(AgUiThread).where(AgUiThread.id == thread_id)
    )
    thread = result.scalar_one_or_none()

    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    await db.delete(thread)
    await db.commit()

    logger.info(f"Deleted AG-UI thread: {thread_id}")
    return {"success": True, "deleted": thread_id}


@router.patch("/threads/{thread_id}")
async def update_thread(
    thread_id: str,
    title: str = Query(..., description="New thread title"),
    db: AsyncSession = Depends(get_db),
) -> AgUiThreadListItem:
    """Update a thread's title."""
    result = await db.execute(
        select(AgUiThread).where(AgUiThread.id == thread_id)
    )
    thread = result.scalar_one_or_none()

    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    thread.title = title
    await db.commit()

    # Get message count
    count_result = await db.execute(
        select(func.count(AgUiMessage.id))
        .where(AgUiMessage.thread_id == thread.id)
    )
    message_count = count_result.scalar() or 0

    return AgUiThreadListItem(
        id=thread.id,
        title=thread.title,
        created_at=thread.created_at,
        updated_at=thread.updated_at,
        message_count=message_count,
    )
