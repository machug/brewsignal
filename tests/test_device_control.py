"""Tests for the device control abstraction layer.

Tests cover:
- DeviceControlAdapter ABC contract
- HAAdapter with mocked HTTP responses
- DeviceControlRouter routing and entity ID parsing
- Error handling and edge cases
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import asdict
import sys
from pathlib import Path

# Add backend to path - import device_control subpackage directly
# to avoid services/__init__.py which triggers database imports
backend_path = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_path / "services"))
sys.path.insert(0, str(backend_path))


class TestDeviceInfo:
    """Tests for DeviceInfo dataclass."""

    def test_device_info_creation(self):
        from device_control.base import DeviceInfo

        info = DeviceInfo(
            entity_id="ha://switch.heater",
            name="Fermentation Heater",
            device_type="switch",
            state="off",
        )

        assert info.entity_id == "ha://switch.heater"
        assert info.name == "Fermentation Heater"
        assert info.device_type == "switch"
        assert info.state == "off"
        assert info.power_w is None
        assert info.extra is None

    def test_device_info_with_power(self):
        from device_control.base import DeviceInfo

        info = DeviceInfo(
            entity_id="shelly://192.168.1.50/0",
            name="Heat Mat",
            device_type="relay",
            state="on",
            power_w=45.2,
        )

        assert info.power_w == 45.2

    def test_device_info_to_dict(self):
        from device_control.base import DeviceInfo

        info = DeviceInfo(
            entity_id="ha://switch.test",
            name="Test",
            device_type="switch",
            state="on",
        )

        d = asdict(info)
        assert d["entity_id"] == "ha://switch.test"
        assert d["state"] == "on"


class TestDeviceControlAdapter:
    """Tests for DeviceControlAdapter ABC."""

    def test_adapter_is_abstract(self):
        from device_control.base import DeviceControlAdapter

        with pytest.raises(TypeError, match="abstract"):
            DeviceControlAdapter()

    def test_adapter_requires_get_state(self):
        from device_control.base import DeviceControlAdapter

        class IncompleteAdapter(DeviceControlAdapter):
            async def set_state(self, entity_id, state):
                pass

            async def test_connection(self):
                pass

        with pytest.raises(TypeError, match="get_state"):
            IncompleteAdapter()

    def test_adapter_requires_set_state(self):
        from device_control.base import DeviceControlAdapter

        class IncompleteAdapter(DeviceControlAdapter):
            async def get_state(self, entity_id):
                pass

            async def test_connection(self):
                pass

        with pytest.raises(TypeError, match="set_state"):
            IncompleteAdapter()

    def test_adapter_requires_test_connection(self):
        from device_control.base import DeviceControlAdapter

        class IncompleteAdapter(DeviceControlAdapter):
            async def get_state(self, entity_id):
                pass

            async def set_state(self, entity_id, state):
                pass

        with pytest.raises(TypeError, match="test_connection"):
            IncompleteAdapter()

    @pytest.mark.asyncio
    async def test_adapter_default_discover_devices(self):
        from device_control.base import DeviceControlAdapter

        class MinimalAdapter(DeviceControlAdapter):
            async def get_state(self, entity_id):
                return "on"

            async def set_state(self, entity_id, state):
                return True

            async def test_connection(self):
                return True

        adapter = MinimalAdapter()
        devices = await adapter.discover_devices()
        assert devices == []

    @pytest.mark.asyncio
    async def test_adapter_default_get_power_usage(self):
        from device_control.base import DeviceControlAdapter

        class MinimalAdapter(DeviceControlAdapter):
            async def get_state(self, entity_id):
                return "on"

            async def set_state(self, entity_id, state):
                return True

            async def test_connection(self):
                return True

        adapter = MinimalAdapter()
        power = await adapter.get_power_usage("test")
        assert power is None


class TestHAAdapter:
    """Tests for HAAdapter with mocked HTTP responses."""

    @pytest.fixture
    def mock_ha_client(self):
        """Create a mock HAClient."""
        with patch("device_control.ha_adapter.HAClient") as mock_class:
            mock_client = AsyncMock()
            mock_class.return_value = mock_client
            yield mock_client

    def test_ha_adapter_init(self, mock_ha_client):
        from device_control.ha_adapter import HAAdapter

        adapter = HAAdapter("http://ha.local:8123", "test-token")
        assert adapter._client is not None

    def test_parse_entity_id_with_prefix(self, mock_ha_client):
        from device_control.ha_adapter import HAAdapter

        adapter = HAAdapter("http://ha.local", "token")
        assert adapter._parse_entity_id("ha://switch.heater") == "switch.heater"

    def test_parse_entity_id_without_prefix(self, mock_ha_client):
        from device_control.ha_adapter import HAAdapter

        adapter = HAAdapter("http://ha.local", "token")
        # Legacy format without prefix should pass through unchanged
        assert adapter._parse_entity_id("switch.heater") == "switch.heater"

    @pytest.mark.asyncio
    async def test_get_state_returns_on(self, mock_ha_client):
        from device_control.ha_adapter import HAAdapter

        mock_ha_client.get_state.return_value = {"state": "on"}

        adapter = HAAdapter("http://ha.local", "token")
        state = await adapter.get_state("ha://switch.heater")

        assert state == "on"
        mock_ha_client.get_state.assert_called_once_with("switch.heater")

    @pytest.mark.asyncio
    async def test_get_state_returns_off(self, mock_ha_client):
        from device_control.ha_adapter import HAAdapter

        mock_ha_client.get_state.return_value = {"state": "off"}

        adapter = HAAdapter("http://ha.local", "token")
        state = await adapter.get_state("switch.cooler")

        assert state == "off"

    @pytest.mark.asyncio
    async def test_get_state_unavailable_returns_none(self, mock_ha_client):
        from device_control.ha_adapter import HAAdapter

        mock_ha_client.get_state.return_value = {"state": "unavailable"}

        adapter = HAAdapter("http://ha.local", "token")
        state = await adapter.get_state("switch.offline")

        assert state is None

    @pytest.mark.asyncio
    async def test_get_state_not_found_returns_none(self, mock_ha_client):
        from device_control.ha_adapter import HAAdapter

        mock_ha_client.get_state.return_value = None

        adapter = HAAdapter("http://ha.local", "token")
        state = await adapter.get_state("switch.nonexistent")

        assert state is None

    @pytest.mark.asyncio
    async def test_set_state_on_success(self, mock_ha_client):
        from device_control.ha_adapter import HAAdapter

        mock_ha_client.call_service.return_value = True

        adapter = HAAdapter("http://ha.local", "token")
        result = await adapter.set_state("ha://switch.heater", "on")

        assert result is True
        mock_ha_client.call_service.assert_called_once_with(
            "switch", "turn_on", "switch.heater"
        )

    @pytest.mark.asyncio
    async def test_set_state_off_success(self, mock_ha_client):
        from device_control.ha_adapter import HAAdapter

        mock_ha_client.call_service.return_value = True

        adapter = HAAdapter("http://ha.local", "token")
        result = await adapter.set_state("switch.heater", "off")

        assert result is True
        mock_ha_client.call_service.assert_called_once_with(
            "switch", "turn_off", "switch.heater"
        )

    @pytest.mark.asyncio
    async def test_set_state_invalid_state(self, mock_ha_client):
        from device_control.ha_adapter import HAAdapter

        adapter = HAAdapter("http://ha.local", "token")
        result = await adapter.set_state("switch.heater", "invalid")

        assert result is False
        mock_ha_client.call_service.assert_not_called()

    @pytest.mark.asyncio
    async def test_set_state_failure(self, mock_ha_client):
        from device_control.ha_adapter import HAAdapter

        mock_ha_client.call_service.return_value = False

        adapter = HAAdapter("http://ha.local", "token")
        result = await adapter.set_state("switch.heater", "on")

        assert result is False

    @pytest.mark.asyncio
    async def test_test_connection(self, mock_ha_client):
        from device_control.ha_adapter import HAAdapter

        mock_ha_client.test_connection.return_value = True

        adapter = HAAdapter("http://ha.local", "token")
        result = await adapter.test_connection()

        assert result is True

    @pytest.mark.asyncio
    async def test_discover_devices(self, mock_ha_client):
        from device_control.ha_adapter import HAAdapter

        mock_ha_client.get_entities_by_domain.return_value = [
            {"entity_id": "switch.heater", "friendly_name": "Heater", "state": "on"},
            {"entity_id": "switch.cooler", "friendly_name": "Cooler", "state": "off"},
        ]

        adapter = HAAdapter("http://ha.local", "token")
        devices = await adapter.discover_devices()

        assert len(devices) == 2
        assert devices[0].entity_id == "ha://switch.heater"
        assert devices[0].name == "Heater"
        assert devices[0].state == "on"
        assert devices[1].entity_id == "ha://switch.cooler"
        assert devices[1].state == "off"

    @pytest.mark.asyncio
    async def test_get_power_usage_from_attributes(self, mock_ha_client):
        from device_control.ha_adapter import HAAdapter

        mock_ha_client.get_state.return_value = {
            "state": "on",
            "attributes": {"current_power_w": 42.5},
        }

        adapter = HAAdapter("http://ha.local", "token")
        power = await adapter.get_power_usage("switch.heater")

        assert power == 42.5

    @pytest.mark.asyncio
    async def test_get_power_usage_no_attribute(self, mock_ha_client):
        from device_control.ha_adapter import HAAdapter

        mock_ha_client.get_state.return_value = {
            "state": "on",
            "attributes": {},
        }

        adapter = HAAdapter("http://ha.local", "token")
        power = await adapter.get_power_usage("switch.heater")

        assert power is None

    @pytest.mark.asyncio
    async def test_close(self, mock_ha_client):
        from device_control.ha_adapter import HAAdapter

        adapter = HAAdapter("http://ha.local", "token")
        await adapter.close()

        mock_ha_client.close.assert_called_once()


class TestRouterConfig:
    """Tests for RouterConfig dataclass."""

    def test_default_config(self):
        from device_control.router import RouterConfig

        config = RouterConfig()

        assert config.ha_enabled is False
        assert config.ha_url is None
        assert config.ha_token is None
        assert config.shelly_enabled is False
        assert config.gateway_enabled is False

    def test_ha_config(self):
        from device_control.router import RouterConfig

        config = RouterConfig(
            ha_enabled=True,
            ha_url="http://ha.local:8123",
            ha_token="secret-token",
        )

        assert config.ha_enabled is True
        assert config.ha_url == "http://ha.local:8123"
        assert config.ha_token == "secret-token"


class TestDeviceControlRouter:
    """Tests for DeviceControlRouter."""

    @pytest.fixture
    def mock_ha_adapter(self):
        """Create a mock HAAdapter."""
        with patch("device_control.router.HAAdapter") as mock_class:
            mock_adapter = AsyncMock()
            mock_class.return_value = mock_adapter
            yield mock_adapter

    def test_router_init_no_config(self):
        from device_control.router import DeviceControlRouter

        router = DeviceControlRouter()

        assert router._config is not None
        assert router._initialized is False

    def test_router_init_with_config(self):
        from device_control.router import DeviceControlRouter, RouterConfig

        config = RouterConfig(ha_enabled=True, ha_url="http://ha", ha_token="tok")
        router = DeviceControlRouter(config)

        assert router._config.ha_enabled is True

    def test_parse_scheme_with_ha_prefix(self):
        from device_control.router import DeviceControlRouter

        router = DeviceControlRouter()
        scheme, entity = router._parse_scheme("ha://switch.heater")

        assert scheme == "ha"
        assert entity == "switch.heater"

    def test_parse_scheme_with_shelly_prefix(self):
        from device_control.router import DeviceControlRouter

        router = DeviceControlRouter()
        scheme, entity = router._parse_scheme("shelly://192.168.1.50/0")

        assert scheme == "shelly"
        assert entity == "192.168.1.50/0"

    def test_parse_scheme_with_gateway_prefix(self):
        from device_control.router import DeviceControlRouter

        router = DeviceControlRouter()
        scheme, entity = router._parse_scheme("gateway://BSG-123/192.168.1.50/0")

        assert scheme == "gateway"
        assert entity == "BSG-123/192.168.1.50/0"

    def test_parse_scheme_without_prefix_defaults_to_ha(self):
        from device_control.router import DeviceControlRouter

        router = DeviceControlRouter()
        scheme, entity = router._parse_scheme("switch.heater")

        # Legacy format should default to HA
        assert scheme == "ha"
        assert entity == "switch.heater"

    def test_parse_scheme_case_insensitive(self):
        from device_control.router import DeviceControlRouter

        router = DeviceControlRouter()
        scheme, _ = router._parse_scheme("HA://switch.heater")

        assert scheme == "ha"

    def test_has_adapter_false_when_not_configured(self):
        from device_control.router import DeviceControlRouter, RouterConfig

        router = DeviceControlRouter(RouterConfig())

        assert router.has_adapter("ha://switch.test") is False

    def test_has_adapter_true_when_configured(self, mock_ha_adapter):
        from device_control.router import DeviceControlRouter, RouterConfig

        config = RouterConfig(ha_enabled=True, ha_url="http://ha", ha_token="tok")
        router = DeviceControlRouter(config)

        assert router.has_adapter("ha://switch.test") is True

    def test_has_adapter_false_for_unconfigured_scheme(self, mock_ha_adapter):
        from device_control.router import DeviceControlRouter, RouterConfig

        config = RouterConfig(ha_enabled=True, ha_url="http://ha", ha_token="tok")
        router = DeviceControlRouter(config)

        # Shelly not enabled
        assert router.has_adapter("shelly://192.168.1.50/0") is False

    @pytest.mark.asyncio
    async def test_get_state_routes_to_ha(self, mock_ha_adapter):
        from device_control.router import DeviceControlRouter, RouterConfig

        mock_ha_adapter.get_state.return_value = "on"

        config = RouterConfig(ha_enabled=True, ha_url="http://ha", ha_token="tok")
        router = DeviceControlRouter(config)

        state = await router.get_state("ha://switch.heater")

        assert state == "on"
        mock_ha_adapter.get_state.assert_called_once_with("ha://switch.heater")

    @pytest.mark.asyncio
    async def test_get_state_legacy_format_routes_to_ha(self, mock_ha_adapter):
        from device_control.router import DeviceControlRouter, RouterConfig

        mock_ha_adapter.get_state.return_value = "off"

        config = RouterConfig(ha_enabled=True, ha_url="http://ha", ha_token="tok")
        router = DeviceControlRouter(config)

        # Legacy format without scheme prefix
        state = await router.get_state("switch.heater")

        assert state == "off"

    @pytest.mark.asyncio
    async def test_set_state_routes_to_ha(self, mock_ha_adapter):
        from device_control.router import DeviceControlRouter, RouterConfig

        mock_ha_adapter.set_state.return_value = True

        config = RouterConfig(ha_enabled=True, ha_url="http://ha", ha_token="tok")
        router = DeviceControlRouter(config)

        result = await router.set_state("ha://switch.heater", "on")

        assert result is True
        mock_ha_adapter.set_state.assert_called_once_with("ha://switch.heater", "on")

    @pytest.mark.asyncio
    async def test_get_state_raises_for_unknown_scheme(self, mock_ha_adapter):
        from device_control.router import DeviceControlRouter, RouterConfig
        from device_control.base import DeviceControlError

        config = RouterConfig(ha_enabled=True, ha_url="http://ha", ha_token="tok")
        router = DeviceControlRouter(config)

        with pytest.raises(DeviceControlError, match="No adapter for scheme 'shelly'"):
            await router.get_state("shelly://192.168.1.50/0")

    @pytest.mark.asyncio
    async def test_set_state_raises_for_unknown_scheme(self, mock_ha_adapter):
        from device_control.router import DeviceControlRouter, RouterConfig
        from device_control.base import DeviceControlError

        config = RouterConfig(ha_enabled=True, ha_url="http://ha", ha_token="tok")
        router = DeviceControlRouter(config)

        with pytest.raises(DeviceControlError, match="No adapter for scheme 'gateway'"):
            await router.set_state("gateway://BSG-123/192.168.1.50/0", "on")

    @pytest.mark.asyncio
    async def test_test_connection(self, mock_ha_adapter):
        from device_control.router import DeviceControlRouter, RouterConfig

        mock_ha_adapter.test_connection.return_value = True

        config = RouterConfig(ha_enabled=True, ha_url="http://ha", ha_token="tok")
        router = DeviceControlRouter(config)

        result = await router.test_connection("ha")

        assert result is True

    @pytest.mark.asyncio
    async def test_test_connection_unknown_scheme(self, mock_ha_adapter):
        from device_control.router import DeviceControlRouter, RouterConfig

        config = RouterConfig(ha_enabled=True, ha_url="http://ha", ha_token="tok")
        router = DeviceControlRouter(config)

        result = await router.test_connection("shelly")

        assert result is False

    @pytest.mark.asyncio
    async def test_discover_devices_single_adapter(self, mock_ha_adapter):
        from device_control.router import DeviceControlRouter, RouterConfig
        from device_control.base import DeviceInfo

        mock_ha_adapter.discover_devices.return_value = [
            DeviceInfo("ha://switch.heater", "Heater", "switch", "on"),
        ]

        config = RouterConfig(ha_enabled=True, ha_url="http://ha", ha_token="tok")
        router = DeviceControlRouter(config)

        devices = await router.discover_devices("ha")

        assert len(devices) == 1
        assert devices[0].entity_id == "ha://switch.heater"

    @pytest.mark.asyncio
    async def test_discover_devices_all_adapters(self, mock_ha_adapter):
        from device_control.router import DeviceControlRouter, RouterConfig
        from device_control.base import DeviceInfo

        mock_ha_adapter.discover_devices.return_value = [
            DeviceInfo("ha://switch.heater", "Heater", "switch", "on"),
            DeviceInfo("ha://switch.cooler", "Cooler", "switch", "off"),
        ]

        config = RouterConfig(ha_enabled=True, ha_url="http://ha", ha_token="tok")
        router = DeviceControlRouter(config)

        devices = await router.discover_devices()  # No scheme = all

        assert len(devices) == 2

    @pytest.mark.asyncio
    async def test_get_power_usage(self, mock_ha_adapter):
        from device_control.router import DeviceControlRouter, RouterConfig

        mock_ha_adapter.get_power_usage.return_value = 42.0

        config = RouterConfig(ha_enabled=True, ha_url="http://ha", ha_token="tok")
        router = DeviceControlRouter(config)

        power = await router.get_power_usage("ha://switch.heater")

        assert power == 42.0

    def test_reconfigure_updates_config(self, mock_ha_adapter):
        from device_control.router import DeviceControlRouter, RouterConfig

        config1 = RouterConfig(ha_enabled=True, ha_url="http://ha1", ha_token="tok1")
        router = DeviceControlRouter(config1)

        # Force initialization
        router._ensure_initialized()
        assert router._initialized is True

        # Reconfigure with different URL
        config2 = RouterConfig(ha_enabled=True, ha_url="http://ha2", ha_token="tok2")
        router.reconfigure(config2)

        # Should reset initialized flag
        assert router._initialized is False
        assert router._config.ha_url == "http://ha2"

    def test_reconfigure_no_change_skips_reinit(self, mock_ha_adapter):
        from device_control.router import DeviceControlRouter, RouterConfig

        config = RouterConfig(ha_enabled=True, ha_url="http://ha", ha_token="tok")
        router = DeviceControlRouter(config)

        router._ensure_initialized()
        assert router._initialized is True

        # Reconfigure with same values
        router.reconfigure(config)

        # Should NOT reset since config unchanged
        assert router._initialized is True

    @pytest.mark.asyncio
    async def test_close_cleans_up(self, mock_ha_adapter):
        from device_control.router import DeviceControlRouter, RouterConfig

        config = RouterConfig(ha_enabled=True, ha_url="http://ha", ha_token="tok")
        router = DeviceControlRouter(config)

        # Force init
        router._ensure_initialized()
        assert len(router._adapters) == 1

        await router.close()

        assert len(router._adapters) == 0
        assert router._initialized is False
        mock_ha_adapter.close.assert_called_once()


class TestGlobalRouterFunctions:
    """Tests for module-level router functions."""

    def test_get_device_router_initially_none(self):
        from device_control import router as router_module

        # Reset global state
        router_module._router = None

        result = router_module.get_device_router()
        assert result is None

    def test_init_device_router_creates_router(self):
        from device_control import router as router_module
        from device_control.router import RouterConfig

        # Reset global state
        router_module._router = None

        with patch("device_control.router.HAAdapter"):
            config = RouterConfig(ha_enabled=True, ha_url="http://ha", ha_token="tok")
            router = router_module.init_device_router(config)

            assert router is not None
            assert router_module.get_device_router() is router

    def test_init_device_router_reconfigures_existing(self):
        from device_control import router as router_module
        from device_control.router import RouterConfig

        with patch("device_control.router.HAAdapter"):
            config1 = RouterConfig(ha_enabled=True, ha_url="http://ha1", ha_token="t1")
            router1 = router_module.init_device_router(config1)

            config2 = RouterConfig(ha_enabled=True, ha_url="http://ha2", ha_token="t2")
            router2 = router_module.init_device_router(config2)

            # Should be same instance, just reconfigured
            assert router1 is router2
            assert router2._config.ha_url == "http://ha2"

    @pytest.mark.asyncio
    async def test_close_device_router(self):
        from device_control import router as router_module
        from device_control.router import RouterConfig

        with patch("device_control.router.HAAdapter") as mock_ha:
            mock_ha.return_value = AsyncMock()

            config = RouterConfig(ha_enabled=True, ha_url="http://ha", ha_token="tok")
            router_module.init_device_router(config)

            await router_module.close_device_router()

            assert router_module.get_device_router() is None


class TestShellyDirectAdapter:
    """Tests for ShellyDirectAdapter with mocked HTTP responses."""

    @pytest.fixture
    def mock_httpx_client(self):
        """Create a mock httpx.AsyncClient."""
        with patch("device_control.shelly_adapter.httpx.AsyncClient") as mock_class:
            mock_client = AsyncMock()
            mock_client.is_closed = False
            mock_class.return_value = mock_client
            yield mock_client

    def _make_response(self, status_code: int, json_data: dict = None):
        """Helper to create a mock response.

        Note: httpx response.json() is sync, not async.
        """
        response = MagicMock()
        response.status_code = status_code
        if json_data is not None:
            response.json.return_value = json_data
        return response

    # --- Entity ID Parsing ---

    def test_parse_entity_id_basic(self):
        from device_control.shelly_adapter import ShellyDirectAdapter

        adapter = ShellyDirectAdapter()
        ip, channel = adapter._parse_entity_id("shelly://192.168.1.50/0")

        assert ip == "192.168.1.50"
        assert channel == 0

    def test_parse_entity_id_different_channel(self):
        from device_control.shelly_adapter import ShellyDirectAdapter

        adapter = ShellyDirectAdapter()
        ip, channel = adapter._parse_entity_id("shelly://192.168.1.50/1")

        assert ip == "192.168.1.50"
        assert channel == 1

    def test_parse_entity_id_default_channel(self):
        from device_control.shelly_adapter import ShellyDirectAdapter

        adapter = ShellyDirectAdapter()
        # No channel specified - should default to 0
        ip, channel = adapter._parse_entity_id("shelly://192.168.1.50")

        assert ip == "192.168.1.50"
        assert channel == 0

    def test_parse_entity_id_with_port(self):
        from device_control.shelly_adapter import ShellyDirectAdapter

        adapter = ShellyDirectAdapter()
        ip, channel = adapter._parse_entity_id("shelly://192.168.1.50:8080/0")

        assert ip == "192.168.1.50:8080"
        assert channel == 0

    def test_parse_entity_id_without_scheme(self):
        from device_control.shelly_adapter import ShellyDirectAdapter

        adapter = ShellyDirectAdapter()
        # Should handle raw IP as well
        ip, channel = adapter._parse_entity_id("192.168.1.50/0")

        assert ip == "192.168.1.50"
        assert channel == 0

    # --- Gen2 API (RPC) ---

    @pytest.mark.asyncio
    async def test_get_state_gen2_on(self, mock_httpx_client):
        from device_control.shelly_adapter import ShellyDirectAdapter

        # Gen2 response
        mock_httpx_client.get.return_value = self._make_response(
            200, {"output": True, "apower": 42.5}
        )

        adapter = ShellyDirectAdapter()
        state = await adapter.get_state("shelly://192.168.1.50/0")

        assert state == "on"
        mock_httpx_client.get.assert_called_once()
        call_url = mock_httpx_client.get.call_args[0][0]
        assert "rpc/Switch.GetStatus" in call_url

    @pytest.mark.asyncio
    async def test_get_state_gen2_off(self, mock_httpx_client):
        from device_control.shelly_adapter import ShellyDirectAdapter

        mock_httpx_client.get.return_value = self._make_response(200, {"output": False})

        adapter = ShellyDirectAdapter()
        state = await adapter.get_state("shelly://192.168.1.50/0")

        assert state == "off"

    @pytest.mark.asyncio
    async def test_set_state_gen2_on(self, mock_httpx_client):
        from device_control.shelly_adapter import ShellyDirectAdapter

        mock_httpx_client.get.return_value = self._make_response(200, {"was_on": False})

        adapter = ShellyDirectAdapter()
        result = await adapter.set_state("shelly://192.168.1.50/0", "on")

        assert result is True
        call_url = mock_httpx_client.get.call_args[0][0]
        assert "rpc/Switch.Set" in call_url
        assert "on=true" in call_url

    @pytest.mark.asyncio
    async def test_set_state_gen2_off(self, mock_httpx_client):
        from device_control.shelly_adapter import ShellyDirectAdapter

        mock_httpx_client.get.return_value = self._make_response(200, {"was_on": True})

        adapter = ShellyDirectAdapter()
        result = await adapter.set_state("shelly://192.168.1.50/0", "off")

        assert result is True
        call_url = mock_httpx_client.get.call_args[0][0]
        assert "on=false" in call_url

    # --- Gen1 API Fallback ---

    @pytest.mark.asyncio
    async def test_get_state_gen1_fallback_on(self, mock_httpx_client):
        from device_control.shelly_adapter import ShellyDirectAdapter

        # Gen2 fails (404), Gen1 succeeds
        mock_httpx_client.get.side_effect = [
            self._make_response(404),
            self._make_response(200, {"ison": True, "power": 45.0}),
        ]

        adapter = ShellyDirectAdapter()
        state = await adapter.get_state("shelly://192.168.1.50/0")

        assert state == "on"
        assert mock_httpx_client.get.call_count == 2

    @pytest.mark.asyncio
    async def test_get_state_gen1_fallback_off(self, mock_httpx_client):
        from device_control.shelly_adapter import ShellyDirectAdapter

        mock_httpx_client.get.side_effect = [
            self._make_response(404),
            self._make_response(200, {"ison": False}),
        ]

        adapter = ShellyDirectAdapter()
        state = await adapter.get_state("shelly://192.168.1.50/0")

        assert state == "off"

    @pytest.mark.asyncio
    async def test_set_state_gen1_fallback(self, mock_httpx_client):
        from device_control.shelly_adapter import ShellyDirectAdapter

        # Gen2 fails, Gen1 succeeds
        mock_httpx_client.get.side_effect = [
            self._make_response(404),
            self._make_response(200, {"ison": True}),
        ]

        adapter = ShellyDirectAdapter()
        result = await adapter.set_state("shelly://192.168.1.50/0", "on")

        assert result is True
        # Second call should be Gen1 format
        gen1_call_url = mock_httpx_client.get.call_args_list[1][0][0]
        assert "/relay/0" in gen1_call_url
        assert "turn=on" in gen1_call_url

    # --- Error Handling ---

    @pytest.mark.asyncio
    async def test_get_state_device_offline(self, mock_httpx_client):
        from device_control.shelly_adapter import ShellyDirectAdapter
        import httpx

        mock_httpx_client.get.side_effect = httpx.ConnectError("Connection refused")

        adapter = ShellyDirectAdapter()
        state = await adapter.get_state("shelly://192.168.1.50/0")

        assert state is None

    @pytest.mark.asyncio
    async def test_set_state_device_offline(self, mock_httpx_client):
        from device_control.shelly_adapter import ShellyDirectAdapter
        import httpx

        mock_httpx_client.get.side_effect = httpx.ConnectError("Connection refused")

        adapter = ShellyDirectAdapter()
        result = await adapter.set_state("shelly://192.168.1.50/0", "on")

        assert result is False

    @pytest.mark.asyncio
    async def test_get_state_both_apis_fail(self, mock_httpx_client):
        from device_control.shelly_adapter import ShellyDirectAdapter

        # Both Gen2 and Gen1 fail
        mock_httpx_client.get.return_value = self._make_response(500)

        adapter = ShellyDirectAdapter()
        state = await adapter.get_state("shelly://192.168.1.50/0")

        assert state is None

    @pytest.mark.asyncio
    async def test_set_state_invalid_state(self, mock_httpx_client):
        from device_control.shelly_adapter import ShellyDirectAdapter

        adapter = ShellyDirectAdapter()
        result = await adapter.set_state("shelly://192.168.1.50/0", "invalid")

        assert result is False
        mock_httpx_client.get.assert_not_called()

    # --- Power Usage ---

    @pytest.mark.asyncio
    async def test_get_power_usage_gen2(self, mock_httpx_client):
        from device_control.shelly_adapter import ShellyDirectAdapter

        mock_httpx_client.get.return_value = self._make_response(
            200, {"output": True, "apower": 42.5}
        )

        adapter = ShellyDirectAdapter()
        power = await adapter.get_power_usage("shelly://192.168.1.50/0")

        assert power == 42.5

    @pytest.mark.asyncio
    async def test_get_power_usage_gen1(self, mock_httpx_client):
        from device_control.shelly_adapter import ShellyDirectAdapter

        # Gen2 fails, Gen1 succeeds with power
        mock_httpx_client.get.side_effect = [
            self._make_response(404),
            self._make_response(200, {"ison": True, "power": 38.2}),
        ]

        adapter = ShellyDirectAdapter()
        power = await adapter.get_power_usage("shelly://192.168.1.50/0")

        assert power == 38.2

    @pytest.mark.asyncio
    async def test_get_power_usage_not_available(self, mock_httpx_client):
        from device_control.shelly_adapter import ShellyDirectAdapter

        # Device without power meter
        mock_httpx_client.get.return_value = self._make_response(
            200, {"output": True}  # No apower field
        )

        adapter = ShellyDirectAdapter()
        power = await adapter.get_power_usage("shelly://192.168.1.50/0")

        assert power is None

    # --- Connection Test ---

    @pytest.mark.asyncio
    async def test_test_connection_success(self, mock_httpx_client):
        from device_control.shelly_adapter import ShellyDirectAdapter

        mock_httpx_client.get.return_value = self._make_response(
            200, {"id": "shellyplus1pm-abc123"}
        )

        adapter = ShellyDirectAdapter()
        # Need to register a device first
        adapter._devices["192.168.1.50"] = {"gen": 2}
        result = await adapter.test_connection()

        assert result is True

    @pytest.mark.asyncio
    async def test_test_connection_no_devices(self, mock_httpx_client):
        from device_control.shelly_adapter import ShellyDirectAdapter

        adapter = ShellyDirectAdapter()
        # No devices registered
        result = await adapter.test_connection()

        # Should return True (no devices to test = nothing broken)
        assert result is True

    # --- Device Caching ---

    @pytest.mark.asyncio
    async def test_caches_device_generation(self, mock_httpx_client):
        from device_control.shelly_adapter import ShellyDirectAdapter

        # First call - Gen2 succeeds
        mock_httpx_client.get.return_value = self._make_response(200, {"output": True})

        adapter = ShellyDirectAdapter()

        # First call discovers it's Gen2
        await adapter.get_state("shelly://192.168.1.50/0")
        first_call_count = mock_httpx_client.get.call_count

        # Second call should skip Gen2 detection
        await adapter.get_state("shelly://192.168.1.50/0")
        second_call_count = mock_httpx_client.get.call_count

        # Should only make 1 call on second request (cached Gen2)
        assert second_call_count == first_call_count + 1

    @pytest.mark.asyncio
    async def test_close(self, mock_httpx_client):
        from device_control.shelly_adapter import ShellyDirectAdapter

        # Need to trigger client creation first
        mock_httpx_client.get.return_value = self._make_response(200, {"output": True})

        adapter = ShellyDirectAdapter()
        await adapter.get_state("shelly://192.168.1.50/0")  # Creates client
        await adapter.close()

        mock_httpx_client.aclose.assert_called_once()
