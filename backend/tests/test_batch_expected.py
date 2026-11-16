"""Batch expected stats (tilt_ui-4x2f.3): live while planning/brewing, snapshot from fermenting."""
import json
from datetime import datetime, timezone

import pytest
from sqlalchemy import select, text

from backend import database as dbm
from backend import temp_controller as tc
from backend.models import Batch, FermentationAlert, Reading, Recipe, RecipeFermentable, RecipeHop
from backend.services.alert_service import AlertType, detect_and_persist_alerts
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


@pytest.mark.asyncio
async def test_recipe_edit_does_not_move_fermenting_batch(client, test_db, monkeypatch):
    r = await _recipe(test_db)
    bid = await _new_batch(client, r.id)
    await client.put(f"/api/batches/{bid}", json={"status": "fermenting"})
    batch = await _load_batch(test_db, bid)
    og0, fg0 = batch.expected_og, batch.expected_fg
    trigger0 = tc.rest_trigger_sg(og0, fg0, 65)

    resp = await client.put(f"/api/recipes/{r.id}", json={"efficiency_percent": 40.0})
    assert resp.status_code == 200, resp.text
    assert effective_stats(await _load_recipe(test_db, r.id)).fg != fg0  # the edit did move the recipe

    batch = await _load_batch(test_db, bid)  # fresh read
    assert (batch.expected_og, batch.expected_fg) == (og0, fg0)
    # rest rule inputs
    assert await tc._rest_gravities(test_db, batch) == (og0, fg0)
    # dry hop alert: default trigger comes from the snapshot
    test_db.add(RecipeHop(recipe_id=r.id, name="Citra", amount_grams=30, timing={"use": "dry_hop"}))
    await test_db.commit()
    sg = round(trigger0 - 0.0005, 4)
    reading = Reading(batch_id=bid, sg_raw=sg, sg_calibrated=sg)
    test_db.add(reading)
    await test_db.flush()
    await detect_and_persist_alerts(db=test_db, batch_id=bid, device_id="BLUE", reading=reading,
                                    live_reading={"sg": sg}, og=og0, fg=fg0)
    alerts = (await test_db.execute(select(FermentationAlert).where(
        FermentationAlert.batch_id == bid, FermentationAlert.alert_type == AlertType.DRY_HOP_DUE))).scalars().all()
    assert len(alerts) == 1 and json.loads(alerts[0].context)["trigger_sg"] == pytest.approx(trigger0)
    # ML expected FG
    from backend.ml.pipeline_manager import MLPipelineManager
    seen = {}
    mgr = MLPipelineManager()
    monkeypatch.setattr(mgr, "get_device_state", lambda device_id, **kw: seen.update(kw) or None)
    batch.device_id = "BLUE"
    await mgr.predict_batch(test_db, await _load_batch(test_db, bid))
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


@pytest.mark.asyncio
async def test_backfill_uses_legacy_stats_for_running_batches(test_db):
    # stored legacy og/fg differ from what the calculator gives for the ingredients
    r = await _recipe(test_db, og=1.099, fg=1.033, abv=9.9, ibu=77.0, color_srm=12.0)
    live = Batch(name="plan", status="planning", recipe_id=r.id)
    ferm = Batch(name="f", status="fermenting", recipe_id=r.id)
    done = Batch(name="d", status="completed", recipe_id=r.id)
    gone = Batch(name="x", status="fermenting", recipe_id=r.id, deleted_at=datetime.now(timezone.utc))
    test_db.add_all([live, ferm, done, gone])
    await test_db.commit()
    # run the migration again as if the columns were new
    async with test_db.bind.begin() as conn:
        for name in EXPECTED:
            await conn.execute(text(f"ALTER TABLE batches DROP COLUMN {name}"))
        assert await conn.run_sync(dbm._migrate_add_batch_expected_columns) is True
        # second run is a no-op
        assert await conn.run_sync(dbm._migrate_add_batch_expected_columns) is False
    for b in (ferm, done, gone):
        row = (await test_db.execute(text(
            "SELECT expected_og, expected_fg, expected_abv, expected_ibu, expected_srm FROM batches WHERE id=:i"),
            {"i": b.id})).one()
        assert tuple(row) == (1.099, 1.033, 9.9, 77.0, 12.0), b.name
    row = (await test_db.execute(text("SELECT expected_og FROM batches WHERE id=:i"), {"i": live.id})).one()
    assert row[0] is None
    assert effective_stats(await _load_recipe(test_db, r.id)).og != 1.099  # stored really differs


@pytest.mark.asyncio
async def test_backfill_calculator_fallback_fills_gaps(test_db, monkeypatch):
    r = await _recipe(test_db)  # no legacy stats stored
    b = Batch(name="f", status="fermenting", recipe_id=r.id)
    test_db.add(b)
    await test_db.commit()
    from sqlalchemy.ext.asyncio import async_sessionmaker
    monkeypatch.setattr(dbm, "async_session_factory", async_sessionmaker(test_db.bind, expire_on_commit=False))
    await dbm._backfill_batch_expected_from_calculator()
    b = await _load_batch(test_db, b.id)
    assert b.expected_og == effective_stats(await _load_recipe(test_db, r.id)).og


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
