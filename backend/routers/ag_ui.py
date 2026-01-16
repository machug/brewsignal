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
    role: str  # "user", "assistant", "system"
    content: str
    createdAt: Optional[str] = None


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
) -> AsyncGenerator[str, None]:
    """Generate AG-UI events from LLM streaming response."""

    thread_id = request.threadId or str(uuid.uuid4())
    run_id = str(uuid.uuid4())
    message_id = str(uuid.uuid4())

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
        ]

        # Add system prompt for recipe assistant
        system_prompt = _get_recipe_system_prompt(request.state)
        llm_messages.insert(0, {"role": "system", "content": system_prompt})

        # Emit TEXT_MESSAGE_START
        yield AGUIEvent(
            "TEXT_MESSAGE_START",
            messageId=message_id,
            role="assistant",
        ).to_sse()

        # Stream from LLM
        full_content = ""
        async for chunk in service.stream_chat(llm_messages):
            if chunk:
                full_content += chunk
                yield AGUIEvent(
                    "TEXT_MESSAGE_CONTENT",
                    messageId=message_id,
                    delta=chunk,
                ).to_sse()

        # Emit TEXT_MESSAGE_END
        yield AGUIEvent(
            "TEXT_MESSAGE_END",
            messageId=message_id,
        ).to_sse()

        # Check if response contains a recipe and emit state update
        recipe = _extract_recipe_json(full_content)
        if recipe:
            yield AGUIEvent(
                "STATE_DELTA",
                delta=[
                    {"op": "add", "path": "/recipe", "value": recipe},
                    {"op": "add", "path": "/hasRecipe", "value": True},
                ],
            ).to_sse()

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


def _get_recipe_system_prompt(state: Optional[dict] = None) -> str:
    """Get the system prompt for recipe assistant."""
    batch_size = state.get("batchSize", 19) if state else 19
    efficiency = state.get("efficiency", 72) if state else 72

    return f"""You are BrewSignal's AI Brewing Assistant, an expert homebrewer who helps create beer recipes.

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
    - STATE_DELTA: State updates (e.g., recipe extracted)
    - RUN_FINISHED: Agent run completed
    - RUN_ERROR: Error occurred
    """
    return StreamingResponse(
        generate_ag_ui_events(service, request),
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
    }
