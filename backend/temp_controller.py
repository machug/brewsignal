"""Background task for temperature control.

Supports multiple control backends via the device control abstraction layer:
- Home Assistant (existing)
- Direct Shelly HTTP (planned - tilt_ui-amh)
- Gateway relay (planned - tilt_ui-123)
"""

import asyncio
import logging
import os
from types import SimpleNamespace
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select

from .database import async_session_factory
from .models import Batch, ControlEntityState, ControlEvent, AmbientReading, serialize_datetime_to_utc
from .routers.config import get_config_value
from .services.alert_service import AlertSeverity, AlertType, _clear_alert, _upsert_alert
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
MIN_CYCLE_MINUTES = 5  # Minimum time between state changes of one switch (compressor protection)


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


# Safety limits (tilt_ui-f50x). Override with environment variables.
# Stale sensor: a Tilt broadcasts every few seconds, so 15 min is ~100+ missed
# readings. Slower devices (RAPT/iSpindel-class, 5-15 min cadence) get 3x.
SENSOR_STALE_MINUTES = _env_float("BREWSIGNAL_SENSOR_STALE_MINUTES", 15)
# Heater adds ~1.1 C/h to the wort, so 4 h continuous is ~4 C of heating: a
# runaway, not a normal run. A fridge legitimately runs for days during a
# cold crash (wort moves only ~0.35 C/h), so the cooler has a progress rule plus
# a long absolute backstop instead.
MAX_HEATER_ON_MINUTES = _env_float("BREWSIGNAL_MAX_HEATER_ON_MINUTES", 240)
MAX_COOLER_ON_MINUTES = _env_float("BREWSIGNAL_MAX_COOLER_ON_MINUTES", 4320)  # 72 h absolute backstop
# Cooler "no progress" rule: a cold crash legitimately runs the cooler for days
# (wort cools ~0.35 C/h), so the cooler trips only when it has been on for this
# long without the wort cooling by at least the minimum progress.
COOLER_NO_PROGRESS_MINUTES = _env_float("BREWSIGNAL_COOLER_NO_PROGRESS_MINUTES", 360)
COOLER_MIN_PROGRESS_C = _env_float("BREWSIGNAL_COOLER_MIN_PROGRESS_C", 0.5)
# After a max-on trip the device may not be turned on again for this long.
MAX_ON_LOCKOUT_MINUTES = _env_float("BREWSIGNAL_MAX_ON_LOCKOUT_MINUTES", 30)
# After a failed 'on' command, wait this long before trying 'on' again.
FAILURE_BACKOFF_MINUTES = _env_float("BREWSIGNAL_FAILURE_BACKOFF_MINUTES", 5)


def _now() -> datetime:
    """Controller clock (monkeypatched in tests)."""
    return datetime.now(timezone.utc)


# Per-ENTITY switch bookkeeping, persisted in control_entity_state:
# {entity_id: {"last_switch", "on_since", "locked_until", "fail_until"}}
_entity_state: dict[str, dict] = {}

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
    # Calibrated temp, or raw temp if not available (explicit None check: 0.0 C is valid)
    temp = reading.get("temp")
    return temp if temp is not None else reading.get("temp_raw")


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


def _utc(dt: Optional[datetime]) -> Optional[datetime]:
    """SQLite hands back naive datetimes; everything here is UTC."""
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


async def _entity(db, entity_id: str) -> dict:
    """Return the (lazily DB-loaded) switch record for an entity."""
    ent = _entity_state.get(entity_id)
    if ent is None:
        ent = {"last_switch": None, "on_since": None, "locked_until": None, "fail_until": None,
               "ref_temp": None, "ref_at": None}
        try:
            row = await db.get(ControlEntityState, entity_id)
            if row is not None:
                ent["last_switch"] = _utc(row.last_switch_at)
                ent["on_since"] = _utc(row.on_since)
                ent["locked_until"] = _utc(row.locked_until)
                ent["ref_temp"] = row.progress_ref_temp
                ent["ref_at"] = _utc(row.progress_ref_at)
        except Exception as e:
            # Unknown history: fall back to "never switched". Logged, not fatal.
            logger.error(f"Could not load persisted switch state for {entity_id}: {e}")
        _entity_state[entity_id] = ent
    return ent


async def _persist_entity(db, entity_id: str) -> None:
    """Write the entity's switch record to the DB. Never raises."""
    ent = _entity_state[entity_id]
    try:
        await db.merge(ControlEntityState(
            entity_id=entity_id,
            last_switch_at=ent["last_switch"],
            on_since=ent["on_since"],
            locked_until=ent["locked_until"],
            progress_ref_temp=ent["ref_temp"],
            progress_ref_at=ent["ref_at"],
        ))
        await db.commit()
    except Exception as e:
        logger.error(f"Could not persist switch state for {entity_id}: {e}")
        try:
            await db.rollback()
        except Exception:
            pass


async def _read_state(router: DeviceControlRouter, entity_id: str) -> Optional[str]:
    """Read actual device state; None on unavailable or error."""
    try:
        state = await router.get_state(entity_id)
    except Exception as e:
        logger.error(f"Failed to read state of {entity_id}: {e}")
        return None
    return state if state in ("on", "off") else None


async def _set_entity_state(
    router: DeviceControlRouter,
    db,
    entity_id: str,
    kind: str,
    state: str,
    force: bool = False,
) -> bool:
    """Single choke point for every switch command.

    - min-cycle is per ENTITY and persisted (honoured across restarts and when
      two batches share a switch); `force` skips it (overrides, safety-offs)
    - 'on' is refused during a max-on lockout, even when forced
    - after a failed 'on' no further 'on' is attempted for FAILURE_BACKOFF_MINUTES
      ('off' is always allowed: it is the safe direction)
    """
    ent = await _entity(db, entity_id)
    now = _now()

    if not force and ent["last_switch"] is not None:
        elapsed = now - ent["last_switch"]
        if elapsed < timedelta(minutes=MIN_CYCLE_MINUTES):
            remaining = MIN_CYCLE_MINUTES - elapsed.total_seconds() / 60
            logger.debug(f"{entity_id}: not switching to '{state}' - min cycle ({remaining:.1f} min remaining)")
            return False

    if state == "on":
        if ent["locked_until"] is not None and now < ent["locked_until"]:
            logger.warning(f"{entity_id}: refusing 'on' - max-on lockout until {ent['locked_until'].isoformat()}")
            return False
        if ent["fail_until"] is not None and now < ent["fail_until"]:
            logger.debug(f"{entity_id}: not retrying 'on' - backing off after a failed command")
            return False

    try:
        success = await router.set_state(entity_id, state)
    except Exception as e:
        logger.error(f"{entity_id}: set_state('{state}') raised: {e}")
        success = False

    if success:
        # A redundant "on" for a device that is already on is not a transition:
        # keep the original continuous-on start (else repeated "on" requests
        # would postpone the max-on cutoff forever) and the min-cycle clock.
        already_on = state == "on" and ent["on_since"] is not None
        if not already_on:
            ent["last_switch"] = now
        ent["on_since"] = (ent["on_since"] if already_on else now) if state == "on" else None
        ent["fail_until"] = None
        if state == "off":
            ent["ref_temp"] = ent["ref_at"] = None  # progress reference starts fresh next run
        await _persist_entity(db, entity_id)
    elif state == "on":
        ent["fail_until"] = now + timedelta(minutes=FAILURE_BACKOFF_MINUTES)
    return success


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
    last_state = _batch_heater_states.get(batch_id, {}).get("state")
    logger.debug(f"Batch {batch_id}: Attempting to set heater to '{state}' (entity: {entity_id})")

    success = await _set_entity_state(router, db, entity_id, "heater", state, force=force)
    action = "heat_on" if state == "on" else "heat_off"

    if success:
        _batch_heater_states[batch_id] = {
            "state": state,
            "last_change": _now(),
            "entity_id": entity_id,
        }
        logger.info(f"Batch {batch_id}: Heater state changed: {last_state} -> {state}")
        await log_control_event(db, action, wort_temp, ambient_temp, target_temp, device_id, batch_id)
    else:
        logger.error(f"Batch {batch_id}: Heater not set to '{state}' (entity: {entity_id})")

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
    last_state = _batch_cooler_states.get(batch_id, {}).get("state")
    logger.debug(f"Batch {batch_id}: Attempting to set cooler to '{state}' (entity: {entity_id})")

    success = await _set_entity_state(router, db, entity_id, "cooler", state, force=force)
    action = "cool_on" if state == "on" else "cool_off"

    if success:
        _batch_cooler_states[batch_id] = {
            "state": state,
            "last_change": _now(),
            "entity_id": entity_id,
        }
        logger.info(f"Batch {batch_id}: Cooler state changed: {last_state} -> {state}")
        await log_control_event(db, action, wort_temp, ambient_temp, target_temp, device_id, batch_id)
    else:
        logger.error(f"Batch {batch_id}: Cooler not set to '{state}' (entity: {entity_id})")

    return success


# ---------------------------------------------------------------------------
# Safety helpers (tilt_ui-f50x, tilt_ui-8d49)
# ---------------------------------------------------------------------------

async def _raise_alert(db, batch: Batch, alert_type: str, message: str) -> None:
    """Persist (upsert) a critical alert on the batch. Never raises."""
    try:
        await _upsert_alert(
            db, batch.id, batch.device_id, alert_type, AlertSeverity.CRITICAL,
            message, None, None, _now(),
        )
        await db.commit()
    except Exception as e:
        logger.error(f"Batch {batch.id}: could not persist {alert_type} alert: {e}")
        try:
            await db.rollback()
        except Exception:
            pass


async def _clear_batch_alert(db, batch_id: int, alert_type: str) -> None:
    try:
        if await _clear_alert(db, batch_id, alert_type, _now()):
            await db.commit()
    except Exception as e:
        logger.error(f"Batch {batch_id}: could not clear {alert_type} alert: {e}")
        try:
            await db.rollback()
        except Exception:
            pass


def get_device_reading_age(device_id: str) -> Optional[timedelta]:
    """Age of the cached reading for a device, or None if it cannot be trusted.

    None (= treat as stale) when the reading or its timestamp is missing or
    unparseable, or is more than 5 min in the FUTURE (a Pi that booted with a
    wrong clock would otherwise see an old cached reading as fresh).
    """
    from .state import latest_readings

    reading = latest_readings.get(device_id) if device_id else None
    if not reading:
        return None
    ts = reading.get("last_seen") or reading.get("timestamp")
    if not ts:
        return None
    try:
        seen = _utc(datetime.fromisoformat(str(ts).replace("Z", "+00:00")))
    except (ValueError, TypeError):
        return None
    age = _now() - seen
    if age < timedelta(minutes=-5):
        return None
    return age


def _stale_limit(device_id: str) -> timedelta:
    """Tilt broadcasts every few seconds; RAPT/iSpindel-class devices report
    every 5-15 min, so they get 3x the threshold to avoid false trips."""
    from .state import latest_readings

    dtype = (latest_readings.get(device_id) or {}).get("device_type", "tilt")
    mult = 1 if dtype == "tilt" else 3
    return timedelta(minutes=SENSOR_STALE_MINUTES * mult)


def _max_on_minutes(kind: str) -> float:
    return MAX_HEATER_ON_MINUTES if kind == "heater" else MAX_COOLER_ON_MINUTES


async def _observe_entity(
    router, db, entity_id: str, kind: str, temp: Optional[float] = None,
) -> tuple[Optional[str], Optional[str]]:
    """Read the real state and track the continuous on-run.

    Returns (state, trip). state is None when unavailable. trip is None, or the
    reason the device must be forced off: "max_on" (heater 4 h; cooler 72 h
    absolute backstop) or "no_progress" (cooler on >= 6 h without the wort
    cooling by 0.5 C; `temp` is the temperature being controlled).
    A switch found 'on' with no recorded start (manual toggle in HA, or a
    record lost) starts counting now.
    """
    state = await _read_state(router, entity_id)
    ent = await _entity(db, entity_id)
    trip = None
    now = _now()
    if state == "on":
        dirty = False
        if ent["on_since"] is None:
            ent["on_since"] = now
            dirty = True
        elif now - ent["on_since"] > timedelta(minutes=_max_on_minutes(kind)):
            trip = "max_on"
        if kind == "cooler" and temp is not None and trip is None:
            if ent["ref_at"] is None or ent["ref_temp"] is None:
                ent["ref_temp"], ent["ref_at"] = temp, now
                dirty = True
            elif temp <= ent["ref_temp"] - COOLER_MIN_PROGRESS_C:
                ent["ref_temp"], ent["ref_at"] = temp, now
                dirty = True
            elif now - ent["ref_at"] >= timedelta(minutes=COOLER_NO_PROGRESS_MINUTES):
                trip = "no_progress"
        if dirty:
            await _persist_entity(db, entity_id)
    elif state == "off" and (ent["on_since"] is not None or ent["ref_at"] is not None):
        ent["on_since"] = None
        ent["ref_temp"] = ent["ref_at"] = None
        await _persist_entity(db, entity_id)
    return state, trip


def _trip_message(prefix: str, kind: str, entity: str, trip: str) -> str:
    if trip == "no_progress":
        return (
            f"{prefix}: cooler {entity} ran {COOLER_NO_PROGRESS_MINUTES / 60:g} h without the wort cooling "
            f"by {COOLER_MIN_PROGRESS_C:g} C; forced OFF and locked out for {MAX_ON_LOCKOUT_MINUTES:g} min. "
            f"Check the sensor is in the beer."
        )
    return (
        f"{prefix}: {kind} {entity} has been on continuously for more than "
        f"{_max_on_minutes(kind) / 60:g} h; forced OFF and locked out for {MAX_ON_LOCKOUT_MINUTES:g} min. "
        f"Check the temperature sensor."
    )


async def _start_lockout(db, entity_id: str) -> None:
    ent = await _entity(db, entity_id)
    ent["locked_until"] = _now() + timedelta(minutes=MAX_ON_LOCKOUT_MINUTES)
    await _persist_entity(db, entity_id)


async def _ensure_batch_off(
    router, db, batch_id: int, kind: str, entity_id: str,
    wort_temp: Optional[float], ambient_temp, target_temp, device_id,
) -> bool:
    """Force one entity off (bypasses min-cycle). True if confirmed off."""
    state = await _read_state(router, entity_id)
    if state == "off":
        return True
    setter = set_heater_state_for_batch if kind == "heater" else set_cooler_state_for_batch
    return await setter(
        router, entity_id, "off", db, batch_id,
        wort_temp, ambient_temp, target_temp, device_id, force=True,
    )


ACTIVE_STATUSES = ("fermenting", "conditioning")


def find_equipment_conflicts(batches) -> dict[int, dict]:
    """Detect batches that share a heater/cooler switch or a sensor.

    Returns {batch_id: {"messages": [...], "force_off": bool}} for every batch
    that must NOT be driven. A pre-pitch 'planning' batch that collides with
    exactly one fermenting/conditioning batch loses (it is skipped, the active
    batch keeps its equipment). Any other collision blocks all members
    (force_off=True). Either way the caller switches off whatever a loser drives
    that no non-conflicted batch uses.
    """
    groups: dict[tuple[str, str], list] = {}
    for b in batches:
        keys = set()
        heater = None if b.status in ("planning", "brewing") else b.heater_entity_id
        for e in (heater, b.cooler_entity_id):
            if e:
                keys.add(("equipment", e))
        if b.device_id:
            keys.add(("sensor", b.device_id))
        for k in keys:
            groups.setdefault(k, []).append(b)

    result: dict[int, dict] = {}
    for (ns, ident), members in groups.items():
        if len(members) < 2:
            continue
        active = [m for m in members if m.status in ACTIVE_STATUSES]
        if len(active) == 1:
            losers, force_off = [m for m in members if m.status not in ACTIVE_STATUSES], False
        else:
            losers, force_off = members, True
        what = "switch" if ns == "equipment" else "sensor"
        for m in losers:
            info = result.setdefault(m.id, {"messages": [], "force_off": False})
            others = ", ".join(
                f"batch {o.id} ({o.name or 'unnamed'})" for o in members if o.id != m.id
            )
            info["messages"].append(f"{what} '{ident}' is also used by {others}")
            info["force_off"] = info["force_off"] or force_off
    return result


def _driven_roles(b) -> list[tuple[str, str]]:
    """(kind, entity) pairs the controller actually drives for this batch.
    Pre-pitch chilling (planning/brewing) only ever drives the cooler."""
    roles = []
    if b.heater_entity_id and b.status not in ("planning", "brewing"):
        roles.append(("heater", b.heater_entity_id))
    if b.cooler_entity_id:
        roles.append(("cooler", b.cooler_entity_id))
    return roles


async def _handle_conflicted_batch(
    router, db, batch, info: dict, driven_entities: set[str],
) -> None:
    """Do not drive a batch whose equipment/sensor is shared. Alert, and switch
    off whatever it drives unless a non-conflicted batch legitimately uses that
    switch. A conflict loser (e.g. a planning batch already chilling) therefore
    cannot leave its equipment running unsupervised."""
    msg = f"Batch {batch.id} ({batch.name or 'unnamed'}) not controlled: " + "; ".join(info["messages"])
    logger.error(msg)
    await _raise_alert(db, batch, AlertType.EQUIPMENT_CONFLICT, msg)
    for kind, entity in _driven_roles(batch):
        if entity not in driven_entities:
            await _ensure_batch_off(router, db, batch.id, kind, entity, None, None, batch.temp_target, batch.device_id)


_BATCH_FIELDS = (
    "id", "name", "status", "device_id", "heater_entity_id", "cooler_entity_id",
    "temp_target", "temp_hysteresis",
)


async def run_control_cycle(
    router: DeviceControlRouter,
    db,
    batches,
    global_target: float,
    global_hysteresis: float,
    ambient_temp: Optional[float],
) -> None:
    """One pass over all controllable batches.

    Batches are processed sequentially: they share one DB session and, with
    shared equipment, one per-entity switch record. Needed columns are copied
    up front: a rollback in a persistence helper expires ORM instances, and
    reloading them in async code raises MissingGreenlet.
    """
    batches = [SimpleNamespace(**{f: getattr(b, f) for f in _BATCH_FIELDS}) for b in batches]
    conflicts = find_equipment_conflicts(batches)
    driven = set()
    for b in batches:
        if b.id not in conflicts:
            driven.update(e for _, e in _driven_roles(b))

    for batch in batches:
        try:
            if batch.id in conflicts:
                await _handle_conflicted_batch(router, db, batch, conflicts[batch.id], driven)
            else:
                await _clear_batch_alert(db, batch.id, AlertType.EQUIPMENT_CONFLICT)
                await control_batch_temperature(
                    router, batch, db, global_target, global_hysteresis, ambient_temp
                )
        except Exception as e:
            logger.error(f"Batch {batch.id}: control error: {e}", exc_info=True)


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

    Safety (tilt_ui-f50x): stale/missing sensor -> both off + alert; max
    continuous on-time -> off + lockout + alert; a device is only turned on
    when the opposite device is confirmed off.
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

    # Use batch-specific settings or fall back to global
    target_temp = batch.temp_target if batch.temp_target is not None else global_target
    hysteresis = batch.temp_hysteresis if batch.temp_hysteresis is not None else global_hysteresis

    # Stale-sensor guard: never act on a missing, old or untrustworthy reading
    # (includes the reading cache reloaded from disk at startup).
    wort_temp = get_device_temp(device_id) if device_id else None
    age = get_device_reading_age(device_id) if device_id else None
    if wort_temp is None or age is None or age > _stale_limit(device_id):
        age_txt = "missing" if age is None else f"{age.total_seconds() / 60:.0f} min old"
        msg = (
            f"Batch {batch_id}: wort temperature from device {device_id} is {age_txt} "
            f"(limit {_stale_limit(device_id).total_seconds() / 60:.0f} min); heater and cooler forced OFF"
        )
        logger.warning(msg)
        for kind, entity in (("heater", heater_entity), ("cooler", cooler_entity)):
            if entity:
                await _ensure_batch_off(router, db, batch_id, kind, entity, wort_temp, ambient_temp, target_temp, device_id)
        await _raise_alert(db, batch, AlertType.SENSOR_STALE, msg)
        return
    await _clear_batch_alert(db, batch_id, AlertType.SENSOR_STALE)

    # Read real device state, track continuous on-time, enforce max-on.
    # NOTE: the sync updates our cache but never resets last_switch, so external
    # (manual HA) toggles do not bypass the min-cycle protection.
    current_heater_state = current_cooler_state = None
    tripped = False
    unavailable = False
    for kind, entity, states in (
        ("heater", heater_entity, _batch_heater_states),
        ("cooler", cooler_entity, _batch_cooler_states),
    ):
        if not entity:
            continue
        actual, exceeded = await _observe_entity(router, db, entity, kind, wort_temp)
        if actual is None:
            # Keep going: the other device's max-on must still be enforced
            logger.warning(f"Batch {batch_id}: {kind.capitalize()} entity {entity} is unavailable")
            unavailable = True
            continue
        states.setdefault(batch_id, {})["state"] = actual
        if exceeded:
            tripped = True
            msg = _trip_message(f"Batch {batch_id}", kind, entity, exceeded)
            logger.error(msg)
            await _start_lockout(db, entity)
            await _ensure_batch_off(router, db, batch_id, kind, entity, wort_temp, ambient_temp, target_temp, device_id)
            await _raise_alert(db, batch, AlertType.MAX_ON_EXCEEDED, msg)
    if tripped or unavailable:
        return  # cannot safely control with an unavailable or just-tripped entity
    await _clear_batch_alert(db, batch_id, AlertType.MAX_ON_EXCEEDED)

    # Re-read from the cache (an off above may have changed it)
    current_heater_state = _batch_heater_states.get(batch_id, {}).get("state") if heater_entity else None
    current_cooler_state = _batch_cooler_states.get(batch_id, {}).get("state") if cooler_entity else None

    async def _turn_off_cooler(force: bool = False) -> None:
        nonlocal current_cooler_state
        if await set_cooler_state_for_batch(
            router, cooler_entity, "off", db, batch_id,
            wort_temp, ambient_temp, target_temp, device_id, force=force,
        ):
            current_cooler_state = "off"

    async def _turn_off_heater(force: bool = False) -> None:
        nonlocal current_heater_state
        if await set_heater_state_for_batch(
            router, heater_entity, "off", db, batch_id,
            wort_temp, ambient_temp, target_temp, device_id, force=force,
        ):
            current_heater_state = "off"

    # Manual overrides. 'off' bypasses min-cycle (safe direction); 'on' does not,
    # and only goes ahead once the opposite device is confirmed off.
    if batch_id in _batch_overrides:
        override = _batch_overrides[batch_id]

        heater_override = override.get("heater")
        if heater_override:
            override_until = heater_override.get("until")
            if override_until and _now() > override_until:
                logger.info(f"Batch {batch_id}: Heater override expired, returning to auto mode")
                del _batch_overrides[batch_id]["heater"]
            else:
                desired_state = heater_override.get("state")
                if heater_entity and current_heater_state != desired_state:
                    if desired_state == "on" and cooler_entity and current_cooler_state != "off":
                        await _turn_off_cooler(force=True)
                    if desired_state == "off" or not cooler_entity or current_cooler_state == "off":
                        if await set_heater_state_for_batch(
                            router, heater_entity, desired_state, db, batch_id,
                            wort_temp, ambient_temp, target_temp, device_id, force=(desired_state == "off")
                        ):
                            current_heater_state = desired_state
                    else:
                        logger.error(f"Batch {batch_id}: heater override 'on' skipped - cooler not confirmed off")

        cooler_override = override.get("cooler")
        if cooler_override:
            override_until = cooler_override.get("until")
            if override_until and _now() > override_until:
                logger.info(f"Batch {batch_id}: Cooler override expired, returning to auto mode")
                del _batch_overrides[batch_id]["cooler"]
            else:
                desired_state = cooler_override.get("state")
                if cooler_entity and current_cooler_state != desired_state:
                    if desired_state == "on" and heater_entity and current_heater_state != "off":
                        await _turn_off_heater(force=True)
                    if desired_state == "off" or not heater_entity or current_heater_state == "off":
                        if await set_cooler_state_for_batch(
                            router, cooler_entity, desired_state, db, batch_id,
                            wort_temp, ambient_temp, target_temp, device_id, force=(desired_state == "off")
                        ):
                            current_cooler_state = desired_state
                    else:
                        logger.error(f"Batch {batch_id}: cooler override 'on' skipped - heater not confirmed off")

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
        f"Batch {batch_id}: Control check: wort={wort_temp:.2f}C, target={target_temp:.2f}C, "
        f"hysteresis={hysteresis:.2f}C, heat_on<={heat_on_threshold:.2f}C, heat_off>={heat_off_threshold:.2f}C, "
        f"cool_on>={cool_on_threshold:.2f}C, cool_off<={cool_off_threshold:.2f}C, "
        f"heater={current_heater_state}, cooler={current_cooler_state}"
    )

    # Automatic control logic with mutual exclusion
    # CRITICAL: Turn OFF opposite device FIRST, then turn ON current device,
    # and ONLY if the opposite device is confirmed off. If the off was refused
    # (min-cycle) or failed, the other device stays off this cycle.
    if wort_temp <= heat_on_threshold:
        # Need heating - FIRST ensure cooler is OFF
        if cooler_entity and current_cooler_state == "on":
            logger.info(f"Batch {batch_id}: Turning cooler OFF (heater needs to run)")
            await _turn_off_cooler()

        # THEN turn heater ON (only if cooler is confirmed off)
        if heater_entity and current_heater_state != "on":
            if cooler_entity and current_cooler_state != "off":
                logger.warning(f"Batch {batch_id}: heater ON withheld - cooler not confirmed off")
            else:
                logger.info(f"Batch {batch_id}: Wort temp {wort_temp:.1f}C at/below threshold {heat_on_threshold:.1f}C, turning heater ON")
                await set_heater_state_for_batch(
                    router, heater_entity, "on", db, batch_id,
                    wort_temp, ambient_temp, target_temp, device_id
                )

    elif wort_temp >= cool_on_threshold:
        # Need cooling - FIRST ensure heater is OFF
        if heater_entity and current_heater_state == "on":
            logger.info(f"Batch {batch_id}: Turning heater OFF (cooler needs to run)")
            await _turn_off_heater()

        # THEN turn cooler ON (only if heater is confirmed off)
        if cooler_entity and current_cooler_state != "on":
            if heater_entity and current_heater_state != "off":
                logger.warning(f"Batch {batch_id}: cooler ON withheld - heater not confirmed off")
            else:
                logger.info(f"Batch {batch_id}: Wort temp {wort_temp:.1f}C at/above threshold {cool_on_threshold:.1f}C, turning cooler ON")
                await set_cooler_state_for_batch(
                    router, cooler_entity, "on", db, batch_id,
                    wort_temp, ambient_temp, target_temp, device_id
                )

    else:
        # Within deadband - check if we should turn OFF at target temp
        if wort_temp >= heat_off_threshold and heater_entity and current_heater_state == "on":
            # Reached target temp while heating - turn heater OFF to prevent overshoot
            logger.info(f"Batch {batch_id}: Wort temp {wort_temp:.1f}C reached target {heat_off_threshold:.1f}C, turning heater OFF")
            await _turn_off_heater()
        elif wort_temp <= cool_off_threshold and cooler_entity and current_cooler_state == "on":
            # Reached target temp while cooling - turn cooler OFF to prevent undershoot
            logger.info(f"Batch {batch_id}: Wort temp {wort_temp:.1f}C reached target {cool_off_threshold:.1f}C, turning cooler OFF")
            await _turn_off_cooler()
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
                f"Batch {batch_id}: Within hysteresis band ({heat_on_threshold:.1f}C-{cool_on_threshold:.1f}C), "
                f"maintaining states: heater={current_heater_state}, cooler={current_cooler_state}"
            )


async def get_latest_chamber_reading(db) -> tuple[Optional[float], Optional[datetime]]:
    """Most recent chamber (temperature, timestamp)."""
    from sqlalchemy import desc
    from .models import ChamberReading

    result = await db.execute(
        select(ChamberReading.temperature, ChamberReading.timestamp)
        .where(ChamberReading.temperature.isnot(None))
        .order_by(desc(ChamberReading.timestamp))
        .limit(1)
    )
    row = result.first()
    return (row[0], _utc(row[1])) if row else (None, None)


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

    Shares the safety rules of batch control: persisted per-entity min-cycle,
    stale-sensor guard, max-on, and on only when the opposite is confirmed off.
    """
    global _idle_heater_state, _idle_cooler_state

    # Get heater/cooler entities independently from the most recent batch that had each
    # (a single batch may not have both configured, so query separately)
    heater_result = await db.execute(
        select(Batch.heater_entity_id)
        .where(
            Batch.deleted_at.is_(None),
            Batch.heater_entity_id.isnot(None),
        )
        .order_by(Batch.updated_at.desc())
        .limit(1)
    )
    heater_entity = heater_result.scalar_one_or_none()

    cooler_result = await db.execute(
        select(Batch.cooler_entity_id)
        .where(
            Batch.deleted_at.is_(None),
            Batch.cooler_entity_id.isnot(None),
        )
        .order_by(Batch.updated_at.desc())
        .limit(1)
    )
    cooler_entity = cooler_result.scalar_one_or_none()

    if not heater_entity and not cooler_entity:
        logger.debug("Chamber idle: no heater or cooler entity configured")
        return

    # Read chamber temperature
    chamber_temp, chamber_ts = await get_latest_chamber_reading(db)
    if chamber_temp is None:
        logger.debug("Chamber idle: no chamber temperature available")
        return

    async def _idle_set(kind: str, entity: str, state: str, force: bool = False) -> bool:
        states = _idle_heater_state if kind == "heater" else _idle_cooler_state
        old_state = states.get("state")
        success = await _set_entity_state(router, db, entity, kind, state, force=force)
        if success:
            states["state"] = state
            states["last_change"] = _now()
            logger.info(f"Chamber idle: {kind.capitalize()} state changed: {old_state} -> {state}")
            action = ("heat_" if kind == "heater" else "cool_") + state
            await log_control_event(db, action, chamber_temp, ambient_temp, target_temp, None, batch_id=None)
        else:
            logger.error(f"Chamber idle: {kind.capitalize()} not set to '{state}'")
        return success

    # Stale chamber sensor: both off, no further action
    age = None if chamber_ts is None else _now() - chamber_ts
    if age is None or age > timedelta(minutes=SENSOR_STALE_MINUTES) or age < timedelta(minutes=-5):
        logger.warning(f"Chamber idle: chamber reading is stale ({age}); heater and cooler forced OFF")
        for kind, entity in (("heater", heater_entity), ("cooler", cooler_entity)):
            if entity and await _read_state(router, entity) != "off":
                await _idle_set(kind, entity, "off", force=True)
        return

    # Sync cached idle state with actual device state; enforce max-on for every
    # configured entity before any early return.
    tripped = False
    unavailable = False
    for kind, entity, states in (
        ("heater", heater_entity, _idle_heater_state),
        ("cooler", cooler_entity, _idle_cooler_state),
    ):
        if not entity:
            continue
        actual, exceeded = await _observe_entity(router, db, entity, kind, chamber_temp)
        if actual is None:
            logger.warning(f"Chamber idle: {kind.capitalize()} entity {entity} is unavailable")
            unavailable = True
            continue
        if states.get("state") != actual:
            logger.debug(f"Chamber idle: Syncing {kind} cache: {states.get('state')} -> {actual}")
        states["state"] = actual
        if exceeded:
            tripped = True
            logger.error(_trip_message("Chamber idle", kind, entity, exceeded))
            await _start_lockout(db, entity)
            await _idle_set(kind, entity, "off", force=True)

    # An unavailable device may still be physically on, so with the opposite
    # state unconfirmed nothing is turned on (same as batch control).
    if tripped or unavailable:
        return

    current_heater = _idle_heater_state.get("state") if heater_entity else None
    current_cooler = _idle_cooler_state.get("state") if cooler_entity else None

    # Asymmetric hysteresis thresholds (same logic as control_batch_temperature)
    heat_on_threshold = round(target_temp - hysteresis, 1)
    heat_off_threshold = round(target_temp, 1)
    cool_on_threshold = round(target_temp + hysteresis, 1)
    cool_off_threshold = round(target_temp, 1)

    logger.debug(
        f"Chamber idle: chamber={chamber_temp:.1f}C, target={target_temp:.1f}C, "
        f"hysteresis={hysteresis:.1f}C, heater={current_heater}, cooler={current_cooler}"
    )

    async def _set_idle_heater(state: str) -> bool:
        return await _idle_set("heater", heater_entity, state)

    async def _set_idle_cooler(state: str) -> bool:
        return await _idle_set("cooler", cooler_entity, state)

    # Control logic with mutual exclusion (same pattern as control_batch_temperature)
    if chamber_temp <= heat_on_threshold:
        # Need heating - FIRST ensure cooler is OFF
        if cooler_entity and current_cooler == "on":
            logger.info("Chamber idle: Turning cooler OFF (heater needs to run)")
            if await _set_idle_cooler("off"):
                current_cooler = "off"

        # THEN turn heater ON, only if cooler is confirmed off
        if heater_entity and current_heater != "on":
            if cooler_entity and current_cooler != "off":
                logger.warning("Chamber idle: heater ON withheld - cooler not confirmed off")
            else:
                logger.info(f"Chamber idle: Chamber temp {chamber_temp:.1f}C at/below threshold {heat_on_threshold:.1f}C, turning heater ON")
                await _set_idle_heater("on")

    elif chamber_temp >= cool_on_threshold:
        # Need cooling - FIRST ensure heater is OFF
        if heater_entity and current_heater == "on":
            logger.info("Chamber idle: Turning heater OFF (cooler needs to run)")
            if await _set_idle_heater("off"):
                current_heater = "off"

        # THEN turn cooler ON, only if heater is confirmed off
        if cooler_entity and current_cooler != "on":
            if heater_entity and current_heater != "off":
                logger.warning("Chamber idle: cooler ON withheld - heater not confirmed off")
            else:
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

                # Control each batch sequentially (shared DB session, shared per-entity state)
                if batches:
                    await run_control_cycle(
                        router, db, batches, global_target, global_hysteresis, ambient_temp
                    )

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

    # Overrides are mutually exclusive: an 'on' replaces an 'on' on the opposite device
    if state == "on":
        other = "cooler" if device_type == "heater" else "heater"
        if _batch_overrides[batch_id].get(other, {}).get("state") == "on":
            logger.warning(f"Batch {batch_id}: {other} 'on' override cleared because {device_type} 'on' was requested")
            del _batch_overrides[batch_id][other]

    _batch_overrides[batch_id][device_type] = {
        "state": state,
        "until": _now() + timedelta(minutes=duration_minutes) if duration_minutes > 0 else None,
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


async def manual_switch(
    router: DeviceControlRouter,
    db,
    entity_id: str,
    kind: str,
    state: str,
    batch_id: Optional[int] = None,
) -> tuple[bool, str]:
    """Manual on/off through the controller's safe switching (tilt_ui-xrq5.1).

    'off' always goes through. 'on' respects the min-cycle, max-on lockout and
    failure back-off, and only happens once every opposite device paired with
    this one on a live batch is confirmed off.
    """
    if state == "off":
        ok = await _set_entity_state(router, db, entity_id, kind, "off", force=True)
        return ok, "turned off" if ok else "command failed"

    q = select(Batch).where(
        Batch.deleted_at.is_(None),
        (Batch.heater_entity_id == entity_id) | (Batch.cooler_entity_id == entity_id),
    )
    if batch_id is not None:
        q = select(Batch).where(Batch.id == batch_id)
    opposites = set()
    for b in (await db.execute(q)).scalars():
        if b.status not in ("fermenting", "conditioning", "planning", "brewing") and batch_id is None:
            continue
        other = b.cooler_entity_id if kind == "heater" else b.heater_entity_id
        if other and other != entity_id:
            opposites.add(other)
    for other in opposites:
        if await _read_state(router, other) != "off":
            other_kind = "cooler" if kind == "heater" else "heater"
            if not await _set_entity_state(router, db, other, other_kind, "off", force=True) \
                    or await _read_state(router, other) != "off":
                return False, f"refused: opposite device {other} is not confirmed off"
    ok = await _set_entity_state(router, db, entity_id, kind, "on", force=False)
    return ok, "turned on" if ok else "refused: minimum cycle time, max-on lockout or a recent failed command"


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
