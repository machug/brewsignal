"""Equipment sharing guard, migration and API 409 (tilt_ui-8d49)."""

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, select, text

from backend import temp_controller as tc
from backend.database import _migrate_active_equipment_unique_indexes
from backend.models import FermentationAlert
from backend.state import latest_readings
from backend.tests.test_temp_controller_safety import (  # noqa: F401  (fixtures + helpers)
    COOLER, HEATER, FakeRouter, active_alerts, clean_state, clock, make_batch, set_reading,
)


async def drop_unique_indexes(db):
    """Simulate a legacy DB that already holds a conflict (the index would forbid it)."""
    for name in ("idx_fermenting_heater_unique", "idx_fermenting_device_unique",
                 "idx_active_heater_unique", "idx_active_cooler_unique", "idx_active_device_unique"):
        await db.execute(text(f"DROP INDEX IF EXISTS {name}"))
    await db.commit()


@pytest.mark.asyncio
async def test_shared_equipment_is_not_driven_by_either_batch(test_db, clock):
    """2026-06-10 incident: batch 11 conditioning (3C) + batch 12 fermenting (19C), same switches and Tilt."""
    await drop_unique_indexes(test_db)
    b1 = await make_batch(test_db, "Stout", status="conditioning", target=3.0)
    b2 = await make_batch(test_db, "IPA", status="fermenting", target=19.0)
    router = FakeRouter({HEATER: "on", COOLER: "on"})
    set_reading(clock, 16.0)

    await tc.run_control_cycle(router, test_db, [b1, b2], 19.0, 1.0, None)

    assert router.ons() == []
    assert router.states == {HEATER: "off", COOLER: "off"}
    for b, other in ((b1, b2), (b2, b1)):
        assert await active_alerts(test_db, b.id) == ["equipment_conflict"]
    alert = (await test_db.execute(
        select(FermentationAlert).where(FermentationAlert.batch_id == b1.id)
    )).scalars().one()
    assert f"batch {b2.id} (IPA)" in alert.message


@pytest.mark.asyncio
async def test_conflict_clears_when_resolved(test_db, clock):
    await drop_unique_indexes(test_db)
    b1 = await make_batch(test_db, "Stout", status="conditioning")
    b2 = await make_batch(test_db, "IPA", status="fermenting")
    router = FakeRouter({HEATER: "off", COOLER: "off"})
    set_reading(clock, 19.0)
    await tc.run_control_cycle(router, test_db, [b1, b2], 19.0, 1.0, None)
    assert await active_alerts(test_db, b1.id) == ["equipment_conflict"]
    await tc.run_control_cycle(router, test_db, [b2], 19.0, 1.0, None)
    assert await active_alerts(test_db, b2.id) == []


@pytest.mark.asyncio
async def test_planning_batch_yields_to_active_batch(test_db, clock):
    await drop_unique_indexes(test_db)
    active = await make_batch(test_db, "Active", status="fermenting", device="BLUE")
    planning = await make_batch(test_db, "Next", status="planning", device="GREEN", heater=None)
    router = FakeRouter({HEATER: "off", COOLER: "off"})
    set_reading(clock, 23.0, device="BLUE")
    set_reading(clock, 23.0, device="GREEN")

    await tc.run_control_cycle(router, test_db, [active, planning], 19.0, 1.0, None)

    # active batch keeps driving the shared cooler (one command, no fight)
    assert router.calls == [(COOLER, "on")]
    assert await active_alerts(test_db, planning.id) == ["equipment_conflict"]
    assert await active_alerts(test_db, active.id) == []


def test_find_conflicts_shared_sensor_only():
    class B:
        def __init__(self, id, status, heater, cooler, device):
            self.id, self.status, self.name = id, status, f"b{id}"
            self.heater_entity_id, self.cooler_entity_id, self.device_id = heater, cooler, device

    a = B(1, "fermenting", "switch.h1", "switch.c1", "BLUE")
    b = B(2, "conditioning", "switch.h2", "switch.c2", "BLUE")
    c = B(3, "fermenting", "switch.h3", "switch.c3", "RED")
    res = tc.find_equipment_conflicts([a, b, c])
    assert set(res) == {1, 2}
    assert res[1]["force_off"] and "sensor 'BLUE'" in res[1]["messages"][0]
    # a heater of one batch used as cooler of another is also a conflict
    d = B(4, "fermenting", "switch.x", None, "R1")
    e = B(5, "fermenting", None, "switch.x", "R2")
    assert set(tc.find_equipment_conflicts([d, e])) == {4, 5}


# ---------------------------------------------------------------- migration

LEGACY_SCHEMA = [
    "CREATE TABLE batches (id INTEGER PRIMARY KEY, status VARCHAR(20), device_id VARCHAR(100), "
    "heater_entity_id VARCHAR(100), cooler_entity_id VARCHAR(100), deleted_at DATETIME)",
    "CREATE UNIQUE INDEX idx_fermenting_heater_unique ON batches (heater_entity_id) "
    "WHERE status = 'fermenting' AND heater_entity_id IS NOT NULL",
]


def legacy_conn(rows):
    engine = create_engine("sqlite://")
    conn = engine.connect()
    for stmt in LEGACY_SCHEMA:
        conn.execute(text(stmt))
    for r in rows:
        conn.execute(text(
            "INSERT INTO batches (id, status, device_id, heater_entity_id, cooler_entity_id, deleted_at) "
            "VALUES (:id, :status, :device, :heater, :cooler, :deleted)"
        ), {"id": r[0], "status": r[1], "device": r[2], "heater": r[3], "cooler": r[4],
            "deleted": r[5] if len(r) > 5 else None})
    return conn


def index_names(conn):
    return {r[0] for r in conn.execute(text("SELECT name FROM sqlite_master WHERE type='index'"))}


def test_migration_without_conflicts_creates_indexes_and_enforces():
    # Mirrors the Pi: one fermenting batch, old batches completed on the same switches
    conn = legacy_conn([
        (1, "completed", None, "switch.h", "switch.c"),
        (2, "fermenting", "BLUE", "switch.h", "switch.c"),
        (3, "brewing", "BLUE", "switch.h", None),
    ])
    assert _migrate_active_equipment_unique_indexes(conn) == []
    assert {"idx_active_heater_unique", "idx_active_cooler_unique", "idx_active_device_unique"} <= index_names(conn)
    assert "idx_fermenting_heater_unique" in index_names(conn)  # legacy index untouched

    # A conditioning batch can no longer share equipment with the fermenting one
    for col, val in (("heater_entity_id", "switch.h"), ("cooler_entity_id", "switch.c"), ("device_id", "BLUE")):
        with pytest.raises(Exception, match="UNIQUE"):
            conn.execute(text(f"INSERT INTO batches (id, status, {col}) VALUES (99, 'conditioning', :v)"), {"v": val})
    # soft-deleted and non-controlled statuses are still free to reuse
    conn.execute(text("INSERT INTO batches (id, status, heater_entity_id, deleted_at) VALUES (98, 'conditioning', 'switch.h', '2026-01-01')"))
    conn.execute(text("INSERT INTO batches (id, status, heater_entity_id) VALUES (97, 'planning', 'switch.h')"))
    # idempotent
    assert _migrate_active_equipment_unique_indexes(conn) == []


def test_migration_with_existing_conflict_does_not_crash_and_keeps_legacy_index():
    conn = legacy_conn([
        (11, "conditioning", "BLUE", "switch.h", "switch.c"),   # 2026-06-10 shape
        (12, "fermenting", "BLUE", "switch.h", "switch.c"),
    ])
    conflicted = _migrate_active_equipment_unique_indexes(conn)  # must not raise
    assert set(conflicted) == {"heater_entity_id", "cooler_entity_id", "device_id"}
    names = index_names(conn)
    assert not {"idx_active_heater_unique", "idx_active_cooler_unique", "idx_active_device_unique"} & names
    assert "idx_fermenting_heater_unique" in names
    # the DB still works
    conn.execute(text("INSERT INTO batches (id, status, heater_entity_id) VALUES (13, 'planning', 'switch.z')"))


def test_migration_conflict_in_one_column_still_creates_the_others():
    conn = legacy_conn([
        (1, "conditioning", "BLUE", "switch.h1", "switch.c"),
        (2, "fermenting", "RED", "switch.h2", "switch.c"),  # only the cooler is shared
    ])
    assert _migrate_active_equipment_unique_indexes(conn) == ["cooler_entity_id"]
    names = index_names(conn)
    assert "idx_active_heater_unique" in names and "idx_active_device_unique" in names
    assert "idx_active_cooler_unique" not in names


def test_migration_skips_when_columns_missing():
    engine = create_engine("sqlite://")
    conn = engine.connect()
    conn.execute(text("CREATE TABLE batches (id INTEGER PRIMARY KEY, status TEXT)"))
    assert _migrate_active_equipment_unique_indexes(conn) == []


@pytest.mark.asyncio
async def test_init_db_creates_indexes(test_db):
    rows = await test_db.execute(text("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='batches'"))
    names = {r[0] for r in rows}
    assert {"idx_active_heater_unique", "idx_active_cooler_unique", "idx_active_device_unique"} <= names


# ---------------------------------------------------------------- API 409

async def _active(client, name, status, **fields):
    r = await client.post("/api/batches", json={"name": name})
    assert r.status_code == 201
    bid = r.json()["id"]
    r = await client.put(f"/api/batches/{bid}", json={"status": status, **fields})
    return bid, r


@pytest.mark.asyncio
async def test_api_409_equipment_shared_with_conditioning_batch(client):
    a, r = await _active(client, "A", "conditioning", heater_entity_id="switch.h", cooler_entity_id="switch.c")
    assert r.status_code == 200

    # new batch moving to fermenting on the same heater / cooler / device -> 409 naming the other batch
    b = (await client.post("/api/batches", json={"name": "B"})).json()["id"]
    r = await client.put(f"/api/batches/{b}", json={"status": "fermenting", "heater_entity_id": "switch.h"})
    assert r.status_code == 409
    assert "switch.h" in r.json()["detail"] and f"ID: {a}" in r.json()["detail"]

    r = await client.put(f"/api/batches/{b}", json={"status": "fermenting", "cooler_entity_id": "switch.c"})
    assert r.status_code == 409
    assert "Cooler" in r.json()["detail"]

    # B must be unchanged after the refusal
    assert (await client.get(f"/api/batches/{b}")).json()["status"] == "planning"


@pytest.mark.asyncio
async def test_api_409_on_status_change_when_equipment_already_assigned(client):
    a, _ = await _active(client, "A", "fermenting", heater_entity_id="switch.h", cooler_entity_id="switch.c", device_id="BLUE")
    # B is set up in planning with the same equipment (allowed), then cannot start
    b = (await client.post("/api/batches", json={"name": "B"})).json()["id"]
    r = await client.put(f"/api/batches/{b}", json={"heater_entity_id": "switch.h", "cooler_entity_id": "switch.c", "device_id": "BLUE"})
    assert r.status_code == 200
    r = await client.put(f"/api/batches/{b}", json={"status": "conditioning"})
    assert r.status_code == 409
    r = await client.put(f"/api/batches/{b}", json={"status": "fermenting"})
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_api_heater_used_as_cooler_elsewhere_is_409(client):
    await _active(client, "A", "fermenting", heater_entity_id="switch.x")
    b = (await client.post("/api/batches", json={"name": "B"})).json()["id"]
    r = await client.put(f"/api/batches/{b}", json={"status": "fermenting", "cooler_entity_id": "switch.x"})
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_api_allows_distinct_equipment_and_reuse_after_completion(client):
    a, _ = await _active(client, "A", "fermenting", heater_entity_id="switch.h", cooler_entity_id="switch.c")
    _, r = await _active(client, "B", "fermenting", heater_entity_id="switch.h2", cooler_entity_id="switch.c2")
    assert r.status_code == 200
    assert (await client.put(f"/api/batches/{a}", json={"status": "completed"})).status_code == 200
    _, r = await _active(client, "C", "conditioning", heater_entity_id="switch.h", cooler_entity_id="switch.c")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_api_create_conflict_is_409(client):
    await _active(client, "A", "conditioning", heater_entity_id="switch.h")
    r = await client.post("/api/batches", json={"name": "B", "status": "fermenting", "heater_entity_id": "switch.h"})
    assert r.status_code == 409
