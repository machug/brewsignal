"""
Alert detection service for fermentation monitoring.

This service:
- Detects alert conditions (temperature out of range or running away, anomalies,
  stalled fermentation, low battery, sensor offline)
- Persists alerts to the database with proper lifecycle tracking
- Updates existing alerts when conditions persist
- Clears alerts when conditions resolve
"""
import asyncio
import json
import logging
import statistics
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Batch, FermentationAlert, Reading, Recipe

logger = logging.getLogger(__name__)


class AlertType:
    """Alert type constants."""
    TEMPERATURE_HIGH = "temperature_high"
    TEMPERATURE_LOW = "temperature_low"
    ANOMALY = "anomaly"
    STALL = "stall"
    # Temperature-controller safety alerts (tilt_ui-f50x, tilt_ui-8d49)
    SENSOR_STALE = "sensor_stale"
    MAX_ON_EXCEEDED = "max_on_exceeded"
    EQUIPMENT_CONFLICT = "equipment_conflict"
    # Informational: the automatic diacetyl rest rule changed the target (tilt_ui-ml8e)
    REST_STARTED = "rest_started"
    # Warning: the rule is on but has no OG/FG to work out its trigger
    REST_BLOCKED = "rest_blocked"
    # Sensing alerts (tilt_ui-lgtu)
    SENSOR_OFFLINE = "sensor_offline"
    BATTERY_LOW = "battery_low"
    TEMP_RUNAWAY = "temp_runaway"


# Stall rule thresholds (tilt_ui-zbhm; tuned on synthetic curves, re-tune on real batches)
STALL_MAX_SLOPE = 2.5e-5  # SG/hour, i.e. 0.6 gravity points/day
STALL_MIN_DROP = 0.004  # must have fermented 4 points first
STALL_FG_MARGIN = 0.004  # and still be 4 points above expected FG

# Sensing alert thresholds (tilt_ui-lgtu; from sensing-anomaly.md, not yet
# exercised on a real batch - re-tune with tilt_ui-xrq5.7)
TEMP_DEBOUNCE = timedelta(minutes=30)  # out of yeast range this long before alerting
RUNAWAY_MARGIN_C = 2.0  # above target by more than this...
RUNAWAY_RATE_C_PER_H = 1.5  # ...and rising at least this fast over RUNAWAY_WINDOW
RUNAWAY_WINDOW = timedelta(minutes=30)
BATTERY_LOW_PCT = 20  # raise below this
BATTERY_OK_PCT = 25  # clear at or above this (gap stops flapping)
OFFLINE_MIN = timedelta(minutes=30)  # offline = no stored reading for
OFFLINE_INTERVALS = 6  # max(OFFLINE_MIN, this many median report intervals)
OFFLINE_CHECK_SECONDS = 300

# When each (batch, temperature alert type) first went out of range. In memory
# only: a restart just restarts the 30 min wait.
_temp_out_since: dict[tuple[int, str], datetime] = {}


def _naive_utc(dt: datetime) -> datetime:
    """SQLite returns naive UTC, Postgres aware; compare everything as naive UTC."""
    return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt


class AlertSeverity:
    """Alert severity constants."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


async def get_alert_context(
    session,
    batch_id: int,
    current_sg: Optional[float],
) -> dict:
    """Get context needed for alert detection (yeast temp range, progress)."""
    from sqlalchemy.orm import selectinload

    context = {
        "yeast_temp_min": None,
        "yeast_temp_max": None,
        "progress_percent": None,
        "og": None,
        "fg": None,
        "temp_target": None,
    }

    # Fetch batch with recipe and yeast eagerly loaded
    stmt = (
        select(Batch)
        .where(Batch.id == batch_id)
        .options(
            selectinload(Batch.recipe).selectinload(Recipe.cultures),
            selectinload(Batch.yeast_strain),
        )
    )
    result = await session.execute(stmt)
    batch = result.scalar_one_or_none()

    if not batch:
        return context

    # Get yeast temperature range (prefer batch override, then recipe yeast)
    if batch.yeast_strain:
        context["yeast_temp_min"] = batch.yeast_strain.temp_low
        context["yeast_temp_max"] = batch.yeast_strain.temp_high
    elif batch.recipe:
        culture = next(
            (c for c in batch.recipe.cultures if c.temp_min_c is not None or c.temp_max_c is not None),
            None,
        )
        if culture:
            context["yeast_temp_min"] = culture.temp_min_c
            context["yeast_temp_max"] = culture.temp_max_c

    # Target for the runaway rule: the batch override, else the global target
    # when this batch is under temperature control.
    context["temp_target"] = batch.temp_target
    if batch.temp_target is None and (batch.heater_entity_id or batch.cooler_entity_id):
        from backend.routers.config import get_config_value
        context["temp_target"] = await get_config_value(session, "temp_target")

    # Calculate progress if we have OG and current SG
    og = batch.measured_og or (batch.recipe.og if batch.recipe else None)
    fg = batch.recipe.fg if batch.recipe else None
    context["og"] = og
    context["fg"] = fg

    if og and fg and current_sg:
        expected_drop = og - fg
        if expected_drop > 0:
            actual_drop = og - current_sg
            progress = (actual_drop / expected_drop) * 100
            context["progress_percent"] = min(max(progress, 0), 100)

    return context


async def detect_and_persist_alerts(
    db: AsyncSession,
    batch_id: int,
    device_id: str,
    reading: Reading,
    live_reading: dict,
    yeast_temp_min: Optional[float] = None,
    yeast_temp_max: Optional[float] = None,
    progress_percent: Optional[float] = None,
    og: Optional[float] = None,
    fg: Optional[float] = None,
    temp_target: Optional[float] = None,
    now: Optional[datetime] = None,
) -> list[FermentationAlert]:
    """
    Detect alert conditions and persist to database.

    Args:
        db: Database session
        batch_id: The batch ID
        device_id: The device ID
        reading: The Reading ORM object that was just saved
        live_reading: The live reading dict with ML data
        yeast_temp_min: Minimum yeast temperature tolerance (Celsius)
        yeast_temp_max: Maximum yeast temperature tolerance (Celsius)
        progress_percent: Fermentation progress percentage (0-100)
        og: Batch OG (measured, else recipe) for the stall rule
        fg: Expected FG (recipe) for the stall rule
        temp_target: Control target (Celsius) for the runaway rule
        now: Clock override for tests

    Returns:
        List of active alerts for this batch
    """
    now = now or datetime.now(timezone.utc)
    current_alerts: list[FermentationAlert] = []

    # A reading arrived, so the sensor is not offline.
    await _clear_alert(db, batch_id, AlertType.SENSOR_OFFLINE, now)

    # Get current temperature
    current_temp = live_reading.get("temp") if live_reading else None

    # --- Temperature Alerts ---
    # Each side of the yeast range is judged alone (a strain may list only one
    # limit). The alert is raised only after the wort has been out of range
    # for TEMP_DEBOUNCE, so one odd reading or a brief swing does not alert.
    if current_temp is not None:
        sides = (
            (AlertType.TEMPERATURE_LOW, yeast_temp_min, "below", "minimum",
             yeast_temp_min is not None and current_temp < yeast_temp_min),
            (AlertType.TEMPERATURE_HIGH, yeast_temp_max, "above", "maximum",
             yeast_temp_max is not None and current_temp > yeast_temp_max),
        )
        for alert_type, limit, direction, limit_name, out_of_range in sides:
            key = (batch_id, alert_type)
            if not out_of_range:
                _temp_out_since.pop(key, None)
                await _clear_alert(db, batch_id, alert_type, now)
                continue
            if now - _temp_out_since.setdefault(key, now) < TEMP_DEBOUNCE:
                continue
            deviation = round(abs(current_temp - limit), 1)
            current_alerts.append(await _upsert_alert(
                db=db,
                batch_id=batch_id,
                device_id=device_id,
                alert_type=alert_type,
                severity=AlertSeverity.WARNING,
                message=f"Temperature is {deviation}°C {direction} yeast {limit_name} ({limit}°C)",
                context=json.dumps({
                    "current_temp": current_temp,
                    "yeast_temp_min": yeast_temp_min,
                    "yeast_temp_max": yeast_temp_max,
                    "deviation": deviation,
                }),
                trigger_reading_id=reading.id,
                now=now,
            ))

    # --- Temperature Runaway (tilt_ui-lgtu) ---
    # Well above target AND still climbing fast. Needs no yeast range. The
    # "climbing" test keeps a cold crash quiet (far above target, but falling).
    # Once raised it stays until the wort is back near target.
    if current_temp is not None and temp_target is not None:
        if current_temp <= temp_target + RUNAWAY_MARGIN_C:
            await _clear_alert(db, batch_id, AlertType.TEMP_RUNAWAY, now)
        else:
            ref = _naive_utc(now)
            past = (await db.execute(
                select(Reading.temp_calibrated, Reading.timestamp)
                .where(
                    Reading.batch_id == batch_id,
                    Reading.temp_calibrated.is_not(None),
                    Reading.timestamp <= ref - RUNAWAY_WINDOW,
                    Reading.timestamp >= ref - 2 * RUNAWAY_WINDOW,
                )
                .order_by(Reading.timestamp.desc())
                .limit(1)
            )).first()
            if past:
                hours = (ref - _naive_utc(past.timestamp)).total_seconds() / 3600
                rate = (current_temp - past.temp_calibrated) / hours
                if rate >= RUNAWAY_RATE_C_PER_H:
                    current_alerts.append(await _upsert_alert(
                        db=db,
                        batch_id=batch_id,
                        device_id=device_id,
                        alert_type=AlertType.TEMP_RUNAWAY,
                        severity=AlertSeverity.CRITICAL,
                        message=(
                            f"Temperature is {current_temp - temp_target:.1f}°C above target "
                            f"({temp_target}°C) and rising {rate:.1f}°C/hour"
                        ),
                        context=json.dumps({
                            "current_temp": current_temp,
                            "temp_target": temp_target,
                            "rate_c_per_hour": round(rate, 2),
                        }),
                        trigger_reading_id=reading.id,
                        now=now,
                    ))

    # --- Battery Alerts (tilt_ui-lgtu) ---
    # Only devices that report a battery level (RAPT, iSpindel, GravityMon).
    battery = live_reading.get("battery_percent") if live_reading else None
    if battery is not None:
        if battery < BATTERY_LOW_PCT:
            current_alerts.append(await _upsert_alert(
                db=db,
                batch_id=batch_id,
                device_id=device_id,
                alert_type=AlertType.BATTERY_LOW,
                severity=AlertSeverity.WARNING,
                message=f"Hydrometer battery is low ({battery:.0f}%)",
                context=json.dumps({"battery_percent": battery}),
                trigger_reading_id=reading.id,
                now=now,
            ))
        elif battery >= BATTERY_OK_PCT:
            await _clear_alert(db, batch_id, AlertType.BATTERY_LOW, now)

    # --- Anomaly Alerts (step change) ---
    # The detector flags a level shift once per event (tilt_ui-zbhm), so the
    # alert must NOT clear on the next normal reading or nobody would see it.
    # It stays until dismissed; a later step updates the same alert.
    if live_reading and live_reading.get("is_anomaly"):
        reasons = live_reading.get("anomaly_reasons") or []
        if "step_change_up" in reasons:
            message = "Gravity jumped up suddenly - dry hop, or the hydrometer was moved?"
        elif "step_change_down" in reasons:
            message = "Gravity dropped suddenly - was the hydrometer lifted or moved?"
        else:
            message = f"Anomaly detected: {reasons or 'unknown reason'}"
        alert = await _upsert_alert(
            db=db,
            batch_id=batch_id,
            device_id=device_id,
            alert_type=AlertType.ANOMALY,
            severity=AlertSeverity.WARNING,
            message=message,
            context=json.dumps({
                "anomaly_score": live_reading.get("anomaly_score"),
                "anomaly_reasons": reasons,
                "sg": live_reading.get("sg"),
                "temp": live_reading.get("temp"),
            }),
            trigger_reading_id=reading.id,
            now=now,
        )
        current_alerts.append(alert)

    # --- Stall Alerts (tilt_ui-zbhm) ---
    # Stalled = the trailing 12 h slope is flatter than 0.6 pt/day, AFTER the
    # beer has dropped at least 4 pt from OG (so lag phase never counts), and
    # it is still more than 4 pt above the expected FG. Without an FG the
    # alert is only INFO. Without OG or a full 12 h window: no judgement.
    slope_12h = live_reading.get("sg_slope_12h") if live_reading else None
    current_sg = live_reading.get("sg") if live_reading else None
    stalled = (
        slope_12h is not None
        and og is not None
        and current_sg is not None
        and slope_12h > -STALL_MAX_SLOPE
        and og - current_sg >= STALL_MIN_DROP
        and (fg is None or current_sg - fg > STALL_FG_MARGIN)
    )
    if stalled:
        alert = await _upsert_alert(
            db=db,
            batch_id=batch_id,
            device_id=device_id,
            alert_type=AlertType.STALL,
            severity=AlertSeverity.WARNING if fg is not None else AlertSeverity.INFO,
            message="Fermentation appears stalled - gravity has barely moved in 12 hours",
            context=json.dumps({
                "sg_slope_12h": slope_12h,
                "points_per_day": round(-slope_12h * 24 * 1000, 2),
                "og": og,
                "expected_fg": fg,
                "progress_percent": progress_percent,
                "sg": current_sg,
            }),
            trigger_reading_id=reading.id,
            now=now,
        )
        current_alerts.append(alert)
    else:
        await _clear_alert(db, batch_id, AlertType.STALL, now)

    return current_alerts


async def _upsert_alert(
    db: AsyncSession,
    batch_id: int,
    device_id: str,
    alert_type: str,
    severity: str,
    message: str,
    context: Optional[str],
    trigger_reading_id: Optional[int],
    now: datetime,
) -> FermentationAlert:
    """
    Create a new alert or update an existing active alert.

    If an active alert of this type exists for this batch, update its last_seen_at.
    Otherwise, create a new alert.
    """
    # Look for existing active alert of this type
    stmt = select(FermentationAlert).where(
        FermentationAlert.batch_id == batch_id,
        FermentationAlert.alert_type == alert_type,
        FermentationAlert.cleared_at.is_(None),
    )
    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing:
        # Update existing alert
        existing.last_seen_at = now
        existing.message = message  # Update message with latest values
        existing.context = context
        existing.trigger_reading_id = trigger_reading_id
        logger.debug(f"Updated existing {alert_type} alert for batch {batch_id}")
        return existing
    else:
        # Create new alert
        alert = FermentationAlert(
            batch_id=batch_id,
            device_id=device_id,
            alert_type=alert_type,
            severity=severity,
            message=message,
            context=context,
            trigger_reading_id=trigger_reading_id,
            first_detected_at=now,
            last_seen_at=now,
        )
        db.add(alert)
        logger.info(f"Created new {alert_type} alert for batch {batch_id}: {message}")
        return alert


async def _clear_alert(
    db: AsyncSession,
    batch_id: int,
    alert_type: str,
    now: datetime,
) -> bool:
    """
    Clear an active alert of the given type.

    Returns True if an alert was cleared, False if no active alert existed.
    """
    stmt = select(FermentationAlert).where(
        FermentationAlert.batch_id == batch_id,
        FermentationAlert.alert_type == alert_type,
        FermentationAlert.cleared_at.is_(None),
    )
    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing:
        existing.cleared_at = now
        logger.info(f"Cleared {alert_type} alert for batch {batch_id}")
        return True
    return False


async def check_offline_sensors(db: AsyncSession, now: Optional[datetime] = None) -> int:
    """Raise/clear sensor_offline for every active batch with a device (tilt_ui-lgtu).

    Offline = no stored reading for max(OFFLINE_MIN, OFFLINE_INTERVALS x the
    device's median report interval). Must run on a timer: the ingest path
    cannot notice a reading that never came. A batch with no readings at all
    gets no judgement. Returns how many batches are offline.
    """
    now = now or datetime.now(timezone.utc)
    ref = _naive_utc(now)
    batches = (await db.execute(
        select(Batch.id, Batch.device_id).where(
            Batch.status.in_(("fermenting", "conditioning")),
            Batch.deleted_at.is_(None),
            Batch.device_id.is_not(None),
        )
    )).all()
    offline = 0
    for batch_id, device_id in batches:
        stamps = [_naive_utc(t) for t in (await db.execute(
            select(Reading.timestamp)
            .where(Reading.batch_id == batch_id)
            .order_by(Reading.timestamp.desc())
            .limit(21)
        )).scalars().all()]
        if not stamps:
            continue
        limit = OFFLINE_MIN
        if len(stamps) >= 3:
            gaps = [a - b for a, b in zip(stamps, stamps[1:])]
            limit = max(limit, OFFLINE_INTERVALS * statistics.median(gaps))
        age = ref - stamps[0]
        # The temperature controller already raises a critical sensor_stale
        # alert for batches it controls; do not double up.
        stale = (await db.execute(
            select(FermentationAlert.id).where(
                FermentationAlert.batch_id == batch_id,
                FermentationAlert.alert_type == AlertType.SENSOR_STALE,
                FermentationAlert.cleared_at.is_(None),
            ).limit(1)
        )).first()
        if age > limit and not stale:
            offline += 1
            await _upsert_alert(
                db=db,
                batch_id=batch_id,
                device_id=device_id,
                alert_type=AlertType.SENSOR_OFFLINE,
                severity=AlertSeverity.WARNING,
                message=f"No reading from the hydrometer for {_format_age(age)}",
                context=json.dumps({
                    "last_reading_at": stamps[0].isoformat() + "Z",
                    "limit_minutes": round(limit.total_seconds() / 60),
                }),
                trigger_reading_id=None,
                now=now,
            )
        else:
            await _clear_alert(db, batch_id, AlertType.SENSOR_OFFLINE, now)
    await db.commit()
    return offline


def _format_age(age: timedelta) -> str:
    minutes = int(age.total_seconds() // 60)
    return f"{minutes} minutes" if minutes < 120 else f"{minutes // 60} hours"


async def offline_watch_loop(session_factory, interval_seconds: float = OFFLINE_CHECK_SECONDS) -> None:
    """Run check_offline_sensors forever. Sleeps first so the scanner can report after startup."""
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            async with session_factory() as db:
                await check_offline_sensors(db)
        except Exception:
            logger.exception("Offline sensor check failed")


async def get_active_alerts(
    db: AsyncSession,
    batch_id: int,
) -> list[FermentationAlert]:
    """Get all active (non-cleared) alerts for a batch."""
    stmt = (
        select(FermentationAlert)
        .where(
            FermentationAlert.batch_id == batch_id,
            FermentationAlert.cleared_at.is_(None),
        )
        .order_by(FermentationAlert.first_detected_at.desc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_alert_history(
    db: AsyncSession,
    batch_id: int,
    include_cleared: bool = True,
    limit: int = 50,
) -> list[FermentationAlert]:
    """Get alert history for a batch."""
    stmt = (
        select(FermentationAlert)
        .where(FermentationAlert.batch_id == batch_id)
    )
    if not include_cleared:
        stmt = stmt.where(FermentationAlert.cleared_at.is_(None))

    stmt = stmt.order_by(FermentationAlert.first_detected_at.desc()).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())
