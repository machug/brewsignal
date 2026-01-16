"""AG-UI Protocol endpoints for streaming AI assistant.

This module implements the Agent-User Interaction Protocol (AG-UI)
for real-time streaming communication with the AI assistant.
"""

import json
import logging
import uuid
from typing import AsyncGenerator, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.routers.assistant import get_llm_config
from backend.services.llm import LLMService
from backend.services.llm.tools import TOOL_DEFINITIONS, execute_tool

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

    thread_id = request.threadId or str(uuid.uuid4())
    run_id = str(uuid.uuid4())

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
        # Build messages for LLM
        llm_messages = [
            {"role": m.role, "content": m.content}
            for m in request.messages
            if m.role != "tool"  # Handle tool messages separately
        ]

        # Add tool result messages
        for m in request.messages:
            if m.role == "tool" and m.toolCallId:
                llm_messages.append({
                    "role": "tool",
                    "tool_call_id": m.toolCallId,
                    "content": m.content
                })

        # Add system prompt for recipe assistant
        system_prompt = _get_recipe_system_prompt(request.state)
        llm_messages.insert(0, {"role": "system", "content": system_prompt})

        # Run agent loop (handles tool calls)
        async for event in _run_agent_loop(
            service, db, llm_messages, thread_id, run_id
        ):
            yield event

        # Emit RUN_FINISHED
        yield AGUIEvent(
            "RUN_FINISHED",
            threadId=thread_id,
            runId=run_id,
        ).to_sse()

    except Exception as e:
        logger.error(f"AG-UI streaming error: {e}")
        yield AGUIEvent(
            "RUN_ERROR",
            message=str(e),
            code="INTERNAL_ERROR",
        ).to_sse()


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

        # If no tool calls, we're done
        if not tool_calls or not any(tc.get("id") for tc in tool_calls):
            logger.info("AG-UI: No tool calls, finishing")
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


def _get_recipe_system_prompt(state: Optional[dict] = None) -> str:
    """Get the system prompt for recipe assistant."""
    batch_size = state.get("batchSize", 19) if state else 19
    efficiency = state.get("efficiency", 72) if state else 72

    return f"""You are BrewSignal's AI Brewing Assistant, an expert homebrewer who helps create beer recipes.

## Your Tools
You have access to tools to search the BrewSignal database:
- **search_yeast**: Search 449+ yeast strains by name, producer, type, attenuation, or temperature range
- **search_styles**: Search BJCP beer styles by name, category, or characteristics
- **get_yeast_by_id**: Get detailed info about a specific yeast by product ID
- **get_style_by_name**: Get complete BJCP guidelines for a specific style

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
