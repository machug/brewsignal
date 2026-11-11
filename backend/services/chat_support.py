"""Helpers the /api/chat router needs: system prompt, lite-LLM check, background memory extraction."""

import hashlib
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


MIN_EXTRACT_CHARS = 20  # shorter user turns ("ok", "thanks") carry nothing worth remembering
_extracted: dict[str, None] = {}  # turns already extracted (insertion-ordered, bounded)


async def _extract_memories_background(messages: list[dict], user_id: str, llm_config):
    """Background task: extract long-term memories from the latest chat turn.

    Only the last user message and the reply that followed go to mem0 (not the whole
    thread, which would re-extract and re-bill old turns). Skips trivial turns and
    never runs twice for the same turn.
    """
    try:
        turns = [m for m in messages if m.get("role") in ("user", "assistant") and m.get("content")]
        user_idx = max((i for i, m in enumerate(turns) if m["role"] == "user"), default=None)
        if user_idx is None:
            return
        turn = turns[user_idx:user_idx + 2]
        if len(turn) < 2 or len(turn[0]["content"].strip()) < MIN_EXTRACT_CHARS:
            return
        key = hashlib.sha1(f"{user_id}\0{turn[0]['content']}\0{turn[1]['content']}".encode()).hexdigest()
        if key in _extracted:
            return
        _extracted[key] = None
        if len(_extracted) > 500:
            _extracted.pop(next(iter(_extracted)))

        result = await add_memory(turn, user_id=user_id, llm_config=llm_config)
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
