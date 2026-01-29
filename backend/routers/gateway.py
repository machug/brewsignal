"""WebSocket endpoint for BrewSignal Gateway devices.

Gateways are ESP32 devices that relay Tilt BLE readings to the cloud.
Each gateway authenticates via a unique gateway_id and optional user token.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import async_session_factory, get_db
from ..models import Device, Reading, Gateway
from ..services.calibration import calibration_service
from ..services.batch_linker import link_reading_to_batch
from ..websocket import manager as broadcast_manager
from ..state import update_reading
from ..models import serialize_datetime_to_utc
from .users import get_user_id_from_token

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ws", tags=["gateway"])

# Track connected gateways
connected_gateways: dict[str, WebSocket] = {}


async def process_gateway_reading(
    gateway_id: str,
    user_id: Optional[str],
    payload: dict,
) -> Optional[dict]:
    """Process a reading received from a gateway.

    Args:
        gateway_id: The gateway's unique ID
        user_id: The owning user's ID (for cloud mode)
        payload: Reading data from gateway

    Returns:
        Processed reading dict for broadcast, or None if invalid
    """
    # Extract reading data
    device_id = payload.get("device_id")
    color = payload.get("color", "Unknown")
    temp_c = payload.get("temp")  # Gateway sends Celsius
    sg = payload.get("gravity") or payload.get("sg")
    rssi = payload.get("rssi")

    if not device_id or temp_c is None or sg is None:
        logger.warning(f"Gateway {gateway_id}: Invalid reading payload: {payload}")
        return None

    async with async_session_factory() as session:
        # Get or create Device record
        device = await session.get(Device, device_id)
        if not device:
            device = Device(
                id=device_id,
                device_type="tilt",
                name=color,
                native_temp_unit="c",
                native_gravity_unit="sg",
                calibration_type="linear",
                paired=False,
                user_id=user_id,  # Associate with gateway owner
            )
            session.add(device)

        # Update device metadata
        timestamp = datetime.now(timezone.utc)
        device.last_seen = timestamp
        device.color = color

        # Apply calibration
        sg_calibrated, temp_calibrated = await calibration_service.calibrate_reading(
            session, device_id, sg, temp_c
        )

        # Validate reading
        status = "valid"
        if not (0.500 <= sg_calibrated <= 1.200) or not (0.0 <= temp_calibrated <= 100.0):
            status = "invalid"

        # Link to active batch
        batch_id = await link_reading_to_batch(session, device_id)

        # Store reading if device is paired and linked to batch
        if device.paired and batch_id is not None:
            db_reading = Reading(
                device_id=device_id,
                batch_id=batch_id,
                timestamp=timestamp,
                sg_raw=sg,
                sg_calibrated=sg_calibrated,
                temp_raw=temp_c,
                temp_calibrated=temp_calibrated,
                rssi=rssi,
                status=status,
                source_protocol="gateway",  # Track that this came from gateway
            )
            session.add(db_reading)

        await session.commit()

        # Build broadcast payload
        broadcast_payload = {
            "id": device_id,
            "device_id": device_id,
            "device_type": "tilt",
            "color": color,
            "beer_name": device.beer_name or "Untitled",
            "original_gravity": device.original_gravity,
            "sg": sg_calibrated,
            "sg_raw": sg,
            "temp": temp_calibrated,
            "temp_raw": temp_c,
            "rssi": rssi,
            "timestamp": serialize_datetime_to_utc(timestamp),
            "last_seen": serialize_datetime_to_utc(timestamp),
            "paired": device.paired,
            "source": "gateway",
            "gateway_id": gateway_id,
        }

        # Update state cache and broadcast to frontend clients
        update_reading(device_id, broadcast_payload)
        await broadcast_manager.broadcast(broadcast_payload)

        return broadcast_payload


async def register_gateway(
    session: AsyncSession,
    gateway_id: str,
    user_id: Optional[str],
) -> Gateway:
    """Register or update a gateway in the database."""
    gateway = await session.get(Gateway, gateway_id)

    if not gateway:
        gateway = Gateway(
            id=gateway_id,
            user_id=user_id,
            name=f"Gateway {gateway_id[-6:]}",
        )
        session.add(gateway)
        logger.info(f"Registered new gateway: {gateway_id}")

    gateway.last_seen = datetime.now(timezone.utc)
    gateway.is_online = True

    await session.commit()
    return gateway


@router.websocket("/gateway/{gateway_id}")
async def gateway_websocket(
    websocket: WebSocket,
    gateway_id: str,
    token: Optional[str] = Query(None),
):
    """WebSocket endpoint for gateway devices.

    Protocol:
    - Gateway connects with its unique ID in the URL
    - Optional token query param for user association
    - Gateway sends readings as JSON: {"type": "reading", "device_id": "...", ...}
    - Server can send commands: {"type": "command", "action": "...", ...}

    Example URL: wss://api.brewsignal.io/ws/gateway/BSG-AABBCCDDEE00?token=xxx
    """
    # Validate token if provided (associates gateway with user)
    user_id = None
    if token:
        user_id = await get_user_id_from_token(token)
        if not user_id:
            await websocket.close(code=4001, reason="Invalid token")
            return

    await websocket.accept()
    logger.info(f"Gateway connected: {gateway_id} (user: {user_id or 'anonymous'})")

    # Register gateway in database
    async with async_session_factory() as session:
        await register_gateway(session, gateway_id, user_id)

    # Track connection
    connected_gateways[gateway_id] = websocket

    # Send welcome message
    await websocket.send_json({
        "type": "connected",
        "gateway_id": gateway_id,
        "server_time": serialize_datetime_to_utc(datetime.now(timezone.utc)),
    })

    try:
        while True:
            # Receive message from gateway
            data = await websocket.receive_text()

            try:
                message = json.loads(data)
            except json.JSONDecodeError:
                logger.warning(f"Gateway {gateway_id}: Invalid JSON: {data[:100]}")
                continue

            msg_type = message.get("type")

            if msg_type == "reading":
                # Process Tilt reading
                await process_gateway_reading(gateway_id, user_id, message)

            elif msg_type == "ping":
                # Heartbeat
                await websocket.send_json({"type": "pong"})

            elif msg_type == "status":
                # Gateway status update (wifi strength, uptime, etc.)
                logger.debug(f"Gateway {gateway_id} status: {message}")

            else:
                logger.warning(f"Gateway {gateway_id}: Unknown message type: {msg_type}")

    except WebSocketDisconnect:
        logger.info(f"Gateway disconnected: {gateway_id}")
    except Exception as e:
        logger.error(f"Gateway {gateway_id} error: {e}")
    finally:
        # Clean up
        connected_gateways.pop(gateway_id, None)

        # Mark gateway offline
        async with async_session_factory() as session:
            gateway = await session.get(Gateway, gateway_id)
            if gateway:
                gateway.is_online = False
                await session.commit()


async def send_command_to_gateway(gateway_id: str, command: dict) -> bool:
    """Send a command to a connected gateway.

    Args:
        gateway_id: Target gateway ID
        command: Command dict to send

    Returns:
        True if sent successfully, False if gateway not connected
    """
    websocket = connected_gateways.get(gateway_id)
    if not websocket:
        return False

    try:
        await websocket.send_json(command)
        return True
    except Exception as e:
        logger.error(f"Failed to send command to {gateway_id}: {e}")
        return False


def get_connected_gateway_ids() -> list[str]:
    """Get list of currently connected gateway IDs."""
    return list(connected_gateways.keys())
