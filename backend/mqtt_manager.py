"""MQTT Connection Manager for Home Assistant integration.

Manages MQTT connection lifecycle, reconnection, and configuration updates.
Follows the pattern of temp_controller.py for background task management.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .database import async_session_factory
from .models import Batch
from .services.mqtt_client import get_mqtt_client, init_mqtt_client
from .routers.config import get_config_value, set_config_value

logger = logging.getLogger(__name__)

# Module-level state
_mqtt_task: Optional[asyncio.Task] = None
_mqtt_enabled: bool = False
_shutdown_event: asyncio.Event = asyncio.Event()


async def _load_mqtt_config(db: AsyncSession) -> dict:
    """Load MQTT configuration from database."""
    return {
        "enabled": await get_config_value(db, "mqtt_enabled") or False,
        "host": await get_config_value(db, "mqtt_host") or "",
        "port": await get_config_value(db, "mqtt_port") or 1883,
        "username": await get_config_value(db, "mqtt_username") or "",
        "password": await get_config_value(db, "mqtt_password") or "",
        "topic_prefix": await get_config_value(db, "mqtt_topic_prefix") or "brewsignal",
    }


async def _publish_active_batches_discovery(db: AsyncSession) -> None:
    """Publish discovery for the active fermenting batch (stable IDs).

    With stable entity IDs there is one HA device. If a fermenting batch
    exists, publish discovery with its name. Otherwise mark unavailable.
    """
    client = get_mqtt_client()
    if not client:
        return

    # Get the first fermenting batch (stable IDs support one active batch)
    result = await db.execute(
        select(Batch).where(
            Batch.status == "fermenting",
            Batch.deleted_at.is_(None),
        ).limit(1)
    )
    batch = result.scalar_one_or_none()

    if batch:
        await client.publish_discovery(
            batch_name=batch.name or f"Batch #{batch.batch_number}",
        )
        logger.info("Published MQTT discovery for active batch %d", batch.id)
    else:
        await client.publish_unavailable()
        logger.info("No active batch — MQTT entities marked unavailable")


async def _migrate_old_discovery(db: AsyncSession) -> None:
    """One-time migration: remove old per-batch MQTT discovery configs.

    Queries all batches and publishes empty configs to their old per-batch
    discovery topics. Tracked via 'mqtt_stable_ids_migrated' config key.
    """
    already_migrated = await get_config_value(db, "mqtt_stable_ids_migrated")
    if already_migrated:
        return

    client = get_mqtt_client()
    if not client:
        return

    logger.info("Running one-time MQTT stable IDs migration...")

    # Get all batch IDs to clean up their old discovery topics
    result = await db.execute(select(Batch.id))
    batch_ids = [row[0] for row in result.all()]

    for bid in batch_ids:
        await client.remove_old_discovery(bid)

    await set_config_value(db, "mqtt_stable_ids_migrated", True)
    await db.commit()
    logger.info("MQTT stable IDs migration complete — cleaned %d old batches", len(batch_ids))


async def mqtt_connection_loop() -> None:
    """Main MQTT connection management loop.

    Maintains connection to MQTT broker with reconnection on failure.
    Runs until shutdown_event is set.
    """
    global _mqtt_enabled

    logger.info("MQTT manager starting")
    client = init_mqtt_client()
    backoff = 1  # Initial backoff in seconds
    max_backoff = 60  # Maximum backoff

    while not _shutdown_event.is_set():
        try:
            # Create a new session for config check
            async with async_session_factory() as db:
                config = await _load_mqtt_config(db)

            _mqtt_enabled = config["enabled"]

            if not _mqtt_enabled:
                # MQTT disabled, wait and check again
                await asyncio.sleep(10)
                continue

            if not config["host"]:
                logger.debug("MQTT host not configured, waiting...")
                await asyncio.sleep(10)
                continue

            # Configure client
            client.configure(
                host=config["host"],
                port=config["port"],
                username=config["username"] if config["username"] else None,
                password=config["password"] if config["password"] else None,
                topic_prefix=config["topic_prefix"],
            )

            # Test connection
            connected = await client.connect()
            if connected:
                logger.info("MQTT connection established")
                backoff = 1  # Reset backoff on success

                # One-time migration: clean up old per-batch discovery topics
                async with async_session_factory() as db:
                    await _migrate_old_discovery(db)

                # Publish discovery for the active batch
                async with async_session_factory() as db:
                    await _publish_active_batches_discovery(db)

                # Stay connected, periodically check config
                while not _shutdown_event.is_set() and _mqtt_enabled:
                    await asyncio.sleep(30)
                    # Reload config to detect changes
                    async with async_session_factory() as db:
                        config = await _load_mqtt_config(db)
                    _mqtt_enabled = config["enabled"]

                    if not _mqtt_enabled:
                        logger.info("MQTT disabled via config")
                        await client.disconnect()
                        break
            else:
                logger.warning("MQTT connection failed, retrying in %ds", backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, max_backoff)

        except asyncio.CancelledError:
            logger.info("MQTT manager cancelled")
            break
        except Exception as e:
            logger.error("MQTT manager error: %s", e)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, max_backoff)

    await client.disconnect()
    logger.info("MQTT manager stopped")


def start_mqtt_manager() -> None:
    """Start the MQTT manager background task."""
    global _mqtt_task, _shutdown_event

    _shutdown_event.clear()

    if _mqtt_task is None or _mqtt_task.done():
        _mqtt_task = asyncio.create_task(mqtt_connection_loop())
        logger.info("MQTT manager task started")


def stop_mqtt_manager() -> None:
    """Stop the MQTT manager background task."""
    global _mqtt_task, _shutdown_event

    _shutdown_event.set()

    if _mqtt_task and not _mqtt_task.done():
        _mqtt_task.cancel()
        logger.info("MQTT manager task stopped")


def is_mqtt_enabled() -> bool:
    """Check if MQTT is currently enabled."""
    return _mqtt_enabled


async def publish_batch_reading(
    gravity: Optional[float] = None,
    temperature: Optional[float] = None,
    og: Optional[float] = None,
    start_time: Optional[datetime] = None,
    status: str = "fermenting",
    heater_active: Optional[bool] = None,
    cooler_active: Optional[bool] = None,
) -> None:
    """Publish a batch reading via MQTT to stable active topics.

    Fire-and-forget - doesn't block on failures.

    Args:
        gravity: Current gravity (SG)
        temperature: Current temperature (Celsius)
        og: Original gravity for ABV calculation
        start_time: Batch start time for days calculation
        status: Batch status string
        heater_active: Heater state
        cooler_active: Cooler state
    """
    if not _mqtt_enabled:
        return

    client = get_mqtt_client()
    if not client:
        return

    # Calculate ABV if we have OG and current gravity
    abv = None
    if og and gravity:
        abv = (og - gravity) * 131.25

    # Calculate days fermenting
    days_fermenting = None
    if start_time:
        now = datetime.now(timezone.utc)
        if start_time.tzinfo is None:
            start_time = start_time.replace(tzinfo=timezone.utc)
        delta = now - start_time
        days_fermenting = delta.total_seconds() / 86400

    # Fire-and-forget publish
    asyncio.create_task(
        client.publish_reading(
            gravity=gravity,
            temperature=temperature,
            abv=abv,
            status=status,
            days_fermenting=days_fermenting,
            heater_active=heater_active,
            cooler_active=cooler_active,
        )
    )


async def publish_batch_discovery(batch_name: str) -> None:
    """Publish MQTT auto-discovery with stable entity IDs.

    Fire-and-forget - doesn't block on failures.

    Args:
        batch_name: Human-readable batch name
    """
    if not _mqtt_enabled:
        return

    client = get_mqtt_client()
    if not client:
        return

    asyncio.create_task(
        client.publish_discovery(batch_name)
    )


async def mark_batch_unavailable() -> None:
    """Mark MQTT entities as unavailable (batch completed/deleted).

    Fire-and-forget - doesn't block on failures.
    """
    if not _mqtt_enabled:
        return

    client = get_mqtt_client()
    if not client:
        return

    asyncio.create_task(
        client.publish_unavailable()
    )
