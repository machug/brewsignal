"""Automatic diacetyl rest rule (tilt_ui-ml8e): gravity-triggered, debounced, one-shot."""

from datetime import timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from backend import temp_controller as tc
from backend.models import Batch, ControlEvent, FermentationAlert, Reading, Recipe
from backend.state import latest_readings
from backend.tests.test_temp_controller_safety import (  # noqa: F401
    COOLER, HEATER, T0, FakeRouter, active_alerts, clean_state, clock,
)

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
    assert b.temp_target == 18.0 and b.rest_fired_at is None and b.rest_below_since is None


@pytest.mark.asyncio
async def test_fires_once_after_hold_and_never_reverts(test_db, clock):
    b = await make_batch(test_db)
    b = await run_hours(test_db, clock, b.id, 2.75, 1.019)
    assert b.temp_target == 18.0 and b.rest_below_since is not None  # still holding

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
    assert b.rest_below_since is None
    b = await run_hours(test_db, clock, b.id, 2.75, 1.019)
    assert b.temp_target == 18.0  # 2.75 h of the new hold, not 5.5 h in total
    b = await run_hours(test_db, clock, b.id, 0.5, 1.019)
    assert b.temp_target == 21.0


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", ["stale", "anomaly", "paused", "no_sg", "implausible"])
async def test_untrustworthy_reading_restarts_the_hold(test_db, clock, bad):
    b = await make_batch(test_db)
    await run_hours(test_db, clock, b.id, 2.5, 1.019)
    if bad == "stale":
        set_sg(clock, 1.019, age=timedelta(minutes=20))
    elif bad == "anomaly":
        set_sg(clock, 1.000, is_anomaly=True)
    elif bad == "no_sg":
        set_sg(clock, None)
    elif bad == "implausible":
        set_sg(clock, 0.0)
    else:
        set_sg(clock, 1.000)
        (await test_db.get(Batch, b.id)).readings_paused = True
        await test_db.commit()
    b = await cycle(test_db, b.id)
    assert b.rest_below_since is None and b.rest_fired_at is None and b.temp_target == 18.0


@pytest.mark.asyncio
async def test_short_restart_keeps_the_hold(test_db, clock):
    """A deploy restarts the service for under a minute: the hold is on the batch, so it goes on."""
    b = await make_batch(test_db)
    await run_hours(test_db, clock, b.id, 2.75, 1.019, step_min=1)
    tc._entity_state.clear()  # service restart: all in-memory controller state is gone
    clock.advance(minutes=10)
    b = await run_hours(test_db, clock, b.id, 0.25, 1.019, step_min=1)
    assert b.temp_target == 21.0


@pytest.mark.asyncio
async def test_hold_bookkeeping_does_not_touch_updated_at(test_db, clock):
    b = await make_batch(test_db)
    before = b.updated_at
    b = await run_hours(test_db, clock, b.id, 1, 1.019)
    assert b.rest_confirmed_at is not None and b.updated_at == before


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
@pytest.mark.parametrize("change", [{"rest_trigger_percent": 90.0}, {"measured_og": 1.042}])
async def test_changed_threshold_restarts_the_hold(test_db, clock, change):
    """Time held under the old threshold does not count towards the new one."""
    b = await make_batch(test_db)
    await run_hours(test_db, clock, b.id, 2.9, 1.012, step_min=6)
    for k, v in change.items():  # direct edit: the hold columns are not cleared for us
        setattr(await test_db.get(Batch, b.id), k, v)
    await test_db.commit()
    b = await run_hours(test_db, clock, b.id, 2.9, 1.012, step_min=6)
    assert b.temp_target == 18.0 and b.rest_fired_at is None
    b = await run_hours(test_db, clock, b.id, 0.3, 1.012, step_min=6)
    assert b.temp_target == 21.0


@pytest.mark.asyncio
async def test_repeated_cached_reading_adds_no_hold_time(test_db, clock):
    """One low reading, then the hydrometer goes quiet: seeing the cached reading again must not count."""
    b = await make_batch(test_db, rest_hold_hours=0.2)  # 12 min, under the 15 min stale limit
    set_sg(clock, 1.019)
    for _ in range(14):
        b = await cycle(test_db, b.id)
        clock.advance(minutes=1)  # the cached reading gets older, no new one arrives
    assert b.temp_target == 18.0 and b.rest_fired_at is None
    set_sg(clock, 1.019)  # a new low reading, 14 min after the first
    b = await cycle(test_db, b.id)
    assert b.temp_target == 21.0


@pytest.mark.asyncio
async def test_slow_device_hold_is_stable_with_a_real_clock(test_db, monkeypatch):
    """A device that reports every 20 min is seen ~20 times per reading. With a clock that
    moves between calls, the same reading must still give the same timestamp each cycle."""
    t = {"now": T0}

    def ticking():
        t["now"] += timedelta(milliseconds=7)  # every call sees a later time, as in production
        return t["now"]
    monkeypatch.setattr(tc, "_now", ticking)

    b = await make_batch(test_db, rest_hold_hours=0.5)
    first = T0
    for n in range(3):  # readings at 0, 20 and 40 min
        seen = first + timedelta(minutes=20 * n)
        latest_readings["BLUE"] = {"sg": 1.019, "temp": 18.0, "last_seen": seen.isoformat(), "device_type": "rapt"}
        for _ in range(20):
            t["now"] += timedelta(minutes=1)
            b = await cycle(test_db, b.id)
            if n < 2:
                assert tc._utc(b.rest_below_since) == first and tc._utc(b.rest_confirmed_at) == seen
        if n == 1:
            assert b.rest_fired_at is None  # 20 min of readings: under the 30 min hold
    assert b.temp_target == 21.0  # the 40 min reading completed the hold


@pytest.mark.asyncio
async def test_api_clears_blocked_warning_when_batch_leaves_fermenting(client, test_db, clock):
    b = await make_batch(test_db, recipe_id=None)
    set_sg(clock, 1.012)
    await cycle(test_db, b.id)
    assert "rest_blocked" in await active_alerts(test_db, b.id)
    r = await client.put(f"/api/batches/{b.id}", json={"status": "conditioning"})
    assert r.status_code == 200, r.text
    assert "rest_blocked" not in await active_alerts(test_db, b.id)


@pytest.mark.asyncio
@pytest.mark.parametrize("stored,blocks", [
    ({"is_anomaly": True, "sg_calibrated": 1.019}, True),
    ({"status": "invalid", "sg_calibrated": 1.019}, True),
    ({"sg_calibrated": 1.030}, True),           # stored sample is above the trigger
    ({"sg_calibrated": 1.019}, False),          # clean stored sample
    ({"is_anomaly": True, "sg_calibrated": 1.019, "age_h": 2}, False),  # too old to matter
])
async def test_recent_stored_reading_vetoes_live_gravity(test_db, clock, stored, blocks):
    """The live cache drops the anomaly flag on the next broadcast; the stored reading keeps it."""
    b = await make_batch(test_db, rest_hold_hours=0.0)
    stored = dict(stored)
    ts = clock() - timedelta(hours=stored.pop("age_h", 0), minutes=5)
    test_db.add(Reading(batch_id=b.id, device_id=None, timestamp=ts, **stored))
    await test_db.commit()
    set_sg(clock, 1.019)  # live broadcast: low, and not flagged
    b = await cycle(test_db, b.id)
    assert (b.rest_fired_at is None) == blocks


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
    assert b.temp_target == 2.0 and b.rest_fired_at is None and b.rest_below_since is None


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
    {"rest_temp_target": 23.0, "rest_below_since": None, "rest_confirmed_at": None},  # API edited (re-armed) the rule
    {"rest_trigger_percent": 90.0, "rest_below_since": None, "rest_confirmed_at": None},
    {"rest_trigger_percent": None},    # API switched the rule off
    {"status": "conditioning"},
    {"temp_target": 2.0},              # brewer started a cold crash
    {"temp_target": 19.0},
    {"rest_hold_hours": 12.0},         # brewer asked for a longer hold
    {"readings_paused": True},         # brewer is taking the hydrometer out
    {"measured_og": 1.070},            # trigger gravity changed
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
    if "rest_below_since" in edit:
        assert b.rest_below_since is None  # the stale cycle did not write the old hold back


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
    b.rest_fired_at = b.rest_below_since = b.rest_confirmed_at = b.created_at
    await test_db.commit()

    # Re-saving the same rule and other fields keeps it fired. The form shows Fahrenheit
    # to 1 decimal, so an untouched value comes back up to 0.05 F (0.028 C) off.
    r = await client.put(f"/api/batches/{bid}", json={
        "name": "B", "rest_trigger_percent": 75, "rest_temp_target": 21.028, "rest_hold_hours": 4})
    assert r.json()["rest_fired_at"] is not None and r.json()["rest_hold_hours"] == 4

    # An unrelated update that does not mention the rule leaves it alone.
    r = await client.put(f"/api/batches/{bid}", json={"notes": "x"})
    assert r.json()["rest_trigger_percent"] == 75 and r.json()["rest_fired_at"] is not None

    # The smallest real edit in the form (0.1 F = 0.056 C) re-arms the rule.
    r = await client.put(f"/api/batches/{bid}", json={"rest_temp_target": 21.084})
    assert r.json()["rest_fired_at"] is None
    b = await test_db.get(Batch, bid)
    b.rest_fired_at = b.created_at
    await test_db.commit()

    # A changed rule is re-armed.
    r = await client.put(f"/api/batches/{bid}", json={"rest_trigger_percent": 80})
    assert r.json()["rest_fired_at"] is None
    test_db.expire_all()
    b = await test_db.get(Batch, bid)
    assert b.rest_below_since is None and b.rest_confirmed_at is None

    # Explicit null switches it off.
    r = await client.put(f"/api/batches/{bid}", json={"rest_trigger_percent": None})
    assert r.json()["rest_trigger_percent"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [
    {"rest_trigger_percent": 5, "rest_temp_target": 21},
    {"rest_trigger_percent": 99, "rest_temp_target": 21},
    {"rest_trigger_percent": 75, "rest_temp_target": 45},
    {"rest_trigger_percent": 75, "rest_temp_target": 5},   # could never take effect
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
    assert {"rest_trigger_percent", "rest_temp_target", "rest_hold_hours",
            "rest_below_since", "rest_confirmed_at", "rest_hold_trigger_sg", "rest_fired_at"} <= cols


# ------------------------------------------------------------------ status for the batch page (tilt_ui-og8s)

async def control_on(client):
    r = await client.patch("/api/config", json={"ha_enabled": True, "temp_control_enabled": True})
    assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_status_endpoint_reports_rule_state(client, test_db, clock):
    await control_on(client)
    off = await make_batch(test_db, name="off", device_id="RED", heater_entity_id=None, cooler_entity_id=None,
                           rest_trigger_percent=None)
    r = await client.get(f"/api/control/batch/{off.id}/status")
    assert r.status_code == 200 and r.json()["rest"] is None

    b = await make_batch(test_db)
    rest = (await client.get(f"/api/control/batch/{b.id}/status")).json()["rest"]
    assert rest["state"] == "waiting" and rest["trigger_sg"] == pytest.approx(TRIGGER)
    assert rest["rest_temp"] == 21.0 and rest["will_raise"] is True and rest["hold_hours"] == 3.0 and rest["below_since"] is None

    await run_hours(test_db, clock, b.id, 1, 1.019)
    rest = (await client.get(f"/api/control/batch/{b.id}/status")).json()["rest"]
    assert rest["state"] == "holding" and rest["below_since"].endswith("Z")

    await run_hours(test_db, clock, b.id, 2.5, 1.019)
    rest = (await client.get(f"/api/control/batch/{b.id}/status")).json()["rest"]
    assert rest["state"] == "started" and rest["fired_at"].endswith("Z") and rest["below_since"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("kw,state", [
    ({"recipe_id": None}, "blocked"),
    ({"status": "conditioning"}, "inactive"),
    ({"temp_target": 2.0}, "inactive"),
    ({"recipe_id": None, "status": "planning"}, "inactive"),   # not run yet: paused, not a warning
    ({"heater_entity_id": None, "cooler_entity_id": None}, "inactive"),  # the loop does not drive it
])
async def test_status_endpoint_other_states(client, test_db, kw, state):
    await control_on(client)
    b = await make_batch(test_db, **kw)
    rest = (await client.get(f"/api/control/batch/{b.id}/status")).json()["rest"]
    assert rest["state"] == state


@pytest.mark.asyncio
async def test_status_is_inactive_when_temperature_control_is_off(client, test_db, clock):
    """The control loop does not run the rule then, so the page must not say 'armed' or 'holding'."""
    b = await make_batch(test_db)
    await run_hours(test_db, clock, b.id, 1, 1.019)  # a hold was running before control was switched off
    rest = (await client.get(f"/api/control/batch/{b.id}/status")).json()["rest"]
    assert rest["state"] == "inactive" and rest["below_since"] is None


@pytest.mark.asyncio
async def test_status_reports_no_raise_and_equipment_conflict(client, test_db):
    await control_on(client)
    warm = await make_batch(test_db, temp_target=25.0)
    rest = (await client.get(f"/api/control/batch/{warm.id}/status")).json()["rest"]
    assert rest["state"] == "waiting" and rest["will_raise"] is False

    # A conflicted batch is not driven by the control loop, so its rule cannot run.
    await tc._raise_alert(test_db, warm, "equipment_conflict", "shared heater")
    rest = (await client.get(f"/api/control/batch/{warm.id}/status")).json()["rest"]
    assert rest["state"] == "inactive"
