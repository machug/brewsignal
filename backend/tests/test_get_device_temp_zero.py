"""tilt_ui-xrq5.3: a wort temperature of exactly 0.0 C is valid."""

import pytest

from backend import temp_controller as tc
from backend.state import latest_readings
from backend.tests.test_temp_controller_safety import (  # noqa: F401
    HEATER, COOLER, FakeRouter, active_alerts, clean_state, clock, cycle, make_batch, set_reading,
)


def test_get_device_temp_zero_is_valid(clock):
    latest_readings["BLUE"] = {"temp": 0.0, "temp_raw": 5.0}
    assert tc.get_device_temp("BLUE") == 0.0
    latest_readings["BLUE"] = {"temp": None, "temp_raw": 0.0}
    assert tc.get_device_temp("BLUE") == 0.0
    latest_readings["BLUE"] = {"temp": None, "temp_raw": 5.0}
    assert tc.get_device_temp("BLUE") == 5.0
    latest_readings["BLUE"] = {}
    assert tc.get_device_temp("BLUE") is None


@pytest.mark.asyncio
async def test_controller_acts_on_zero_degree_reading(test_db, clock):
    b = await make_batch(test_db, target=0.0)
    router = FakeRouter({HEATER: "off", COOLER: "off"})
    set_reading(clock, 0.0)
    await cycle(router, test_db, b)
    assert router.calls == []  # on target: idle, but no "no temperature" fail-safe either
    assert await active_alerts(test_db, b.id) == []
    set_reading(clock, -2.0)
    await cycle(router, test_db, b)
    assert router.states[HEATER] == "on"
