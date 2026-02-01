"""Fermentation monitoring tools for the AI brewing assistant."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.config import get_settings
from backend.models import (
    Batch, Reading, Device, Recipe, YeastStrain, AmbientReading, RecipeCulture
)
from backend.services.alert_service import get_active_alerts
from backend.state import latest_readings

logger = logging.getLogger(__name__)


def _user_owns_batch_condition(user_id: Optional[str]):
    """Create a SQLAlchemy condition for batch ownership.

    In LOCAL mode: includes user's batches + "local" user + unclaimed (NULL)
    In CLOUD mode: strict user_id filtering
    """
    settings = get_settings()
    if settings.is_local:
        return or_(
            Batch.user_id == user_id,
            Batch.user_id == "local",
            Batch.user_id.is_(None),
        )
    return Batch.user_id == user_id


async def list_fermentations(
    db: AsyncSession,
    user_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 10
) -> dict[str, Any]:
    """List fermentation batches with current progress."""
    # Build query with eager loading
    stmt = (
        select(Batch)
        .options(
            selectinload(Batch.recipe).selectinload(Recipe.style),
            selectinload(Batch.recipe).selectinload(Recipe.cultures),
            selectinload(Batch.device),
            selectinload(Batch.yeast_strain),
        )
        .where(Batch.deleted_at.is_(None))  # Exclude deleted
    )

    # Filter by user ownership
    if user_id:
        stmt = stmt.where(_user_owns_batch_condition(user_id))

    # Filter by status
    if status and status != "all":
        stmt = stmt.where(Batch.status == status)

    # Order by most recently active
    stmt = stmt.order_by(Batch.updated_at.desc()).limit(limit)

    result = await db.execute(stmt)
    batches = result.scalars().all()

    if not batches:
        return {
            "count": 0,
            "message": "No fermentation batches found",
            "batches": []
        }

    now = datetime.now(timezone.utc)
    batch_list = []

    for batch in batches:
        # Get live reading if available
        live_reading = latest_readings.get(batch.device_id) if batch.device_id else None

        # Calculate days fermenting
        days_fermenting = None
        if batch.start_time:
            start = batch.start_time.replace(tzinfo=timezone.utc) if batch.start_time.tzinfo is None else batch.start_time
            delta = now - start
            days_fermenting = round(delta.total_seconds() / 86400, 1)

        # Calculate progress
        progress_percent = None
        current_sg = live_reading.get("sg") if live_reading else None
        if batch.measured_og and current_sg:
            target_fg = batch.recipe.fg if batch.recipe and batch.recipe.fg else 1.010
            if batch.measured_og > target_fg:
                progress = (batch.measured_og - current_sg) / (batch.measured_og - target_fg) * 100
                progress_percent = min(100.0, max(0.0, round(progress, 1)))

        # Get yeast info
        yeast_name = None
        temp_min = None
        temp_max = None
        if batch.yeast_strain:
            yeast_name = batch.yeast_strain.name
            temp_min = batch.yeast_strain.temp_low
            temp_max = batch.yeast_strain.temp_high
        elif batch.recipe and batch.recipe.cultures:
            culture = batch.recipe.cultures[0]
            yeast_name = culture.name
            temp_min = culture.temp_min_c
            temp_max = culture.temp_max_c
        elif batch.recipe and batch.recipe.yeast_name:
            # Fallback to yeast fields stored directly on Recipe
            yeast_name = batch.recipe.yeast_name
            temp_min = batch.recipe.yeast_temp_min
            temp_max = batch.recipe.yeast_temp_max

        # Temperature status
        current_temp = live_reading.get("temp") if live_reading else None
        temp_status = "unknown"
        if current_temp is not None and temp_min is not None and temp_max is not None:
            if current_temp < temp_min:
                temp_status = "too_cold"
            elif current_temp > temp_max:
                temp_status = "too_warm"
            else:
                temp_status = "in_range"

        batch_list.append({
            "batch_id": batch.id,
            "name": batch.name or (batch.recipe.name if batch.recipe else f"Batch #{batch.id}"),
            "recipe_name": batch.recipe.name if batch.recipe else None,
            "style": batch.recipe.style.name if batch.recipe and batch.recipe.style else None,
            "status": batch.status,
            "device_id": batch.device_id,
            "days_fermenting": days_fermenting,
            "current_sg": current_sg,
            "current_temp_c": current_temp,
            "measured_og": batch.measured_og,
            "target_fg": batch.recipe.fg if batch.recipe else None,
            "progress_percent": progress_percent,
            "yeast_name": yeast_name,
            "temp_status": temp_status,
        })

    return {
        "count": len(batch_list),
        "batches": batch_list
    }


async def get_fermentation_status(
    db: AsyncSession,
    batch_id: int,
    user_id: Optional[str] = None,
) -> dict[str, Any]:
    """Get comprehensive status for a specific fermentation batch."""
    # Query batch with all relationships and ownership check
    stmt = (
        select(Batch)
        .options(
            selectinload(Batch.recipe).selectinload(Recipe.style),
            selectinload(Batch.recipe).selectinload(Recipe.cultures),
            selectinload(Batch.device),
            selectinload(Batch.yeast_strain),
        )
        .where(Batch.id == batch_id)
    )

    # Filter by user ownership
    if user_id:
        stmt = stmt.where(_user_owns_batch_condition(user_id))

    result = await db.execute(stmt)
    batch = result.scalar_one_or_none()

    if not batch:
        return {"error": f"Batch not found: {batch_id}"}

    now = datetime.now(timezone.utc)

    # Get live reading
    live_reading = latest_readings.get(batch.device_id) if batch.device_id else None
    current_sg = live_reading.get("sg") if live_reading else None
    current_temp = live_reading.get("temp") if live_reading else None
    reading_confidence = live_reading.get("confidence") if live_reading else None
    reading_time = live_reading.get("last_seen") if live_reading else None

    # Build batch info
    batch_info = {
        "id": batch.id,
        "name": batch.name or (batch.recipe.name if batch.recipe else f"Batch #{batch.id}"),
        "status": batch.status,
        "brew_date": batch.brew_date.isoformat() if batch.brew_date else None,
        "start_time": batch.start_time.isoformat() if batch.start_time else None,
        "measured_og": batch.measured_og,
        "measured_fg": batch.measured_fg,
        "notes": batch.notes,
    }

    # Build recipe info
    recipe_info = None
    if batch.recipe:
        recipe_info = {
            "name": batch.recipe.name,
            "style": batch.recipe.style.name if batch.recipe.style else None,
            "target_og": batch.recipe.og,
            "target_fg": batch.recipe.fg,
            "target_abv": batch.recipe.abv,
            "primary_temp_c": batch.recipe.primary_temp_c,
        }

    # Build device info
    device_info = None
    if batch.device:
        device_info = {
            "id": batch.device.id,
            "type": batch.device.device_type,
            "name": batch.device.display_name or batch.device.name,
            "battery_voltage": batch.device.battery_voltage,
        }

    # Current reading
    current_reading = None
    if live_reading:
        current_reading = {
            "sg": current_sg,
            "temp_c": current_temp,
            "confidence": reading_confidence,
            "timestamp": reading_time,
            "sg_rate": live_reading.get("sg_rate"),
            "temp_rate": live_reading.get("temp_rate"),
        }

    # Progress calculations
    progress_info = {"available": False}
    if batch.measured_og and current_sg:
        target_fg = batch.recipe.fg if batch.recipe and batch.recipe.fg else 1.010
        if batch.measured_og > target_fg:
            progress = (batch.measured_og - current_sg) / (batch.measured_og - target_fg) * 100
            progress_percent = min(100.0, max(0.0, round(progress, 1)))
            current_attenuation = (batch.measured_og - current_sg) / (batch.measured_og - 1.0) * 100

            progress_info = {
                "available": True,
                "percent_complete": progress_percent,
                "current_attenuation": round(current_attenuation, 1),
                "gravity_drop": round(batch.measured_og - current_sg, 4),
                "remaining_gravity": round(current_sg - target_fg, 4) if current_sg > target_fg else 0,
            }

    # Days fermenting
    if batch.start_time:
        start = batch.start_time.replace(tzinfo=timezone.utc) if batch.start_time.tzinfo is None else batch.start_time
        delta = now - start
        progress_info["days_fermenting"] = round(delta.total_seconds() / 86400, 1)

    # Temperature analysis
    temp_info = {"available": False}
    yeast_temp_min = None
    yeast_temp_max = None
    yeast_name = None

    if batch.yeast_strain:
        yeast_name = batch.yeast_strain.name
        yeast_temp_min = batch.yeast_strain.temp_low
        yeast_temp_max = batch.yeast_strain.temp_high
    elif batch.recipe and batch.recipe.cultures:
        culture = batch.recipe.cultures[0]
        yeast_name = culture.name
        yeast_temp_min = culture.temp_min_c
        yeast_temp_max = culture.temp_max_c
    elif batch.recipe and batch.recipe.yeast_name:
        # Fallback to yeast fields stored directly on Recipe
        yeast_name = batch.recipe.yeast_name
        yeast_temp_min = batch.recipe.yeast_temp_min
        yeast_temp_max = batch.recipe.yeast_temp_max

    if current_temp is not None:
        temp_info = {
            "available": True,
            "current_c": current_temp,
            "yeast_name": yeast_name,
            "yeast_min_c": yeast_temp_min,
            "yeast_max_c": yeast_temp_max,
            "target_c": batch.temp_target,
        }

        if yeast_temp_min is not None and yeast_temp_max is not None:
            if current_temp < yeast_temp_min:
                temp_info["status"] = "too_cold"
                temp_info["deviation_c"] = round(yeast_temp_min - current_temp, 1)
                temp_info["message"] = f"Temperature is {temp_info['deviation_c']}°C below yeast minimum"
            elif current_temp > yeast_temp_max:
                temp_info["status"] = "too_warm"
                temp_info["deviation_c"] = round(current_temp - yeast_temp_max, 1)
                temp_info["message"] = f"Temperature is {temp_info['deviation_c']}°C above yeast maximum"
            else:
                temp_info["status"] = "in_range"
                temp_info["message"] = "Temperature is within yeast tolerance"
        else:
            temp_info["status"] = "unknown"
            temp_info["message"] = "Yeast temperature range not specified"

    # ML predictions
    predictions = {"available": False}
    if batch.device_id:
        try:
            from backend.main import get_ml_manager
            ml_mgr = get_ml_manager()
            if ml_mgr:
                expected_fg = batch.recipe.fg if batch.recipe and batch.recipe.fg else None
                state = ml_mgr.get_device_state(batch.device_id, expected_fg=expected_fg)
                if state and state.get("predictions"):
                    pred = state["predictions"]
                    predictions = {
                        "available": True,
                        "predicted_fg": pred.get("predicted_fg"),
                        "hours_to_completion": pred.get("hours_to_completion"),
                        "confidence": pred.get("confidence"),
                    }
        except Exception as e:
            logger.warning(f"Failed to get ML predictions: {e}")

    # Fetch persistent alerts from database
    alerts = []
    try:
        active_alerts = await get_active_alerts(db, batch.id)
        for alert in active_alerts:
            alerts.append({
                "type": alert.alert_type,
                "severity": alert.severity,
                "message": alert.message,
                "first_detected_at": alert.first_detected_at.isoformat() if alert.first_detected_at else None,
                "last_seen_at": alert.last_seen_at.isoformat() if alert.last_seen_at else None,
            })
    except Exception as e:
        logger.warning(f"Failed to fetch alerts from database: {e}")
        # Fallback to ephemeral alerts if database fetch fails
        if temp_info.get("status") == "too_cold":
            alerts.append({
                "type": "temperature_low",
                "severity": "warning",
                "message": temp_info["message"],
                "first_detected_at": reading_time,
                "last_seen_at": reading_time,
            })
        elif temp_info.get("status") == "too_warm":
            alerts.append({
                "type": "temperature_high",
                "severity": "warning",
                "message": temp_info["message"],
                "first_detected_at": reading_time,
                "last_seen_at": reading_time,
            })
        if live_reading and live_reading.get("is_anomaly"):
            alerts.append({
                "type": "anomaly",
                "severity": "info",
                "message": f"Anomaly detected: {live_reading.get('anomaly_reasons', 'unknown reason')}",
                "first_detected_at": reading_time,
                "last_seen_at": reading_time,
            })

    return {
        "found": True,
        "batch": batch_info,
        "recipe": recipe_info,
        "device": device_info,
        "current_reading": current_reading,
        "progress": progress_info,
        "temperature": temp_info,
        "predictions": predictions,
        "alerts": alerts,
    }


async def get_fermentation_history(
    db: AsyncSession,
    batch_id: int,
    hours: int = 24,
    include_anomalies_only: bool = False,
    user_id: Optional[str] = None,
) -> dict[str, Any]:
    """Get historical readings for a batch with trend analysis."""
    # Validate hours
    hours = min(720, max(1, hours))  # 1 hour to 30 days

    # First verify batch exists and user owns it
    batch_stmt = (
        select(Batch)
        .options(selectinload(Batch.recipe))
        .where(Batch.id == batch_id)
    )
    if user_id:
        batch_stmt = batch_stmt.where(_user_owns_batch_condition(user_id))

    batch_result = await db.execute(batch_stmt)
    batch = batch_result.scalar_one_or_none()

    if not batch:
        return {"error": f"Batch not found: {batch_id}"}

    # Query readings
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    stmt = (
        select(Reading)
        .where(
            Reading.batch_id == batch_id,
            Reading.timestamp >= cutoff
        )
        .order_by(Reading.timestamp.asc())
    )

    if include_anomalies_only:
        stmt = stmt.where(Reading.is_anomaly == True)

    result = await db.execute(stmt)
    readings = result.scalars().all()

    if not readings:
        return {
            "batch_id": batch_id,
            "batch_name": batch.name or (batch.recipe.name if batch.recipe else f"Batch #{batch.id}"),
            "hours_requested": hours,
            "count": 0,
            "message": "No readings found in the specified time period",
            "readings": []
        }

    # Calculate summary statistics
    sg_values = [r.sg_calibrated or r.sg_raw for r in readings if (r.sg_calibrated or r.sg_raw)]
    temp_values = [r.temp_calibrated or r.temp_raw for r in readings if (r.temp_calibrated or r.temp_raw)]

    summary = {}
    if sg_values:
        summary["sg"] = {
            "min": round(min(sg_values), 4),
            "max": round(max(sg_values), 4),
            "start": round(sg_values[0], 4),
            "end": round(sg_values[-1], 4),
            "change": round(sg_values[-1] - sg_values[0], 4),
        }

    if temp_values:
        summary["temp_c"] = {
            "min": round(min(temp_values), 1),
            "max": round(max(temp_values), 1),
            "avg": round(sum(temp_values) / len(temp_values), 1),
        }

    # Calculate trend (simple linear regression approximation)
    trend_analysis = {}
    if len(sg_values) >= 2:
        # Points per hour rate
        time_span_hours = (readings[-1].timestamp - readings[0].timestamp).total_seconds() / 3600
        if time_span_hours > 0:
            sg_rate_per_hour = (sg_values[-1] - sg_values[0]) / time_span_hours
            trend_analysis["sg_rate_per_hour"] = round(sg_rate_per_hour, 6)

            if sg_rate_per_hour < -0.001:
                trend_analysis["sg_trend"] = "actively_fermenting"
            elif sg_rate_per_hour < -0.0001:
                trend_analysis["sg_trend"] = "slowly_fermenting"
            else:
                trend_analysis["sg_trend"] = "stable"

    if len(temp_values) >= 2:
        time_span_hours = (readings[-1].timestamp - readings[0].timestamp).total_seconds() / 3600
        if time_span_hours > 0:
            temp_rate = (temp_values[-1] - temp_values[0]) / time_span_hours
            trend_analysis["temp_rate_per_hour"] = round(temp_rate, 3)

            if temp_rate > 0.5:
                trend_analysis["temp_trend"] = "rising"
            elif temp_rate < -0.5:
                trend_analysis["temp_trend"] = "falling"
            else:
                trend_analysis["temp_trend"] = "stable"

    # Sample readings (downsample if too many)
    max_readings = 50
    sample_readings = []
    if len(readings) <= max_readings:
        sample_readings = readings
    else:
        # Evenly sample
        step = len(readings) / max_readings
        indices = [int(i * step) for i in range(max_readings)]
        sample_readings = [readings[i] for i in indices]

    readings_list = [
        {
            "timestamp": r.timestamp.isoformat(),
            "sg": r.sg_calibrated or r.sg_raw,
            "temp_c": r.temp_calibrated or r.temp_raw,
            "confidence": r.confidence,
            "is_anomaly": r.is_anomaly,
            "anomaly_reasons": r.anomaly_reasons,
        }
        for r in sample_readings
    ]

    return {
        "batch_id": batch_id,
        "batch_name": batch.name or (batch.recipe.name if batch.recipe else f"Batch #{batch.id}"),
        "hours_requested": hours,
        "time_range": {
            "start": readings[0].timestamp.isoformat(),
            "end": readings[-1].timestamp.isoformat(),
        },
        "count": len(readings),
        "summary": summary,
        "trend_analysis": trend_analysis,
        "readings": readings_list,
    }


async def get_ambient_conditions(db: AsyncSession) -> dict[str, Any]:
    """Get current ambient temperature and humidity."""
    # Get most recent ambient reading
    stmt = (
        select(AmbientReading)
        .order_by(AmbientReading.timestamp.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    ambient = result.scalar_one_or_none()

    now = datetime.now(timezone.utc)

    response = {
        "available": False,
        "message": "No ambient sensor data available"
    }

    if ambient:
        age_minutes = (now - ambient.timestamp).total_seconds() / 60
        response = {
            "available": True,
            "temperature_c": ambient.temperature,
            "humidity_percent": ambient.humidity,
            "timestamp": ambient.timestamp.isoformat(),
            "age_minutes": round(age_minutes, 1),
            "entity_id": ambient.entity_id,
        }

        if age_minutes > 30:
            response["warning"] = "Data may be stale (over 30 minutes old)"

    # Get active fermentations to compare
    batch_stmt = (
        select(Batch)
        .where(
            Batch.deleted_at.is_(None),
            Batch.status.in_(["fermenting", "conditioning"])
        )
    )
    batch_result = await db.execute(batch_stmt)
    active_batches = batch_result.scalars().all()

    if active_batches and response.get("available"):
        comparisons = []
        for batch in active_batches:
            if batch.device_id:
                live = latest_readings.get(batch.device_id)
                if live and live.get("temp") is not None:
                    delta = round(live["temp"] - response["temperature_c"], 1)
                    comparisons.append({
                        "batch_id": batch.id,
                        "batch_name": batch.name or f"Batch #{batch.id}",
                        "fermentation_temp_c": live["temp"],
                        "delta_from_ambient_c": delta,
                    })
        if comparisons:
            response["fermentation_comparisons"] = comparisons

    return response


async def compare_batches(
    db: AsyncSession,
    batch_id: int,
    comparison_type: Optional[str] = "recipe",
    limit: int = 5,
    user_id: Optional[str] = None,
) -> dict[str, Any]:
    """Find similar historical batches for comparison."""
    # Get reference batch with ownership check
    ref_stmt = (
        select(Batch)
        .options(
            selectinload(Batch.recipe).selectinload(Recipe.style),
            selectinload(Batch.recipe).selectinload(Recipe.cultures),
            selectinload(Batch.yeast_strain),
        )
        .where(Batch.id == batch_id)
    )
    if user_id:
        ref_stmt = ref_stmt.where(_user_owns_batch_condition(user_id))

    ref_result = await db.execute(ref_stmt)
    ref_batch = ref_result.scalar_one_or_none()

    if not ref_batch:
        return {"error": f"Batch not found: {batch_id}"}

    # Build filter based on comparison type - also filter by user ownership
    similar_stmt = (
        select(Batch)
        .options(
            selectinload(Batch.recipe).selectinload(Recipe.style),
            selectinload(Batch.yeast_strain),
        )
        .where(
            Batch.id != batch_id,
            Batch.deleted_at.is_(None),
            Batch.status.in_(["completed", "conditioning"])  # Only compare to finished batches
        )
    )
    if user_id:
        similar_stmt = similar_stmt.where(_user_owns_batch_condition(user_id))

    comparison_type = comparison_type or "recipe"

    if comparison_type == "recipe" and ref_batch.recipe_id:
        similar_stmt = similar_stmt.where(Batch.recipe_id == ref_batch.recipe_id)
    elif comparison_type == "style" and ref_batch.recipe and ref_batch.recipe.style_id:
        # Join through recipe to style
        similar_stmt = similar_stmt.join(Recipe).where(Recipe.style_id == ref_batch.recipe.style_id)
    elif comparison_type == "yeast":
        # Match by yeast strain or recipe culture
        if ref_batch.yeast_strain_id:
            similar_stmt = similar_stmt.where(Batch.yeast_strain_id == ref_batch.yeast_strain_id)
        elif ref_batch.recipe and ref_batch.recipe.cultures:
            yeast_name = ref_batch.recipe.cultures[0].name
            # This is trickier - need to match by culture name
            similar_stmt = (
                similar_stmt
                .join(Recipe)
                .join(RecipeCulture)
                .where(RecipeCulture.name.ilike(f"%{yeast_name}%"))
            )

    similar_stmt = similar_stmt.order_by(Batch.end_time.desc().nullsfirst()).limit(limit)

    similar_result = await db.execute(similar_stmt)
    similar_batches = similar_result.scalars().all()

    # Build reference batch info
    ref_info = {
        "batch_id": ref_batch.id,
        "name": ref_batch.name or (ref_batch.recipe.name if ref_batch.recipe else f"Batch #{ref_batch.id}"),
        "recipe_name": ref_batch.recipe.name if ref_batch.recipe else None,
        "style": ref_batch.recipe.style.name if ref_batch.recipe and ref_batch.recipe.style else None,
        "status": ref_batch.status,
        "measured_og": ref_batch.measured_og,
        "measured_fg": ref_batch.measured_fg,
        "measured_abv": ref_batch.measured_abv,
        "measured_attenuation": ref_batch.measured_attenuation,
    }

    # Build similar batches list
    similar_list = []
    for batch in similar_batches:
        fermentation_days = None
        if batch.start_time and batch.end_time:
            fermentation_days = round((batch.end_time - batch.start_time).total_seconds() / 86400, 1)

        similar_list.append({
            "batch_id": batch.id,
            "name": batch.name or (batch.recipe.name if batch.recipe else f"Batch #{batch.id}"),
            "recipe_name": batch.recipe.name if batch.recipe else None,
            "style": batch.recipe.style.name if batch.recipe and batch.recipe.style else None,
            "brew_date": batch.brew_date.isoformat() if batch.brew_date else None,
            "measured_og": batch.measured_og,
            "measured_fg": batch.measured_fg,
            "measured_abv": batch.measured_abv,
            "measured_attenuation": batch.measured_attenuation,
            "fermentation_days": fermentation_days,
        })

    # Generate comparison insights
    insights = []
    if similar_list:
        # Compare OG/FG
        if ref_batch.measured_og:
            avg_og = sum(b["measured_og"] for b in similar_list if b["measured_og"]) / len([b for b in similar_list if b["measured_og"]]) if any(b["measured_og"] for b in similar_list) else None
            if avg_og:
                diff = round(ref_batch.measured_og - avg_og, 3)
                if abs(diff) > 0.005:
                    insights.append(f"OG is {abs(diff):.3f} {'higher' if diff > 0 else 'lower'} than average of similar batches")

        # Compare attenuation
        if ref_batch.measured_attenuation:
            attens = [b["measured_attenuation"] for b in similar_list if b["measured_attenuation"]]
            if attens:
                avg_atten = sum(attens) / len(attens)
                diff = ref_batch.measured_attenuation - avg_atten
                if abs(diff) > 5:
                    insights.append(f"Attenuation is {abs(diff):.1f}% {'higher' if diff > 0 else 'lower'} than average")

    return {
        "reference_batch": ref_info,
        "comparison_type": comparison_type,
        "similar_batches_count": len(similar_list),
        "similar_batches": similar_list,
        "insights": insights,
    }


async def get_yeast_fermentation_advice(
    db: AsyncSession,
    yeast_query: str,
    batch_id: Optional[int] = None,
    user_id: Optional[str] = None,
) -> dict[str, Any]:
    """Get yeast-specific fermentation advice."""
    # Search for the yeast strain
    yeast_stmt = select(YeastStrain).where(
        or_(
            YeastStrain.product_id.ilike(f"%{yeast_query}%"),
            YeastStrain.name.ilike(f"%{yeast_query}%"),
        )
    ).limit(1)

    result = await db.execute(yeast_stmt)
    yeast = result.scalar_one_or_none()

    if not yeast:
        return {
            "found": False,
            "error": f"Yeast strain not found: {yeast_query}",
            "suggestion": "Try searching with a product ID (e.g., 'US-05', 'WLP001') or partial name"
        }

    # Build yeast profile
    yeast_profile = {
        "name": yeast.name,
        "producer": yeast.producer,
        "product_id": yeast.product_id,
        "type": yeast.type,
        "form": yeast.form,
        "temp_range_c": {
            "min": yeast.temp_low,
            "max": yeast.temp_high,
            "optimal": round((yeast.temp_low + yeast.temp_high) / 2, 1) if yeast.temp_low and yeast.temp_high else None,
        },
        "attenuation_range_percent": {
            "min": yeast.attenuation_low,
            "max": yeast.attenuation_high,
        },
        "flocculation": yeast.flocculation,
        "alcohol_tolerance": yeast.alcohol_tolerance,
        "description": yeast.description,
    }

    # Generate fermentation advice based on yeast characteristics
    advice = []

    # Temperature advice
    if yeast.temp_low and yeast.temp_high:
        optimal = round((yeast.temp_low + yeast.temp_high) / 2, 1)
        advice.append({
            "category": "temperature",
            "recommendation": f"Ferment at {yeast.temp_low}-{yeast.temp_high}°C. Optimal: {optimal}°C.",
            "details": "Lower temperatures generally produce cleaner flavors, higher temperatures produce more esters and phenols."
        })

        if yeast.type == "lager":
            advice.append({
                "category": "temperature",
                "recommendation": "Consider a diacetyl rest at 18-20°C for 2-3 days near the end of fermentation.",
                "details": "This helps the yeast clean up diacetyl (buttery flavor) before cold conditioning."
            })

    # Attenuation advice
    if yeast.attenuation_low and yeast.attenuation_high:
        if yeast.attenuation_high > 80:
            advice.append({
                "category": "attenuation",
                "recommendation": "This is a highly attenuative strain - expect a dry finish.",
                "details": f"Expected attenuation: {yeast.attenuation_low}-{yeast.attenuation_high}%"
            })
        elif yeast.attenuation_low < 70:
            advice.append({
                "category": "attenuation",
                "recommendation": "This is a low-attenuating strain - expect residual sweetness.",
                "details": f"Expected attenuation: {yeast.attenuation_low}-{yeast.attenuation_high}%"
            })

    # Flocculation advice
    if yeast.flocculation:
        if yeast.flocculation.lower() in ["high", "very high"]:
            advice.append({
                "category": "flocculation",
                "recommendation": "High flocculation - beer should clear quickly.",
                "details": "May need to rouse yeast if fermentation stalls. Consider a warmer finish to ensure complete attenuation."
            })
        elif yeast.flocculation.lower() in ["low", "very low"]:
            advice.append({
                "category": "flocculation",
                "recommendation": "Low flocculation - beer may take longer to clear.",
                "details": "Cold crashing or fining agents may help achieve clarity if desired."
            })

    # Pitch rate advice based on form
    if yeast.form == "dry":
        advice.append({
            "category": "pitching",
            "recommendation": "Rehydrate dry yeast in warm water (25-30°C) for 15-30 minutes before pitching.",
            "details": "Some brewers pitch directly, but rehydration can improve cell viability."
        })
    elif yeast.form == "liquid":
        advice.append({
            "category": "pitching",
            "recommendation": "Consider making a starter for liquid yeast, especially for high-gravity beers.",
            "details": "A 1-2L starter is typically sufficient for most ales under 1.060 OG."
        })

    # Batch-specific recommendations
    batch_specific = None
    if batch_id:
        batch_stmt = (
            select(Batch)
            .options(
                selectinload(Batch.recipe),
                selectinload(Batch.device),
            )
            .where(Batch.id == batch_id)
        )
        if user_id:
            batch_stmt = batch_stmt.where(_user_owns_batch_condition(user_id))
        batch_result = await db.execute(batch_stmt)
        batch = batch_result.scalar_one_or_none()

        if batch:
            batch_specific = {
                "batch_id": batch.id,
                "batch_name": batch.name or (batch.recipe.name if batch.recipe else f"Batch #{batch.id}"),
            }

            # Check current temperature
            if batch.device_id:
                live = latest_readings.get(batch.device_id)
                if live and live.get("temp") is not None:
                    current_temp = live["temp"]
                    batch_specific["current_temp_c"] = current_temp

                    if yeast.temp_low and current_temp < yeast.temp_low:
                        batch_specific["temp_warning"] = f"Temperature ({current_temp}°C) is below yeast minimum ({yeast.temp_low}°C). Consider raising temperature."
                    elif yeast.temp_high and current_temp > yeast.temp_high:
                        batch_specific["temp_warning"] = f"Temperature ({current_temp}°C) is above yeast maximum ({yeast.temp_high}°C). Consider cooling."
                    else:
                        batch_specific["temp_status"] = "Temperature is within yeast tolerance range."

            # OG-specific advice
            if batch.measured_og:
                batch_specific["measured_og"] = batch.measured_og
                if batch.measured_og > 1.070:
                    batch_specific["high_gravity_note"] = "High gravity wort - ensure adequate yeast pitch rate and consider incremental feeding."

    return {
        "found": True,
        "yeast": yeast_profile,
        "advice": advice,
        "batch_specific": batch_specific,
    }
