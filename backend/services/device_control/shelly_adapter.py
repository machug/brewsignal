"""Direct Shelly device control adapter.

Controls Shelly smart plugs/relays directly via HTTP without Home Assistant.
Supports both Gen1 (original Shelly) and Gen2 (Shelly Plus/Pro) APIs.

Entity ID format: shelly://<ip>[:<port>][/<channel>]
Examples:
    - shelly://192.168.1.50/0
    - shelly://192.168.1.50 (defaults to channel 0)
    - shelly://192.168.1.50:8080/1
"""

import logging
from typing import Optional

import httpx

from .base import DeviceControlAdapter, DeviceInfo

logger = logging.getLogger(__name__)

# Timeout for HTTP requests to Shelly devices (local network should be fast)
REQUEST_TIMEOUT = 5.0


class ShellyDirectAdapter(DeviceControlAdapter):
    """Direct HTTP control of Shelly devices.

    Automatically detects Gen1 vs Gen2 API and caches the result per device.
    """

    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None
        # Cache device info: {ip: {"gen": 1|2, "model": "...", ...}}
        self._devices: dict[str, dict] = {}

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=REQUEST_TIMEOUT)
        return self._client

    def _parse_entity_id(self, entity_id: str) -> tuple[str, int]:
        """Parse entity ID into (ip, channel).

        Args:
            entity_id: Format shelly://ip[:port][/channel] or ip/channel

        Returns:
            Tuple of (ip_with_optional_port, channel)
        """
        # Strip shelly:// prefix if present
        if entity_id.startswith("shelly://"):
            entity_id = entity_id[9:]

        # Split into ip and channel
        if "/" in entity_id:
            parts = entity_id.rsplit("/", 1)
            ip = parts[0]
            try:
                channel = int(parts[1])
            except ValueError:
                channel = 0
        else:
            ip = entity_id
            channel = 0

        return ip, channel

    def _get_cached_gen(self, ip: str) -> Optional[int]:
        """Get cached device generation (1 or 2), or None if not cached."""
        if ip in self._devices:
            return self._devices[ip].get("gen")
        return None

    def _cache_device(self, ip: str, gen: int, model: str = "") -> None:
        """Cache device info after successful detection."""
        self._devices[ip] = {"gen": gen, "model": model}
        logger.debug(f"Cached Shelly device: {ip} as Gen{gen} ({model})")

    async def _try_gen2_get_status(
        self, client: httpx.AsyncClient, ip: str, channel: int
    ) -> Optional[dict]:
        """Try Gen2 RPC API to get switch status.

        Returns response dict if successful, None if failed/not Gen2.
        """
        url = f"http://{ip}/rpc/Switch.GetStatus?id={channel}"
        try:
            response = await client.get(url)
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            logger.debug(f"Gen2 API failed for {ip}: {e}")
        return None

    async def _try_gen1_get_status(
        self, client: httpx.AsyncClient, ip: str, channel: int
    ) -> Optional[dict]:
        """Try Gen1 legacy API to get relay status.

        Returns response dict if successful, None if failed.
        """
        url = f"http://{ip}/relay/{channel}"
        try:
            response = await client.get(url)
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            logger.debug(f"Gen1 API failed for {ip}: {e}")
        return None

    async def _try_gen2_set(
        self, client: httpx.AsyncClient, ip: str, channel: int, on: bool
    ) -> bool:
        """Try Gen2 RPC API to set switch state.

        Returns True if successful.
        """
        url = f"http://{ip}/rpc/Switch.Set?id={channel}&on={'true' if on else 'false'}"
        try:
            response = await client.get(url)
            return response.status_code == 200
        except Exception as e:
            logger.debug(f"Gen2 set failed for {ip}: {e}")
        return False

    async def _try_gen1_set(
        self, client: httpx.AsyncClient, ip: str, channel: int, on: bool
    ) -> bool:
        """Try Gen1 legacy API to set relay state.

        Returns True if successful.
        """
        turn = "on" if on else "off"
        url = f"http://{ip}/relay/{channel}?turn={turn}"
        try:
            response = await client.get(url)
            return response.status_code == 200
        except Exception as e:
            logger.debug(f"Gen1 set failed for {ip}: {e}")
        return False

    async def get_state(self, entity_id: str) -> Optional[str]:
        """Get current state of Shelly switch.

        Tries Gen2 API first, falls back to Gen1 if needed.
        Caches the device generation for future calls.

        Returns:
            "on", "off", or None if device unreachable
        """
        ip, channel = self._parse_entity_id(entity_id)
        client = await self._get_client()
        cached_gen = self._get_cached_gen(ip)

        # If we know it's Gen1, skip Gen2 attempt
        if cached_gen == 1:
            data = await self._try_gen1_get_status(client, ip, channel)
            if data is not None:
                return "on" if data.get("ison") else "off"
            return None

        # Try Gen2 first
        data = await self._try_gen2_get_status(client, ip, channel)
        if data is not None:
            self._cache_device(ip, 2)
            return "on" if data.get("output") else "off"

        # Fall back to Gen1
        data = await self._try_gen1_get_status(client, ip, channel)
        if data is not None:
            self._cache_device(ip, 1)
            return "on" if data.get("ison") else "off"

        logger.warning(f"Failed to get state from Shelly {ip}")
        return None

    async def set_state(self, entity_id: str, state: str) -> bool:
        """Set Shelly switch state.

        Args:
            entity_id: Shelly entity ID
            state: "on" or "off"

        Returns:
            True if successful
        """
        if state not in ("on", "off"):
            logger.error(f"Invalid state '{state}' - must be 'on' or 'off'")
            return False

        ip, channel = self._parse_entity_id(entity_id)
        client = await self._get_client()
        on = state == "on"
        cached_gen = self._get_cached_gen(ip)

        # If we know it's Gen1, skip Gen2 attempt
        if cached_gen == 1:
            success = await self._try_gen1_set(client, ip, channel, on)
            if success:
                logger.info(f"Shelly {ip} channel {channel} -> {state}")
            return success

        # Try Gen2 first
        if await self._try_gen2_set(client, ip, channel, on):
            self._cache_device(ip, 2)
            logger.info(f"Shelly {ip} (Gen2) channel {channel} -> {state}")
            return True

        # Fall back to Gen1
        if await self._try_gen1_set(client, ip, channel, on):
            self._cache_device(ip, 1)
            logger.info(f"Shelly {ip} (Gen1) channel {channel} -> {state}")
            return True

        logger.error(f"Failed to set Shelly {ip} to {state}")
        return False

    async def test_connection(self) -> bool:
        """Test if any registered Shelly devices are reachable.

        Returns True if no devices registered or at least one is reachable.
        """
        if not self._devices:
            return True  # No devices to test

        client = await self._get_client()
        for ip, info in self._devices.items():
            gen = info.get("gen", 2)
            try:
                if gen == 2:
                    url = f"http://{ip}/rpc/Shelly.GetDeviceInfo"
                else:
                    url = f"http://{ip}/shelly"

                response = await client.get(url)
                if response.status_code == 200:
                    return True
            except Exception:
                continue

        return False

    async def get_power_usage(self, entity_id: str) -> Optional[float]:
        """Get current power consumption in watts.

        Only available on power-monitoring models (Plug, PM variants).
        """
        ip, channel = self._parse_entity_id(entity_id)
        client = await self._get_client()
        cached_gen = self._get_cached_gen(ip)

        # If we know it's Gen1, skip Gen2 attempt
        if cached_gen == 1:
            data = await self._try_gen1_get_status(client, ip, channel)
            if data is not None:
                return data.get("power")  # Gen1 uses "power"
            return None

        # Try Gen2 first
        data = await self._try_gen2_get_status(client, ip, channel)
        if data is not None:
            self._cache_device(ip, 2)
            return data.get("apower")  # Gen2 uses "apower" (active power)

        # Fall back to Gen1
        data = await self._try_gen1_get_status(client, ip, channel)
        if data is not None:
            self._cache_device(ip, 1)
            return data.get("power")

        return None

    async def discover_devices(self) -> list[DeviceInfo]:
        """Discover Shelly devices on local network via mDNS.

        Note: This requires the zeroconf library and network access.
        Returns empty list if discovery is not available.
        """
        # TODO: Implement mDNS discovery using zeroconf
        # For now, return cached devices
        devices = []
        for ip, info in self._devices.items():
            devices.append(
                DeviceInfo(
                    entity_id=f"shelly://{ip}/0",
                    name=info.get("model", f"Shelly {ip}"),
                    device_type="relay",
                    state=None,  # Would need to query
                )
            )
        return devices

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
