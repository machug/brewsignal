"""Background task for temperature control.

Supports multiple control backends via the device control abstraction layer:
- Home Assistant (existing)
- Direct Shelly HTTP (planned - tilt_ui-amh)
- Gateway relay (planned - tilt_ui-123)
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select

from .database import async_session_factory
from .models import Batch, ControlEvent, AmbientReading, serialize_datetime_to_utc
from .routers.config import get_config_value
from .services.device_control import (
    get_device_router,
    init_device_router,
    RouterConfig,
    DeviceControlRouter,
)
from .websocket import manager as ws_manager

logger = logging.getLogger(__name__)

_controller_task: asyncio.Task | None = None
CONTROL_INTERVAL_SECONDS = 60
MIN_CYCLE_MINUTES = 5  # Minimum time between heater state changes

# Track per-batch heater states to avoid redundant API calls
# Keys are batch_id, values are {"state": "on"/"off", "last_change": datetime}
_batch_heater_states: dict[int, dict] = {}

# Track per-batch cooler states (same structure as heater states)
_batch_cooler_states: dict[int, dict] = {}

# Track per-batch manual overrides
# Keys are batch_id, values are {"state": "on"/"off", "until": datetime or None}
_batch_overrides: dict[int, dict] = {}

# Track pitch-ready notifications sent (to avoid spamming)
# Keys are batch_id, values are True if notification already sent
_pitch_ready_sent: dict[int, bool] = {}

# Track chamber idle heater/cooler state
_idle_heater_state: dict = {}   # {"state": "on"/"off", "last_change": datetime}
_idle_cooler_state: dict = {}

# Track HA config to detect changes


def cleanup_batch_state(batch_id: int) -> None:
    """Clean up runtime state for a batch (called when batch leaves fermenting/conditioning status)."""
    if batch_id in _batch_heater_states:
        logger.debug(f"Cleaning up heater state for batch {batch_id}")
        del _batch_heater_states[batch_id]
    if batch_id in _batch_cooler_states:
        logger.debug(f"Cleaning up cooler state for batch {batch_id}")
        del _batch_cooler_states[batch_id]
    if batch_id in _batch_overrides:
        logger.debug(f"Cleaning up override for batch {batch_id}")
        del _batch_overrides[batch_id]
_last_ha_url: Optional[str] = None
_last_ha_token: Optional[str] = None

# Event to trigger immediate control check (for override)
_wake_event: asyncio.Event | None = None


async def _wait_or_wake(seconds: float) -> None:
    """Sleep for specified seconds, but wake early if _wake_event is set."""
    global _wake_event
    if _wake_event is None:
        await asyncio.sleep(seconds)
        return

    try:
        await asyncio.wait_for(_wake_event.wait(), timeout=seconds)
        _wake_event.clear()  # Reset for next wait
    except asyncio.TimeoutError:
        pass  # Normal timeout, continue


def _trigger_immediate_check() -> None:
    """Wake the control loop to run immediately."""
    global _wake_event
    if _wake_event is not None:
        _wake_event.set()


async def _send_pitch_ready_notification(batch: Batch, wort_temp: float, target_temp: float) -> None:
    """Send a WebSocket notification that wort has reached pitch temperature.

    This is called when a batch in "planning" status reaches its target temp
    during pre-pitch chilling.
    """
    batch_id = batch.id

    # Check if we already sent notification for this batch
    if _pitch_ready_sent.get(batch_id):
        return

    # Mark as sent to avoid spamming
    _pitch_ready_sent[batch_id] = True

    logger.info(
        f"Batch {batch_id} ({batch.name}): Pitch temperature reached! "
        f"Wort: {wort_temp:.1f}°C, Target: {target_temp:.1f}°C"
    )

    # Broadcast via WebSocket
    try:
        await ws_manager.broadcast({
            "type": "pitch_ready",
            "batch_id": batch_id,
            "batch_name": batch.name,
            "wort_temp": round(wort_temp, 1),
            "target_temp": round(target_temp, 1),
            "message": f"🍺 Ready to pitch! {batch.name} has reached {wort_temp:.1f}°C",
            "timestamp": serialize_datetime_to_utc(datetime.now(timezone.utc)),
        })
    except Exception as e:
        logger.warning(f"Failed to send pitch_ready notification: {e}")


def get_device_temp(device_id: str) -> Optional[float]:
    """Get the latest wort temperature for a specific device.

    Returns temperature in Celsius (calibrated if available).
    """
    from .state import latest_readings

    if not device_id or device_id not in latest_readings:
        return None

    reading = latest_readings[device_id]
    # Return calibrated temp, or raw temp if not available
    return reading.get("temp") or reading.get("temp_raw")


def get_latest_tilt_temp() -> Optional[float]:
    """Get the latest wort temperature from any active Tilt.

    Returns temperature in Celsius (calibrated if available).
    """
    # Import here to avoid circular imports
    from .state import latest_readings

    if not latest_readings:
        return None

    # Get the most recently seen Tilt
    latest = None
    latest_time = None

    for reading in latest_readings.values():
        last_seen_str = reading.get("last_seen")
        if last_seen_str:
            try:
                last_seen = datetime.fromisoformat(last_seen_str.replace("Z", "+00:00"))
                if latest_time is None or last_seen > latest_time:
                    latest_time = last_seen
                    latest = reading
            except (ValueError, TypeError):
                continue

    if latest:
        # Return calibrated temp, or raw temp if not available
        return latest.get("temp") or latest.get("temp_raw")

    return None


def get_latest_tilt_id() -> Optional[str]:
    """Get the ID of the most recently active Tilt."""
    from .state import latest_readings

    if not latest_readings:
        return None

    latest_id = None
    latest_time = None

    for tilt_id, reading in latest_readings.items():
        last_seen_str = reading.get("last_seen")
        if last_seen_str:
            try:
                last_seen = datetime.fromisoformat(last_seen_str.replace("Z", "+00:00"))
                if latest_time is None or last_seen > latest_time:
                    latest_time = last_seen
                    latest_id = tilt_id
            except (ValueError, TypeError):
                continue

    return latest_id


async def get_latest_ambient_temp(db) -> Optional[float]:
    """Get the most recent ambient temperature reading."""
    from sqlalchemy import desc

    result = await db.execute(
        select(AmbientReading.temperature)
        .where(AmbientReading.temperature.isnot(None))
        .order_by(desc(AmbientReading.timestamp))
        .limit(1)
    )
    row = result.scalar_one_or_none()
    return row


async def get_latest_chamber_temp(db) -> Optional[float]:
    """Get the most recent chamber temperature reading."""
    from sqlalchemy import desc
    from .models import ChamberReading

    result = await db.execute(
        select(ChamberReading.temperature)
        .where(ChamberReading.temperature.isnot(None))
        .order_by(desc(ChamberReading.timestamp))
        .limit(1)
    )
    return result.scalar_one_or_none()


async def log_control_event(
    db,
    action: str,
    wort_temp: Optional[float],
    ambient_temp: Optional[float],
    target_temp: Optional[float],
    device_id: Optional[str],
    batch_id: Optional[int] = None,
) -> None:
    """Log a control event to the database."""
    event = ControlEvent(
        action=action,
        wort_temp=wort_temp,
        ambient_temp=ambient_temp,
        target_temp=target_temp,
        device_id=device_id,
        batch_id=batch_id,
    )
    db.add(event)
    await db.commit()

    # Broadcast event via WebSocket
    await ws_manager.broadcast_json({
        "type": "control_event",
        "action": action,
        "wort_temp": wort_temp,
        "ambient_temp": ambient_temp,
        "target_temp": target_temp,
        "batch_id": batch_id,
        "timestamp": serialize_datetime_to_utc(datetime.now(timezone.utc))
    })

    batch_info = f", batch_id={batch_id}" if batch_id else ""
    logger.info(f"Control event: {action} (wort={wort_temp}, target={target_temp}{batch_info})")


async def set_heater_state_for_batch(
    router: DeviceControlRouter,
    entity_id: str,
    state: str,
    db,
    batch_id: int,
    wort_temp: float,
    ambient_temp: Optional[float],
    target_temp: float,
    device_id: Optional[str],
    force: bool = False
) -> bool:
    """Turn heater on or off for a specific batch and log the event."""
    global _batch_heater_states

    # Get batch's heater state tracking
    batch_state = _batch_heater_states.get(batch_id, {})
    last_state = batch_state.get("state")
    last_change = batch_state.get("last_change")

    # Check minimum cycle time (skip for forced changes like overrides)
    if not force and last_change is not None:
        elapsed = datetime.now(timezone.utc) - last_change
        if elapsed < timedelta(minutes=MIN_CYCLE_MINUTES):
            remaining = MIN_CYCLE_MINUTES - (elapsed.total_seconds() / 60)
            logger.debug(f"Batch {batch_id}: Skipping heater change to '{state}' - min cycle time not met ({remaining:.1f} min remaining)")
            return False

    logger.debug(f"Batch {batch_id}: Attempting to set heater to '{state}' (entity: {entity_id})")

    success = await router.set_state(entity_id, state)
    action = "heat_on" if state == "on" else "heat_off"

    if success:
        _batch_heater_states[batch_id] = {
            "state": state,
            "last_change": datetime.now(timezone.utc),
            "entity_id": entity_id,
        }
        logger.info(f"Batch {batch_id}: Heater state changed: {last_state} -> {state}")
        await log_control_event(db, action, wort_temp, ambient_temp, target_temp, device_id, batch_id)
    else:
        logger.error(f"Batch {batch_id}: Failed to set heater to '{state}' (entity: {entity_id})")

    return success


async def set_cooler_state_for_batch(
    router: DeviceControlRouter,
    entity_id: str,
    state: str,
    db,
    batch_id: int,
    wort_temp: float,
    ambient_temp: Optional[float],
    target_temp: float,
    device_id: Optional[str],
    force: bool = False
) -> bool:
    """Turn cooler on or off for a specific batch and log the event."""
    global _batch_cooler_states

    # Get batch's cooler state tracking
    batch_state = _batch_cooler_states.get(batch_id, {})
    last_state = batch_state.get("state")
    last_change = batch_state.get("last_change")

    # Check minimum cycle time (skip for forced changes like overrides)
    if not force and last_change is not None:
        elapsed = datetime.now(timezone.utc) - last_change
        if elapsed < timedelta(minutes=MIN_CYCLE_MINUTES):
            remaining = MIN_CYCLE_MINUTES - (elapsed.total_seconds() / 60)
            logger.debug(f"Batch {batch_id}: Skipping cooler change to '{state}' - min cycle time not met ({remaining:.1f} min remaining)")
            return False

    logger.debug(f"Batch {batch_id}: Attempting to set cooler to '{state}' (entity: {entity_id})")

    success = await router.set_state(entity_id, state)
    action = "cool_on" if state == "on" else "cool_off"

    if success:
        _batch_cooler_states[batch_id] = {
            "state": state,
            "last_change": datetime.now(timezone.utc),
            "entity_id": entity_id,
        }
        logger.info(f"Batch {batch_id}: Cooler state changed: {last_state} -> {state}")
        await log_control_event(db, action, wort_temp, ambient_temp, target_temp, device_id, batch_id)
    else:
        logger.error(f"Batch {batch_id}: Failed to set cooler to '{state}' (entity: {entity_id})")

    return success


async def control_batch_temperature(
    router: DeviceControlRouter,
    batch: Batch,
    db,
    global_target: float,
    global_hysteresis: float,
    ambient_temp: Optional[float],
) -> None:
    """Control both heating and cooling for a single batch.

    For "planning" or "brewing" status batches (pre-pitch chilling):
    - Only cooling is allowed to bring wort down to pitch temp
    - Heating is disabled to prevent accidentally warming the wort
    - A "pitch_ready" WebSocket notification is sent when target is reached
    """
    batch_id = batch.id
    device_id = batch.device_id
    heater_entity = batch.heater_entity_id
    cooler_entity = batch.cooler_entity_id
    is_chilling_mode = batch.status in ("planning", "brewing")  # Pre-pitch chilling

    # In chilling mode, only cooler is used
    if is_chilling_mode:
        heater_entity = None  # Disable heater during planning

    if not heater_entity and not cooler_entity:
        return

    # Get temperature from batch's linked device
    wort_temp = get_device_temp(device_id) if device_id else None
    if wort_temp is None:
        logger.debug(f"Batch {batch_id}: No temperature available from device {device_id}")
        return

    # Use batch-specific settings or fall back to global
    target_temp = batch.temp_target if batch.temp_target is not None else global_target
    hysteresis = batch.temp_hysteresis if batch.temp_hysteresis is not None else global_hysteresis

    # Sync cached heater state with actual device state
    # NOTE: This sync happens before checking minimum cycle time. If the heater state
    # was changed externally (e.g., manual toggle in HA), this sync updates our cache
    # but does NOT reset the last_change timestamp. This means external changes won't
    # bypass the MIN_CYCLE_MINUTES protection, which is intentional to prevent rapid
    # cycling even when users manually toggle the heater.
    if heater_entity:
        actual_heater_state = await router.get_state(heater_entity)
        if actual_heater_state in ("on", "off"):
            if batch_id in _batch_heater_states:
                if _batch_heater_states[batch_id].get("state") != actual_heater_state:
                    logger.debug(f"Batch {batch_id}: Syncing heater cache: {_batch_heater_states[batch_id].get('state')} -> {actual_heater_state}")
                # Only update the state, preserve the existing last_change timestamp
                _batch_heater_states[batch_id]["state"] = actual_heater_state
            else:
                # Initialize state tracking for new batch (no last_change yet)
                _batch_heater_states[batch_id] = {"state": actual_heater_state}
        elif actual_heater_state is None:
            logger.warning(f"Batch {batch_id}: Heater entity {heater_entity} is unavailable")
            return  # Early return - cannot control unavailable entity

    # Sync cached cooler state with actual device state
    if cooler_entity:
        actual_cooler_state = await router.get_state(cooler_entity)
        if actual_cooler_state in ("on", "off"):
            if batch_id in _batch_cooler_states:
                if _batch_cooler_states[batch_id].get("state") != actual_cooler_state:
                    logger.debug(f"Batch {batch_id}: Syncing cooler cache: {_batch_cooler_states[batch_id].get('state')} -> {actual_cooler_state}")
                # Only update the state, preserve the existing last_change timestamp
                _batch_cooler_states[batch_id]["state"] = actual_cooler_state
            else:
                # Initialize state tracking for new batch (no last_change yet)
                _batch_cooler_states[batch_id] = {"state": actual_cooler_state}
        elif actual_cooler_state is None:
            logger.warning(f"Batch {batch_id}: Cooler entity {cooler_entity} is unavailable")
            return  # Early return - cannot control unavailable entity

    current_heater_state = _batch_heater_states.get(batch_id, {}).get("state")
    current_cooler_state = _batch_cooler_states.get(batch_id, {}).get("state")

    # Check for manual overrides for this batch
    if batch_id in _batch_overrides:
        override = _batch_overrides[batch_id]

        # Handle heater override
        heater_override = override.get("heater")
        if heater_override:
            override_until = heater_override.get("until")
            if override_until and datetime.now(timezone.utc) > override_until:
                # Override expired
                logger.info(f"Batch {batch_id}: Heater override expired, returning to auto mode")
                del _batch_overrides[batch_id]["heater"]
            else:
                # Override active
                desired_state = heater_override.get("state")
                if heater_entity and current_heater_state != desired_state:
                    await set_heater_state_for_batch(
                        router, heater_entity, desired_state, db, batch_id,
                        wort_temp, ambient_temp, target_temp, device_id, force=True
                    )

        # Handle cooler override
        cooler_override = override.get("cooler")
        if cooler_override:
            override_until = cooler_override.get("until")
            if override_until and datetime.now(timezone.utc) > override_until:
                # Override expired
                logger.info(f"Batch {batch_id}: Cooler override expired, returning to auto mode")
                del _batch_overrides[batch_id]["cooler"]
            else:
                # Override active
                desired_state = cooler_override.get("state")
                if cooler_entity and current_cooler_state != desired_state:
                    await set_cooler_state_for_batch(
                        router, cooler_entity, desired_state, db, batch_id,
                        wort_temp, ambient_temp, target_temp, device_id, force=True
                    )

        # If either override is active, skip automatic control
        if heater_override or cooler_override:
            return

    # Calculate thresholds (asymmetric hysteresis to prevent overshoot)
    # Turn ON at target ± hysteresis, turn OFF at target (not target ± hysteresis)
    heat_on_threshold = round(target_temp - hysteresis, 1)
    heat_off_threshold = round(target_temp, 1)  # Turn OFF at target to prevent overshoot
    cool_on_threshold = round(target_temp + hysteresis, 1)
    cool_off_threshold = round(target_temp, 1)  # Turn OFF at target to prevent undershoot

    logger.debug(
        f"Batch {batch_id}: Control check: wort={wort_temp:.2f}F, target={target_temp:.2f}F, "
        f"hysteresis={hysteresis:.2f}F, heat_on<={heat_on_threshold:.2f}F, heat_off>={heat_off_threshold:.2f}F, "
        f"cool_on>={cool_on_threshold:.2f}F, cool_off<={cool_off_threshold:.2f}F, "
        f"heater={current_heater_state}, cooler={current_cooler_state}"
    )

    # Automatic control logic with mutual exclusion
    # CRITICAL: Turn OFF opposite device FIRST, then turn ON current device
    # This prevents both devices from being ON simultaneously
    if wort_temp <= heat_on_threshold:
        # Need heating - FIRST ensure cooler is OFF
        if cooler_entity and current_cooler_state == "on":
            logger.info(f"Batch {batch_id}: Turning cooler OFF (heater needs to run)")
            await set_cooler_state_for_batch(
                router, cooler_entity, "off", db, batch_id,
                wort_temp, ambient_temp, target_temp, device_id
            )
            # Refresh state after change
            current_cooler_state = _batch_cooler_states.get(batch_id, {}).get("state")

        # THEN turn heater ON (only if cooler is confirmed off)
        if heater_entity and current_heater_state != "on":
            logger.info(f"Batch {batch_id}: Wort temp {wort_temp:.1f}F at/below threshold {heat_on_threshold:.1f}F, turning heater ON")
            await set_heater_state_for_batch(
                router, heater_entity, "on", db, batch_id,
                wort_temp, ambient_temp, target_temp, device_id
            )
            # Refresh state after change
            current_heater_state = _batch_heater_states.get(batch_id, {}).get("state")

    elif wort_temp >= cool_on_threshold:
        # Need cooling - FIRST ensure heater is OFF
        if heater_entity and current_heater_state == "on":
            logger.info(f"Batch {batch_id}: Turning heater OFF (cooler needs to run)")
            await set_heater_state_for_batch(
                router, heater_entity, "off", db, batch_id,
                wort_temp, ambient_temp, target_temp, device_id
            )
            # Refresh state after change
            current_heater_state = _batch_heater_states.get(batch_id, {}).get("state")

        # THEN turn cooler ON (only if heater is confirmed off)
        if cooler_entity and current_cooler_state != "on":
            logger.info(f"Batch {batch_id}: Wort temp {wort_temp:.1f}F at/above threshold {cool_on_threshold:.1f}F, turning cooler ON")
            await set_cooler_state_for_batch(
                router, cooler_entity, "on", db, batch_id,
                wort_temp, ambient_temp, target_temp, device_id
            )
            # Refresh state after change
            current_cooler_state = _batch_cooler_states.get(batch_id, {}).get("state")

    else:
        # Within deadband - check if we should turn OFF at target temp
        if wort_temp >= heat_off_threshold and heater_entity and current_heater_state == "on":
            # Reached target temp while heating - turn heater OFF to prevent overshoot
            logger.info(f"Batch {batch_id}: Wort temp {wort_temp:.1f}F reached target {heat_off_threshold:.1f}F, turning heater OFF")
            await set_heater_state_for_batch(
                router, heater_entity, "off", db, batch_id,
                wort_temp, ambient_temp, target_temp, device_id
            )
        elif wort_temp <= cool_off_threshold and cooler_entity and current_cooler_state == "on":
            # Reached target temp while cooling - turn cooler OFF to prevent undershoot
            logger.info(f"Batch {batch_id}: Wort temp {wort_temp:.1f}C reached target {cool_off_threshold:.1f}C, turning cooler OFF")
            await set_cooler_state_for_batch(
                router, cooler_entity, "off", db, batch_id,
                wort_temp, ambient_temp, target_temp, device_id
            )
            # If in chilling mode (planning status), send pitch-ready notification
            if is_chilling_mode:
                await _send_pitch_ready_notification(batch, wort_temp, target_temp)
        elif is_chilling_mode and wort_temp <= target_temp:
            # In chilling mode and at/below target - send pitch-ready notification
            # This catches the case where temp drifted to target without active cooling
            await _send_pitch_ready_notification(batch, wort_temp, target_temp)
        else:
            # Maintain current states
            logger.debug(
                f"Batch {batch_id}: Within hysteresis band ({heat_on_threshold:.1f}F-{cool_on_threshold:.1f}F), "
                f"maintaining states: heater={current_heater_state}, cooler={current_cooler_state}"
            )


async def control_chamber_idle(
    router: DeviceControlRouter,
    db,
    target_temp: float,
    hysteresis: float,
    ambient_temp: Optional[float],
) -> None:
    """Control chamber temperature when no batches are actively being controlled.

    Uses the chamber sensor (not wort sensor) to maintain a target temperature
    in the fermentation chamber when idle. This prevents the chamber from
    getting too hot or cold between batches.
    """
    global _idle_heater_state, _idle_cooler_state

    # Get heater/cooler entities from the most recent batch that had them configured
    # (entities are assigned per-batch, not in global settings)
    heater_entity = None
    cooler_entity = None
    result = await db.execute(
        select(Batch.heater_entity_id, Batch.cooler_entity_id)
        .where(
            Batch.deleted_at.is_(None),
            (Batch.heater_entity_id.isnot(None)) | (Batch.cooler_entity_id.isnot(None)),
        )
        .order_by(Batch.updated_at.desc())
        .limit(1)
    )
    row = result.first()
    if row:
        heater_entity = row[0]
        cooler_entity = row[1]

    if not heater_entity and not cooler_entity:
        logger.debug("Chamber idle: no heater or cooler entity configured")
        return

    # Read chamber temperature
    chamber_temp = await get_latest_chamber_temp(db)
    if chamber_temp is None:
        logger.debug("Chamber idle: no chamber temperature available")
        return

    # Sync cached idle heater state with actual device state
    if heater_entity:
        actual_heater_state = await router.get_state(heater_entity)
        if actual_heater_state in ("on", "off"):
            if _idle_heater_state:
                if _idle_heater_state.get("state") != actual_heater_state:
                    logger.debug(f"Chamber idle: Syncing heater cache: {_idle_heater_state.get('state')} -> {actual_heater_state}")
                _idle_heater_state["state"] = actual_heater_state
            else:
                _idle_heater_state = {"state": actual_heater_state}
        elif actual_heater_state is None:
            logger.warning(f"Chamber idle: Heater entity {heater_entity} is unavailable, skipping heater")
            heater_entity = None  # Skip heater but continue with cooler

    # Sync cached idle cooler state with actual device state
    if cooler_entity:
        actual_cooler_state = await router.get_state(cooler_entity)
        if actual_cooler_state in ("on", "off"):
            if _idle_cooler_state:
                if _idle_cooler_state.get("state") != actual_cooler_state:
                    logger.debug(f"Chamber idle: Syncing cooler cache: {_idle_cooler_state.get('state')} -> {actual_cooler_state}")
                _idle_cooler_state["state"] = actual_cooler_state
            else:
                _idle_cooler_state = {"state": actual_cooler_state}
        elif actual_cooler_state is None:
            logger.warning(f"Chamber idle: Cooler entity {cooler_entity} is unavailable, skipping cooler")
            cooler_entity = None  # Skip cooler but continue with heater

    # If both unavailable, nothing to do
    if not heater_entity and not cooler_entity:
        return

    current_heater = _idle_heater_state.get("state")
    current_cooler = _idle_cooler_state.get("state")

    # Asymmetric hysteresis thresholds (same logic as control_batch_temperature)
    heat_on_threshold = round(target_temp - hysteresis, 1)
    heat_off_threshold = round(target_temp, 1)
    cool_on_threshold = round(target_temp + hysteresis, 1)
    cool_off_threshold = round(target_temp, 1)

    logger.debug(
        f"Chamber idle: chamber={chamber_temp:.1f}C, target={target_temp:.1f}C, "
        f"hysteresis={hysteresis:.1f}C, heater={current_heater}, cooler={current_cooler}"
    )

    # Helper to check minimum cycle time for idle state changes
    def _can_change_idle(state_dict: dict) -> bool:
        last_change = state_dict.get("last_change")
        if last_change is None:
            return True
        elapsed = datetime.now(timezone.utc) - last_change
        return elapsed >= timedelta(minutes=MIN_CYCLE_MINUTES)

    # Helper to set idle heater state
    async def _set_idle_heater(state: str) -> bool:
        if not _can_change_idle(_idle_heater_state):
            logger.debug(f"Chamber idle: Skipping heater change to '{state}' - min cycle time not met")
            return False
        success = await router.set_state(heater_entity, state)
        if success:
            old_state = _idle_heater_state.get("state")
            _idle_heater_state["state"] = state
            _idle_heater_state["last_change"] = datetime.now(timezone.utc)
            logger.info(f"Chamber idle: Heater state changed: {old_state} -> {state}")
            action = "heat_on" if state == "on" else "heat_off"
            await log_control_event(db, action, chamber_temp, ambient_temp, target_temp, None, batch_id=None)
        else:
            logger.error(f"Chamber idle: Failed to set heater to '{state}'")
        return success

    # Helper to set idle cooler state
    async def _set_idle_cooler(state: str) -> bool:
        if not _can_change_idle(_idle_cooler_state):
            logger.debug(f"Chamber idle: Skipping cooler change to '{state}' - min cycle time not met")
            return False
        success = await router.set_state(cooler_entity, state)
        if success:
            old_state = _idle_cooler_state.get("state")
            _idle_cooler_state["state"] = state
            _idle_cooler_state["last_change"] = datetime.now(timezone.utc)
            logger.info(f"Chamber idle: Cooler state changed: {old_state} -> {state}")
            action = "cool_on" if state == "on" else "cool_off"
            await log_control_event(db, action, chamber_temp, ambient_temp, target_temp, None, batch_id=None)
        else:
            logger.error(f"Chamber idle: Failed to set cooler to '{state}'")
        return success

    # Control logic with mutual exclusion (same pattern as control_batch_temperature)
    if chamber_temp <= heat_on_threshold:
        # Need heating - FIRST ensure cooler is OFF
        if cooler_entity and current_cooler == "on":
            logger.info("Chamber idle: Turning cooler OFF (heater needs to run)")
            await _set_idle_cooler("off")
            current_cooler = _idle_cooler_state.get("state")

        # THEN turn heater ON
        if heater_entity and current_heater != "on":
            logger.info(f"Chamber idle: Chamber temp {chamber_temp:.1f}C at/below threshold {heat_on_threshold:.1f}C, turning heater ON")
            await _set_idle_heater("on")

    elif chamber_temp >= cool_on_threshold:
        # Need cooling - FIRST ensure heater is OFF
        if heater_entity and current_heater == "on":
            logger.info("Chamber idle: Turning heater OFF (cooler needs to run)")
            await _set_idle_heater("off")
            current_heater = _idle_heater_state.get("state")

        # THEN turn cooler ON
        if cooler_entity and current_cooler != "on":
            logger.info(f"Chamber idle: Chamber temp {chamber_temp:.1f}C at/above threshold {cool_on_threshold:.1f}C, turning cooler ON")
            await _set_idle_cooler("on")

    else:
        # Within deadband - turn off at target to prevent overshoot
        if chamber_temp >= heat_off_threshold and heater_entity and current_heater == "on":
            logger.info(f"Chamber idle: Chamber temp {chamber_temp:.1f}C reached target {heat_off_threshold:.1f}C, turning heater OFF")
            await _set_idle_heater("off")
        elif chamber_temp <= cool_off_threshold and cooler_entity and current_cooler == "on":
            logger.info(f"Chamber idle: Chamber temp {chamber_temp:.1f}C reached target {cool_off_threshold:.1f}C, turning cooler OFF")
            await _set_idle_cooler("off")
        else:
            logger.debug(
                f"Chamber idle: Within hysteresis band ({heat_on_threshold:.1f}C-{cool_on_threshold:.1f}C), "
                f"maintaining states: heater={current_heater}, cooler={current_cooler}"
            )


async def temperature_control_loop() -> None:
    """Main temperature control loop - handles multiple batches with their own heaters."""
    global _last_ha_url, _last_ha_token, _wake_event

    _wake_event = asyncio.Event()

    while True:
        try:
            async with async_session_factory() as db:
                # Check if temperature control is enabled
                temp_control_enabled = await get_config_value(db, "temp_control_enabled")

                if not temp_control_enabled:
                    await _wait_or_wake(CONTROL_INTERVAL_SECONDS)
                    continue

                # Check if HA is enabled (for now - future: support other backends)
                ha_enabled = await get_config_value(db, "ha_enabled")
                if not ha_enabled:
                    await _wait_or_wake(CONTROL_INTERVAL_SECONDS)
                    continue

                # Get HA config - reinitialize router if config changed
                ha_url = await get_config_value(db, "ha_url")
                ha_token = await get_config_value(db, "ha_token")

                if not ha_url or not ha_token:
                    await _wait_or_wake(CONTROL_INTERVAL_SECONDS)
                    continue

                # Reinitialize device router if config changed
                if ha_url != _last_ha_url or ha_token != _last_ha_token:
                    logger.info("Device control config changed, reinitializing router")
                    init_device_router(RouterConfig(
                        ha_enabled=True,
                        ha_url=ha_url,
                        ha_token=ha_token,
                    ))
                    _last_ha_url = ha_url
                    _last_ha_token = ha_token

                router = get_device_router()
                if not router:
                    init_device_router(RouterConfig(
                        ha_enabled=True,
                        ha_url=ha_url,
                        ha_token=ha_token,
                    ))
                    _last_ha_url = ha_url
                    _last_ha_token = ha_token
                    router = get_device_router()

                if not router:
                    await _wait_or_wake(CONTROL_INTERVAL_SECONDS)
                    continue

                # Get global control parameters (used as defaults)
                global_target = await get_config_value(db, "temp_target") or 68.0
                global_hysteresis = await get_config_value(db, "temp_hysteresis") or 1.0
                ambient_temp = await get_latest_ambient_temp(db)

                # Get all active batches with heater OR cooler entities configured
                # Include "planning" batches with cooler for pre-pitch chilling
                result = await db.execute(
                    select(Batch).where(
                        Batch.deleted_at.is_(None),  # Exclude soft-deleted
                        Batch.device_id.isnot(None),
                        Batch.temp_target.isnot(None),  # Must have target temp set
                        (
                            # Fermenting/conditioning: heater or cooler
                            (Batch.status.in_(["fermenting", "conditioning"]) &
                             ((Batch.heater_entity_id.isnot(None)) | (Batch.cooler_entity_id.isnot(None))))
                            |
                            # Planning: cooler only (for pre-pitch chilling)
                            (Batch.status == "planning") & (Batch.cooler_entity_id.isnot(None))
                        ),
                    )
                )
                batches = result.scalars().all()

                # Control each batch's temperature concurrently for better performance
                if batches:
                    await asyncio.gather(*[
                        control_batch_temperature(
                            router, batch, db, global_target, global_hysteresis, ambient_temp
                        )
                        for batch in batches
                    ], return_exceptions=True)

                # Chamber idle mode: control when no batches are active
                if not batches:
                    idle_enabled = await get_config_value(db, "chamber_idle_enabled")
                    if idle_enabled:
                        idle_target = await get_config_value(db, "chamber_idle_target") or 15.0
                        idle_hysteresis = await get_config_value(db, "chamber_idle_hysteresis") or 2.0
                        await control_chamber_idle(
                            router, db, idle_target, idle_hysteresis, ambient_temp
                        )
                else:
                    # Batches active - clear idle state
                    if _idle_heater_state or _idle_cooler_state:
                        logger.info("Chamber idle: batch control active, clearing idle state")
                        _idle_heater_state.clear()
                        _idle_cooler_state.clear()

                # Cleanup old batch entries from in-memory state dictionaries
                active_batch_ids = {b.id for b in batches}
                planning_batch_ids = {b.id for b in batches if b.status == "planning"}

                for batch_id in list(_batch_heater_states.keys()):
                    if batch_id not in active_batch_ids:
                        logger.debug(f"Cleaning up heater state for inactive batch {batch_id}")
                        del _batch_heater_states[batch_id]
                for batch_id in list(_batch_cooler_states.keys()):
                    if batch_id not in active_batch_ids:
                        logger.debug(f"Cleaning up cooler state for inactive batch {batch_id}")
                        del _batch_cooler_states[batch_id]
                for batch_id in list(_batch_overrides.keys()):
                    if batch_id not in active_batch_ids:
                        logger.debug(f"Cleaning up override for inactive batch {batch_id}")
                        del _batch_overrides[batch_id]
                # Clean up pitch_ready tracking for batches no longer in planning
                for batch_id in list(_pitch_ready_sent.keys()):
                    if batch_id not in planning_batch_ids:
                        logger.debug(f"Cleaning up pitch_ready flag for batch {batch_id} (no longer planning)")
                        del _pitch_ready_sent[batch_id]

        except Exception as e:
            logger.error(f"Temperature control error: {e}", exc_info=True)

        await _wait_or_wake(CONTROL_INTERVAL_SECONDS)


def get_control_status() -> dict:
    """Get current temperature control status (legacy global status)."""
    wort_temp = get_latest_tilt_temp()

    return {
        "heater_state": None,  # No longer a single global heater
        "override_active": False,
        "override_state": None,
        "override_until": None,
        "wort_temp": wort_temp,
    }


def get_batch_control_status(batch_id: int) -> dict:
    """Get temperature control status for a specific batch.

    Returns state_available=True if runtime state exists for this batch,
    False if state was cleaned up (e.g., batch completed/archived).
    """
    heater_state = _batch_heater_states.get(batch_id)
    cooler_state = _batch_cooler_states.get(batch_id)
    override = _batch_overrides.get(batch_id)

    # state_available indicates whether runtime state exists for this batch
    # False means state was cleaned up (batch no longer fermenting) or never existed
    state_available = heater_state is not None or cooler_state is not None

    # For backward compatibility, keep override_state (deprecated)
    # It will return heater override state if present, otherwise cooler override state
    legacy_override_state = None
    if override:
        if override.get("heater"):
            legacy_override_state = override["heater"].get("state")
        elif override.get("cooler"):
            legacy_override_state = override["cooler"].get("state")

    return {
        "batch_id": batch_id,
        "enabled": True,  # Batch-level control is always enabled if state exists
        "heater_state": heater_state.get("state") if heater_state else None,
        "heater_entity": heater_state.get("entity_id") if heater_state else None,
        "cooler_state": cooler_state.get("state") if cooler_state else None,
        "cooler_entity": cooler_state.get("entity_id") if cooler_state else None,
        "override_active": override is not None,
        "override_state": legacy_override_state,  # Deprecated - kept for backward compat
        "override_until": serialize_datetime_to_utc(override.get("heater", {}).get("until") or override.get("cooler", {}).get("until")) if override else None,
        "target_temp": None,  # Would need to query DB for batch.temp_target
        "hysteresis": None,  # Would need to query DB for batch.temp_hysteresis
        "wort_temp": None,  # Would need to get from latest_readings
        "state_available": state_available,
    }


def get_chamber_idle_status() -> dict:
    """Get current chamber idle control status."""
    return {
        "heater_state": _idle_heater_state.get("state"),
        "cooler_state": _idle_cooler_state.get("state"),
    }


def set_manual_override(
    state: Optional[str],
    duration_minutes: int = 60,
    batch_id: Optional[int] = None,
    device_type: str = "heater"
) -> bool:
    """Set manual override for heater or cooler control.

    Args:
        state: "on", "off", or None to cancel override
        duration_minutes: How long override lasts (default 60 min)
        batch_id: If provided, override for specific batch; otherwise legacy global override
        device_type: "heater" or "cooler" - which device to override

    Returns:
        True if override was set/cleared successfully
    """
    global _batch_overrides

    if batch_id is None:
        # Legacy global override - no longer supported for multi-batch
        logger.warning("Global override not supported in multi-batch mode. Use batch_id parameter.")
        return False

    if device_type not in ("heater", "cooler"):
        logger.error(f"Invalid device_type: {device_type}. Must be 'heater' or 'cooler'.")
        return False

    if state is None:
        # Cancel override for specific device type
        if batch_id in _batch_overrides and device_type in _batch_overrides[batch_id]:
            del _batch_overrides[batch_id][device_type]
            # Clean up batch entry if no overrides remain
            if not _batch_overrides[batch_id]:
                del _batch_overrides[batch_id]
        logger.info(f"Batch {batch_id}: Manual override cancelled for {device_type}, returning to auto mode")
        _trigger_immediate_check()
        return True

    if state not in ("on", "off"):
        return False

    # Initialize nested structure if needed
    if batch_id not in _batch_overrides:
        _batch_overrides[batch_id] = {}

    _batch_overrides[batch_id][device_type] = {
        "state": state,
        "until": datetime.now(timezone.utc) + timedelta(minutes=duration_minutes) if duration_minutes > 0 else None,
    }
    logger.info(f"Batch {batch_id}: Manual override set: {device_type} {state} for {duration_minutes} minutes")
    _trigger_immediate_check()
    return True


def sync_cached_state(state: Optional[str], batch_id: Optional[int] = None, device_type: str = "heater") -> None:
    """Keep the in-memory device state in sync with external changes (e.g., manual HA toggles).

    Args:
        state: "on", "off", or None
        batch_id: The batch ID to sync state for
        device_type: "heater" or "cooler" - which device to sync
    """
    global _batch_heater_states, _batch_cooler_states

    if state in ("on", "off", None) and batch_id is not None:
        if device_type == "heater":
            _batch_heater_states.setdefault(batch_id, {})["state"] = state
        elif device_type == "cooler":
            _batch_cooler_states.setdefault(batch_id, {})["state"] = state


# Backward compatibility alias
def sync_cached_heater_state(state: Optional[str], batch_id: Optional[int] = None) -> None:
    """Legacy function - use sync_cached_state instead."""
    sync_cached_state(state, batch_id, device_type="heater")


def start_temp_controller() -> None:
    """Start the temperature control background task."""
    global _controller_task
    if _controller_task is None or _controller_task.done():
        _controller_task = asyncio.create_task(temperature_control_loop())
        logger.info("Temperature controller started")


def stop_temp_controller() -> None:
    """Stop the temperature control background task."""
    global _controller_task
    if _controller_task and not _controller_task.done():
        _controller_task.cancel()
        logger.info("Temperature controller stopped")
