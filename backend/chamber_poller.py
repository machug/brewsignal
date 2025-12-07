"""Background task to poll Home Assistant for chamber readings."""

import asyncio
import logging
from datetime import datetime, timezone

from .database import async_session_factory
from .models import ChamberReading, serialize_datetime_to_utc
from .routers.config import get_config_value
from .services.ha_client import get_ha_client, init_ha_client
from .websocket import manager as ws_manager

logger = logging.getLogger(__name__)

_polling_task: asyncio.Task | None = None
_polling_lock: asyncio.Lock | None = None
POLL_INTERVAL_SECONDS = 30


def _validate_entity_id(entity_id: str) -> bool:
    """Validate Home Assistant entity ID format (domain.entity_name).

    Args:
        entity_id: Entity ID to validate

    Returns:
        True if valid format, False otherwise
    """
    if not entity_id or not isinstance(entity_id, str):
        return False
    parts = entity_id.split(".", 1)
    return len(parts) == 2 and all(part.strip() for part in parts)


async def poll_chamber() -> None:
    """Poll HA for chamber temperature and humidity, store and broadcast."""
    while True:
        try:
            async with async_session_factory() as db:
                ha_enabled = await get_config_value(db, "ha_enabled")

                if not ha_enabled:
                    await asyncio.sleep(POLL_INTERVAL_SECONDS)
                    continue

                # Ensure HA client is initialized
                ha_url = await get_config_value(db, "ha_url")
                ha_token = await get_config_value(db, "ha_token")

                if not ha_url or not ha_token:
                    await asyncio.sleep(POLL_INTERVAL_SECONDS)
                    continue

                ha_client = get_ha_client()
                if not ha_client:
                    init_ha_client(ha_url, ha_token)
                    ha_client = get_ha_client()

                if not ha_client:
                    await asyncio.sleep(POLL_INTERVAL_SECONDS)
                    continue

                # Get entity IDs
                temp_entity = await get_config_value(db, "ha_chamber_temp_entity_id")
                humidity_entity = await get_config_value(db, "ha_chamber_humidity_entity_id")

                # Validate entity IDs
                if temp_entity and not _validate_entity_id(temp_entity):
                    logger.warning(f"Invalid chamber temp entity ID format: {temp_entity}")
                    temp_entity = None

                if humidity_entity and not _validate_entity_id(humidity_entity):
                    logger.warning(f"Invalid chamber humidity entity ID format: {humidity_entity}")
                    humidity_entity = None

                if not temp_entity and not humidity_entity:
                    await asyncio.sleep(POLL_INTERVAL_SECONDS)
                    continue

                # Fetch values
                temperature = None
                humidity = None

                if temp_entity:
                    state = await ha_client.get_state(temp_entity)
                    if state and state.get("state") not in ("unavailable", "unknown"):
                        try:
                            temperature = float(state["state"])
                        except (ValueError, TypeError):
                            logger.warning(f"Invalid temp state: {state.get('state')}")

                if humidity_entity:
                    state = await ha_client.get_state(humidity_entity)
                    if state and state.get("state") not in ("unavailable", "unknown"):
                        try:
                            humidity = float(state["state"])
                        except (ValueError, TypeError):
                            logger.warning(f"Invalid humidity state: {state.get('state')}")

                # Store reading if we got any data
                if temperature is not None or humidity is not None:
                    reading = ChamberReading(
                        temperature=temperature,
                        humidity=humidity,
                        entity_id=temp_entity or humidity_entity
                    )
                    db.add(reading)
                    await db.commit()

                    # Broadcast via WebSocket
                    await ws_manager.broadcast_json({
                        "type": "chamber",
                        "temperature": temperature,
                        "humidity": humidity,
                        "timestamp": serialize_datetime_to_utc(datetime.now(timezone.utc))
                    })

                    logger.debug(f"Chamber: temp={temperature}, humidity={humidity}")

        except Exception as e:
            logger.error(f"Chamber polling error: {e}")

        await asyncio.sleep(POLL_INTERVAL_SECONDS)


async def start_chamber_poller() -> None:
    """Start the chamber polling background task."""
    global _polling_task, _polling_lock

    # Initialize lock on first call
    if _polling_lock is None:
        _polling_lock = asyncio.Lock()

    async with _polling_lock:
        if _polling_task is None or _polling_task.done():
            _polling_task = asyncio.create_task(poll_chamber())
            logger.info("Chamber poller started")


def stop_chamber_poller() -> None:
    """Stop the chamber polling background task."""
    global _polling_task
    if _polling_task and not _polling_task.done():
        _polling_task.cancel()
        logger.info("Chamber poller stopped")
