"""Device API endpoints for universal hydrometer device registry."""

import json
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import Device

router = APIRouter(prefix="/api/devices", tags=["devices"])


# Pydantic Schemas
class DeviceCreate(BaseModel):
    """Schema for creating a new device."""
    id: str
    device_type: str = "tilt"
    name: str
    display_name: Optional[str] = None
    beer_name: Optional[str] = None
    original_gravity: Optional[float] = None
    native_gravity_unit: str = "sg"
    native_temp_unit: str = "f"
    calibration_type: str = "none"
    calibration_data: Optional[dict[str, Any]] = None
    auth_token: Optional[str] = None
    color: Optional[str] = None
    mac: Optional[str] = None

    @field_validator("device_type")
    @classmethod
    def validate_device_type(cls, v: str) -> str:
        valid_types = {"tilt", "ispindel", "gravitymon", "floaty"}
        if v not in valid_types:
            raise ValueError(f"device_type must be one of: {', '.join(valid_types)}")
        return v

    @field_validator("native_gravity_unit")
    @classmethod
    def validate_gravity_unit(cls, v: str) -> str:
        valid_units = {"sg", "plato", "brix"}
        if v not in valid_units:
            raise ValueError(f"native_gravity_unit must be one of: {', '.join(valid_units)}")
        return v

    @field_validator("native_temp_unit")
    @classmethod
    def validate_temp_unit(cls, v: str) -> str:
        valid_units = {"f", "c"}
        if v not in valid_units:
            raise ValueError(f"native_temp_unit must be 'f' or 'c'")
        return v

    @field_validator("original_gravity")
    @classmethod
    def validate_og(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and (v < 0.990 or v > 1.200):
            raise ValueError("original_gravity must be between 0.990 and 1.200")
        return v


class DeviceUpdate(BaseModel):
    """Schema for updating an existing device."""
    name: Optional[str] = None
    display_name: Optional[str] = None
    beer_name: Optional[str] = None
    original_gravity: Optional[float] = None
    native_gravity_unit: Optional[str] = None
    native_temp_unit: Optional[str] = None
    calibration_type: Optional[str] = None
    calibration_data: Optional[dict[str, Any]] = None
    auth_token: Optional[str] = None

    @field_validator("native_gravity_unit")
    @classmethod
    def validate_gravity_unit(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in {"sg", "plato", "brix"}:
            raise ValueError("native_gravity_unit must be one of: sg, plato, brix")
        return v

    @field_validator("native_temp_unit")
    @classmethod
    def validate_temp_unit(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in {"f", "c"}:
            raise ValueError("native_temp_unit must be 'f' or 'c'")
        return v

    @field_validator("original_gravity")
    @classmethod
    def validate_og(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and (v < 0.990 or v > 1.200):
            raise ValueError("original_gravity must be between 0.990 and 1.200")
        return v


class DeviceResponse(BaseModel):
    """Schema for device response."""
    id: str
    device_type: str
    name: str
    display_name: Optional[str]
    beer_name: Optional[str]
    original_gravity: Optional[float]
    native_gravity_unit: str
    native_temp_unit: str
    calibration_type: str
    calibration_data: Optional[dict[str, Any]]
    auth_token: Optional[str]
    last_seen: Optional[datetime]
    battery_voltage: Optional[float]
    firmware_version: Optional[str]
    color: Optional[str]
    mac: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True

    @classmethod
    def from_orm_with_calibration(cls, device: Device) -> "DeviceResponse":
        """Convert Device model to DeviceResponse, handling calibration_data."""
        return cls(
            id=device.id,
            device_type=device.device_type,
            name=device.name,
            display_name=device.display_name,
            beer_name=device.beer_name,
            original_gravity=device.original_gravity,
            native_gravity_unit=device.native_gravity_unit,
            native_temp_unit=device.native_temp_unit,
            calibration_type=device.calibration_type,
            calibration_data=device.calibration_data,  # Uses @property
            auth_token=device.auth_token,
            last_seen=device.last_seen,
            battery_voltage=device.battery_voltage,
            firmware_version=device.firmware_version,
            color=device.color,
            mac=device.mac,
            created_at=device.created_at,
        )


# API Endpoints
@router.get("", response_model=list[DeviceResponse])
async def list_devices(
    device_type: Optional[str] = Query(None, description="Filter by device type"),
    db: AsyncSession = Depends(get_db),
):
    """List all devices, optionally filtered by device type."""
    query = select(Device).order_by(Device.created_at.desc())

    if device_type:
        query = query.where(Device.device_type == device_type)

    result = await db.execute(query)
    devices = result.scalars().all()

    # Convert to response models with calibration_data
    return [DeviceResponse.from_orm_with_calibration(d) for d in devices]


@router.get("/{device_id}", response_model=DeviceResponse)
async def get_device(device_id: str, db: AsyncSession = Depends(get_db)):
    """Get a specific device by ID."""
    device = await db.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    return DeviceResponse.from_orm_with_calibration(device)


@router.post("", response_model=DeviceResponse, status_code=201)
async def create_device(
    device_data: DeviceCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new device manually (for devices not auto-registered)."""
    # Check if device already exists
    existing = await db.get(Device, device_data.id)
    if existing:
        raise HTTPException(status_code=400, detail="Device with this ID already exists")

    # Create new device
    device = Device(
        id=device_data.id,
        device_type=device_data.device_type,
        name=device_data.name,
        display_name=device_data.display_name,
        beer_name=device_data.beer_name,
        original_gravity=device_data.original_gravity,
        native_gravity_unit=device_data.native_gravity_unit,
        native_temp_unit=device_data.native_temp_unit,
        calibration_type=device_data.calibration_type,
        auth_token=device_data.auth_token,
        color=device_data.color,
        mac=device_data.mac,
        created_at=datetime.now(timezone.utc),
    )

    # Set calibration data using property setter
    if device_data.calibration_data is not None:
        device.calibration_data = device_data.calibration_data

    db.add(device)
    await db.commit()
    await db.refresh(device)

    return DeviceResponse.from_orm_with_calibration(device)


@router.put("/{device_id}", response_model=DeviceResponse)
async def update_device(
    device_id: str,
    update_data: DeviceUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update device properties (name, display_name, beer_name, etc.)."""
    device = await db.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    # Update fields if provided
    if update_data.name is not None:
        device.name = update_data.name
    if update_data.display_name is not None:
        device.display_name = update_data.display_name
    if update_data.beer_name is not None:
        device.beer_name = update_data.beer_name
    if update_data.original_gravity is not None:
        device.original_gravity = update_data.original_gravity
    if update_data.native_gravity_unit is not None:
        device.native_gravity_unit = update_data.native_gravity_unit
    if update_data.native_temp_unit is not None:
        device.native_temp_unit = update_data.native_temp_unit
    if update_data.calibration_type is not None:
        device.calibration_type = update_data.calibration_type
    if update_data.calibration_data is not None:
        device.calibration_data = update_data.calibration_data
    if update_data.auth_token is not None:
        device.auth_token = update_data.auth_token

    await db.commit()
    await db.refresh(device)

    return DeviceResponse.from_orm_with_calibration(device)


@router.delete("/{device_id}")
async def delete_device(device_id: str, db: AsyncSession = Depends(get_db)):
    """Delete a device and all its readings."""
    device = await db.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    await db.delete(device)
    await db.commit()

    return {"status": "deleted", "device_id": device_id}
