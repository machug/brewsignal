"""Dry hop reminder (tilt_ui-n1w7)."""

import pytest
from sqlalchemy import select

from backend.models import Batch, FermentationAlert, Reading, Recipe, RecipeHop
from backend.services.alert_service import AlertType, detect_and_persist_alerts

HOPS = (("Citra", 35), ("Amarillo", 25), ("Mosaic", 20))


async def _batch(db, hops=True, trigger=None, done=None, status="fermenting"):
    recipe = Recipe(name="APA", target_og=1.050, target_fg=1.011)
    db.add(recipe)
    await db.flush()
    if hops:
        for name, g in HOPS:
            db.add(RecipeHop(recipe_id=recipe.id, name=name, amount_grams=g, timing={"use": "dry_hop"}))
        db.add(RecipeHop(recipe_id=recipe.id, name="Magnum", amount_grams=10, timing={"use": "add_to_boil"}))
    batch = Batch(name="APA", status=status, recipe_id=recipe.id, expected_og=1.050, expected_fg=1.011, dry_hop_trigger_sg=trigger, dry_hop_done_at=done)
    db.add(batch)
    await db.flush()
    return batch


async def _run(db, batch, sg):
    reading = Reading(batch_id=batch.id, sg_raw=sg, sg_calibrated=sg)
    db.add(reading)
    await db.flush()
    await detect_and_persist_alerts(
        db=db, batch_id=batch.id, device_id="BLUE", reading=reading,
        live_reading={"sg": sg}, og=1.050, fg=1.011,
    )
    await db.flush()
    return (await db.execute(select(FermentationAlert).where(
        FermentationAlert.batch_id == batch.id,
        FermentationAlert.alert_type == AlertType.DRY_HOP_DUE,
        FermentationAlert.cleared_at.is_(None),
    ))).scalars().all()


@pytest.mark.asyncio
async def test_raised_at_and_below_explicit_trigger(test_db):
    batch = await _batch(test_db, trigger=1.025)
    assert await _run(test_db, batch, 1.026) == []
    rows = await _run(test_db, batch, 1.025)
    assert len(rows) == 1 and rows[0].severity == "warning"
    assert "Citra 35 g, Amarillo 25 g, Mosaic 20 g" in rows[0].message
    assert "Magnum" not in rows[0].message


@pytest.mark.asyncio
async def test_default_trigger_is_65_percent(test_db):
    batch = await _batch(test_db)  # 1.050 - 0.039 * 0.65 = 1.02465
    assert await _run(test_db, batch, 1.025) == []
    assert len(await _run(test_db, batch, 1.024)) == 1


@pytest.mark.asyncio
async def test_not_raised_without_dry_hops(test_db):
    assert await _run(test_db, await _batch(test_db, hops=False, trigger=1.025), 1.020) == []


@pytest.mark.asyncio
async def test_not_raised_when_done_or_not_fermenting(test_db):
    from datetime import datetime, timezone
    done = await _batch(test_db, trigger=1.025, done=datetime.now(timezone.utc))
    assert await _run(test_db, done, 1.020) == []
    planning = await _batch(test_db, trigger=1.025, status="planning")
    assert await _run(test_db, planning, 1.020) == []


@pytest.mark.asyncio
async def test_stays_raised_when_gravity_bounces_back(test_db):
    batch = await _batch(test_db, trigger=1.025)
    assert len(await _run(test_db, batch, 1.024)) == 1
    assert len(await _run(test_db, batch, 1.030)) == 1


@pytest.mark.asyncio
async def test_endpoint_sets_done_and_clears_alert(client, test_db):
    batch = await _batch(test_db, trigger=1.025)
    assert len(await _run(test_db, batch, 1.020)) == 1
    await test_db.commit()
    resp = await client.post(f"/api/batches/{batch.id}/dry-hop-done")
    assert resp.status_code == 200
    assert resp.json()["dry_hop_done_at"] is not None
    assert resp.json()["dry_hop_trigger_sg"] == 1.025
    assert await _run(test_db, batch, 1.020) == []


@pytest.mark.asyncio
async def test_endpoint_404_missing(client):
    assert (await client.post("/api/batches/9999/dry-hop-done")).status_code == 404


@pytest.mark.asyncio
async def test_dismiss_all_keeps_the_dry_hop_reminder(test_db):
    from backend.routers.batches import dismiss_all_alerts
    from backend.models import FermentationAlert
    from backend.services.alert_service import AlertType
    from datetime import datetime, timezone
    batch = Batch(name="DH", status="fermenting")
    test_db.add(batch)
    await test_db.flush()
    now = datetime.now(timezone.utc)
    for t in (AlertType.DRY_HOP_DUE, AlertType.STALL):
        test_db.add(FermentationAlert(batch_id=batch.id, alert_type=t, severity="warning", message=t,
                                      first_detected_at=now, last_seen_at=now))
    await test_db.flush()
    await dismiss_all_alerts(batch.id, test_db)
    left = (await test_db.execute(select(FermentationAlert.alert_type).where(
        FermentationAlert.batch_id == batch.id, FermentationAlert.cleared_at.is_(None)))).scalars().all()
    assert left == [AlertType.DRY_HOP_DUE]
