"""Temperature controller safety tests (tilt_ui-f50x, tilt_ui-8d49).

Uses a fake Home Assistant router and a controllable clock; never touches real
equipment.
"""

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select, text

from backend import temp_controller as tc
from backend.models import Batch, ChamberReading, ControlEntityState, FermentationAlert
from backend.state import latest_readings

T0 = datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc)
HEATER = "switch.beer_heater"
COOLER = "switch.beer_cooling"


class FakeRouter:
    """Stands in for DeviceControlRouter (Home Assistant)."""

    def __init__(self, states=None):
        self.states = dict(states or {})
        self.calls: list[tuple[str, str]] = []
        self.fail: set[tuple[str, str]] = set()      # (entity, state) -> returns False
        self.raise_on: set[tuple[str, str]] = set()  # (entity, state) -> raises

    async def get_state(self, entity_id):
        return self.states.get(entity_id)

    async def set_state(self, entity_id, state):
        self.calls.append((entity_id, state))
        if (entity_id, state) in self.raise_on:
            raise ConnectionError("HA unreachable")
        if (entity_id, state) in self.fail:
            return False
        self.states[entity_id] = state
        return True

    def ons(self, entity=None):
        return [c for c in self.calls if c[1] == "on" and (entity is None or c[0] == entity)]


class Clock:
    def __init__(self):
        self.now = T0

    def __call__(self):
        return self.now

    def advance(self, **kw):
        self.now += timedelta(**kw)


@pytest.fixture
def clock(monkeypatch):
    c = Clock()
    monkeypatch.setattr(tc, "_now", c)
    return c


@pytest.fixture(autouse=True)
def clean_state():
    def wipe():
        tc._entity_state.clear()
        tc._batch_heater_states.clear()
        tc._batch_cooler_states.clear()
        tc._batch_overrides.clear()
        tc._idle_heater_state.clear()
        tc._idle_cooler_state.clear()
        latest_readings.clear()

    wipe()
    yield
    wipe()


def set_reading(clock, temp, age=timedelta(0), device="BLUE", device_type="tilt"):
    latest_readings[device] = {
        "temp": temp,
        "last_seen": (clock() - age).isoformat(),
        "device_type": device_type,
    }


async def make_batch(db, name="A", status="fermenting", device="BLUE", heater=HEATER, cooler=COOLER, target=19.0):
    b = Batch(
        name=name, status=status, device_id=device,
        heater_entity_id=heater, cooler_entity_id=cooler,
        temp_target=target, temp_hysteresis=1.0,
    )
    db.add(b)
    await db.commit()
    await db.refresh(b)
    return b


async def cycle(router, db, batch):
    await tc.control_batch_temperature(router, batch, db, 19.0, 1.0, None)


async def active_alerts(db, batch_id=None):
    q = select(FermentationAlert).where(FermentationAlert.cleared_at.is_(None))
    if batch_id is not None:
        q = q.where(FermentationAlert.batch_id == batch_id)
    return [a.alert_type for a in (await db.execute(q)).scalars()]


# ---------------------------------------------------------------- f50x item 1

@pytest.mark.asyncio
async def test_stale_sensor_turns_both_off_and_resumes(test_db, clock):
    b = await make_batch(test_db)
    router = FakeRouter({HEATER: "on", COOLER: "off"})
    set_reading(clock, 15.0, age=timedelta(minutes=20))  # heater was on, sensor went silent

    await cycle(router, test_db, b)

    assert router.states == {HEATER: "off", COOLER: "off"}
    assert router.ons() == []
    assert "sensor_stale" in await active_alerts(test_db, b.id)

    # still stale next minute: nothing is re-sent (already off), still no 'on'
    router.calls.clear()
    clock.advance(minutes=1)
    await cycle(router, test_db, b)
    assert router.calls == []

    # fresh, cold reading returns; after the min-cycle the heater resumes and alert clears
    clock.advance(minutes=6)
    set_reading(clock, 15.0)
    await cycle(router, test_db, b)
    assert router.ons(HEATER) == [(HEATER, "on")]
    assert "sensor_stale" not in await active_alerts(test_db, b.id)


@pytest.mark.asyncio
@pytest.mark.parametrize("reading", [
    None,                                                        # no reading at all
    {"temp": 15.0},                                              # no timestamp
    {"temp": 15.0, "last_seen": "garbage"},                      # unparseable
])
async def test_missing_or_untimestamped_reading_is_stale(test_db, clock, reading):
    b = await make_batch(test_db)
    router = FakeRouter({HEATER: "on", COOLER: "off"})
    if reading is not None:
        latest_readings["BLUE"] = reading
    await cycle(router, test_db, b)
    assert router.states[HEATER] == "off"
    assert router.ons() == []


@pytest.mark.asyncio
async def test_startup_never_acts_on_old_cached_reading(test_db, clock):
    """Cache reloaded from disk after a restart: reading 2 days old must not start the heater."""
    b = await make_batch(test_db)
    router = FakeRouter({HEATER: "off", COOLER: "off"})
    set_reading(clock, 10.0, age=timedelta(days=2))
    await cycle(router, test_db, b)
    assert router.ons() == []


@pytest.mark.asyncio
async def test_reading_from_the_future_is_not_trusted(test_db, clock):
    """Pi booted with a wrong (old) clock: cached last_seen looks like the future."""
    b = await make_batch(test_db)
    router = FakeRouter({HEATER: "off", COOLER: "off"})
    set_reading(clock, 10.0, age=timedelta(hours=-3))
    await cycle(router, test_db, b)
    assert router.ons() == []
    assert "sensor_stale" in await active_alerts(test_db, b.id)


@pytest.mark.asyncio
async def test_slow_device_types_get_longer_stale_limit(test_db, clock):
    b = await make_batch(test_db, device="PILL")
    router = FakeRouter({HEATER: "off", COOLER: "off"})
    set_reading(clock, 15.0, age=timedelta(minutes=20), device="PILL", device_type="rapt")
    await cycle(router, test_db, b)
    assert router.ons(HEATER)  # 20 min is fine for a 5-15 min reporter


# ---------------------------------------------------------------- f50x item 2

@pytest.mark.asyncio
async def test_max_heater_on_forces_off_alerts_and_locks_out(test_db, clock):
    b = await make_batch(test_db)
    router = FakeRouter({HEATER: "off", COOLER: "off"})
    set_reading(clock, 15.0)
    await cycle(router, test_db, b)  # controller turns heater on at T0
    assert router.states[HEATER] == "on"

    # Wrong sensor keeps reading cold. Stay under the limit: still on.
    clock.advance(hours=3, minutes=59)
    set_reading(clock, 15.0)
    await cycle(router, test_db, b)
    assert router.states[HEATER] == "on"

    clock.advance(minutes=2)  # > 4 h continuous
    set_reading(clock, 15.0)
    await cycle(router, test_db, b)
    assert router.states[HEATER] == "off"
    assert "max_on_exceeded" in await active_alerts(test_db, b.id)

    # Sensor still says cold, but the heater stays locked out
    router.calls.clear()
    clock.advance(minutes=10)
    set_reading(clock, 15.0)
    await cycle(router, test_db, b)
    assert router.ons() == []

    # After the lockout it may run again
    clock.advance(minutes=25)
    set_reading(clock, 15.0)
    await cycle(router, test_db, b)
    assert router.ons(HEATER)


@pytest.mark.asyncio
async def test_max_cooler_on_limit_is_longer(test_db, clock):
    b = await make_batch(test_db)
    router = FakeRouter({HEATER: "off", COOLER: "off"})
    set_reading(clock, 23.0)
    await cycle(router, test_db, b)
    assert router.states[COOLER] == "on"

    clock.advance(hours=11)
    set_reading(clock, 23.0)
    await cycle(router, test_db, b)
    assert router.states[COOLER] == "on"  # 11 h of fridge is legitimate

    clock.advance(hours=1, minutes=1)
    set_reading(clock, 23.0)
    await cycle(router, test_db, b)
    assert router.states[COOLER] == "off"
    assert "max_on_exceeded" in await active_alerts(test_db, b.id)


@pytest.mark.asyncio
async def test_max_on_counts_across_restart_and_manual_on(test_db, clock):
    b = await make_batch(test_db)
    # Heater found ON with no record (manual toggle): counting starts now
    router = FakeRouter({HEATER: "on", COOLER: "off"})
    set_reading(clock, 18.5)  # in deadband, nothing else to do
    await cycle(router, test_db, b)
    row = await test_db.get(ControlEntityState, HEATER)
    assert row.on_since is not None

    tc._entity_state.clear()  # service restart
    clock.advance(hours=4, minutes=5)
    set_reading(clock, 18.5)
    await cycle(router, test_db, b)
    assert router.states[HEATER] == "off"


# ---------------------------------------------------------------- f50x item 3

@pytest.mark.asyncio
async def test_last_switch_persisted_and_min_cycle_survives_restart(test_db, clock):
    b = await make_batch(test_db)
    router = FakeRouter({HEATER: "off", COOLER: "off"})
    set_reading(clock, 15.0)
    await cycle(router, test_db, b)
    assert router.ons(HEATER)

    row = await test_db.get(ControlEntityState, HEATER)
    assert row.last_switch_at is not None

    # Service restarts, HA switch was turned off meanwhile; wort still cold 1 min later
    tc._entity_state.clear()
    tc._batch_heater_states.clear()
    router.states[HEATER] = "off"
    router.calls.clear()
    clock.advance(minutes=1)
    set_reading(clock, 15.0)
    await cycle(router, test_db, b)
    assert router.ons() == []  # compressor/relay protection honoured

    clock.advance(minutes=5)
    set_reading(clock, 15.0)
    await cycle(router, test_db, b)
    assert router.ons(HEATER)


@pytest.mark.asyncio
async def test_min_cycle_is_per_entity_not_per_batch(test_db, clock):
    """Same switch seen through a different batch id must still be protected."""
    b = await make_batch(test_db)
    router = FakeRouter({HEATER: "off", COOLER: "off"})
    set_reading(clock, 23.0)
    await cycle(router, test_db, b)
    assert router.states[COOLER] == "on"
    tc._batch_cooler_states.clear()
    clock.advance(minutes=1)
    set_reading(clock, 19.0)  # at target: wants cooler off
    await cycle(router, test_db, b)
    assert router.states[COOLER] == "on"  # too soon to switch again
    clock.advance(minutes=5)
    set_reading(clock, 19.0)
    await cycle(router, test_db, b)
    assert router.states[COOLER] == "off"


# ---------------------------------------------------------------- f50x item 4

@pytest.mark.asyncio
async def test_opposite_off_refused_by_min_cycle_blocks_other_on(test_db, clock):
    b = await make_batch(test_db)
    router = FakeRouter({HEATER: "off", COOLER: "off"})
    set_reading(clock, 23.0)
    await cycle(router, test_db, b)  # cooler on at T0
    assert router.states[COOLER] == "on"

    router.calls.clear()
    clock.advance(minutes=1)
    set_reading(clock, 15.0)  # suddenly cold: heater wanted, cooler off refused
    await cycle(router, test_db, b)
    assert router.states == {HEATER: "off", COOLER: "on"}
    assert router.ons() == []

    clock.advance(minutes=5)
    set_reading(clock, 15.0)
    await cycle(router, test_db, b)  # now cooler off succeeds ...
    assert router.states[COOLER] == "off"
    # ... heater on follows (opposite confirmed off), never both on
    assert router.states[HEATER] == "on"
    order = [c for c in router.calls if c[1] in ("on", "off")]
    assert order.index((COOLER, "off")) < order.index((HEATER, "on"))


@pytest.mark.asyncio
async def test_opposite_off_failure_blocks_other_on(test_db, clock):
    b = await make_batch(test_db)
    router = FakeRouter({HEATER: "off", COOLER: "on"})
    router.fail.add((COOLER, "off"))
    set_reading(clock, 15.0)
    await cycle(router, test_db, b)
    assert router.states == {HEATER: "off", COOLER: "on"}
    assert router.ons() == []


@pytest.mark.asyncio
async def test_heater_off_failure_blocks_cooler_on(test_db, clock):
    b = await make_batch(test_db)
    router = FakeRouter({HEATER: "on", COOLER: "off"})
    router.raise_on.add((HEATER, "off"))
    set_reading(clock, 23.0)
    await cycle(router, test_db, b)
    assert router.ons() == []


@pytest.mark.asyncio
async def test_override_on_requires_opposite_off(test_db, clock):
    b = await make_batch(test_db)
    router = FakeRouter({HEATER: "off", COOLER: "on"})
    router.fail.add((COOLER, "off"))
    set_reading(clock, 19.5)
    tc.set_manual_override("on", 60, batch_id=b.id, device_type="heater")
    await cycle(router, test_db, b)
    assert router.ons() == []


# ---------------------------------------------------------------- f50x item 5

@pytest.mark.asyncio
async def test_failed_on_is_not_retried_every_cycle(test_db, clock):
    b = await make_batch(test_db)
    router = FakeRouter({HEATER: "off", COOLER: "off"})
    router.fail.add((HEATER, "on"))
    for _ in range(4):  # 4 one-minute cycles
        set_reading(clock, 15.0)
        await cycle(router, test_db, b)
        clock.advance(minutes=1)
    assert len(router.ons(HEATER)) == 1  # one attempt, then back-off

    router.fail.clear()
    clock.advance(minutes=2)
    set_reading(clock, 15.0)
    await cycle(router, test_db, b)
    assert router.states[HEATER] == "on"  # retried after the back-off


@pytest.mark.asyncio
async def test_ha_exception_is_contained(test_db, clock):
    b = await make_batch(test_db)
    router = FakeRouter({HEATER: "off", COOLER: "off"})
    router.raise_on.add((HEATER, "on"))
    set_reading(clock, 15.0)
    await cycle(router, test_db, b)  # must not raise
    assert router.states[HEATER] == "off"
    # no persisted switch time for a command that never happened
    assert await test_db.get(ControlEntityState, HEATER) is None


@pytest.mark.asyncio
async def test_unavailable_entity_does_no_switching(test_db, clock):
    b = await make_batch(test_db)
    router = FakeRouter({COOLER: "off"})  # heater unavailable (None)
    set_reading(clock, 15.0)
    await cycle(router, test_db, b)
    assert router.calls == []


@pytest.mark.asyncio
async def test_normal_hysteresis_unchanged(test_db, clock):
    b = await make_batch(test_db)
    router = FakeRouter({HEATER: "off", COOLER: "off"})
    set_reading(clock, 19.0)   # on target: idle
    await cycle(router, test_db, b)
    assert router.calls == []
    set_reading(clock, 18.0)   # <= target - h: heat
    await cycle(router, test_db, b)
    assert router.states[HEATER] == "on"
    clock.advance(minutes=6)
    set_reading(clock, 19.0)   # reached target: heater off
    await cycle(router, test_db, b)
    assert router.states[HEATER] == "off"


# ---------------------------------------------------------- idle mode (same rules)

@pytest.mark.asyncio
async def test_idle_stale_chamber_sensor_turns_off(test_db, clock):
    await make_batch(test_db, status="completed")
    test_db.add(ChamberReading(timestamp=clock() - timedelta(minutes=40), temperature=5.0))
    await test_db.commit()
    router = FakeRouter({HEATER: "on", COOLER: "off"})
    await tc.control_chamber_idle(router, test_db, 15.0, 2.0, None)
    assert router.states[HEATER] == "off"
    assert router.ons() == []


@pytest.mark.asyncio
async def test_idle_heater_withheld_when_cooler_off_refused(test_db, clock):
    await make_batch(test_db, status="completed")
    test_db.add(ChamberReading(timestamp=clock(), temperature=5.0))
    await test_db.commit()
    router = FakeRouter({HEATER: "off", COOLER: "on"})
    router.fail.add((COOLER, "off"))
    await tc.control_chamber_idle(router, test_db, 15.0, 2.0, None)
    assert router.ons() == []
