"""Ready-to-cold-crash alert (tilt_ui-v25i): gravity flat for 48 h at the expected FG."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from backend.models import Batch, FermentationAlert, Reading, Recipe, RecipeHop
from backend.services import push
from backend.services.alert_service import AlertType, detect_and_persist_alerts

T0 = datetime(2026, 11, 1, 0, 0, tzinfo=timezone.utc)
OG, FG = 1.050, 1.010


@pytest.fixture(autouse=True)
def _no_push(monkeypatch):
    sent = []
    monkeypatch.setattr(push, "notify_soon", lambda *a: sent.append(a))
    return sent


async def _batch(db, **kw):
    batch = Batch(name="APA", status="fermenting", device_id="BLUE", **kw)
    db.add(batch)
    await db.flush()
    return batch


async def _run(db, batch, sgs, step=timedelta(hours=2), start=T0, **kw):
    """Store one reading per ``step`` with the given SGs, running detection after each."""
    at = start
    for sg in sgs:
        reading = Reading(batch_id=batch.id, device_id="BLUE", sg_calibrated=sg, timestamp=at)
        db.add(reading)
        await db.flush()
        await detect_and_persist_alerts(
            db=db, batch_id=batch.id, device_id="BLUE", reading=reading,
            live_reading={"sg": sg}, og=OG, now=at, **{"fg": FG, **kw},
        )
        await db.flush()
        at += step
    return at


async def _alerts(db, batch, active_only=True):
    q = select(FermentationAlert).where(
        FermentationAlert.batch_id == batch.id,
        FermentationAlert.alert_type == AlertType.CRASH_READY,
    )
    if active_only:
        q = q.where(FermentationAlert.cleared_at.is_(None))
    return (await db.execute(q)).scalars().all()


@pytest.mark.asyncio
async def test_flat_at_fg_for_48h_raises_once_with_push(test_db, _no_push):
    batch = await _batch(test_db)
    await _run(test_db, batch, [1.011, 1.010, 1.011] * 8)  # 46 h span: not yet
    assert await _alerts(test_db, batch) == []
    await _run(test_db, batch, [1.010] * 3, start=T0 + timedelta(hours=48))
    assert len(await _alerts(test_db, batch)) == 1
    assert [t for t, *_ in _no_push] == ["Ready to cold crash: APA"]


@pytest.mark.asyncio
@pytest.mark.parametrize("sgs", [
    [1.016 - 0.0002 * i for i in range(30)],  # still dropping 1.016 -> 1.010
    [1.020] * 30,  # flat, but 10 pt above FG: that is a stall
])
async def test_still_dropping_or_above_fg_does_not_raise(test_db, sgs):
    batch = await _batch(test_db)
    await _run(test_db, batch, sgs)
    assert await _alerts(test_db, batch) == []


@pytest.mark.asyncio
async def test_no_fg_no_alert(test_db):
    batch = await _batch(test_db)
    await _run(test_db, batch, [1.010] * 30, fg=None)
    assert await _alerts(test_db, batch) == []


@pytest.mark.asyncio
async def test_crash_started_clears_and_dismiss_does_not_reraise(test_db, _no_push):
    batch = await _batch(test_db)
    at = await _run(test_db, batch, [1.010] * 30, temp_target=19.0)
    assert len(await _alerts(test_db, batch)) == 1
    await _run(test_db, batch, [1.010], start=at, temp_target=2.0)  # brewer starts the crash
    assert await _alerts(test_db, batch) == []
    await _run(test_db, batch, [1.010] * 3, start=at + timedelta(hours=2), temp_target=19.0)
    assert await _alerts(test_db, batch) == []  # once per batch: no second ping
    assert len(_no_push) == 1


@pytest.mark.asyncio
async def test_pending_dry_hop_blocks(test_db):
    batch = await _batch(test_db)
    test_db.add(FermentationAlert(
        batch_id=batch.id, device_id="BLUE", alert_type=AlertType.DRY_HOP_DUE,
        severity="warning", message="Dry hop now", first_detected_at=T0, last_seen_at=T0,
    ))
    await test_db.flush()
    await _run(test_db, batch, [1.010] * 30)
    assert await _alerts(test_db, batch) == []


@pytest.mark.asyncio
async def test_gap_in_window_does_not_count_as_flat(test_db):
    batch = await _batch(test_db)
    at = await _run(test_db, batch, [1.010] * 3)  # 0-4 h
    await _run(test_db, batch, [1.010] * 3, start=at + timedelta(hours=44))  # back after an outage
    assert await _alerts(test_db, batch) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("change", [{"status": "completed"}, {"temp_target": 2.0}])
async def test_batch_update_clears_alert(client, test_db, change):
    batch = await _batch(test_db)
    await _run(test_db, batch, [1.010] * 30)
    await test_db.commit()
    assert len(await _alerts(test_db, batch)) == 1
    r = await client.put(f"/api/batches/{batch.id}", json=change)
    assert r.status_code == 200, r.text
    assert await _alerts(test_db, batch) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("done,raised", [(None, False), (T0, True)])
async def test_unfinished_dry_hop_blocks_before_its_reminder(test_db, done, raised):
    recipe = Recipe(name="APA", target_og=OG, target_fg=FG)
    test_db.add(recipe)
    await test_db.flush()
    test_db.add(RecipeHop(recipe_id=recipe.id, name="Citra", amount_grams=50, timing={"use": "dry_hop"}))
    # Trigger below where gravity sits, so the dry hop reminder never fires.
    batch = await _batch(test_db, recipe_id=recipe.id, dry_hop_trigger_sg=1.005, dry_hop_done_at=done)
    await _run(test_db, batch, [1.010] * 30)
    assert len(await _alerts(test_db, batch)) == (1 if raised else 0)
