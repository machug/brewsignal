"""Device control abstraction layer.

This module provides a unified interface for controlling smart devices
(heaters, coolers) across different backends:
- Home Assistant (existing)
- Direct Shelly HTTP (planned)
- Gateway relay (planned)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class DeviceInfo:
    """Information about a discovered device."""
    entity_id: str
    name: str
    device_type: str  # "switch", "relay", etc.
    state: str | None  # "on", "off", or None if unknown
    power_w: float | None = None  # Power consumption if available
    extra: dict[str, Any] | None = None


class DeviceControlAdapter(ABC):
    """Abstract base class for device control backends.

    Each adapter handles a specific control mechanism (HA, Shelly direct, etc.)
    and provides a unified interface for the temperature controller.
    """

    @abstractmethod
    async def get_state(self, entity_id: str) -> str | None:
        """Get current state of a device.

        Args:
            entity_id: Device identifier (format depends on adapter)

        Returns:
            "on", "off", or None if state cannot be determined
        """
        pass

    @abstractmethod
    async def set_state(self, entity_id: str, state: str) -> bool:
        """Set device state.

        Args:
            entity_id: Device identifier
            state: "on" or "off"

        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
    async def test_connection(self) -> bool:
        """Test if the backend is reachable and configured correctly.

        Returns:
            True if connection is working
        """
        pass

    async def discover_devices(self) -> list[DeviceInfo]:
        """Discover available devices.

        Not all adapters support discovery. Default returns empty list.
        """
        return []

    async def get_power_usage(self, entity_id: str) -> float | None:
        """Get current power consumption in watts.

        Not all adapters/devices support power monitoring.
        """
        return None

    async def close(self) -> None:
        """Clean up resources. Override if adapter needs cleanup."""
        pass


class DeviceControlError(Exception):
    """Error during device control operation."""
    pass
