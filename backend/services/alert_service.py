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


class AlertSeverity:
    """Alert severity constants."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


async def detect_and_persist_alerts(
    db: AsyncSession,
    batch_id: int,
    device_id: str,
    reading: Reading,
    live_reading: dict,
    yeast_temp_min: Optional[float] = None,
    yeast_temp_max: Optional[float] = None,
    progress_percent: Optional[float] = None,
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

    Returns:
        List of active alerts for this batch
    """
    now = datetime.now(timezone.utc)
    current_alerts: list[FermentationAlert] = []

    # Get current temperature
    current_temp = live_reading.get("temp") if live_reading else None
    sg_rate = live_reading.get("sg_rate") if live_reading else None

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

    # --- Anomaly Alerts ---
    if live_reading and live_reading.get("is_anomaly"):
        anomaly_reasons = live_reading.get("anomaly_reasons", "unknown reason")
        alert = await _upsert_alert(
            db=db,
            batch_id=batch_id,
            device_id=device_id,
            alert_type=AlertType.ANOMALY,
            severity=AlertSeverity.INFO,
            message=f"Anomaly detected: {anomaly_reasons}",
            context=json.dumps({
                "anomaly_score": live_reading.get("anomaly_score"),
                "anomaly_reasons": anomaly_reasons,
                "sg": live_reading.get("sg"),
                "temp": live_reading.get("temp"),
            }),
            trigger_reading_id=reading.id,
            now=now,
        )
        current_alerts.append(alert)
    else:
        # No anomaly - clear alert if one exists
        await _clear_alert(db, batch_id, AlertType.ANOMALY, now)

    # --- Stall Alerts ---
    # Only check for stall if we have sg_rate and fermentation isn't near completion
    if sg_rate is not None and progress_percent is not None:
        if abs(sg_rate) < 0.0001 and progress_percent < 90:
            alert = await _upsert_alert(
                db=db,
                batch_id=batch_id,
                device_id=device_id,
                alert_type=AlertType.STALL,
                severity=AlertSeverity.WARNING,
                message="Fermentation appears stalled - gravity not changing",
                context=json.dumps({
                    "sg_rate": sg_rate,
                    "progress_percent": progress_percent,
                    "sg": live_reading.get("sg") if live_reading else None,
                }),
                trigger_reading_id=reading.id,
                now=now,
            )
            current_alerts.append(alert)
        else:
            # Fermentation active or near completion - clear stall alert
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
