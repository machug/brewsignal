"""A calibration saved on the Calibration page is applied on every ingest path (tilt_ui-9ywh).

The page saves to devices.calibration_type / calibration_data. The BLE and gateway
paths used to read the legacy calibration_points table, so a Tilt calibration was
never applied. These tests run the real handlers against the test database, with
no mock of the calibration service.
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

import backend.main as main
from backend.models import Batch, Device, Reading
from backend.scanner import TiltReading
from backend.services.calibration import calibrate_values, calibration_service
from backend.state import latest_readings

LINEAR = {"points": [[1.000, 1.000], [1.015, 1.012], [1.020, 1.018]]}


def test_calibrate_values_by_type():
    assert calibrate_values("none", None, 1.050, 20.0) == (1.050, 20.0)
    assert calibrate_values(None, None, 1.050, 20.0) == (1.050, 20.0)
    sg, temp = calibrate_values("offset", {"sg_offset": 0.002, "temp_offset": -0.5}, 1.050, 20.0)
    assert sg == pytest.approx(1.052) and temp == pytest.approx(19.5)
    sg, temp = calibrate_values("linear", LINEAR, 1.015, 20.0)
    assert sg == pytest.approx(1.012) and temp == 20.0  # no temp points: temperature unchanged
    sg, _ = calibrate_values("linear", LINEAR, 1.0175, 20.0)
    assert sg == pytest.approx(1.015)
    # one point is not a curve yet: not applied
    assert calibrate_values("linear", {"points": [[1.046, 1.060]]}, 1.046, 20.0)[0] == 1.046
    # legacy key
    assert calibrate_values("linear", {"sg_points": LINEAR["points"]}, 1.015, None)[0] == pytest.approx(1.012)
    sg, _ = calibrate_values("polynomial", {"coefficients": [0.001, 1.0]}, 1.050, 20.0, angle=25.0)
    assert sg == pytest.approx(1.025)


@pytest.mark.asyncio
async def test_service_reads_the_device_settings(test_db):
    test_db.add(Device(id="BLUE", device_type="tilt", name="BLUE", calibration_type="linear", calibration_data=LINEAR))
    await test_db.commit()
    sg, temp = await calibration_service.calibrate_reading(test_db, "BLUE", 1.015, 18.0)
    assert sg == pytest.approx(1.012) and temp == 18.0
    assert await calibration_service.calibrate_reading(test_db, "NOPE", 1.015, 18.0) == (1.015, 18.0)


@pytest.mark.asyncio
@pytest.mark.parametrize("cal_type,raw_json", [
    ("linear", '{"points": [[1.0], [1.02, 1.018]]}'),      # malformed point
    ("linear", '{"points": [[1.0, 1.0], [1.0, null]]}'),   # null number
    ("offset", '{"sg_offset": null, "temp_offset": 0}'),
    ("linear", '[]'),                                       # not an object
    ("linear", '{not json'),                                # corrupt text
])
async def test_unusable_calibration_falls_back_to_raw(test_db, cal_type, raw_json):
    """Bad stored calibration must not lose the reading: the controller would see a dead sensor."""
    d = Device(id="BLUE", device_type="tilt", name="BLUE", calibration_type=cal_type)
    d._calibration_data = raw_json
    test_db.add(d)
    await test_db.commit()
    assert await calibration_service.calibrate_reading(test_db, "BLUE", 1.015, 18.0) == (1.015, 18.0)


def test_points_with_the_same_raw_value_do_not_pin_gravity():
    """Two points at one raw value used to return a constant for every reading beyond them."""
    dup = {"points": [[1.000, 1.000], [1.000, 1.002]]}
    assert calibrate_values("linear", dup, 1.045, None)[0] == 1.045          # one distinct point: not applied
    three = {"points": [[1.000, 1.000], [1.000, 1.002], [1.020, 1.021]]}
    assert calibrate_values("linear", three, 1.040, None)[0] == pytest.approx(1.041)
    assert calibrate_values("linear", three, 1.010, None)[0] == pytest.approx(1.011)


@pytest.mark.asyncio
async def test_api_rejects_points_with_the_same_raw_value(client, test_db):
    test_db.add(Device(id="BLUE", device_type="tilt", name="BLUE"))
    await test_db.commit()
    r = await client.put("/api/devices/BLUE/calibration", json={
        "calibration_type": "linear", "calibration_data": {"points": [[1.000, 1.000], [1.000, 1.002]]}})
    assert r.status_code == 422
    r = await client.put("/api/devices/BLUE/calibration", json={
        "calibration_type": "linear", "calibration_data": {"points": [[1.000, 1.000], [1.020, 1.018]]}})
    assert r.status_code == 200, r.text


def test_linear_temperature_points():
    data = {"points": [], "temp_points": [[10.0, 11.0], [20.0, 20.0]]}
    sg, temp = calibrate_values("linear", data, 1.015, 15.0)
    assert sg == 1.015 and temp == pytest.approx(15.5)


@pytest.mark.asyncio
async def test_tilt_broadcast_is_calibrated_end_to_end(test_db, monkeypatch):
    """The BLE Tilt handler: live value and stored reading both carry the calibrated gravity."""
    monkeypatch.setattr(main, "async_session_factory", async_sessionmaker(test_db.bind, expire_on_commit=False))
    monkeypatch.setattr(main, "ml_pipeline_manager", None)
    main._last_tilt_storage.clear()
    latest_readings.clear()

    test_db.add(Device(id="BLUE", device_type="tilt", name="BLUE", paired=True,
                       calibration_type="linear", calibration_data=LINEAR))
    test_db.add(Batch(name="A", status="fermenting", device_id="BLUE"))
    await test_db.commit()

    await main.handle_tilt_reading(TiltReading(
        color="BLUE", mac="AA:BB:CC:DD:EE:01", sg=1.015, temp_f=68.0, rssi=-50,
        timestamp=datetime.now(timezone.utc),
    ))

    live = latest_readings["BLUE"]
    assert live["sg_raw"] == 1.015 and live["sg"] == pytest.approx(1.012)
    stored = (await test_db.execute(select(Reading).where(Reading.device_id == "BLUE"))).scalars().one()
    assert stored.sg_raw == 1.015 and stored.sg_calibrated == pytest.approx(1.012)
    latest_readings.clear()
