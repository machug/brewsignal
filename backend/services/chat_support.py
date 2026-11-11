"""Helpers the /api/chat router needs: system prompt, lite-LLM check, background memory extraction."""

import json
import logging
from pathlib import Path
from typing import Optional

import prompty
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.memory import add_memory

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent / "llm" / "prompts"


async def _extract_memories_background(messages: list[dict], user_id: str, llm_config):
    """Background task to extract and store memories from conversation.

    Runs after each successful agent run to extract facts, preferences,
    and learnings from the conversation into long-term memory.
    """
    try:
        # Filter to just user/assistant messages for memory extraction
        conversation = [
            msg for msg in messages
            if msg.get("role") in ("user", "assistant") and msg.get("content")
        ]

        if len(conversation) < 2:
            return  # Need at least a user message and response

        result = await add_memory(conversation, user_id=user_id, llm_config=llm_config)
        extracted = result.get("results", [])
        if extracted:
            logger.info(f"Extracted {len(extracted)} memories for user {user_id[:8]}...")
    except Exception as e:
        logger.warning(f"Background memory extraction failed: {e}")


async def _get_lite_llm_config(db: AsyncSession) -> tuple[bool, Optional[str]]:
    """Check if lite LLM is enabled and get hailo URL if available.

    Returns (is_enabled, hailo_url) tuple.
    """
    from backend.models import Config
    from backend.routers.system import check_hailo_ollama_status

    try:
        result = await db.execute(
            select(Config).where(Config.key == "ai_lite_enabled")
        )
        config_row = result.scalar_one_or_none()
        if not config_row:
            return False, None

        try:
            enabled = json.loads(config_row.value)
        except (json.JSONDecodeError, TypeError):
            enabled = config_row.value == "true"

        if not enabled:
            return False, None

        # Check if hailo-ollama is running
        for url in ["http://localhost:8000", "http://127.0.0.1:8000"]:
            status = check_hailo_ollama_status(url)
            if status and status.running:
                return True, url

        return False, None
    except Exception as e:
        logger.warning(f"Failed to check lite LLM config: {e}")
        return False, None


async def _get_recipe_system_prompt(db: AsyncSession, state: Optional[dict] = None) -> str:
    """Get the system prompt for recipe assistant using Prompty.

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

    # Load and prepare the assistant prompt using Prompty
    prompt_path = PROMPTS_DIR / "assistant.prompty"
    p = prompty.load(str(prompt_path))
    rendered = prompty.prepare(p, inputs={
        "batch_size": batch_size,
        "efficiency": efficiency,
        "equipment_note": equipment_note,
    })

    # Extract system message content from rendered messages
    # prompty.prepare returns a list of message dicts
    for msg in rendered:
        if msg.get("role") == "system":
            return msg.get("content", "")

    # Fallback if no system message found
    logger.warning("No system message found in prompty output")
    return str(rendered)
