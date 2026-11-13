"""Automatic diacetyl rest rule (tilt_ui-ml8e): gravity-triggered, debounced, one-shot."""

from datetime import timedelta

import pytest
from sqlalchemy import select

from backend import temp_controller as tc
from backend.models import Batch, ControlEvent, FermentationAlert, Recipe
from backend.state import latest_readings
from backend.tests.test_temp_controller_safety import (  # noqa: F401
    COOLER, HEATER, FakeRouter, active_alerts, clean_state, clock,
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
    assert b.rest_below_since is None and b.rest_fired_at is None and b.temp_target == 18.0


@pytest.mark.asyncio
async def test_hold_survives_restart(test_db, clock):
    b = await make_batch(test_db)
    await run_hours(test_db, clock, b.id, 2.75, 1.019)
    tc._entity_state.clear()  # service restart: the hold start is in the database
    b = await run_hours(test_db, clock, b.id, 0.5, 1.019)
    assert b.temp_target == 21.0


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
    assert r.status_code == 200, r.text
    assert r.json()["rest_trigger_percent"] == 75 and r.json()["rest_hold_hours"] is None

    # Pretend the rule fired.
    b = await test_db.get(Batch, bid)
    b.rest_fired_at = b.rest_below_since = b.created_at
    await test_db.commit()

    # Re-saving the same rule (with Fahrenheit round-trip noise) and other fields keeps it fired.
    r = await client.put(f"/api/batches/{bid}", json={
        "name": "B", "rest_trigger_percent": 75, "rest_temp_target": 21.0000004, "rest_hold_hours": 4})
    assert r.json()["rest_fired_at"] is not None and r.json()["rest_hold_hours"] == 4

    # An unrelated update that does not mention the rule leaves it alone.
    r = await client.put(f"/api/batches/{bid}", json={"notes": "x"})
    assert r.json()["rest_trigger_percent"] == 75 and r.json()["rest_fired_at"] is not None

    # A changed rule is re-armed.
    r = await client.put(f"/api/batches/{bid}", json={"rest_trigger_percent": 80})
    assert r.json()["rest_fired_at"] is None and r.json()["rest_below_since"] is None

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
    r = await client.post("/api/batches", json={"name": "A", "status": "planning"})
    r = await client.put(f"/api/batches/{r.json()['id']}", json=body)
    assert r.status_code == 422
