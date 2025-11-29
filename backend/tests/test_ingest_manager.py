"""Tests for IngestManager device auto-registration."""

import pytest
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Device, Reading
from backend.services.ingest_manager import ingest_manager


@pytest.mark.asyncio
class TestIngestManagerAutoRegistration:
    """Test device auto-registration on first reading."""

    async def test_tilt_auto_registration(self, test_db: AsyncSession):
        """Test auto-registration for Tilt device on first reading."""
        # Tilt payload example (BLE format)
        payload = {
            "color": "RED",
            "temp_f": 68,
            "sg": 1.050,
            "rssi": -75,
        }

        # Verify no device exists initially
        result = await test_db.execute(select(Device).where(Device.id == "RED"))
        device = result.scalar_one_or_none()
        assert device is None

        # Ingest reading - should auto-register device
        reading = await ingest_manager.ingest(
            db=test_db,
            payload=payload,
            source_protocol="http",
        )

        # Verify reading was created
        assert reading is not None
        assert reading.device_type == "tilt"

        # Verify device was auto-registered
        result = await test_db.execute(select(Device).where(Device.id == "RED"))
        device = result.scalar_one_or_none()
        assert device is not None
        assert device.id == "RED"
        assert device.device_type == "tilt"
        assert device.name == "RED"
        assert device.color == "RED"
        assert device.native_gravity_unit == "sg"
        assert device.native_temp_unit == "f"
        assert device.calibration_type == "none"
        assert device.last_seen is not None

    async def test_ispindel_auto_registration(self, test_db: AsyncSession):
        """Test auto-registration for iSpindel device on first reading."""
        # iSpindel payload example
        payload = {
            "name": "iSpindel001",
            "ID": 123456,
            "angle": 25.5,
            "temperature": 20.5,
            "temp_units": "C",
            "battery": 3.8,
            "gravity": 12.5,
            "interval": 900,
            "RSSI": -65,
        }

        # Verify no device exists initially
        result = await test_db.execute(select(Device).where(Device.id == "iSpindel001"))
        device = result.scalar_one_or_none()
        assert device is None

        # Ingest reading - should auto-register device
        reading = await ingest_manager.ingest(
            db=test_db,
            payload=payload,
            source_protocol="http",
        )

        # Verify reading was created
        assert reading is not None
        assert reading.device_type == "ispindel"

        # Verify device was auto-registered
        result = await test_db.execute(select(Device).where(Device.id == "123456"))
        device = result.scalar_one_or_none()
        assert device is not None
        assert device.id == "123456"
        assert device.device_type == "ispindel"
        assert device.name == "123456"
        assert device.native_gravity_unit == "sg"  # iSpindel default is SG
        assert device.native_temp_unit == "c"
        assert device.calibration_type == "none"
        assert device.last_seen is not None
        assert device.battery_voltage == 3.8

    async def test_gravitymon_auto_registration(self, test_db: AsyncSession):
        """Test auto-registration for GravityMon device on first reading."""
        # GravityMon payload example (needs corr-gravity or run-time to be detected as GravityMon)
        payload = {
            "name": "gravmon01",
            "ID": "GM001",
            "angle": 30.2,
            "temperature": 20.5,  # GravityMon native is Celsius
            "temp-units": "C",
            "battery": 4.1,
            "gravity": 1.048,
            "corr-gravity": 1.048,  # This marks it as GravityMon
            "gravity-unit": "G",
            "interval": 600,
            "RSSI": -58,
        }

        # Verify no device exists initially
        result = await test_db.execute(select(Device).where(Device.id == "gravmon01"))
        device = result.scalar_one_or_none()
        assert device is None

        # Ingest reading - should auto-register device
        reading = await ingest_manager.ingest(
            db=test_db,
            payload=payload,
            source_protocol="http",
        )

        # Verify reading was created
        assert reading is not None
        assert reading.device_type == "gravitymon"

        # Verify device was auto-registered
        result = await test_db.execute(select(Device).where(Device.id == "GM001"))
        device = result.scalar_one_or_none()
        assert device is not None
        assert device.id == "GM001"
        assert device.device_type == "gravitymon"
        assert device.name == "GM001"
        assert device.native_gravity_unit == "sg"
        assert device.native_temp_unit == "c"  # GravityMon native is Celsius
        assert device.calibration_type == "none"
        assert device.last_seen is not None
        assert device.battery_voltage == 4.1

    async def test_subsequent_readings_update_not_duplicate(self, test_db: AsyncSession):
        """Test that subsequent readings update existing device, not create duplicates."""
        # First reading
        payload1 = {
            "color": "BLUE",
            "temp_f": 68,
            "sg": 1.050,
        }

        reading1 = await ingest_manager.ingest(
            db=test_db,
            payload=payload1,
            source_protocol="http",
        )
        assert reading1 is not None

        # Get device and its last_seen timestamp
        result = await test_db.execute(select(Device).where(Device.id == "BLUE"))
        device1 = result.scalar_one_or_none()
        assert device1 is not None
        first_seen = device1.last_seen

        # Count devices
        result = await test_db.execute(select(Device))
        devices = result.scalars().all()
        assert len(devices) == 1

        # Second reading from same device
        payload2 = {
            "color": "BLUE",
            "temp_f": 70,
            "sg": 1.048,
        }

        reading2 = await ingest_manager.ingest(
            db=test_db,
            payload=payload2,
            source_protocol="http",
        )
        assert reading2 is not None

        # Verify still only one device
        result = await test_db.execute(select(Device))
        devices = result.scalars().all()
        assert len(devices) == 1

        # Verify device was updated, not duplicated
        result = await test_db.execute(select(Device).where(Device.id == "BLUE"))
        device2 = result.scalar_one_or_none()
        assert device2 is not None
        assert device2.id == device1.id
        # Note: last_seen should be updated, but we can't reliably test exact timing
        assert device2.last_seen is not None

        # Verify two readings exist
        result = await test_db.execute(
            select(Reading).where(Reading.device_id == device1.id)
        )
        readings = result.scalars().all()
        assert len(readings) == 2

    async def test_device_type_set_correctly(self, test_db: AsyncSession):
        """Test that device_type is set correctly based on reading type."""
        # Test Tilt
        tilt_payload = {
            "color": "GREEN",
            "temp_f": 68,
            "sg": 1.050,
        }
        await ingest_manager.ingest(db=test_db, payload=tilt_payload)

        result = await test_db.execute(select(Device).where(Device.id == "GREEN"))
        tilt_device = result.scalar_one_or_none()
        assert tilt_device is not None
        assert tilt_device.device_type == "tilt"

        # Test iSpindel
        ispindel_payload = {
            "name": "iSpindel002",
            "ID": 123457,
            "angle": 25.5,
            "temperature": 20.5,
            "temp_units": "C",
            "battery": 3.8,
            "gravity": 12.5,
        }
        await ingest_manager.ingest(db=test_db, payload=ispindel_payload)

        result = await test_db.execute(select(Device).where(Device.id == "123457"))
        ispindel_device = result.scalar_one_or_none()
        assert ispindel_device is not None
        assert ispindel_device.device_type == "ispindel"

        # Test GravityMon
        gravmon_payload = {
            "name": "gravmon02",
            "ID": "GM002",
            "angle": 30.2,
            "temperature": 20.5,
            "temp-units": "C",
            "battery": 4.1,
            "gravity": 1.048,
            "corr-gravity": 1.048,  # Marks as GravityMon
            "gravity-unit": "G",
        }
        await ingest_manager.ingest(db=test_db, payload=gravmon_payload)

        result = await test_db.execute(select(Device).where(Device.id == "GM002"))
        gravmon_device = result.scalar_one_or_none()
        assert gravmon_device is not None
        assert gravmon_device.device_type == "gravitymon"

    async def test_battery_voltage_updated(self, test_db: AsyncSession):
        """Test that battery voltage is updated with each reading."""
        # First reading with battery
        payload1 = {
            "name": "iSpindel003",
            "ID": 123458,
            "angle": 25.5,
            "temperature": 20.5,
            "temp_units": "C",
            "battery": 4.0,
            "gravity": 12.5,
        }

        await ingest_manager.ingest(db=test_db, payload=payload1)

        result = await test_db.execute(select(Device).where(Device.id == "123458"))
        device = result.scalar_one_or_none()
        assert device is not None
        assert device.battery_voltage == 4.0

        # Second reading with different battery voltage
        payload2 = {
            "name": "iSpindel003",
            "ID": 123458,
            "angle": 26.0,
            "temperature": 20.8,
            "temp_units": "C",
            "battery": 3.9,
            "gravity": 12.3,
        }

        await ingest_manager.ingest(db=test_db, payload=payload2)

        result = await test_db.execute(select(Device).where(Device.id == "123458"))
        device = result.scalar_one_or_none()
        assert device is not None
        assert device.battery_voltage == 3.9  # Updated

    async def test_invalid_payload_no_device_created(self, test_db: AsyncSession):
        """Test that invalid payloads don't create devices."""
        # Invalid payload that can't be parsed
        invalid_payload = {
            "random": "data",
            "invalid": "format",
        }

        reading = await ingest_manager.ingest(
            db=test_db,
            payload=invalid_payload,
            source_protocol="http",
        )

        # Should return None
        assert reading is None

        # No device should be created
        result = await test_db.execute(select(Device))
        devices = result.scalars().all()
        assert len(devices) == 0

    async def test_auth_token_validation(self, test_db: AsyncSession):
        """Test that auth token validation works during auto-registration."""
        # First reading creates device without auth token
        payload = {
            "color": "PURPLE",
            "temp_f": 68,
            "sg": 1.050,
        }

        reading1 = await ingest_manager.ingest(
            db=test_db,
            payload=payload,
            source_protocol="http",
        )
        assert reading1 is not None

        # Manually set auth token on the device
        result = await test_db.execute(select(Device).where(Device.id == "PURPLE"))
        device = result.scalar_one_or_none()
        assert device is not None
        device.auth_token = "secret-token-123"
        await test_db.commit()

        # Try reading with wrong token - should fail
        reading2 = await ingest_manager.ingest(
            db=test_db,
            payload=payload,
            source_protocol="http",
            auth_token="wrong-token",
        )
        assert reading2 is None

        # Try reading with correct token - should succeed
        reading3 = await ingest_manager.ingest(
            db=test_db,
            payload=payload,
            source_protocol="http",
            auth_token="secret-token-123",
        )
        assert reading3 is not None

    async def test_multiple_device_types_simultaneous(self, test_db: AsyncSession):
        """Test auto-registration of multiple device types simultaneously."""
        # Create readings from different device types
        tilt_payload = {
            "color": "YELLOW",
            "temp_f": 68,
            "sg": 1.050,
        }

        ispindel_payload = {
            "name": "iSpindel004",
            "ID": 123459,
            "angle": 25.5,
            "temperature": 20.5,
            "temp_units": "C",
            "battery": 3.8,
            "gravity": 12.5,
        }

        gravmon_payload = {
            "name": "gravmon03",
            "ID": "GM003",
            "angle": 30.2,
            "temperature": 20.5,
            "temp-units": "C",
            "battery": 4.1,
            "gravity": 1.048,
            "corr-gravity": 1.048,  # Marks as GravityMon
            "gravity-unit": "G",
        }

        # Ingest all three
        await ingest_manager.ingest(db=test_db, payload=tilt_payload)
        await ingest_manager.ingest(db=test_db, payload=ispindel_payload)
        await ingest_manager.ingest(db=test_db, payload=gravmon_payload)

        # Verify all three devices exist
        result = await test_db.execute(select(Device))
        devices = result.scalars().all()
        assert len(devices) == 3

        # Verify each device has correct type
        device_types = {d.id: d.device_type for d in devices}
        assert device_types["YELLOW"] == "tilt"
        assert device_types["123459"] == "ispindel"
        assert device_types["GM003"] == "gravitymon"
