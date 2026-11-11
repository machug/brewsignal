"""Cooler no-progress rule and absolute backstop (tilt_ui-xrq5.4)."""

from datetime import timedelta

import pytest

from backend import temp_controller as tc
from backend.models import ChamberReading, ControlEntityState
from backend.tests.test_temp_controller_safety import (  # noqa: F401
    COOLER, HEATER, FakeRouter, active_alerts, clean_state, clock, cycle, make_batch, set_reading,
)

STEP = timedelta(minutes=15)


async def run(db, clock, router, batch, hours, temp_at):
    """One-cycle-per-15-min loop; temp_at(elapsed_hours) gives the wort temp. Returns trip time (h) or None."""
    start = clock()
    t = timedelta(0)
    while t <= timedelta(hours=hours):
        set_reading(clock, temp_at(t.total_seconds() / 3600))
        await cycle(router, db, batch)
        if router.states[COOLER] == "off" and t > timedelta(0) and "max_on_exceeded" in await active_alerts(db, batch.id):
            return t.total_seconds() / 3600
        clock.advance(minutes=15)
        t += STEP
    return None


@pytest.mark.asyncio
async def test_cold_crash_48h_never_trips(test_db, clock):
    b = await make_batch(test_db, target=2.0)
    router = FakeRouter({HEATER: "off", COOLER: "off"})
    tripped = await run(test_db, clock, router, b, 48, lambda h: max(18 - 0.35 * h, 1.0))
    assert tripped is None
    assert "max_on_exceeded" not in await active_alerts(test_db, b.id)
    # the cooler ran for ~46 h and switched off by itself on reaching target
    assert router.states[COOLER] == "off"
    assert router.ons(COOLER) == [(COOLER, "on")]


@pytest.mark.asyncio
async def test_stuck_sensor_trips_at_6h(test_db, clock):
    b = await make_batch(test_db)
    router = FakeRouter({HEATER: "off", COOLER: "off"})
    tripped = await run(test_db, clock, router, b, 8, lambda h: 23.0)
    assert tripped == pytest.approx(6.0, abs=0.3)
    msg = (await test_db.execute(
        __import__("sqlalchemy").select(__import__("backend.models", fromlist=["x"]).FermentationAlert.message))).scalars().first()
    assert "without the wort cooling" in msg and "sensor is in the beer" in msg


@pytest.mark.asyncio
async def test_slow_drift_below_threshold_trips(test_db, clock):
    b = await make_batch(test_db)
    router = FakeRouter({HEATER: "off", COOLER: "off"})
    tripped = await run(test_db, clock, router, b, 12, lambda h: 23.0 - 0.05 * h)  # 0.3 C in 6 h
    assert tripped == pytest.approx(6.0, abs=0.3)


@pytest.mark.asyncio
async def test_lockout_then_cooler_can_resume(test_db, clock):
    b = await make_batch(test_db)
    router = FakeRouter({HEATER: "off", COOLER: "off"})
    assert await run(test_db, clock, router, b, 8, lambda h: 23.0) is not None
    clock.advance(minutes=40)
    set_reading(clock, 23.0)
    await cycle(router, test_db, b)
    assert router.states[COOLER] == "on"  # lockout over
    clock.advance(minutes=1)
    set_reading(clock, 23.0)
    await cycle(router, test_db, b)       # fresh reference taken
    row = await test_db.get(ControlEntityState, COOLER)
    assert row.progress_ref_temp == 23.0


@pytest.mark.asyncio
async def test_restart_keeps_progress_reference(test_db, clock):
    b = await make_batch(test_db)
    router = FakeRouter({HEATER: "off", COOLER: "off"})
    set_reading(clock, 23.0)
    await cycle(router, test_db, b)
    clock.advance(minutes=1)
    set_reading(clock, 23.0)
    await cycle(router, test_db, b)       # reference taken
    clock.advance(hours=5)
    set_reading(clock, 23.0)
    await cycle(router, test_db, b)
    assert router.states[COOLER] == "on"

    row = await test_db.get(ControlEntityState, COOLER)
    assert row.progress_ref_temp == 23.0 and row.progress_ref_at is not None
    tc._entity_state.clear()  # service restart

    clock.advance(hours=1)
    set_reading(clock, 23.0)
    await cycle(router, test_db, b)
    assert router.states[COOLER] == "off"  # 6 h counted across the restart


@pytest.mark.asyncio
async def test_reference_resets_when_cooler_turns_off(test_db, clock):
    b = await make_batch(test_db, target=19.0)
    router = FakeRouter({HEATER: "off", COOLER: "off"})
    set_reading(clock, 23.0)
    await cycle(router, test_db, b)
    clock.advance(minutes=6)
    set_reading(clock, 19.0)  # target reached: cooler off
    await cycle(router, test_db, b)
    assert router.states[COOLER] == "off"
    row = await test_db.get(ControlEntityState, COOLER)
    assert row.progress_ref_temp is None and row.progress_ref_at is None


@pytest.mark.asyncio
async def test_absolute_backstop_trips_even_with_progress(test_db, clock, monkeypatch):
    monkeypatch.setattr(tc, "MAX_COOLER_ON_MINUTES", 600)
    b = await make_batch(test_db, target=2.0)
    router = FakeRouter({HEATER: "off", COOLER: "off"})
    tripped = await run(test_db, clock, router, b, 14, lambda h: 30 - 0.6 * h)
    assert tripped == pytest.approx(10.0, abs=0.3)


@pytest.mark.asyncio
async def test_heater_four_hour_limit_unchanged(test_db, clock):
    b = await make_batch(test_db)
    router = FakeRouter({HEATER: "off", COOLER: "off"})
    set_reading(clock, 15.0)
    await cycle(router, test_db, b)
    assert router.states[HEATER] == "on"
    clock.advance(hours=3, minutes=55)
    set_reading(clock, 15.0)
    await cycle(router, test_db, b)
    assert router.states[HEATER] == "on"
    clock.advance(minutes=10)
    set_reading(clock, 15.0)
    await cycle(router, test_db, b)
    assert router.states[HEATER] == "off"


@pytest.mark.asyncio
async def test_idle_cooler_uses_chamber_air_progress(test_db, clock):
    await make_batch(test_db, status="completed")
    router = FakeRouter({HEATER: "off", COOLER: "off"})

    async def idle(temp):
        test_db.add(ChamberReading(timestamp=clock(), temperature=temp))
        await test_db.commit()
        await tc.control_chamber_idle(router, test_db, 15.0, 2.0, None)

    await idle(25.0)
    assert router.states[COOLER] == "on"
    for _ in range(25):            # 6 h 15 min, chamber air not cooling
        clock.advance(minutes=15)
        await idle(25.0)
    assert router.states[COOLER] == "off"

    # ...but a cooling chamber is left alone
    clock.advance(hours=1)
    await idle(25.0)
    assert router.states[COOLER] == "on"
    for i in range(1, 30):
        clock.advance(minutes=15)
        await idle(25.0 - 0.2 * i)  # 0.8 C/h, stays above the idle cooler-off point
    assert router.states[COOLER] == "on"


def test_migration_adds_progress_columns_to_existing_table():
    from sqlalchemy import create_engine, text
    from backend.database import _migrate_add_control_progress_columns

    conn = create_engine("sqlite://").connect()
    conn.execute(text("CREATE TABLE control_entity_state (entity_id VARCHAR(100) PRIMARY KEY, "
                      "last_switch_at DATETIME, on_since DATETIME, locked_until DATETIME)"))
    conn.execute(text("INSERT INTO control_entity_state (entity_id) VALUES ('switch.x')"))
    _migrate_add_control_progress_columns(conn)
    _migrate_add_control_progress_columns(conn)  # idempotent
    cols = {r[1] for r in conn.execute(text("PRAGMA table_info(control_entity_state)"))}
    assert {"progress_ref_temp", "progress_ref_at"} <= cols
    assert conn.execute(text("SELECT count(*) FROM control_entity_state")).scalar() == 1
    # no table at all: no-op
    _migrate_add_control_progress_columns(create_engine("sqlite://").connect())
