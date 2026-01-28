"""Device control abstraction layer.

Provides unified device control across different backends:
- Home Assistant (ha://)
- Direct Shelly HTTP (shelly://) - planned
- Gateway relay (gateway://) - planned

Usage:
    from backend.services.device_control import (
        init_device_router,
        get_device_router,
        RouterConfig,
    )

    # Initialize at startup
    config = RouterConfig(
        ha_enabled=True,
        ha_url="http://homeassistant.local:8123",
        ha_token="your-token",
    )
    router = init_device_router(config)

    # Control devices
    state = await router.get_state("ha://switch.heater")
    await router.set_state("ha://switch.heater", "on")
"""

from .base import (
    DeviceControlAdapter,
    DeviceControlError,
    DeviceInfo,
)
from .ha_adapter import HAAdapter
from .shelly_adapter import ShellyDirectAdapter
from .router import (
    DeviceControlRouter,
    RouterConfig,
    get_device_router,
    init_device_router,
    close_device_router,
)

__all__ = [
    # Base
    "DeviceControlAdapter",
    "DeviceControlError",
    "DeviceInfo",
    # Adapters
    "HAAdapter",
    "ShellyDirectAdapter",
    # Router
    "DeviceControlRouter",
    "RouterConfig",
    "get_device_router",
    "init_device_router",
    "close_device_router",
]
