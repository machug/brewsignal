"""Batch expected stats (tilt_ui-4x2f.3): live while planning/brewing, snapshot from fermenting."""
import json
from datetime import datetime, timezone

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend import database as dbm
from backend import temp_controller as tc
from backend.models import Batch, FermentationAlert, Reading, Recipe, RecipeFermentable, RecipeHop
from backend.ml.pipeline_manager import MLPipelineManager
from backend.services.alert_service import AlertType, detect_and_persist_alerts, get_alert_context
from backend.services.converters.brewsignal_v2 import RecipeToBrewSignalV2Converter
from backend.services.converters.recipe_to_brewfather import RecipeToBrewfatherConverter
from backend.services.importers.recipe_importer import RecipeImporter
from backend.services.llm.tools.recipe_v2 import update_recipe_document
from backend.services.recipe_stats import (
    batch_expected_fg,
    batch_expected_og,
    batch_with_recipe_options,
    effective_stats,
    recipe_with_ingredients_stmt,
    snapshot_expected,
)

EXPECTED = ("expected_og", "expected_fg", "expected_abv", "expected_ibu", "expected_srm")
from backend.tests.test_rest_rule import cycle, set_sg  # noqa: E402
from backend.tests.test_temp_controller_safety import (  # noqa: E402,F401
    COOLER, HEATER, clean_state, clock,
)

BOIL60 = {"use": "add_to_boil", "duration": {"value": 60, "unit": "min"}}


async def _recipe(db, grain=True, **kw):
    r = Recipe(name=kw.pop("name", "APA"), batch_size_liters=20.0, efficiency_percent=75.0, **kw)
    db.add(r)
    await db.commit()
    if grain:
        db.add(RecipeFermentable(recipe_id=r.id, name="Pale", type="grain", amount_kg=5.0,
                                 yield_percent=80.0, color_srm=3.0))
        db.add(RecipeHop(recipe_id=r.id, name="Hop", alpha_acid_percent=10.0, amount_grams=30.0, timing=BOIL60))
        await db.commit()
    return r


async def _load_batch(db, batch_id):
    return (await db.execute(
        select(Batch).options(*batch_with_recipe_options()).where(Batch.id == batch_id)
        .execution_options(populate_existing=True)
    )).scalar_one()


async def _load_recipe(db, recipe_id):
    return (await db.execute(
        recipe_with_ingredients_stmt().where(Recipe.id == recipe_id).execution_options(populate_existing=True)
    )).scalar_one()


async def _export_recipe(db, recipe_id):
    from sqlalchemy.orm import selectinload
    opts = [selectinload(getattr(Recipe, rel.key)) for rel in Recipe.__mapper__.relationships]
    return (await db.execute(
        select(Recipe).options(*opts).where(Recipe.id == recipe_id).execution_options(populate_existing=True)
    )).scalar_one()


async def _new_batch(client, recipe_id, status="planning", **kw):
    r = await client.post("/api/batches", json={"recipe_id": recipe_id, "status": status, **kw})
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


@pytest.mark.asyncio
async def test_planning_batch_reads_recipe_live(client, test_db):
    r = await _recipe(test_db)
    bid = await _new_batch(client, r.id)
    before = batch_expected_fg(await _load_batch(test_db, bid))
    assert before is not None
    res = await update_recipe_document(
        test_db, r.id, [{"op": "replace", "path": "/recipe/batch_size", "value": {"value": 8, "unit": "l"}}])
    assert "error" not in res, res
    batch = await _load_batch(test_db, bid)
    assert batch.expected_og is None  # no snapshot while planning
    assert batch_expected_fg(batch) != before
    assert batch_expected_og(batch) == pytest.approx(effective_stats(await _load_recipe(test_db, r.id)).og)


@pytest.mark.asyncio
async def test_snapshot_on_entering_fermenting(client, test_db):
    r = await _recipe(test_db)
    bid = await _new_batch(client, r.id)
    resp = await client.put(f"/api/batches/{bid}", json={"status": "fermenting"})
    assert resp.status_code == 200, resp.text
    batch = await _load_batch(test_db, bid)
    stats = effective_stats(await _load_recipe(test_db, r.id))
    assert (batch.expected_og, batch.expected_fg, batch.expected_abv, batch.expected_ibu, batch.expected_srm) == (
        stats.og, stats.fg, stats.abv, stats.ibu, stats.srm)
    assert resp.json()["expected_fg"] == stats.fg
    # a batch created straight into fermenting is snapshotted too
    bid2 = await _new_batch(client, r.id, status="fermenting")
    assert (await _load_batch(test_db, bid2)).expected_fg == stats.fg


async def _fresh(test_db, batch_id):
    """Read a batch through a separate session, as another request would."""
    factory = async_sessionmaker(test_db.bind, expire_on_commit=False)
    async with factory() as session:
        return (await session.execute(
            select(Batch).options(*batch_with_recipe_options()).where(Batch.id == batch_id))).scalar_one()


async def _running_batch(client, test_db):
    r = await _recipe(test_db)
    bid = await _new_batch(client, r.id)
    assert (await client.put(f"/api/batches/{bid}", json={"status": "fermenting"})).status_code == 200
    b = await test_db.get(Batch, bid)
    b.device_id, b.heater_entity_id, b.cooler_entity_id = "BLUE", HEATER, COOLER
    b.temp_target, b.temp_hysteresis = 18.0, 1.0
    b.rest_trigger_percent, b.rest_temp_target, b.rest_hold_hours = 75.0, 21.0, 3.0
    await test_db.commit()
    return r, bid


@pytest.mark.asyncio
async def test_recipe_edit_does_not_move_fermenting_batch(client, test_db, clock, monkeypatch):
    """Review Focus 1: a big FG move on the recipe leaves a running batch's rest
    trigger, dry-hop trigger and ML expected FG alone."""
    r, bid = await _running_batch(client, test_db)
    test_db.add(RecipeHop(recipe_id=r.id, name="Citra", amount_grams=30, timing={"use": "dry_hop"}))
    await test_db.commit()
    b0 = await _fresh(test_db, bid)
    og0, fg0 = b0.expected_og, b0.expected_fg
    rest0, dry0 = tc.rest_trigger_sg(og0, fg0, 75.0), tc.rest_trigger_sg(og0, fg0, 65.0)
    recipe_fg0 = effective_stats(await _load_recipe(test_db, r.id)).fg

    # PUT the recipe so its FG moves a lot (more attenuation-limited, much higher OG)
    resp = await client.put(f"/api/recipes/{r.id}", json={"efficiency_percent": 100.0, "batch_size_liters": 10.0})
    assert resp.status_code == 200, resp.text
    moved = effective_stats(await _load_recipe(test_db, r.id))
    assert abs(moved.fg - recipe_fg0) > 0.01, (moved.fg, recipe_fg0)

    b1 = await _fresh(test_db, bid)
    assert (b1.expected_og, b1.expected_fg) == (og0, fg0)

    # real rest-rule ticks: the hold is timed against the original trigger
    sg = rest0 - 0.001
    for _ in range(8):  # 2 h of 15 min cycles, hold is 3 h
        set_sg(clock, sg)
        await cycle(test_db, bid)
        clock.advance(minutes=15)
    held = await _fresh(test_db, bid)
    assert held.rest_below_since is not None and held.rest_fired_at is None
    assert held.rest_hold_trigger_sg == pytest.approx(rest0)
    for _ in range(6):
        set_sg(clock, sg)
        await cycle(test_db, bid)
        clock.advance(minutes=15)
    fired = await _fresh(test_db, bid)
    assert fired.rest_fired_at is not None and fired.temp_target == 21.0

    # stall/progress inputs come from the batch, not hand-passed gravities
    ctx = await get_alert_context(test_db, bid, sg)
    assert (ctx["og"], ctx["fg"]) == (og0, fg0)
    reading = Reading(batch_id=bid, sg_raw=dry0 - 0.0005, sg_calibrated=dry0 - 0.0005)
    test_db.add(reading)
    await test_db.flush()
    await detect_and_persist_alerts(db=test_db, batch_id=bid, device_id="BLUE", reading=reading,
                                    live_reading={"sg": reading.sg_calibrated}, og=ctx["og"], fg=ctx["fg"])
    alerts = (await test_db.execute(select(FermentationAlert).where(
        FermentationAlert.batch_id == bid, FermentationAlert.alert_type == AlertType.DRY_HOP_DUE))).scalars().all()
    assert len(alerts) == 1 and json.loads(alerts[0].context)["trigger_sg"] == pytest.approx(dry0)

    # GET /predictions hands the pipeline the snapshot FG
    seen = {}
    mgr = MLPipelineManager()
    monkeypatch.setattr(mgr, "get_device_state", lambda device_id, **kw: seen.update(kw) or None)
    monkeypatch.setattr("backend.main.get_ml_manager", lambda: mgr)
    resp = await client.get(f"/api/batches/{bid}/predictions")
    assert resp.status_code == 200, resp.text
    assert seen["expected_fg"] == fg0


@pytest.mark.asyncio
async def test_reassign_recipe_resnapshots_fermenting_batch(client, test_db):
    r1 = await _recipe(test_db, name="One")
    r2 = await _recipe(test_db, name="Two")
    r2.efficiency_percent = 50.0
    await test_db.commit()
    bid = await _new_batch(client, r1.id, status="fermenting")
    fg1 = (await _load_batch(test_db, bid)).expected_fg
    resp = await client.put(f"/api/batches/{bid}", json={"recipe_id": r2.id})
    assert resp.status_code == 200, resp.text
    stats2 = effective_stats(await _load_recipe(test_db, r2.id))
    batch = await _load_batch(test_db, bid)
    assert batch.expected_fg == stats2.fg and batch.expected_og == stats2.og
    assert stats2.fg != fg1


@pytest.mark.asyncio
async def test_unlink_recipe_clears_snapshot(client, test_db):
    r = await _recipe(test_db)
    bid = await _new_batch(client, r.id, status="fermenting")
    assert (await _load_batch(test_db, bid)).expected_fg is not None
    resp = await client.put(f"/api/batches/{bid}", json={"recipe_id": None})
    assert resp.status_code == 200, resp.text
    batch = await _load_batch(test_db, bid)
    assert batch.recipe_id is None
    assert [getattr(batch, f"expected_{n}") for n in ("og", "fg", "abv", "ibu", "srm")] == [None] * 5
    snapshot_expected(batch, await _load_recipe(test_db, r.id))
    assert batch.expected_fg is not None
    snapshot_expected(batch, None)
    assert batch.expected_fg is None


@pytest.mark.asyncio
async def test_measured_og_wins(test_db):
    r = await _recipe(test_db)
    b = Batch(name="B", status="fermenting", recipe_id=r.id, measured_og=1.071, expected_og=1.050, expected_fg=1.010)
    test_db.add(b)
    await test_db.commit()
    assert batch_expected_og(b) == 1.071
    assert batch_expected_fg(b) == 1.010


@pytest.mark.asyncio
async def test_declared_only_recipe_feeds_batch(client, test_db):
    r = await _recipe(test_db, grain=False, target_fg=1.012)
    bid = await _new_batch(client, r.id)
    batch = await _load_batch(test_db, bid)
    assert batch_expected_fg(batch) == 1.012 and batch_expected_og(batch) is None
    await client.put(f"/api/batches/{bid}", json={"status": "fermenting"})
    batch = await _load_batch(test_db, bid)
    assert batch.expected_fg == 1.012 and batch.expected_og is None


def _factory(monkeypatch, test_db):
    monkeypatch.setattr(dbm, "async_session_factory", async_sessionmaker(test_db.bind, expire_on_commit=False))


async def _drop_expected(test_db):
    async with test_db.bind.begin() as conn:
        for name in EXPECTED:
            await conn.execute(text(f"ALTER TABLE batches DROP COLUMN {name}"))


@pytest.mark.asyncio
async def test_backfill_uses_legacy_stats_for_running_batches(test_db, monkeypatch):
    """Review Focus 2: the deploy does not move a running batch."""
    # stored legacy og/fg differ from what the calculator gives for the ingredients
    r = await _recipe(test_db, og=1.099, fg=1.033, abv=9.9, ibu=77.0, color_srm=12.0)
    live = Batch(name="plan", status="planning", recipe_id=r.id)
    ferm = Batch(name="f", status="fermenting", recipe_id=r.id, dry_hop_trigger_sg=None)
    done = Batch(name="d", status="completed", recipe_id=r.id)
    gone = Batch(name="x", status="fermenting", recipe_id=r.id, deleted_at=datetime.now(timezone.utc))
    test_db.add_all([live, ferm, done, gone])
    await test_db.commit()
    ids = {b.name: b.id for b in (live, ferm, done, gone)}
    rid = r.id
    # what the old code ran against: the stored recipe og/fg
    rest_before = tc.rest_trigger_sg(1.099, 1.033, 75.0)
    dry_before = tc.rest_trigger_sg(1.099, 1.033, 65.0)

    await _drop_expected(test_db)  # the pre-migration schema
    async with test_db.bind.begin() as conn:
        await conn.run_sync(dbm._migrate_add_batch_expected_columns)
    _factory(monkeypatch, test_db)
    await dbm._backfill_batch_expected()

    for name in ("f", "d", "x"):
        row = (await test_db.execute(text(
            "SELECT expected_og, expected_fg, expected_abv, expected_ibu, expected_srm FROM batches WHERE id=:i"),
            {"i": ids[name]})).one()
        assert tuple(row) == (1.099, 1.033, 9.9, 77.0, 12.0), name
    assert (await test_db.execute(text("SELECT expected_og FROM batches WHERE id=:i"), {"i": ids["plan"]})).one()[0] is None
    assert effective_stats(await _load_recipe(test_db, rid)).og != 1.099  # stored really differs

    running = await _fresh(test_db, ids["f"])
    og, fg = await tc._rest_gravities(test_db, running)
    assert tc.rest_trigger_sg(og, fg, 75.0) == pytest.approx(rest_before)
    assert tc.rest_trigger_sg(og, fg, 65.0) == pytest.approx(dry_before)  # the dry-hop default trigger


@pytest.mark.asyncio
async def test_backfill_runs_every_boot_and_never_overwrites(test_db, monkeypatch):
    """Columns already present, snapshot all null -> filled; existing snapshot untouched."""
    r = await _recipe(test_db, og=1.099, fg=1.033)  # abv/ibu/srm not stored: calculator fills them
    empty = Batch(name="e", status="fermenting", recipe_id=r.id)
    kept = Batch(name="k", status="conditioning", recipe_id=r.id, expected_og=1.040, expected_fg=1.008)
    test_db.add_all([empty, kept])
    await test_db.commit()
    _factory(monkeypatch, test_db)
    await dbm._backfill_batch_expected()
    stats = effective_stats(await _load_recipe(test_db, r.id))
    e = await _fresh(test_db, empty.id)
    assert (e.expected_og, e.expected_fg) == (1.099, 1.033)
    assert (e.expected_abv, e.expected_ibu, e.expected_srm) == (stats.abv, stats.ibu, stats.srm)
    k = await _fresh(test_db, kept.id)
    assert (k.expected_og, k.expected_fg, k.expected_abv) == (1.040, 1.008, None)
    await dbm._backfill_batch_expected()  # again: no change
    assert (await _fresh(test_db, empty.id)).expected_og == 1.099


@pytest.mark.asyncio
async def test_brewfather_export_uses_effective_stats(test_db):
    # calculable recipe: calculated numbers win over stale targets and legacy columns
    r = await _recipe(test_db, og=1.099, target_og=1.040, target_ibu=33.0)
    recipe = await _export_recipe(test_db, r.id)
    stats = effective_stats(recipe)
    bf = RecipeToBrewfatherConverter().convert(recipe)
    assert bf["og"] == stats.og != 1.099 and bf["fg"] == stats.fg and bf["ibu"] == stats.ibu
    # declared-only recipe: the target is exported
    d = await _recipe(test_db, grain=False, name="D", target_fg=1.012)
    bf = RecipeToBrewfatherConverter().convert(await _export_recipe(test_db, d.id))
    assert bf["fg"] == 1.012 and "og" not in bf


@pytest.mark.asyncio
async def test_strict_beerjson_export_uses_effective_stats(client, test_db):
    r = await _recipe(test_db, og=1.099, target_og=1.040)
    stats = effective_stats(await _load_recipe(test_db, r.id))
    resp = await client.get(f"/api/recipes/{r.id}/export/beerjson")
    assert resp.status_code == 200, resp.text
    out = resp.json()["beerjson"]["recipes"][0]
    assert out["original_gravity"]["value"] == stats.og


@pytest.mark.asyncio
async def test_v2_stat_fields_are_targets_and_roundtrip(test_db):
    r = await _recipe(test_db, og=1.099, target_og=1.044, target_fg=1.011)
    recipe = await _export_recipe(test_db, r.id)
    doc = RecipeToBrewSignalV2Converter().convert(recipe)["recipe"]
    assert doc["original_gravity"] == {"value": 1.044, "unit": "sg"}
    assert doc["final_gravity"] == {"value": 1.011, "unit": "sg"}
    for key in ("alcohol_by_volume", "ibu_estimate", "color_estimate"):
        assert key not in doc
    res = await RecipeImporter().import_recipe(
        json.dumps(RecipeToBrewSignalV2Converter().convert(recipe)), None, test_db)
    assert res.success, res.errors
    assert (res.recipe.target_og, res.recipe.target_fg) == (1.044, 1.011)
    assert res.recipe.target_abv is None and res.recipe.target_ibu is None and res.recipe.target_srm is None

    # no targets: no stat fields, and none come back
    n = await _recipe(test_db, name="NoTargets")
    doc2 = RecipeToBrewSignalV2Converter().convert(await _export_recipe(test_db, n.id))
    for key in ("original_gravity", "final_gravity", "alcohol_by_volume", "ibu_estimate", "color_estimate"):
        assert key not in doc2["recipe"]
    res2 = await RecipeImporter().import_recipe(json.dumps(doc2), None, test_db)
    assert res2.success, res2.errors
    assert all(getattr(res2.recipe, f"target_{k}") is None for k in ("og", "fg", "abv", "ibu", "srm"))


@pytest.mark.asyncio
async def test_sync_batch_sends_expected_columns(test_db):
    from backend.routers.sync import _sync_batch

    sent = {}

    class Resp:
        status_code = 201

    class Client:
        async def post(self, url, headers=None, json=None):
            sent.update(json)
            return Resp()

    b = Batch(name="s", status="fermenting", expected_og=1.050, expected_fg=1.010, expected_srm=5.5,
              created_at=datetime.now(timezone.utc))
    test_db.add(b)
    await test_db.commit()
    await _sync_batch(Client(), "http://x", {}, b, "user")
    assert {n: sent[n] for n in EXPECTED} == {
        "expected_og": 1.050, "expected_fg": 1.010, "expected_abv": None, "expected_ibu": None, "expected_srm": 5.5}


@pytest.mark.asyncio
async def test_resnapshot_resets_rest_hold_state(client, test_db):
    r1, bid = await _running_batch(client, test_db)
    r2 = await _recipe(test_db, name="Two")
    r2.efficiency_percent = 50.0
    await test_db.commit()
    fired = datetime.now(timezone.utc)
    b = await test_db.get(Batch, bid)
    b.rest_below_since = b.rest_confirmed_at = fired
    b.rest_hold_trigger_sg = 1.02
    b.rest_fired_at = fired
    await test_db.commit()
    resp = await client.put(f"/api/batches/{bid}", json={"recipe_id": r2.id})
    assert resp.status_code == 200, resp.text
    after = await _fresh(test_db, bid)
    assert after.rest_below_since is None and after.rest_confirmed_at is None and after.rest_hold_trigger_sg is None
    assert after.rest_fired_at is not None  # one-shot stays fired


@pytest.mark.asyncio
async def test_progress_planning_batch_reads_recipe_live(client, test_db):
    r = await _recipe(test_db)
    bid = await _new_batch(client, r.id)  # planning
    stats = effective_stats(await _load_recipe(test_db, r.id))
    resp = await client.get(f"/api/batches/{bid}/progress")
    assert resp.status_code == 200, resp.text
    targets = resp.json()["targets"]
    assert targets["og"] == pytest.approx(stats.og) and targets["fg"] == pytest.approx(stats.fg)


@pytest.mark.asyncio
async def test_progress_keeps_snapshot_targets_without_recipe(client, test_db):
    b = Batch(name="orphan", status="completed", recipe_id=None, expected_og=1.050, expected_fg=1.010)
    test_db.add(b)
    await test_db.commit()
    resp = await client.get(f"/api/batches/{b.id}/progress")
    assert resp.status_code == 200, resp.text
    assert resp.json()["targets"]["og"] == 1.050 and resp.json()["targets"]["fg"] == 1.010
