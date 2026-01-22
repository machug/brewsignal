"""MQTT integration API endpoints."""

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..services.mqtt_client import get_mqtt_client
from .config import get_config_value

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/mqtt", tags=["mqtt"])


class MQTTStatusResponse(BaseModel):
    enabled: bool
    connected: bool
    host: str
    error: str | None = None


class MQTTTestResponse(BaseModel):
    success: bool
    message: str


@router.get("/status", response_model=MQTTStatusResponse)
async def get_mqtt_status(db: AsyncSession = Depends(get_db)):
    """Get MQTT connection status."""
    mqtt_enabled = await get_config_value(db, "mqtt_enabled")
    mqtt_host = await get_config_value(db, "mqtt_host") or ""

    if not mqtt_enabled:
        return MQTTStatusResponse(enabled=False, connected=False, host=mqtt_host)

    mqtt_client = get_mqtt_client()
    if not mqtt_client:
        return MQTTStatusResponse(
            enabled=True,
            connected=False,
            host=mqtt_host,
            error="Client not initialized"
        )

    return MQTTStatusResponse(
        enabled=True,
        connected=mqtt_client.is_connected(),
        host=mqtt_host
    )


@router.post("/test", response_model=MQTTTestResponse)
async def test_mqtt_connection(db: AsyncSession = Depends(get_db)):
    """Test MQTT connection with current configuration."""
    mqtt_host = await get_config_value(db, "mqtt_host")
    mqtt_port = await get_config_value(db, "mqtt_port") or 1883
    mqtt_username = await get_config_value(db, "mqtt_username")
    mqtt_password = await get_config_value(db, "mqtt_password")

    if not mqtt_host:
        return MQTTTestResponse(success=False, message="Broker host is required")

    mqtt_client = get_mqtt_client()
    if not mqtt_client:
        return MQTTTestResponse(success=False, message="MQTT client not available")

    try:
        result = await mqtt_client.test_connection(
            host=mqtt_host,
            port=int(mqtt_port),
            username=mqtt_username or None,
            password=mqtt_password or None
        )
        return MQTTTestResponse(success=result["success"], message=result["message"])
    except Exception as e:
        logger.exception("MQTT test connection error")
        return MQTTTestResponse(success=False, message=f"Error: {str(e)}")
