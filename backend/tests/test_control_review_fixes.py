"""Review fixes for the controller safety work (tilt_ui-f50x, tilt_ui-8d49)."""

from datetime import timedelta

import pytest
from sqlalchemy import select

from backend import temp_controller as tc
from backend.models import Batch, ControlEntityState, FermentationAlert
from backend.state import latest_readings
from backend.tests.test_equipment_conflicts import drop_unique_indexes
from backend.tests.test_temp_controller_safety import (  # noqa: F401  (fixtures + helpers)
    COOLER, HEATER, FakeRouter, active_alerts, clean_state, clock, cycle, make_batch, set_reading,
)


# ---- codex P1 / gemini 7: conflict losers are shut down, driven set is role-aware

@pytest.mark.asyncio
async def test_conflict_loser_equipment_is_switched_off(test_db, clock):
    """Planning batch already chilling (cooler ON) loses to an active batch sharing the sensor."""
    await drop_unique_indexes(test_db)
    active = await make_batch(test_db, "Active", status="fermenting", device="BLUE")
    planning = await make_batch(test_db, "Next", status="planning", device="BLUE",
                                heater=None, cooler="switch.chill")
    router = FakeRouter({HEATER: "off", COOLER: "off", "switch.chill": "on"})
    set_reading(clock, 19.0, device="BLUE")

    await tc.run_control_cycle(router, test_db, [active, planning], 19.0, 1.0, None)

    assert router.states["switch.chill"] == "off"
    assert "equipment_conflict" in await active_alerts(test_db, planning.id)


@pytest.mark.asyncio
async def test_winner_keeps_shared_switch_loser_does_not_turn_it_off(test_db, clock):
    await drop_unique_indexes(test_db)
    active = await make_batch(test_db, "Active", status="fermenting", device="BLUE")
    planning = await make_batch(test_db, "Next", status="planning", device="GREEN", heater=None)
    router = FakeRouter({HEATER: "off", COOLER: "on"})
    set_reading(clock, 23.0, device="BLUE")
    set_reading(clock, 23.0, device="GREEN")
    await tc.run_control_cycle(router, test_db, [active, planning], 19.0, 1.0, None)
    assert (COOLER, "off") not in router.calls


@pytest.mark.asyncio
async def test_planning_heater_does_not_count_as_driven(test_db, clock):
    """A planning batch never drives its heater, so it must not shield a conflicted heater."""
    await drop_unique_indexes(test_db)
    p = await make_batch(test_db, "P", status="planning", device="D3", heater="switch.hx", cooler="switch.cp")
    f1 = await make_batch(test_db, "F1", status="fermenting", device="D1", heater="switch.hx", cooler="switch.c1")
    f2 = await make_batch(test_db, "F2", status="conditioning", device="D2", heater="switch.hx", cooler="switch.c2")
    router = FakeRouter({"switch.hx": "on", "switch.cp": "off", "switch.c1": "off", "switch.c2": "off"})
    for d in ("D1", "D2", "D3"):
        set_reading(clock, 19.0, device=d)
    await tc.run_control_cycle(router, test_db, [p, f1, f2], 19.0, 1.0, None)
    assert router.states["switch.hx"] == "off"


# ---- gemini 1 / 3 / 4: unavailable entities, idle trip

@pytest.mark.asyncio
async def test_idle_unavailable_opposite_blocks_turn_on(test_db, clock):
    from backend.models import ChamberReading
    await make_batch(test_db, status="completed")
    test_db.add(ChamberReading(timestamp=clock(), temperature=25.0))
    await test_db.commit()
    router = FakeRouter({COOLER: "off"})  # heater unavailable, may still be physically on
    await tc.control_chamber_idle(router, test_db, 15.0, 2.0, None)
    assert router.calls == []


@pytest.mark.asyncio
async def test_unavailable_heater_does_not_hide_cooler_max_on(test_db, clock):
    b = await make_batch(test_db)
    router = FakeRouter({HEATER: "off", COOLER: "off"})
    set_reading(clock, 23.0)
    await cycle(router, test_db, b)
    assert router.states[COOLER] == "on"

    del router.states[HEATER]  # heater plug drops off the network
    clock.advance(hours=12, minutes=5)
    set_reading(clock, 23.0)
    await cycle(router, test_db, b)
    assert router.states[COOLER] == "off"
    assert "max_on_exceeded" in await active_alerts(test_db, b.id)


@pytest.mark.asyncio
async def test_idle_max_on_trip_stops_the_cycle(test_db, clock):
    from backend.models import ChamberReading
    await make_batch(test_db, status="completed")
    router = FakeRouter({HEATER: "on", COOLER: "off"})
    router.fail.add((HEATER, "off"))

    async def idle():
        test_db.add(ChamberReading(timestamp=clock(), temperature=14.0))  # in band, heater stays on
        await test_db.commit()
        await tc.control_chamber_idle(router, test_db, 15.0, 2.0, None)

    await idle()                       # heater found on: counting starts
    clock.advance(hours=4, minutes=5)
    await idle()                       # trip: one forced off (fails), then stop
    assert router.calls == [(HEATER, "off")]


# ---- gemini 5: overrides

@pytest.mark.asyncio
async def test_opposite_on_overrides_are_mutually_exclusive(test_db, clock):
    b = await make_batch(test_db)
    router = FakeRouter({HEATER: "off", COOLER: "off"})
    set_reading(clock, 19.0)
    tc.set_manual_override("on", 60, batch_id=b.id, device_type="heater")
    tc.set_manual_override("on", 60, batch_id=b.id, device_type="cooler")
    assert "heater" not in tc._batch_overrides[b.id]
    await cycle(router, test_db, b)
    assert router.states == {HEATER: "off", COOLER: "on"}


@pytest.mark.asyncio
async def test_override_on_respects_min_cycle_but_off_does_not(test_db, clock):
    b = await make_batch(test_db)
    router = FakeRouter({HEATER: "off", COOLER: "off"})
    set_reading(clock, 23.0)
    await cycle(router, test_db, b)              # auto: cooler on at T0
    assert router.states[COOLER] == "on"

    clock.advance(minutes=1)
    set_reading(clock, 19.0)
    tc.set_manual_override("off", 60, batch_id=b.id, device_type="cooler")
    await cycle(router, test_db, b)
    assert router.states[COOLER] == "off"        # safe direction bypasses min-cycle

    tc.set_manual_override(None, batch_id=b.id, device_type="cooler")
    tc.set_manual_override("on", 60, batch_id=b.id, device_type="cooler")
    router.calls.clear()
    clock.advance(minutes=1)
    set_reading(clock, 19.0)
    await cycle(router, test_db, b)
    assert router.ons() == []                    # compressor protected from override-on
    clock.advance(minutes=5)
    set_reading(clock, 19.0)
    await cycle(router, test_db, b)
    assert router.states[COOLER] == "on"


# ---- gemini 8: persistence failure must not break the rest of the cycle

@pytest.mark.asyncio
async def test_persist_failure_does_not_break_other_batches(test_db, clock, monkeypatch):
    b1 = await make_batch(test_db, "A", device="BLUE", heater="switch.h1", cooler="switch.c1")
    b2 = await make_batch(test_db, "B", device="RED", heater="switch.h2", cooler="switch.c2")
    router = FakeRouter({"switch.h1": "off", "switch.c1": "off", "switch.h2": "off", "switch.c2": "off"})
    set_reading(clock, 15.0, device="BLUE")
    set_reading(clock, 15.0, device="RED")

    async def boom(*a, **k):
        raise RuntimeError("disk full")
    monkeypatch.setattr(test_db, "merge", boom)

    await tc.run_control_cycle(router, test_db, [b1, b2], 19.0, 1.0, None)
    # both heaters still switched on: rollback in the persistence helper did not
    # expire the batch objects the loop was still using
    assert router.states["switch.h1"] == "on" and router.states["switch.h2"] == "on"
