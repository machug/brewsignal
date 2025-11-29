# backend/models_device.py
"""Device model - kept separate to control migration order.

This model is NOT part of Base.metadata.create_all initially.
Migration creates the table manually and migrates data from tilts.
After migration, this can be merged into models.py.
"""

import json
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class Device(Base):
    """Universal hydrometer device registry."""
    __tablename__ = "devices"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    device_type: Mapped[str] = mapped_column(String(20), nullable=False, default="tilt")
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    display_name: Mapped[Optional[str]] = mapped_column(String(100))

    # Current assignment
    beer_name: Mapped[Optional[str]] = mapped_column(String(100))
    original_gravity: Mapped[Optional[float]] = mapped_column()

    # Native units (for display and conversion)
    native_gravity_unit: Mapped[str] = mapped_column(String(10), default="sg")
    native_temp_unit: Mapped[str] = mapped_column(String(5), default="f")

    # Calibration - stored as JSON string, use properties for access
    calibration_type: Mapped[str] = mapped_column(String(20), default="none")
    _calibration_data: Mapped[Optional[str]] = mapped_column("calibration_data", Text)

    @property
    def calibration_data(self) -> Optional[dict[str, Any]]:
        """Get calibration data as dict."""
        if self._calibration_data:
            return json.loads(self._calibration_data)
        return None

    @calibration_data.setter
    def calibration_data(self, value: Optional[dict[str, Any]]) -> None:
        """Set calibration data from dict."""
        if value is not None:
            self._calibration_data = json.dumps(value)
        else:
            self._calibration_data = None

    # Security
    auth_token: Mapped[Optional[str]] = mapped_column(String(100))

    # Status
    last_seen: Mapped[Optional[datetime]] = mapped_column()
    battery_voltage: Mapped[Optional[float]] = mapped_column()
    firmware_version: Mapped[Optional[str]] = mapped_column(String(50))

    # Legacy compatibility (Tilt-specific)
    color: Mapped[Optional[str]] = mapped_column(String(20))
    mac: Mapped[Optional[str]] = mapped_column(String(17))

    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
