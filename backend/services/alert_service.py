"""
Alert detection service for fermentation monitoring.

This service:
- Detects alert conditions (temperature out of range, anomalies, stalled fermentation)
- Persists alerts to the database with proper lifecycle tracking
- Updates existing alerts when conditions persist
- Clears alerts when conditions resolve
"""
import json
import logging
from datetime import datetime, timezone
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


# Stall rule thresholds (tilt_ui-zbhm; tuned on synthetic curves, re-tune on real batches)
STALL_MAX_SLOPE = 2.5e-5  # SG/hour, i.e. 0.6 gravity points/day
STALL_MIN_DROP = 0.004  # must have fermented 4 points first
STALL_FG_MARGIN = 0.004  # and still be 4 points above expected FG


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

    Returns:
        List of active alerts for this batch
    """
    now = datetime.now(timezone.utc)
    current_alerts: list[FermentationAlert] = []

    # Get current temperature
    current_temp = live_reading.get("temp") if live_reading else None

    # --- Temperature Alerts ---
    if current_temp is not None and yeast_temp_min is not None and yeast_temp_max is not None:
        if current_temp < yeast_temp_min:
            # Temperature too low
            deviation = round(yeast_temp_min - current_temp, 1)
            alert = await _upsert_alert(
                db=db,
                batch_id=batch_id,
                device_id=device_id,
                alert_type=AlertType.TEMPERATURE_LOW,
                severity=AlertSeverity.WARNING,
                message=f"Temperature is {deviation}°C below yeast minimum ({yeast_temp_min}°C)",
                context=json.dumps({
                    "current_temp": current_temp,
                    "yeast_temp_min": yeast_temp_min,
                    "yeast_temp_max": yeast_temp_max,
                    "deviation": deviation,
                }),
                trigger_reading_id=reading.id,
                now=now,
            )
            current_alerts.append(alert)
            # Clear high temp alert if it exists
            await _clear_alert(db, batch_id, AlertType.TEMPERATURE_HIGH, now)

        elif current_temp > yeast_temp_max:
            # Temperature too high
            deviation = round(current_temp - yeast_temp_max, 1)
            alert = await _upsert_alert(
                db=db,
                batch_id=batch_id,
                device_id=device_id,
                alert_type=AlertType.TEMPERATURE_HIGH,
                severity=AlertSeverity.WARNING,
                message=f"Temperature is {deviation}°C above yeast maximum ({yeast_temp_max}°C)",
                context=json.dumps({
                    "current_temp": current_temp,
                    "yeast_temp_min": yeast_temp_min,
                    "yeast_temp_max": yeast_temp_max,
                    "deviation": deviation,
                }),
                trigger_reading_id=reading.id,
                now=now,
            )
            current_alerts.append(alert)
            # Clear low temp alert if it exists
            await _clear_alert(db, batch_id, AlertType.TEMPERATURE_LOW, now)

        else:
            # Temperature in range - clear both temperature alerts
            await _clear_alert(db, batch_id, AlertType.TEMPERATURE_HIGH, now)
            await _clear_alert(db, batch_id, AlertType.TEMPERATURE_LOW, now)

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
