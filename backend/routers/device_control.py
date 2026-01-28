"""Device control API endpoints - test connections for HA and Shelly backends."""

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..services.device_control import ShellyDirectAdapter, get_device_router
from .config import get_config_value

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/device-control", tags=["device-control"])


class ShellyTestRequest(BaseModel):
    ip: str  # Single IP to test, e.g., "192.168.1.50"


class ShellyTestResponse(BaseModel):
    success: bool
    message: str
    device_gen: int | None = None  # 1 or 2 if detected


class ShellyDiscoverResponse(BaseModel):
    devices: list[dict]  # List of discovered devices


class DeviceControlStatusResponse(BaseModel):
    backend: str  # "ha" or "shelly"
    ha_enabled: bool
    ha_connected: bool
    shelly_enabled: bool
    shelly_devices: list[str]


@router.get("/status", response_model=DeviceControlStatusResponse)
async def get_device_control_status(db: AsyncSession = Depends(get_db)):
    """Get current device control configuration status."""
    backend = await get_config_value(db, "device_control_backend") or "ha"
    ha_enabled = await get_config_value(db, "ha_enabled") or False
    shelly_enabled = await get_config_value(db, "shelly_enabled") or False
    shelly_devices_str = await get_config_value(db, "shelly_devices") or ""

    # Parse comma-separated IPs
    shelly_devices = [ip.strip() for ip in shelly_devices_str.split(",") if ip.strip()]

    # Check HA connection if enabled
    ha_connected = False
    if ha_enabled:
        router_instance = get_device_router()
        if router_instance:
            try:
                ha_connected = await router_instance.test_connection("ha")
            except Exception:
                pass

    return DeviceControlStatusResponse(
        backend=backend,
        ha_enabled=ha_enabled,
        ha_connected=ha_connected,
        shelly_enabled=shelly_enabled,
        shelly_devices=shelly_devices,
    )


@router.post("/shelly/test", response_model=ShellyTestResponse)
async def test_shelly_device(request: ShellyTestRequest):
    """Test connection to a Shelly device by IP."""
    if not request.ip:
        return ShellyTestResponse(success=False, message="IP address required")

    # Validate IP format (basic check)
    ip = request.ip.strip()
    if not ip or ip.count(".") != 3:
        return ShellyTestResponse(success=False, message="Invalid IP address format")

    adapter = ShellyDirectAdapter()
    try:
        # Try to get state which will detect the device generation
        entity_id = f"shelly://{ip}/0"
        state = await adapter.get_state(entity_id)

        if state is not None:
            # Check what generation was detected
            gen = adapter._get_cached_gen(ip)
            return ShellyTestResponse(
                success=True,
                message=f"Connected! Device is {'on' if state == 'on' else 'off'} (Gen{gen})",
                device_gen=gen,
            )
        else:
            return ShellyTestResponse(
                success=False,
                message="Device not reachable - check IP and network",
            )
    except Exception as e:
        logger.exception(f"Error testing Shelly device {ip}")
        return ShellyTestResponse(success=False, message=f"Error: {str(e)}")
    finally:
        await adapter.close()


@router.post("/shelly/toggle")
async def toggle_shelly_device(request: ShellyTestRequest):
    """Toggle a Shelly device (for testing)."""
    if not request.ip:
        return {"success": False, "message": "IP address required"}

    ip = request.ip.strip()
    adapter = ShellyDirectAdapter()
    try:
        entity_id = f"shelly://{ip}/0"

        # Get current state
        state = await adapter.get_state(entity_id)
        if state is None:
            return {"success": False, "message": "Device not reachable"}

        # Toggle
        new_state = "off" if state == "on" else "on"
        success = await adapter.set_state(entity_id, new_state)

        if success:
            return {"success": True, "message": f"Toggled to {new_state}", "state": new_state}
        else:
            return {"success": False, "message": "Failed to toggle device"}
    except Exception as e:
        logger.exception(f"Error toggling Shelly device {ip}")
        return {"success": False, "message": f"Error: {str(e)}"}
    finally:
        await adapter.close()
