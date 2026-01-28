"""Device control router - dispatches to appropriate adapter by entity ID prefix.

Entity ID schemes:
- ha://switch.entity_name - Home Assistant
- shelly://192.168.1.50/0 - Direct Shelly HTTP (future)
- gateway://BSG-123/192.168.1.50/0 - Gateway relay (future)

For backward compatibility, entity IDs without a scheme prefix are assumed
to be Home Assistant entities (e.g., "switch.heat_mat" = "ha://switch.heat_mat").
"""

import logging
from dataclasses import dataclass

from .base import DeviceControlAdapter, DeviceInfo, DeviceControlError
from .ha_adapter import HAAdapter

logger = logging.getLogger(__name__)


@dataclass
class RouterConfig:
    """Configuration for the device control router."""
    # Home Assistant config
    ha_enabled: bool = False
    ha_url: str | None = None
    ha_token: str | None = None

    # Direct Shelly config (future - tilt_ui-amh)
    shelly_enabled: bool = False

    # Gateway relay config (future - tilt_ui-123)
    gateway_enabled: bool = False


class DeviceControlRouter:
    """Routes control commands to the appropriate adapter based on entity ID.

    The router lazily initializes adapters when first needed and caches them
    for reuse. Use reconfigure() to update settings at runtime.
    """

    def __init__(self, config: RouterConfig | None = None):
        """Initialize router with optional config.

        Args:
            config: Router configuration. Can be updated later via reconfigure().
        """
        self._config = config or RouterConfig()
        self._adapters: dict[str, DeviceControlAdapter] = {}
        self._initialized = False

    def reconfigure(self, config: RouterConfig) -> None:
        """Update configuration and reinitialize adapters.

        Call this when config values change (e.g., HA URL/token updated).
        """
        # Check if config actually changed
        if (self._config.ha_url == config.ha_url and
            self._config.ha_token == config.ha_token and
            self._config.ha_enabled == config.ha_enabled):
            return  # No change

        logger.info("Device control router reconfiguring")
        self._config = config
        self._initialized = False
        # Clear cached adapters - they'll be recreated on next use
        self._adapters.clear()

    def _ensure_initialized(self) -> None:
        """Lazily initialize adapters based on config."""
        if self._initialized:
            return

        # Home Assistant adapter
        if self._config.ha_enabled and self._config.ha_url and self._config.ha_token:
            self._adapters["ha"] = HAAdapter(self._config.ha_url, self._config.ha_token)
            logger.info(f"HA adapter initialized: {self._config.ha_url}")

        # Shelly direct adapter (future - tilt_ui-amh)
        if self._config.shelly_enabled:
            # self._adapters["shelly"] = ShellyDirectAdapter()
            logger.info("Shelly direct adapter: not yet implemented")

        # Gateway relay adapter (future - tilt_ui-123)
        if self._config.gateway_enabled:
            # self._adapters["gateway"] = GatewayRelayAdapter(...)
            logger.info("Gateway relay adapter: not yet implemented")

        self._initialized = True

    def _parse_scheme(self, entity_id: str) -> tuple[str, str]:
        """Parse entity ID into (scheme, entity).

        Returns:
            Tuple of (scheme, entity_id_without_scheme)
            For unschemed IDs, returns ("ha", entity_id) for backward compat.
        """
        if "://" in entity_id:
            scheme, rest = entity_id.split("://", 1)
            return scheme.lower(), rest
        else:
            # Legacy format without scheme - assume HA
            return "ha", entity_id

    def _get_adapter(self, entity_id: str) -> DeviceControlAdapter:
        """Get appropriate adapter for entity ID.

        Raises:
            DeviceControlError: If no adapter available for the scheme
        """
        self._ensure_initialized()

        scheme, _ = self._parse_scheme(entity_id)

        if scheme not in self._adapters:
            available = list(self._adapters.keys()) or ["none"]
            raise DeviceControlError(
                f"No adapter for scheme '{scheme}' (entity: {entity_id}). "
                f"Available: {', '.join(available)}"
            )

        return self._adapters[scheme]

    def has_adapter(self, entity_id: str) -> bool:
        """Check if an adapter is available for the given entity ID."""
        self._ensure_initialized()
        scheme, _ = self._parse_scheme(entity_id)
        return scheme in self._adapters

    async def get_state(self, entity_id: str) -> str | None:
        """Get device state, routing to appropriate adapter.

        Args:
            entity_id: Full entity ID with scheme (e.g., ha://switch.heater)
                      or legacy HA format (e.g., switch.heater)

        Returns:
            "on", "off", or None
        """
        adapter = self._get_adapter(entity_id)
        return await adapter.get_state(entity_id)

    async def set_state(self, entity_id: str, state: str) -> bool:
        """Set device state, routing to appropriate adapter.

        Args:
            entity_id: Full entity ID with scheme
            state: "on" or "off"

        Returns:
            True if successful
        """
        adapter = self._get_adapter(entity_id)
        return await adapter.set_state(entity_id, state)

    async def test_connection(self, scheme: str = "ha") -> bool:
        """Test connection for a specific backend.

        Args:
            scheme: Backend scheme to test (default: "ha")

        Returns:
            True if connection works
        """
        self._ensure_initialized()

        if scheme not in self._adapters:
            return False

        return await self._adapters[scheme].test_connection()

    async def discover_devices(self, scheme: str | None = None) -> list[DeviceInfo]:
        """Discover devices from one or all backends.

        Args:
            scheme: Specific backend to query, or None for all

        Returns:
            List of discovered devices
        """
        self._ensure_initialized()

        if scheme:
            if scheme not in self._adapters:
                return []
            return await self._adapters[scheme].discover_devices()

        # Discover from all adapters
        all_devices: list[DeviceInfo] = []
        for adapter in self._adapters.values():
            devices = await adapter.discover_devices()
            all_devices.extend(devices)

        return all_devices

    async def get_power_usage(self, entity_id: str) -> float | None:
        """Get power usage, routing to appropriate adapter."""
        adapter = self._get_adapter(entity_id)
        return await adapter.get_power_usage(entity_id)

    async def close(self) -> None:
        """Close all adapters."""
        for adapter in self._adapters.values():
            await adapter.close()
        self._adapters.clear()
        self._initialized = False


# Global router instance
_router: DeviceControlRouter | None = None


def get_device_router() -> DeviceControlRouter | None:
    """Get the global device control router."""
    return _router


def init_device_router(config: RouterConfig) -> DeviceControlRouter:
    """Initialize or reconfigure the global device control router."""
    global _router

    if _router is None:
        _router = DeviceControlRouter(config)
    else:
        _router.reconfigure(config)

    return _router


async def close_device_router() -> None:
    """Close the global device control router."""
    global _router
    if _router:
        await _router.close()
        _router = None
