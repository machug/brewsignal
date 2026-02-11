"""Configuration API endpoints."""

import json
import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import Config, ConfigResponse, ConfigUpdate
from ..config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/config", tags=["config"])

# Separate public router for app config (no auth required)
public_router = APIRouter(prefix="/api/config", tags=["config"])

DEFAULT_CONFIG: dict[str, Any] = {
    "temp_units": "C",
    "sg_units": "sg",
    "local_logging_enabled": True,
    "local_interval_minutes": 15,
    "min_rssi": -100,
    "smoothing_enabled": False,
    "smoothing_samples": 5,
    "id_by_mac": False,
    # Home Assistant settings
    "ha_enabled": False,
    "ha_url": "",
    "ha_token": "",
    "ha_ambient_temp_entity_id": "",
    "ha_ambient_humidity_entity_id": "",
    # Chamber settings (fermentation chamber environment)
    "ha_chamber_temp_entity_id": "",
    "ha_chamber_humidity_entity_id": "",
    # Temperature control
    "temp_control_enabled": False,
    "temp_target": 68.0,
    "temp_hysteresis": 1.0,
    "ha_heater_entity_id": "",
    # Chamber idle mode (control chamber when no batches active)
    "chamber_idle_enabled": False,
    "chamber_idle_target": 59.0,    # 15°C in Fahrenheit
    "chamber_idle_hysteresis": 3.6,  # 2°C in Fahrenheit
    # Weather
    "ha_weather_entity_id": "",
    # Alerts (threshold in Celsius)
    "weather_alerts_enabled": False,
    "alert_temp_threshold": 3.0,
    # AI Assistant settings
    "ai_enabled": False,
    "ai_provider": "local",
    "ai_model": "",
    "ai_api_key": "",
    "ai_base_url": "",
    "ai_temperature": 0.7,
    "ai_max_tokens": 2000,
    # MQTT settings for Home Assistant
    "mqtt_enabled": False,
    "mqtt_host": "",
    "mqtt_port": 1883,
    "mqtt_username": "",
    "mqtt_password": "",
    "mqtt_topic_prefix": "brewsignal",
}


async def get_config_value(db: AsyncSession, key: str) -> Any:
    """Get a single config value, returning default if not set."""
    result = await db.execute(select(Config).where(Config.key == key))
    config = result.scalar_one_or_none()
    if config is None:
        return DEFAULT_CONFIG.get(key)
    return json.loads(config.value)


async def set_config_value(db: AsyncSession, key: str, value: Any) -> None:
    """Set a single config value."""
    result = await db.execute(select(Config).where(Config.key == key))
    config = result.scalar_one_or_none()
    if config is None:
        config = Config(key=key, value=json.dumps(value))
        db.add(config)
    else:
        config.value = json.dumps(value)


@router.get("", response_model=ConfigResponse)
async def get_config(db: AsyncSession = Depends(get_db)):
    """Get all configuration settings."""
    # Start with defaults
    config_dict = DEFAULT_CONFIG.copy()

    # Override with stored values
    result = await db.execute(select(Config))
    for config in result.scalars():
        if config.key in config_dict:
            try:
                config_dict[config.key] = json.loads(config.value)
            except json.JSONDecodeError:
                logger.warning("Invalid JSON for config key %s", config.key)

    return ConfigResponse(**config_dict)


@router.patch("", response_model=ConfigResponse)
async def update_config(
    update: ConfigUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Partially update configuration settings.

    Only provided fields are updated; others remain unchanged.
    Values are validated via Pydantic schema before saving.
    """
    # Get fields that were actually provided (not None)
    update_data = update.model_dump(exclude_unset=True)

    # Update each provided field
    for key, value in update_data.items():
        await set_config_value(db, key, value)

    await db.commit()

    # Return full config after update
    return await get_config(db)


# --------------------------------------------------------------------------
# Public App Config (no auth required)
# --------------------------------------------------------------------------

class AppConfigResponse(BaseModel):
    """Public application configuration for frontend bootstrap."""
    deployment_mode: str
    auth_enabled: bool
    auth_required: bool
    supabase_url: Optional[str] = None
    supabase_anon_key: Optional[str] = None


@public_router.get("/app", response_model=AppConfigResponse)
async def get_app_config():
    """Get public application configuration.

    This endpoint returns configuration the frontend needs to bootstrap,
    including auth provider settings. No authentication required.

    The supabase_url and supabase_anon_key are intentionally public -
    they are designed to be used in client-side JavaScript. Security
    is enforced via Supabase RLS policies, not by hiding these values.
    """
    settings = get_settings()

    # Auth is enabled if Supabase credentials are configured
    auth_enabled = bool(settings.supabase_url and settings.supabase_anon_key)

    return AppConfigResponse(
        deployment_mode=settings.deployment_mode.value,
        auth_enabled=auth_enabled,
        auth_required=settings.is_cloud,
        supabase_url=settings.supabase_url if auth_enabled else None,
        supabase_anon_key=settings.supabase_anon_key if auth_enabled else None,
    )
