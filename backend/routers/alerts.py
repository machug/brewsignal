"""Weather alerts and predictive alerts API endpoints."""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..services.ha_client import get_ha_client
from .config import get_config_value

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


class WeatherForecast(BaseModel):
    """Single day weather forecast."""
    datetime: str
    condition: str
    temperature: Optional[float]  # High temp
    templow: Optional[float]  # Low temp


class Alert(BaseModel):
    """Predictive alert based on weather forecast."""
    level: str  # "info", "warning", "critical"
    message: str
    day: str  # Day name (e.g., "Monday")


class AlertsResponse(BaseModel):
    """Response containing forecast and alerts."""
    forecast: list[WeatherForecast]
    alerts: list[Alert]
    weather_entity: Optional[str]
    alerts_enabled: bool


class AlertsConfigResponse(BaseModel):
    """Current alerts configuration."""
    weather_alerts_enabled: bool
    alert_temp_threshold: float
    ha_weather_entity_id: str
    temp_target: Optional[float]


def generate_alerts(
    forecast: list[dict],
    target_temp: Optional[float],
    threshold: float
) -> list[Alert]:
    """Generate predictive alerts based on weather forecast.

    Compares forecast temps against the fermentation target temp
    to warn about potential temperature control issues.
    """
    alerts = []

    if not target_temp or not forecast:
        return alerts

    for day in forecast[:3]:  # Next 3 days
        try:
            # Parse datetime for day name
            dt_str = day.get("datetime", "")
            if dt_str:
                dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
                day_name = dt.strftime("%A")
            else:
                day_name = "Upcoming"

            temp_high = day.get("temperature")
            temp_low = day.get("templow")
            condition = day.get("condition", "unknown")

            # Check for cold conditions that may stress heater
            if temp_low is not None and temp_low < (target_temp - threshold):
                diff = target_temp - temp_low
                alerts.append(Alert(
                    level="warning" if diff > threshold * 2 else "info",
                    message=f"Low of {temp_low:.0f}°, heater will likely run frequently",
                    day=day_name
                ))

            # Check for hot conditions that may require cooling
            if temp_high is not None and temp_high > (target_temp + threshold):
                diff = temp_high - target_temp
                alerts.append(Alert(
                    level="warning" if diff > threshold * 2 else "info",
                    message=f"High of {temp_high:.0f}°, consider cooling or relocating fermenter",
                    day=day_name
                ))

            # Warn about large temperature swings
            if temp_high is not None and temp_low is not None:
                swing = temp_high - temp_low
                if swing > 15:
                    alerts.append(Alert(
                        level="info",
                        message=f"Large temp swing ({swing:.0f}°), monitor fermentation closely",
                        day=day_name
                    ))

        except (ValueError, TypeError) as e:
            logger.warning(f"Error processing forecast day: {e}")
            continue

    return alerts


@router.get("/config", response_model=AlertsConfigResponse)
async def get_alerts_config(db: AsyncSession = Depends(get_db)):
    """Get current alerts configuration."""
    return AlertsConfigResponse(
        weather_alerts_enabled=await get_config_value(db, "weather_alerts_enabled") or False,
        alert_temp_threshold=await get_config_value(db, "alert_temp_threshold") or 5.0,
        ha_weather_entity_id=await get_config_value(db, "ha_weather_entity_id") or "",
        temp_target=await get_config_value(db, "temp_target"),
    )


@router.get("", response_model=AlertsResponse)
async def get_alerts(db: AsyncSession = Depends(get_db)):
    """Get weather forecast and predictive alerts."""
    ha_enabled = await get_config_value(db, "ha_enabled")
    weather_alerts_enabled = await get_config_value(db, "weather_alerts_enabled") or False
    weather_entity = await get_config_value(db, "ha_weather_entity_id") or ""

    if not ha_enabled:
        return AlertsResponse(
            forecast=[],
            alerts=[],
            weather_entity=weather_entity,
            alerts_enabled=weather_alerts_enabled
        )

    if not weather_entity:
        return AlertsResponse(
            forecast=[],
            alerts=[],
            weather_entity=weather_entity,
            alerts_enabled=weather_alerts_enabled
        )

    ha_client = get_ha_client()
    if not ha_client:
        return AlertsResponse(
            forecast=[],
            alerts=[],
            weather_entity=weather_entity,
            alerts_enabled=weather_alerts_enabled
        )

    # Fetch forecast from HA
    raw_forecast = await ha_client.get_weather_forecast(weather_entity)

    if not raw_forecast:
        return AlertsResponse(
            forecast=[],
            alerts=[],
            weather_entity=weather_entity,
            alerts_enabled=weather_alerts_enabled
        )

    # Convert to response format
    forecast = []
    for day in raw_forecast[:5]:  # Return up to 5 days
        forecast.append(WeatherForecast(
            datetime=day.get("datetime", ""),
            condition=day.get("condition", "unknown"),
            temperature=day.get("temperature"),
            templow=day.get("templow"),
        ))

    # Generate alerts if enabled
    alerts = []
    if weather_alerts_enabled:
        target_temp = await get_config_value(db, "temp_target")
        threshold = await get_config_value(db, "alert_temp_threshold") or 5.0
        alerts = generate_alerts(raw_forecast, target_temp, threshold)

    return AlertsResponse(
        forecast=forecast,
        alerts=alerts,
        weather_entity=weather_entity,
        alerts_enabled=weather_alerts_enabled
    )
