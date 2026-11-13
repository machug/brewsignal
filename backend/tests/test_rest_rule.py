"""Automatic diacetyl rest rule (tilt_ui-ml8e): gravity-triggered, debounced, one-shot."""

from datetime import timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from backend import temp_controller as tc
from backend.models import Batch, ControlEvent, FermentationAlert, Recipe
from backend.state import latest_readings
from backend.tests.test_temp_controller_safety import (  # noqa: F401
    COOLER, HEATER, FakeRouter, active_alerts, clean_state, clock,
)


@pytest.fixture(autouse=True)
def clean_holds():
    tc._rest_holds.clear()
    yield
    tc._rest_holds.clear()

OG, FG = 1.050, 1.010
TRIGGER = 1.020  # 75% of the way from 1.050 to 1.010


def set_sg(clock, sg, temp=18.0, age=timedelta(0), **extra):
    latest_readings["BLUE"] = {
        "sg": sg, "temp": temp, "last_seen": (clock() - age).isoformat(), "device_type": "tilt", **extra,
    }


async def make_batch(db, **kw):
    recipe = Recipe(name="Pale", og=OG, fg=FG)
    db.add(recipe)
    await db.flush()
    fields = dict(
        name="A", status="fermenting", device_id="BLUE", recipe_id=recipe.id,
        heater_entity_id=HEATER, cooler_entity_id=COOLER, temp_target=18.0, temp_hysteresis=1.0,
        rest_trigger_percent=75.0, rest_temp_target=21.0, rest_hold_hours=3.0,
    )
    fields.update(kw)
    b = Batch(**fields)
    db.add(b)
    await db.commit()
    await db.refresh(b)
    return b


async def cycle(db, batch_id, router=None):
    """One real control cycle, with the batch loaded fresh as the control loop does."""
    db.expire_all()
    batch = await db.get(Batch, batch_id)
    await tc.run_control_cycle(router or FakeRouter({HEATER: "off", COOLER: "off"}), db, [batch], 19.0, 1.0, None)
    db.expire_all()
    return await db.get(Batch, batch_id)


async def run_hours(db, clock, batch_id, hours, sg, step_min=15):
    for _ in range(int(hours * 60 / step_min)):
        set_sg(clock, sg)
        b = await cycle(db, batch_id)
        clock.advance(minutes=step_min)
    return b


def test_trigger_sg():
    assert tc.rest_trigger_sg(OG, FG, 75) == pytest.approx(TRIGGER)
    assert tc.rest_trigger_sg(None, FG, 75) is None
    assert tc.rest_trigger_sg(OG, None, 75) is None
    assert tc.rest_trigger_sg(1.010, 1.010, 75) is None


@pytest.mark.asyncio
async def test_does_not_fire_above_trigger(test_db, clock):
    b = await make_batch(test_db)
    b = await run_hours(test_db, clock, b.id, 6, 1.021)
    assert b.temp_target == 18.0 and b.rest_fired_at is None and b.id not in tc._rest_holds


@pytest.mark.asyncio
async def test_fires_once_after_hold_and_never_reverts(test_db, clock):
    b = await make_batch(test_db)
    b = await run_hours(test_db, clock, b.id, 2.75, 1.019)
    assert b.temp_target == 18.0 and b.id in tc._rest_holds  # still holding

    b = await run_hours(test_db, clock, b.id, 0.5, 1.019)
    assert b.temp_target == 21.0 and b.rest_fired_at is not None

    events = (await test_db.execute(select(ControlEvent).where(ControlEvent.action == "rest_start"))).scalars().all()
    assert len(events) == 1 and events[0].target_temp == 21.0
    alert = (await test_db.execute(
        select(FermentationAlert).where(FermentationAlert.alert_type == "rest_started"))).scalars().one()
    assert alert.severity == "info" and "1.020" in alert.message and "21.0" in alert.message

    # Brewer cold-crashes later: the fired rule must not touch the target again.
    b.temp_target = 2.0
    await test_db.commit()
    b = await run_hours(test_db, clock, b.id, 8, 1.010)
    assert b.temp_target == 2.0
    events = (await test_db.execute(select(ControlEvent).where(ControlEvent.action == "rest_start"))).scalars().all()
    assert len(events) == 1


@pytest.mark.asyncio
async def test_noise_spike_restarts_the_hold(test_db, clock):
    b = await make_batch(test_db)
    await run_hours(test_db, clock, b.id, 2.5, 1.019)
    b = await run_hours(test_db, clock, b.id, 0.25, 1.024)  # one reading above the trigger
    assert b.id not in tc._rest_holds
    b = await run_hours(test_db, clock, b.id, 2.75, 1.019)
    assert b.temp_target == 18.0  # 2.75 h of the new hold, not 5.5 h in total
    b = await run_hours(test_db, clock, b.id, 0.5, 1.019)
    assert b.temp_target == 21.0


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", ["stale", "anomaly", "paused", "no_sg"])
async def test_untrustworthy_reading_restarts_the_hold(test_db, clock, bad):
    b = await make_batch(test_db)
    await run_hours(test_db, clock, b.id, 2.5, 1.019)
    if bad == "stale":
        set_sg(clock, 1.019, age=timedelta(minutes=20))
    elif bad == "anomaly":
        set_sg(clock, 1.000, is_anomaly=True)
    elif bad == "no_sg":
        set_sg(clock, None)
    else:
        set_sg(clock, 1.000)
        (await test_db.get(Batch, b.id)).readings_paused = True
        await test_db.commit()
    b = await cycle(test_db, b.id)
    assert b.id not in tc._rest_holds and b.rest_fired_at is None and b.temp_target == 18.0


@pytest.mark.asyncio
async def test_restart_restarts_the_hold(test_db, clock):
    b = await make_batch(test_db)
    await run_hours(test_db, clock, b.id, 2.75, 1.019)
    tc._rest_holds.clear()  # service restart
    b = await run_hours(test_db, clock, b.id, 2.75, 1.019)
    assert b.temp_target == 18.0
    b = await run_hours(test_db, clock, b.id, 0.5, 1.019)
    assert b.temp_target == 21.0


@pytest.mark.asyncio
@pytest.mark.parametrize("jump", [{"hours": 3, "minutes": 5}, {"hours": -2}])
async def test_gap_or_clock_step_does_not_count_as_hold(test_db, clock, jump):
    """Two low readings either side of an unchecked gap (outage, clock step) must not fire."""
    b = await make_batch(test_db)
    set_sg(clock, 1.019)
    await cycle(test_db, b.id)
    clock.advance(**jump)
    set_sg(clock, 1.019)
    b = await cycle(test_db, b.id)
    assert b.temp_target == 18.0 and b.rest_fired_at is None
    clock.advance(minutes=1)
    b = await run_hours(test_db, clock, b.id, 2.75, 1.019)
    assert b.temp_target == 18.0  # the hold began again after the gap
    b = await run_hours(test_db, clock, b.id, 0.5, 1.019)
    assert b.temp_target == 21.0


@pytest.mark.asyncio
async def test_never_lowers_a_warmer_target(test_db, clock):
    b = await make_batch(test_db, temp_target=25.0, rest_hold_hours=0.0)  # saison, rest temp 21
    set_sg(clock, 1.019, temp=25.0)
    b = await cycle(test_db, b.id)
    assert b.temp_target == 25.0 and b.rest_fired_at is not None  # finished, target untouched
    alert = (await test_db.execute(
        select(FermentationAlert).where(FermentationAlert.alert_type == "rest_started"))).scalars().one()
    assert "left at 25.0" in alert.message
    assert (await test_db.execute(select(ControlEvent).where(ControlEvent.action == "rest_start"))).first() is None


@pytest.mark.asyncio
async def test_does_not_heat_a_cold_crash(test_db, clock):
    b = await make_batch(test_db, temp_target=2.0)  # cold crashing, status still fermenting
    b = await run_hours(test_db, clock, b.id, 6, 1.012, )
    assert b.temp_target == 2.0 and b.rest_fired_at is None and b.id not in tc._rest_holds


@pytest.mark.asyncio
@pytest.mark.parametrize("kw", [
    {"rest_trigger_percent": None},          # rule off
    {"status": "conditioning"},              # only while fermenting
    {"recipe_id": None},                     # no expected FG
])
async def test_rule_inactive(test_db, clock, kw):
    b = await make_batch(test_db, **kw)
    b = await run_hours(test_db, clock, b.id, 6, 1.012)
    assert b.temp_target == 18.0 and b.rest_fired_at is None


@pytest.mark.asyncio
@pytest.mark.parametrize("edit", [
    {"rest_temp_target": 23.0},        # API edited the rule
    {"rest_trigger_percent": 90.0},
    {"rest_trigger_percent": None},    # API switched the rule off
    {"status": "conditioning"},
    {"temp_target": 2.0},              # brewer started a cold crash
    {"temp_target": 19.0},
])
async def test_stale_snapshot_does_not_fire_after_api_edit(test_db, clock, edit):
    """The API changes the batch after the controller read it: the old rule must not fire."""
    bid = (await make_batch(test_db)).id
    await run_hours(test_db, clock, bid, 2.75, 1.019)
    clock.advance(minutes=30)
    set_sg(clock, 1.019)
    test_db.expire_all()
    fresh = await test_db.get(Batch, bid)
    snapshot = SimpleNamespace(**{f: getattr(fresh, f) for f in tc._BATCH_FIELDS})
    for k, v in edit.items():
        setattr(fresh, k, v)
    await test_db.commit()

    await tc.apply_rest_rule(test_db, snapshot)

    test_db.expire_all()
    b = await test_db.get(Batch, bid)
    assert b.temp_target == edit.get("temp_target", 18.0) and b.rest_fired_at is None


@pytest.mark.asyncio
async def test_missing_fg_warns_then_clears(test_db, clock):
    b = await make_batch(test_db, recipe_id=None)
    set_sg(clock, 1.012)
    await cycle(test_db, b.id)
    assert "rest_blocked" in await active_alerts(test_db, b.id)
    alert = (await test_db.execute(
        select(FermentationAlert).where(FermentationAlert.alert_type == "rest_blocked"))).scalars().one()
    assert alert.severity == "warning"

    # Switching the rule off clears the warning.
    (await test_db.get(Batch, b.id)).rest_trigger_percent = None
    await test_db.commit()
    await cycle(test_db, b.id)
    assert "rest_blocked" not in await active_alerts(test_db, b.id)


@pytest.mark.asyncio
async def test_no_warning_when_rule_can_work(test_db, clock):
    b = await make_batch(test_db)
    set_sg(clock, 1.040)
    await cycle(test_db, b.id)
    assert await active_alerts(test_db, b.id) == []


@pytest.mark.asyncio
async def test_measured_og_wins_over_recipe_og(test_db, clock):
    b = await make_batch(test_db, measured_og=1.060)  # trigger = 1.0225
    b = await run_hours(test_db, clock, b.id, 3.5, 1.022)
    assert b.temp_target == 21.0


@pytest.mark.asyncio
async def test_zero_hold_fires_on_first_reading(test_db, clock):
    b = await make_batch(test_db, rest_hold_hours=0.0)
    set_sg(clock, 1.020)
    b = await cycle(test_db, b.id)
    assert b.temp_target == 21.0


@pytest.mark.asyncio
async def test_heater_follows_new_target_in_the_same_cycle(test_db, clock):
    b = await make_batch(test_db, rest_hold_hours=0.0)
    router = FakeRouter({HEATER: "off", COOLER: "off"})
    set_sg(clock, 1.019, temp=18.0)  # in band for 18 C, 3 C under the rest target
    await cycle(test_db, b.id, router)
    assert router.states[HEATER] == "on"


@pytest.mark.asyncio
async def test_rule_error_does_not_stop_temperature_control(test_db, clock, monkeypatch):
    async def boom(*a, **k):
        raise RuntimeError("rule broke")
    monkeypatch.setattr(tc, "apply_rest_rule", boom)
    b = await make_batch(test_db)
    router = FakeRouter({HEATER: "off", COOLER: "off"})
    set_sg(clock, 1.030, temp=15.0)
    await cycle(test_db, b.id, router)
    assert router.states[HEATER] == "on"


# ------------------------------------------------------------------ API

@pytest.mark.asyncio
async def test_api_set_rearm_and_disable(client, test_db):
    r = await client.post("/api/batches", json={"name": "A", "status": "planning"})
    assert r.status_code == 201, r.text
    bid = r.json()["id"]

    r = await client.put(f"/api/batches/{bid}", json={"rest_trigger_percent": 75})
    assert r.status_code == 422  # needs a rest temperature

    r = await client.put(f"/api/batches/{bid}", json={"rest_trigger_percent": 75, "rest_temp_target": 21})
    assert r.status_code == 422  # needs a batch target: the controller skips batches without one

    r = await client.put(f"/api/batches/{bid}", json={
        "temp_target": 18, "rest_trigger_percent": 75, "rest_temp_target": 21})
    assert r.status_code == 200, r.text
    assert r.json()["rest_trigger_percent"] == 75 and r.json()["rest_hold_hours"] is None

    # Pretend the rule fired.
    b = await test_db.get(Batch, bid)
    b.rest_fired_at = b.created_at
    await test_db.commit()

    # Re-saving the same rule and other fields keeps it fired. The form shows Fahrenheit
    # to 1 decimal, so an untouched value comes back up to 0.05 F (0.028 C) off.
    r = await client.put(f"/api/batches/{bid}", json={
        "name": "B", "rest_trigger_percent": 75, "rest_temp_target": 21.028, "rest_hold_hours": 4})
    assert r.json()["rest_fired_at"] is not None and r.json()["rest_hold_hours"] == 4

    # An unrelated update that does not mention the rule leaves it alone.
    r = await client.put(f"/api/batches/{bid}", json={"notes": "x"})
    assert r.json()["rest_trigger_percent"] == 75 and r.json()["rest_fired_at"] is not None

    # A changed rule is re-armed.
    r = await client.put(f"/api/batches/{bid}", json={"rest_trigger_percent": 80})
    assert r.json()["rest_fired_at"] is None

    # Explicit null switches it off.
    r = await client.put(f"/api/batches/{bid}", json={"rest_trigger_percent": None})
    assert r.json()["rest_trigger_percent"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [
    {"rest_trigger_percent": 5, "rest_temp_target": 21},
    {"rest_trigger_percent": 99, "rest_temp_target": 21},
    {"rest_trigger_percent": 75, "rest_temp_target": 45},
    {"rest_trigger_percent": 75, "rest_temp_target": 21, "rest_hold_hours": 100},
])
async def test_api_rejects_out_of_range(client, body):
    r = await client.post("/api/batches", json={"name": "A", "status": "planning", "temp_target": 18})
    r = await client.put(f"/api/batches/{r.json()['id']}", json=body)
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_api_create_with_rule(client):
    base = {"name": "A", "status": "planning", "rest_trigger_percent": 75}
    assert (await client.post("/api/batches", json=base)).status_code == 422
    assert (await client.post("/api/batches", json={**base, "rest_temp_target": 21})).status_code == 422
    r = await client.post("/api/batches", json={**base, "rest_temp_target": 21, "temp_target": 18})
    assert r.status_code == 201, r.text
    assert r.json()["rest_trigger_percent"] == 75 and r.json()["rest_fired_at"] is None


def test_migration_adds_columns_once():
    from sqlalchemy import create_engine, text
    from backend.database import _migrate_add_rest_rule_columns

    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        _migrate_add_rest_rule_columns(conn)  # no table yet: nothing to do
        conn.execute(text("CREATE TABLE batches (id INTEGER PRIMARY KEY, temp_target FLOAT)"))
        _migrate_add_rest_rule_columns(conn)
        _migrate_add_rest_rule_columns(conn)  # second run is a no-op
        cols = {row[1] for row in conn.execute(text("PRAGMA table_info(batches)"))}
    assert {"rest_trigger_percent", "rest_temp_target", "rest_hold_hours", "rest_fired_at"} <= cols
