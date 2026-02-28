"""MQTT Client Service for Home Assistant integration.

Publishes batch fermentation data to Home Assistant via MQTT auto-discovery.
Follows the singleton pattern like ha_client.py.
"""

import asyncio
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Optional aiomqtt import - graceful degradation if not installed
try:
    import aiomqtt
    AIOMQTT_AVAILABLE = True
except ImportError:
    AIOMQTT_AVAILABLE = False
    logger.info("aiomqtt not installed - MQTT features disabled")


class MQTTClient:
    """MQTT client for publishing batch data to Home Assistant."""

    def __init__(self):
        self._client: Optional["aiomqtt.Client"] = None
        self._connected = False
        self._config: dict = {}
        self._lock = asyncio.Lock()

    @property
    def is_connected(self) -> bool:
        return self._connected

    def configure(
        self,
        host: str,
        port: int = 1883,
        username: Optional[str] = None,
        password: Optional[str] = None,
        topic_prefix: str = "brewsignal",
    ) -> None:
        """Configure MQTT connection parameters."""
        self._config = {
            "host": host,
            "port": port,
            "username": username if username else None,
            "password": password if password else None,
            "topic_prefix": topic_prefix,
        }

    async def connect(self) -> bool:
        """Connect to MQTT broker."""
        if not AIOMQTT_AVAILABLE:
            logger.warning("aiomqtt not available - cannot connect")
            return False

        if not self._config.get("host"):
            logger.warning("MQTT host not configured")
            return False

        async with self._lock:
            try:
                # aiomqtt uses context manager, we'll create client on each publish
                # Test connection by creating a temporary client
                client = aiomqtt.Client(
                    hostname=self._config["host"],
                    port=self._config["port"],
                    username=self._config.get("username"),
                    password=self._config.get("password"),
                )
                async with client:
                    self._connected = True
                    logger.info("MQTT connected to %s:%d", self._config["host"], self._config["port"])
                    return True
            except Exception as e:
                self._connected = False
                logger.error("MQTT connection failed: %s", e)
                return False

    async def disconnect(self) -> None:
        """Disconnect from MQTT broker."""
        self._connected = False
        logger.info("MQTT disconnected")

    async def _get_client(self) -> Optional["aiomqtt.Client"]:
        """Get a new MQTT client instance."""
        if not AIOMQTT_AVAILABLE or not self._config.get("host"):
            return None

        return aiomqtt.Client(
            hostname=self._config["host"],
            port=self._config["port"],
            username=self._config.get("username"),
            password=self._config.get("password"),
        )

    # Stable entity IDs — all sensors share these fixed identifiers
    SENSOR_SUFFIXES = ["gravity", "temperature", "abv", "status", "days"]
    BINARY_SENSOR_SUFFIXES = ["heater", "cooler"]

    async def publish_discovery(self, batch_name: str) -> bool:
        """Publish Home Assistant auto-discovery configs with stable entity IDs.

        Uses fixed unique_ids (brewsignal_active_*) so entities persist across
        batches. The device name updates to reflect the current batch.

        Args:
            batch_name: Human-readable batch name (shown in HA device)

        Returns:
            True if discovery published successfully
        """
        if not AIOMQTT_AVAILABLE:
            return False

        client = await self._get_client()
        if not client:
            return False

        prefix = self._config.get("topic_prefix", "brewsignal")
        availability_topic = f"{prefix}/active/available"
        device_info = {
            "identifiers": ["brewsignal_active"],
            "name": f"BrewSignal: {batch_name}",
            "manufacturer": "BrewSignal",
            "model": "Fermentation Monitor",
        }

        # Sensor definitions
        sensors = [
            {
                "name": "Gravity",
                "unique_id": "brewsignal_active_gravity",
                "state_topic": f"{prefix}/active/gravity",
                "unit_of_measurement": "SG",
                "icon": "mdi:flask-outline",
                "device_class": None,
                "value_template": "{{ value }}",
            },
            {
                "name": "Temperature",
                "unique_id": "brewsignal_active_temperature",
                "state_topic": f"{prefix}/active/temperature",
                "unit_of_measurement": "°C",
                "device_class": "temperature",
                "value_template": "{{ value }}",
            },
            {
                "name": "ABV",
                "unique_id": "brewsignal_active_abv",
                "state_topic": f"{prefix}/active/abv",
                "unit_of_measurement": "%",
                "icon": "mdi:percent",
                "device_class": None,
                "value_template": "{{ value }}",
            },
            {
                "name": "Status",
                "unique_id": "brewsignal_active_status",
                "state_topic": f"{prefix}/active/status",
                "icon": "mdi:information-outline",
                "device_class": None,
                "value_template": "{{ value }}",
            },
            {
                "name": "Days Fermenting",
                "unique_id": "brewsignal_active_days",
                "state_topic": f"{prefix}/active/days_fermenting",
                "unit_of_measurement": "days",
                "icon": "mdi:calendar-clock",
                "device_class": None,
                "value_template": "{{ value }}",
            },
        ]

        # Binary sensors for heater/cooler state
        binary_sensors = [
            {
                "name": "Heater",
                "unique_id": "brewsignal_active_heater",
                "state_topic": f"{prefix}/active/heater_active",
                "payload_on": "ON",
                "payload_off": "OFF",
                "device_class": "heat",
            },
            {
                "name": "Cooler",
                "unique_id": "brewsignal_active_cooler",
                "state_topic": f"{prefix}/active/cooler_active",
                "payload_on": "ON",
                "payload_off": "OFF",
                "device_class": "cold",
            },
        ]

        try:
            async with client:
                # Publish sensor discovery configs
                for sensor in sensors:
                    config = {
                        "name": sensor["name"],
                        "unique_id": sensor["unique_id"],
                        "state_topic": sensor["state_topic"],
                        "device": device_info,
                        "availability_topic": availability_topic,
                        "value_template": sensor.get("value_template", "{{ value }}"),
                    }
                    if sensor.get("unit_of_measurement"):
                        config["unit_of_measurement"] = sensor["unit_of_measurement"]
                    if sensor.get("device_class"):
                        config["device_class"] = sensor["device_class"]
                    if sensor.get("icon"):
                        config["icon"] = sensor["icon"]

                    topic = f"homeassistant/sensor/{sensor['unique_id']}/config"
                    await client.publish(topic, json.dumps(config), retain=True)

                # Publish binary sensor discovery configs
                for sensor in binary_sensors:
                    config = {
                        "name": sensor["name"],
                        "unique_id": sensor["unique_id"],
                        "state_topic": sensor["state_topic"],
                        "device": device_info,
                        "availability_topic": availability_topic,
                        "payload_on": sensor["payload_on"],
                        "payload_off": sensor["payload_off"],
                    }
                    if sensor.get("device_class"):
                        config["device_class"] = sensor["device_class"]

                    topic = f"homeassistant/binary_sensor/{sensor['unique_id']}/config"
                    await client.publish(topic, json.dumps(config), retain=True)

                # Mark device as online
                await client.publish(availability_topic, "online", retain=True)

                logger.info("MQTT discovery published for %s (stable IDs)", batch_name)
                self._connected = True
                return True

        except Exception as e:
            logger.error("Failed to publish MQTT discovery: %s", e)
            self._connected = False
            return False

    async def publish_unavailable(self) -> bool:
        """Mark HA entities as unavailable (batch completed/deleted).

        Publishes "offline" to the availability topic so entities show
        "unavailable" in Home Assistant instead of being destroyed.

        Returns:
            True if published successfully
        """
        if not AIOMQTT_AVAILABLE:
            return False

        client = await self._get_client()
        if not client:
            return False

        prefix = self._config.get("topic_prefix", "brewsignal")

        try:
            async with client:
                await client.publish(
                    f"{prefix}/active/available", "offline", retain=True
                )
                logger.info("MQTT entities marked unavailable")
                self._connected = True
                return True

        except Exception as e:
            logger.error("Failed to mark MQTT unavailable: %s", e)
            self._connected = False
            return False

    async def remove_old_discovery(self, batch_id: int) -> bool:
        """Remove legacy per-batch discovery configs (one-time migration).

        Publishes empty payloads to old homeassistant/.../brewsignal_{batch_id}_*/config
        topics to clean up orphaned entities from the old per-batch scheme.

        Args:
            batch_id: Old batch ID whose entities should be removed

        Returns:
            True if removal published successfully
        """
        if not AIOMQTT_AVAILABLE:
            return False

        client = await self._get_client()
        if not client:
            return False

        try:
            async with client:
                for suffix in self.SENSOR_SUFFIXES:
                    topic = f"homeassistant/sensor/brewsignal_{batch_id}_{suffix}/config"
                    await client.publish(topic, "", retain=True)

                for suffix in self.BINARY_SENSOR_SUFFIXES:
                    topic = f"homeassistant/binary_sensor/brewsignal_{batch_id}_{suffix}/config"
                    await client.publish(topic, "", retain=True)

                logger.info("Removed old MQTT discovery for batch %d", batch_id)
                self._connected = True
                return True

        except Exception as e:
            logger.error("Failed to remove old MQTT discovery for batch %d: %s", batch_id, e)
            self._connected = False
            return False

    async def publish_reading(
        self,
        gravity: Optional[float] = None,
        temperature: Optional[float] = None,
        abv: Optional[float] = None,
        status: Optional[str] = None,
        days_fermenting: Optional[float] = None,
        heater_active: Optional[bool] = None,
        cooler_active: Optional[bool] = None,
    ) -> bool:
        """Publish sensor values to stable active topics.

        Fire-and-forget style - failures are logged but don't block.

        Args:
            gravity: Current gravity reading (SG)
            temperature: Current temperature in Celsius
            abv: Current calculated ABV percentage
            status: Batch status string
            days_fermenting: Days since fermentation started
            heater_active: Whether heater is currently on
            cooler_active: Whether cooler is currently on

        Returns:
            True if all publishes succeeded
        """
        if not AIOMQTT_AVAILABLE:
            return False

        client = await self._get_client()
        if not client:
            return False

        prefix = self._config.get("topic_prefix", "brewsignal")

        try:
            async with client:
                # Publish each value that was provided
                if gravity is not None:
                    await client.publish(
                        f"{prefix}/active/gravity",
                        f"{gravity:.4f}",
                    )

                if temperature is not None:
                    await client.publish(
                        f"{prefix}/active/temperature",
                        f"{temperature:.1f}",
                    )

                if abv is not None:
                    await client.publish(
                        f"{prefix}/active/abv",
                        f"{abv:.1f}",
                    )

                if status is not None:
                    await client.publish(
                        f"{prefix}/active/status",
                        status,
                    )

                if days_fermenting is not None:
                    await client.publish(
                        f"{prefix}/active/days_fermenting",
                        f"{days_fermenting:.1f}",
                    )

                if heater_active is not None:
                    await client.publish(
                        f"{prefix}/active/heater_active",
                        "ON" if heater_active else "OFF",
                    )

                if cooler_active is not None:
                    await client.publish(
                        f"{prefix}/active/cooler_active",
                        "ON" if cooler_active else "OFF",
                    )

                self._connected = True
                return True

        except Exception as e:
            logger.warning("Failed to publish MQTT reading: %s", e)
            self._connected = False
            return False

    async def test_connection(self, host: str, port: int, username: Optional[str], password: Optional[str]) -> dict:
        """Test MQTT connection with provided credentials.

        Returns:
            dict with 'success' bool and 'message' string
        """
        if not AIOMQTT_AVAILABLE:
            return {"success": False, "message": "aiomqtt library not installed"}

        try:
            client = aiomqtt.Client(
                hostname=host,
                port=port,
                username=username if username else None,
                password=password if password else None,
            )
            async with client:
                # Publish a test message
                await client.publish("brewsignal/test", "connection_test")
                return {"success": True, "message": f"Connected to {host}:{port}"}
        except Exception as e:
            return {"success": False, "message": str(e)}


# Global singleton instance
_mqtt_client: Optional[MQTTClient] = None


def get_mqtt_client() -> Optional[MQTTClient]:
    """Get the global MQTT client instance."""
    return _mqtt_client


def init_mqtt_client() -> MQTTClient:
    """Initialize the global MQTT client instance."""
    global _mqtt_client
    if _mqtt_client is None:
        _mqtt_client = MQTTClient()
    return _mqtt_client
