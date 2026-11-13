"""Calibration service for applying SG and temperature corrections.

A device's calibration lives on the device (devices.calibration_type and
calibration_data), which is what the Calibration page saves. Every ingest path
applies it through calibrate_values().

Calibration types:
- none: no calibration
- offset: additive offset (sg_offset, temp_offset)
- linear: linear interpolation between two or more points
- polynomial: polynomial from tilt angle (iSpindel style)

The calibration_points table is legacy and is no longer read or written.
"""

import logging
import math
from typing import Any, Optional, TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Device

if TYPE_CHECKING:
    from ..ingest.base import HydrometerReading

logger = logging.getLogger(__name__)


def linear_interpolate(x: float, points: list[tuple[float, float]]) -> float:
    """Apply linear interpolation/extrapolation to calibrate a value.

    Args:
        x: The raw value to calibrate
        points: List of (raw_value, actual_value) calibration points

    Returns:
        The calibrated value

    Algorithm:
        - 0 or 1 points: return x unchanged. One point is stored while the
          user builds the curve, but is not applied until a second point exists
          (adding points mid-batch must not shift readings early). Use
          calibration_type "offset" for a deliberate single-value correction.
        - 2+ points: find the two closest points bracketing x (or the two
          closest on one side for extrapolation) and interpolate linearly
    """
    # Points that share a raw value are one point (their mean). Two points at the
    # same raw value give no slope: without this, every reading beyond them came
    # back as one constant gravity.
    by_raw: dict[float, list[float]] = {}
    for raw, actual in points:
        by_raw.setdefault(raw, []).append(actual)
    points = sorted((raw, sum(vals) / len(vals)) for raw, vals in by_raw.items())

    if len(points) < 2:
        return x

    # Find bracketing points for interpolation
    # or edge points for extrapolation
    lower = None
    upper = None

    for raw, actual in points:
        if raw <= x:
            lower = (raw, actual)
        if raw >= x and upper is None:
            upper = (raw, actual)

    # Handle extrapolation cases
    if lower is None:
        # x is below all points, extrapolate from first two
        lower = points[0]
        upper = points[1]
    elif upper is None:
        # x is above all points, extrapolate from last two
        lower = points[-2]
        upper = points[-1]

    # Linear interpolation: y = y1 + (x - x1) * (y2 - y1) / (x2 - x1)
    x1, y1 = lower
    x2, y2 = upper

    if x2 == x1:
        # Avoid division by zero if points have same raw value
        return y1

    slope = (y2 - y1) / (x2 - x1)
    return y1 + (x - x1) * slope


def calibrate_values(
    calibration_type: Optional[str],
    calibration_data: Optional[dict],
    gravity: Optional[float],
    temperature: Optional[float],
    angle: Optional[float] = None,
) -> tuple[Optional[float], Optional[float]]:
    """Apply a device's calibration (devices.calibration_type / calibration_data)
    to one gravity and temperature value. The single implementation used by every
    ingest path: BLE (Tilt, RAPT), gateway and HTTP.

    The Calibration page saves to these device fields. Until tilt_ui-9ywh the BLE
    and gateway paths read the legacy calibration_points table instead, so a
    calibration saved on the page was never applied to a Tilt.
    """
    calibration_type = calibration_type or "none"
    data = calibration_data or {}

    if gravity is not None:
        if calibration_type == "offset":
            gravity = gravity + data.get("sg_offset", 0.0)
        elif calibration_type == "polynomial":
            # iSpindel-style polynomial from angle
            coefficients = data.get("coefficients", [])
            if angle is not None and coefficients:
                gravity = apply_polynomial(angle, coefficients)
        elif calibration_type == "linear":
            # The API stores "points"; "sg_points" is the legacy key
            sg_points = data.get("points") or data.get("sg_points", [])
            if sg_points:
                gravity = linear_interpolate(gravity, [(p[0], p[1]) for p in sg_points])

    if temperature is not None:
        if calibration_type in ("offset", "polynomial"):
            temperature = temperature + data.get("temp_offset", 0.0)
        elif calibration_type == "linear":
            temp_points = data.get("temp_points", [])
            if temp_points:
                temperature = linear_interpolate(temperature, [(p[0], p[1]) for p in temp_points])

    return gravity, temperature


def apply_polynomial(angle: float, coefficients: list[float]) -> float:
    """Polynomial calibration: SG = a*x^n + b*x^(n-1) + ... + c, coefficients highest degree first."""
    if not coefficients:
        return 0.0
    result = 0.0
    degree = len(coefficients) - 1
    for i, coef in enumerate(coefficients):
        result += coef * (angle ** (degree - i))
    return result


_bad_calibration_logged: set[str] = set()


def _calibrate_or_raw(device: Device, gravity, temperature, angle=None):
    """calibrate_values for a device, falling back to the raw values if the stored
    calibration is unusable (corrupt JSON, null numbers, malformed points).

    A reading must never be lost to bad calibration data: a missing reading looks
    like a dead sensor to the temperature controller, which then switches the
    heater and cooler off. The problem is logged once per device.
    """
    try:
        cal_sg, cal_temp = calibrate_values(
            device.calibration_type, device.calibration_data, gravity, temperature, angle,
        )
        for raw, cal in ((gravity, cal_sg), (temperature, cal_temp)):
            # A number in must give a finite number out (null or duplicate points can give None/NaN)
            if raw is not None and not (isinstance(cal, (int, float)) and math.isfinite(cal)):
                raise ValueError(f"calibration produced {cal!r}")
        return cal_sg, cal_temp
    except Exception as e:
        if device.id not in _bad_calibration_logged:
            _bad_calibration_logged.add(device.id)
            logger.error(
                "Device %s: stored calibration cannot be applied (%s: %s); using raw values. "
                "Save the calibration again on the Calibration page.",
                device.id, type(e).__name__, e,
            )
        return gravity, temperature


class CalibrationService:
    """Service for calibrating hydrometer readings."""

    async def calibrate_reading(
        self, db: AsyncSession, device_id: str, raw_sg: float, raw_temp: float
    ) -> tuple[float, float]:
        """Calibrate SG and temperature (Celsius) for a device, from the device's
        own calibration settings. Returns the raw values for an unknown device.

        The callers load the Device in the same session just before, so db.get is
        served from the session and costs no query.
        """
        device = await db.get(Device, device_id)
        if device is None:
            return raw_sg, raw_temp
        return _calibrate_or_raw(device, raw_sg, raw_temp)

    def convert_units(self, reading: "HydrometerReading") -> "HydrometerReading":
        """Convert raw values to standard units (SG, Celsius).

        Internal standard is Celsius for temperature per CLAUDE.md:
        - GravityMon/iSpindel: Already send Celsius (no conversion needed)
        - Tilt BLE: Has separate F→C conversion in main.py scanner callback

        Args:
            reading: HydrometerReading with raw values

        Returns:
            Reading with gravity/temperature filled from unit conversion
        """
        from ..ingest.base import GravityUnit, TemperatureUnit
        from ..ingest.units import fahrenheit_to_celsius, plato_to_sg

        # Temperature: Convert to Celsius if Fahrenheit
        # GravityMon/iSpindel already send Celsius, so this is mainly for any
        # future device types that might send Fahrenheit via HTTP ingest
        if reading.temperature_raw is not None:
            if reading.temperature_unit == TemperatureUnit.FAHRENHEIT:
                reading.temperature = fahrenheit_to_celsius(reading.temperature_raw)
            else:
                # Already in Celsius - pass through unchanged
                reading.temperature = reading.temperature_raw

        # Gravity: Convert to SG if Plato
        if reading.gravity_raw is not None:
            if reading.gravity_unit == GravityUnit.PLATO:
                reading.gravity = plato_to_sg(reading.gravity_raw)
            else:
                reading.gravity = reading.gravity_raw

        return reading

    def apply_polynomial(self, angle: float, coefficients: list[float]) -> float:
        """See module-level apply_polynomial."""
        return apply_polynomial(angle, coefficients)

    async def calibrate_device_reading(
        self,
        db: AsyncSession,
        device: Device,
        reading: "HydrometerReading",
    ) -> "HydrometerReading":
        """Apply the device's calibration to a reading (already unit-converted)."""
        reading.gravity, reading.temperature = _calibrate_or_raw(
            device, reading.gravity, reading.temperature, reading.angle,
        )
        return reading

    async def get_or_create_device(
        self,
        db: AsyncSession,
        device_id: str,
        device_type: str,
        name: Optional[str] = None,
        **kwargs: Any,
    ) -> Device:
        """Get existing device or create a new one.

        Args:
            db: Database session
            device_id: Unique device identifier
            device_type: Type of device (tilt, ispindel, gravitymon, floaty)
            name: Display name for the device
            **kwargs: Additional device fields (color, mac, native_gravity_unit, etc.)

        Returns:
            Device model instance
        """
        result = await db.execute(select(Device).where(Device.id == device_id))
        device = result.scalar_one_or_none()

        if device is None:
            device = Device(
                id=device_id,
                device_type=device_type,
                name=name or device_id,
                calibration_type="none",
                **kwargs,
            )
            db.add(device)
            await db.flush()

        return device


# Global calibration service instance
calibration_service = CalibrationService()
