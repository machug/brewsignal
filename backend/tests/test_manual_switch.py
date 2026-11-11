"""tilt_ui-xrq5.1: manual heater toggle goes through the controller's safe switching."""

import pytest

from backend import temp_controller as tc
from backend.routers import control as control_router
from backend.tests.test_temp_controller_safety import (  # noqa: F401
    COOLER, HEATER, FakeRouter, clean_state, clock, make_batch,
)


@pytest.mark.asyncio
async def test_manual_on_requires_opposite_off(test_db, clock):
    await make_batch(test_db)
    router = FakeRouter({HEATER: "off", COOLER: "on"})
    ok, msg = await tc.manual_switch(router, test_db, HEATER, "heater", "on")
    assert ok and router.states == {HEATER: "on", COOLER: "off"}
    assert router.calls.index((COOLER, "off")) < router.calls.index((HEATER, "on"))


@pytest.mark.asyncio
async def test_manual_on_refused_when_opposite_off_fails(test_db, clock):
    await make_batch(test_db)
    router = FakeRouter({HEATER: "off", COOLER: "on"})
    router.fail.add((COOLER, "off"))
    ok, msg = await tc.manual_switch(router, test_db, HEATER, "heater", "on")
    assert not ok and router.ons() == []


@pytest.mark.asyncio
async def test_manual_on_respects_min_cycle_and_off_does_not(test_db, clock):
    await make_batch(test_db)
    router = FakeRouter({HEATER: "off", COOLER: "off"})
    assert (await tc.manual_switch(router, test_db, HEATER, "heater", "on"))[0]
    ok, _ = await tc.manual_switch(router, test_db, HEATER, "heater", "off")
    assert ok  # off always allowed
    clock.advance(minutes=1)
    ok, msg = await tc.manual_switch(router, test_db, HEATER, "heater", "on")
    assert not ok and "minimum cycle" in msg
    clock.advance(minutes=5)
    assert (await tc.manual_switch(router, test_db, HEATER, "heater", "on"))[0]


@pytest.mark.asyncio
async def test_toggle_endpoint_uses_safe_path(client, test_db, clock, monkeypatch):
    b = await make_batch(test_db)
    router = FakeRouter({HEATER: "off", COOLER: "on"})
    router.fail.add((COOLER, "off"))
    monkeypatch.setattr(control_router, "get_device_router", lambda: router)

    async def cfg(db, key):
        return True
    monkeypatch.setattr(control_router, "get_config_value", cfg)

    r = await client.post("/api/control/heater", json={"state": "on", "batch_id": b.id})
    assert r.json()["success"] is False
    assert router.ons() == []

    router.fail.clear()
    r = await client.post("/api/control/heater", json={"state": "on", "batch_id": b.id})
    assert r.json()["success"] is True
    assert router.states == {HEATER: "on", COOLER: "off"}
