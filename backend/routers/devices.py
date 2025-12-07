"""Device API endpoints for universal hydrometer device registry."""

from datetime import datetime, timezone, timedelta
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, field_serializer, field_validator, model_validator
from sqlalchemy import select, delete, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..database import get_db
from ..models import (
    Device,
    CalibrationPoint,
    Reading,
    CalibrationPointCreate,
    CalibrationPointResponse,
    ReadingResponse,
    serialize_datetime_to_utc,
)
from ..services.calibration import calibration_service

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
            raise ValueError("native_temp_unit must be 'f' or 'c'")
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
    model_config = ConfigDict(from_attributes=True)

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
    paired: bool
    paired_at: Optional[datetime]

    @field_serializer('last_seen', 'created_at', 'paired_at')
    def serialize_dt(self, dt: Optional[datetime]) -> Optional[str]:
        return serialize_datetime_to_utc(dt)

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
            paired=device.paired,
            paired_at=device.paired_at,
        )


class CalibrationRequest(BaseModel):
    """Schema for setting device calibration."""
    calibration_type: str
    calibration_data: Optional[dict[str, Any]] = None

    @field_validator("calibration_type")
    @classmethod
    def validate_calibration_type(cls, v: str) -> str:
        valid_types = {"none", "offset", "linear", "polynomial"}
        if v not in valid_types:
            raise ValueError(f"calibration_type must be one of: {', '.join(valid_types)}")
        return v

    @model_validator(mode="after")
    def validate_calibration_data(self) -> "CalibrationRequest":
        """Validate calibration_data structure matches calibration_type."""
        cal_type = self.calibration_type
        cal_data = self.calibration_data

        if cal_type == "none":
            # None type should have no data
            if cal_data is not None:
                raise ValueError("calibration_type 'none' should not have calibration_data")

        elif cal_type == "offset":
            # Offset requires sg_offset and/or temp_offset
            if cal_data is None:
                raise ValueError("calibration_type 'offset' requires calibration_data")
            if "sg_offset" not in cal_data and "temp_offset" not in cal_data:
                raise ValueError("offset calibration requires 'sg_offset' and/or 'temp_offset'")
            # Validate types
            if "sg_offset" in cal_data and not isinstance(cal_data["sg_offset"], (int, float)):
                raise ValueError("sg_offset must be a number")
            if "temp_offset" in cal_data and not isinstance(cal_data["temp_offset"], (int, float)):
                raise ValueError("temp_offset must be a number")

        elif cal_type == "linear":
            # Linear requires points array
            if cal_data is None:
                raise ValueError("calibration_type 'linear' requires calibration_data")
            if "points" not in cal_data:
                raise ValueError("linear calibration requires 'points' array")
            points = cal_data["points"]
            if not isinstance(points, list) or len(points) < 2:
                raise ValueError("linear calibration requires at least 2 points")
            # Validate point structure: [[raw1, actual1], [raw2, actual2], ...]
            for point in points:
                if not isinstance(point, list) or len(point) != 2:
                    raise ValueError("each point must be [raw_value, actual_value]")
                if not all(isinstance(v, (int, float)) for v in point):
                    raise ValueError("point values must be numbers")
                # Validate SG ranges (0.990-1.200)
                if not (0.990 <= point[0] <= 1.200 and 0.990 <= point[1] <= 1.200):
                    raise ValueError("SG calibration points must be between 0.990 and 1.200")

            # Validate temp_points if present
            if "temp_points" in cal_data:
                temp_points = cal_data["temp_points"]
                if not isinstance(temp_points, list):
                    raise ValueError("temp_points must be a list")
                for point in temp_points:
                    if not isinstance(point, list) or len(point) != 2:
                        raise ValueError("each temp point must be [raw_value, actual_value]")
                    if not all(isinstance(v, (int, float)) for v in point):
                        raise ValueError("temp point values must be numbers")
                    # Validate temperature ranges (in Celsius: -10 to 50)
                    if not (-10 <= point[0] <= 50 and -10 <= point[1] <= 50):
                        raise ValueError("Temperature calibration points must be between -10°C and 50°C")

        elif cal_type == "polynomial":
            # Polynomial requires coefficients array
            if cal_data is None:
                raise ValueError("calibration_type 'polynomial' requires calibration_data")
            if "coefficients" not in cal_data:
                raise ValueError("polynomial calibration requires 'coefficients' array")
            coefficients = cal_data["coefficients"]
            if not isinstance(coefficients, list) or len(coefficients) < 1:
                raise ValueError("polynomial calibration requires at least 1 coefficient")
            if not all(isinstance(c, (int, float)) for c in coefficients):
                raise ValueError("all coefficients must be numbers")

        return self


class CalibrationResponse(BaseModel):
    """Schema for calibration response."""
    calibration_type: str
    calibration_data: Optional[dict[str, Any]]


class CalibrationTestRequest(BaseModel):
    """Schema for testing calibration with raw values."""
    angle: Optional[float] = None
    raw_gravity: Optional[float] = None
    raw_temperature: Optional[float] = None

    @model_validator(mode="after")
    def validate_at_least_one(self) -> "CalibrationTestRequest":
        """Ensure at least one input value is provided."""
        if self.angle is None and self.raw_gravity is None and self.raw_temperature is None:
            raise ValueError("at least one of 'angle', 'raw_gravity', or 'raw_temperature' must be provided")
        return self


class CalibrationTestResponse(BaseModel):
    """Schema for calibration test response."""
    calibrated_gravity: Optional[float] = None
    calibrated_temperature: Optional[float] = None


# API Endpoints
@router.get("", response_model=list[DeviceResponse])
async def list_devices(
    device_type: Optional[str] = Query(None, description="Filter by device type"),
    paired_only: bool = Query(False, description="Only return paired devices"),
    db: AsyncSession = Depends(get_db),
):
    """List all devices, optionally filtered by device type and pairing status."""
    query = select(Device).order_by(Device.created_at.desc())

    if device_type:
        query = query.where(Device.device_type == device_type)

    if paired_only:
        query = query.where(Device.paired)

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


@router.post("/{device_id}/pair", response_model=DeviceResponse)
async def pair_device(device_id: str, db: AsyncSession = Depends(get_db)):
    """Pair any device type to enable reading storage.

    Works for Tilt, iSpindel, GravityMon, and future device types.
    """
    device = await db.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    device.paired = True
    device.paired_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(device)

    # Update in-memory cache (if device has readings)
    from ..state import latest_readings
    from ..websocket import manager
    if device_id in latest_readings:
        latest_readings[device_id]["paired"] = True
        await manager.broadcast(latest_readings[device_id])

    return DeviceResponse.from_orm_with_calibration(device)


@router.post("/{device_id}/unpair", response_model=DeviceResponse)
async def unpair_device(device_id: str, db: AsyncSession = Depends(get_db)):
    """Unpair device to stop reading storage.

    Works for all device types.
    """
    device = await db.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    device.paired = False
    device.paired_at = None
    await db.commit()
    await db.refresh(device)

    # Update in-memory cache (if device has readings)
    from ..state import latest_readings
    from ..websocket import manager
    if device_id in latest_readings:
        latest_readings[device_id]["paired"] = False
        await manager.broadcast(latest_readings[device_id])

    return DeviceResponse.from_orm_with_calibration(device)


# CalibrationPoint Endpoints (table-based calibration for Tilt devices)
@router.get("/{device_id}/calibration_points", response_model=list[CalibrationPointResponse])
async def get_device_calibration_points(device_id: str, db: AsyncSession = Depends(get_db)):
    """Get calibration points for any device type."""
    device = await db.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    result = await db.execute(
        select(CalibrationPoint)
        .where(CalibrationPoint.device_id == device_id)
        .order_by(CalibrationPoint.type, CalibrationPoint.raw_value)
    )
    return result.scalars().all()


@router.post("/{device_id}/calibration_points", response_model=CalibrationPointResponse)
async def add_device_calibration_point(
    device_id: str,
    point: CalibrationPointCreate,
    db: AsyncSession = Depends(get_db)
):
    """Add calibration point for any device type."""
    device = await db.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    calibration_point = CalibrationPoint(
        device_id=device_id,
        **point.model_dump()
    )
    db.add(calibration_point)
    await db.commit()
    await db.refresh(calibration_point)

    return calibration_point


@router.delete("/{device_id}/calibration_points/{type}")
async def clear_device_calibration_points(
    device_id: str,
    type: str,
    db: AsyncSession = Depends(get_db)
):
    """Clear calibration points for a specific type (sg or temp)."""
    if type not in ["sg", "temp"]:
        raise HTTPException(status_code=400, detail="Type must be 'sg' or 'temp'")

    device = await db.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    await db.execute(
        delete(CalibrationPoint)
        .where(CalibrationPoint.device_id == device_id)
        .where(CalibrationPoint.type == type)
    )
    await db.commit()

    return {"message": f"Cleared {type} calibration for device {device_id}"}


@router.get("/{device_id}/readings", response_model=list[ReadingResponse])
async def get_device_readings(
    device_id: str,
    hours: Optional[int] = Query(default=None, description="Time window in hours (e.g., 24 for last 24 hours)"),
    batch_id: Optional[int] = Query(default=None, description="Filter readings by batch ID"),
    limit: int = Query(default=5000, le=10000, description="Maximum number of readings to return"),
    db: AsyncSession = Depends(get_db)
):
    """Get readings for any device type, optionally filtered by time window and/or batch.

    Implements intelligent downsampling for longer time windows to ensure
    the data covers the full requested range rather than just recent hours.

    Downsampling strategy:
    - 1H, 6H: Every reading (limit controls max)
    - 24H: Every 5th reading (~2.5 min intervals)
    - 7D: Every 60th reading (~30 min intervals)
    - 30D: Every 360th reading (~3 hour intervals)

    Returns readings in ascending order (oldest → newest) for charting.
    """
    device = await db.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    query = select(Reading).where(Reading.device_id == device_id)

    # Filter by batch_id if provided
    if batch_id is not None:
        query = query.where(Reading.batch_id == batch_id)

    # Apply time window filter if hours is provided
    if hours is not None:
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)
        query = query.where(Reading.timestamp >= cutoff_time)

    # Determine downsampling interval based on time window
    # This ensures we get data spanning the full time range
    downsample_interval = 1
    if hours is not None:
        if hours >= 720:  # 30 days
            downsample_interval = 360  # ~3 hour intervals
        elif hours >= 168:  # 7 days
            downsample_interval = 60   # ~30 min intervals
        elif hours >= 24:  # 24 hours
            downsample_interval = 5    # ~2.5 min intervals
        # else: 1H, 6H use every reading (interval=1)

    # Get all readings in time window, ordered DESC
    query = query.order_by(Reading.timestamp.desc())
    result = await db.execute(query)
    all_readings = list(result.scalars().all())

    # Apply downsampling by taking every Nth reading
    if downsample_interval > 1:
        downsampled = all_readings[::downsample_interval]
    else:
        downsampled = all_readings

    # Apply limit after downsampling
    readings = downsampled[:limit]

    # Reverse to return in ASC order (oldest → newest) for charting
    readings.reverse()
    return readings


# Calibration Endpoints (JSON-based calibration data)
@router.put("/{device_id}/calibration", response_model=CalibrationResponse)
async def set_calibration(
    device_id: str,
    calibration: CalibrationRequest,
    db: AsyncSession = Depends(get_db),
):
    """Set calibration type and data for a device.

    Calibration types:
    - none: No calibration applied
    - offset: Simple offset calibration {"sg_offset": 0.002, "temp_offset": 1.0}
    - linear: Two-point linear {"points": [[raw1, actual1], [raw2, actual2]]}
    - polynomial: iSpindel-style polynomial {"coefficients": [a, b, c, ...]}
    """
    device = await db.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    # Update calibration
    device.calibration_type = calibration.calibration_type
    device.calibration_data = calibration.calibration_data

    await db.commit()
    await db.refresh(device)

    return CalibrationResponse(
        calibration_type=device.calibration_type,
        calibration_data=device.calibration_data,
    )


@router.get("/{device_id}/calibration", response_model=CalibrationResponse)
async def get_calibration(
    device_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get current calibration settings for a device."""
    device = await db.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    return CalibrationResponse(
        calibration_type=device.calibration_type,
        calibration_data=device.calibration_data,
    )


@router.post("/{device_id}/calibration/test", response_model=CalibrationTestResponse)
async def test_calibration(
    device_id: str,
    test_data: CalibrationTestRequest,
    db: AsyncSession = Depends(get_db),
):
    """Test calibration by providing raw values and getting calibrated results.

    Provide one or more of:
    - angle: Tilt angle (for polynomial calibration)
    - raw_gravity: Raw specific gravity value
    - raw_temperature: Raw temperature value

    Returns the calibrated gravity and/or temperature based on the device's
    current calibration settings.
    """
    device = await db.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    calibration_type = device.calibration_type or "none"
    calibration_data = device.calibration_data or {}

    response = CalibrationTestResponse()

    # Test gravity calibration
    if test_data.raw_gravity is not None or test_data.angle is not None:
        gravity = test_data.raw_gravity

        if calibration_type == "offset":
            # Apply offset
            if gravity is not None:
                sg_offset = calibration_data.get("sg_offset", 0.0)
                response.calibrated_gravity = gravity + sg_offset

        elif calibration_type == "polynomial":
            # Apply polynomial from angle
            if test_data.angle is not None:
                coefficients = calibration_data.get("coefficients", [])
                if coefficients:
                    response.calibrated_gravity = calibration_service.apply_polynomial(
                        test_data.angle, coefficients
                    )
            elif gravity is not None:
                # No angle provided but have gravity - just return it
                response.calibrated_gravity = gravity

        elif calibration_type == "linear":
            # Apply linear interpolation
            if gravity is not None:
                points_data = calibration_data.get("points", [])
                if points_data:
                    from ..services.calibration import linear_interpolate
                    points = [(p[0], p[1]) for p in points_data]
                    response.calibrated_gravity = linear_interpolate(gravity, points)

        elif calibration_type == "none":
            # No calibration
            if test_data.angle is not None:
                # Can't process angle without calibration
                response.calibrated_gravity = None
            elif gravity is not None:
                response.calibrated_gravity = gravity

    # Test temperature calibration
    if test_data.raw_temperature is not None:
        temperature = test_data.raw_temperature

        if calibration_type in ("offset", "polynomial"):
            # Apply offset
            temp_offset = calibration_data.get("temp_offset", 0.0)
            response.calibrated_temperature = temperature + temp_offset

        elif calibration_type == "linear":
            # Apply linear interpolation if temp_points exist
            temp_points_data = calibration_data.get("temp_points", [])
            if temp_points_data:
                from ..services.calibration import linear_interpolate
                points = [(p[0], p[1]) for p in temp_points_data]
                response.calibrated_temperature = linear_interpolate(temperature, points)
            else:
                # No temp points - return uncalibrated
                response.calibrated_temperature = temperature

        elif calibration_type == "none":
            # No calibration
            response.calibrated_temperature = temperature

    return response
