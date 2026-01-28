"""Home Assistant device control adapter.

Wraps the existing HAClient to provide the DeviceControlAdapter interface.
"""

import logging

from .base import DeviceControlAdapter, DeviceInfo

# Import HAClient - use try/except to support both installed package and test contexts
try:
    from backend.services.ha_client import HAClient
except ImportError:
    from ha_client import HAClient

logger = logging.getLogger(__name__)


class HAAdapter(DeviceControlAdapter):
    """Control devices via Home Assistant REST API.

    Entity ID format: ha://<entity_id> or just <entity_id> for backward compat
    Examples:
        - ha://switch.fermentation_heater
        - switch.fermentation_cooler (legacy format)
    """

    def __init__(self, url: str, token: str):
        """Initialize with HA connection details.

        Args:
            url: Home Assistant URL (e.g., http://homeassistant.local:8123)
            token: Long-lived access token
        """
        self._client = HAClient(url, token)

    def _parse_entity_id(self, entity_id: str) -> str:
        """Strip ha:// prefix if present."""
        if entity_id.startswith("ha://"):
            return entity_id[5:]
        return entity_id

    async def get_state(self, entity_id: str) -> str | None:
        """Get current state of a switch entity.

        Returns "on", "off", or None if unavailable.
        """
        ha_entity_id = self._parse_entity_id(entity_id)
        state_data = await self._client.get_state(ha_entity_id)

        if not state_data:
            return None

        state = state_data.get("state", "").lower()
        if state in ("on", "off"):
            return state
        elif state == "unavailable":
            logger.warning(f"HA entity {ha_entity_id} is unavailable")
            return None
        else:
            logger.debug(f"HA entity {ha_entity_id} has unexpected state: {state}")
            return None

    async def set_state(self, entity_id: str, state: str) -> bool:
        """Turn switch on or off via HA service call.

        Args:
            entity_id: Switch entity ID (with or without ha:// prefix)
            state: "on" or "off"

        Returns:
            True if service call succeeded
        """
        ha_entity_id = self._parse_entity_id(entity_id)

        if state not in ("on", "off"):
            logger.error(f"Invalid state '{state}' - must be 'on' or 'off'")
            return False

        service = "turn_on" if state == "on" else "turn_off"
        success = await self._client.call_service("switch", service, ha_entity_id)

        if success:
            logger.debug(f"HA: Set {ha_entity_id} to {state}")
        else:
            logger.error(f"HA: Failed to set {ha_entity_id} to {state}")

        return success

    async def test_connection(self) -> bool:
        """Test HA API connectivity."""
        return await self._client.test_connection()

    async def discover_devices(self) -> list[DeviceInfo]:
        """Discover switch entities from Home Assistant."""
        entities = await self._client.get_entities_by_domain(["switch", "input_boolean"])

        return [
            DeviceInfo(
                entity_id=f"ha://{e['entity_id']}",
                name=e["friendly_name"],
                device_type="switch",
                state=e["state"] if e["state"] in ("on", "off") else None,
            )
            for e in entities
        ]

    async def get_power_usage(self, entity_id: str) -> float | None:
        """Get power usage from HA entity attributes (if available)."""
        ha_entity_id = self._parse_entity_id(entity_id)
        state_data = await self._client.get_state(ha_entity_id)

        if not state_data:
            return None

        # Some switch entities expose power via attributes
        attrs = state_data.get("attributes", {})
        # Common attribute names for power
        for key in ("current_power_w", "power", "power_w", "current_power"):
            if key in attrs:
                try:
                    return float(attrs[key])
                except (TypeError, ValueError):
                    pass
        return None

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.close()
