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


async def _run(db, batch, sgs, step=timedelta(hours=2), start=T0, status="valid", **kw):
    """Store one reading per ``step`` with the given SGs, running detection after each."""
    at = start
    for sg in sgs:
        reading = Reading(batch_id=batch.id, device_id="BLUE", sg_calibrated=sg, timestamp=at, status=status)
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


@pytest.mark.asyncio
async def test_gravity_drop_clears_then_reraises_after_new_flat_window(test_db, _no_push):
    batch = await _batch(test_db)
    at = await _run(test_db, batch, [1.013] * 30)  # 58 h flat, 3 pt above FG
    assert len(await _alerts(test_db, batch)) == 1
    at = await _run(test_db, batch, [1.013 - 0.0005 * i for i in range(1, 7)], start=at)  # hop creep: -> 1.010
    assert await _alerts(test_db, batch) == []
    at = await _run(test_db, batch, [1.010] * 20, start=at)  # 40 h flat: not yet
    assert await _alerts(test_db, batch) == []
    await _run(test_db, batch, [1.010] * 6, start=at)  # 52 h flat
    assert len(await _alerts(test_db, batch)) == 1
    assert len(_no_push) == 2


@pytest.mark.asyncio
async def test_small_wobble_keeps_alert(test_db):
    batch = await _batch(test_db)
    at = await _run(test_db, batch, [1.011] * 30)
    await _run(test_db, batch, [1.010, 1.009, 1.010], start=at)
    assert len(await _alerts(test_db, batch)) == 1


@pytest.mark.asyncio
async def test_slow_fall_after_clear_waits_full_window(test_db, _no_push):
    batch = await _batch(test_db)
    at = await _run(test_db, batch, [1.013] * 30)
    assert len(await _alerts(test_db, batch)) == 1
    # 0.03 pt/h: under 2 pt per 48 h, yet it drifts 2+ pt below the alert value.
    sgs = [1.013 - 0.00003 * 2 * i for i in range(1, 70)]  # runs well past clear + 48 h
    await _run(test_db, batch, sgs, start=at)
    assert await _alerts(test_db, batch) == []
    assert len(_no_push) == 1


@pytest.mark.asyncio
async def test_crash_cancels_pending_rearm(test_db, _no_push):
    batch = await _batch(test_db)
    at = await _run(test_db, batch, [1.013] * 30, temp_target=19.0)
    at = await _run(test_db, batch, [1.013 - 0.0005 * i for i in range(1, 7)], start=at, temp_target=19.0)
    assert await _alerts(test_db, batch) == []  # cleared by hop creep, re-raise pending
    at = await _run(test_db, batch, [1.010], start=at, temp_target=2.0)  # brewer crashes anyway
    await _run(test_db, batch, [1.010] * 40, start=at, temp_target=19.0)  # then warms it back up
    assert await _alerts(test_db, batch) == []
    assert len(_no_push) == 1


@pytest.mark.asyncio
async def test_exact_boundaries_count(test_db):
    """1.014 - 1.010 is a hair over 0.004 as a float: 4 pt above FG must still fire."""
    batch = await _batch(test_db)
    at = await _run(test_db, batch, [1.014] * 30)
    assert len(await _alerts(test_db, batch)) == 1
    await _run(test_db, batch, [1.012] * 3, start=at)  # exactly 2 pt below: still held
    assert len(await _alerts(test_db, batch)) == 1


@pytest.mark.asyncio
async def test_rise_and_return_inside_window_does_not_fire(test_db):
    batch = await _batch(test_db)
    sgs = [1.010] * 6 + [1.020] * 6 + [1.016] * 6 + [1.012] * 6 + [1.010] * 6  # sugar added mid-window
    await _run(test_db, batch, sgs)
    assert await _alerts(test_db, batch) == []


@pytest.mark.asyncio
async def test_rise_clears_active_alert(test_db):
    batch = await _batch(test_db)
    at = await _run(test_db, batch, [1.010] * 30)
    assert len(await _alerts(test_db, batch)) == 1
    await _run(test_db, batch, [1.014] * 3, start=at)  # fruit added: fermenting again
    assert await _alerts(test_db, batch) == []


@pytest.mark.asyncio
async def test_one_sparse_reading_cannot_clear(test_db):
    batch = await _batch(test_db)
    at = await _run(test_db, batch, [1.010] * 30)
    await _run(test_db, batch, [1.006], start=at + timedelta(hours=3))  # lone wobble after a 5 h gap
    assert len(await _alerts(test_db, batch)) == 1


@pytest.mark.asyncio
async def test_invalid_readings_ignored(test_db):
    batch = await _batch(test_db)
    at = await _run(test_db, batch, [1.010] * 30)
    await _run(test_db, batch, [0.990] * 3, start=at, status="invalid")
    assert len(await _alerts(test_db, batch)) == 1


@pytest.mark.asyncio
async def test_dry_hop_marked_done_late_waits_a_window(test_db):
    recipe = Recipe(name="APA", target_og=OG, target_fg=FG)
    test_db.add(recipe)
    await test_db.flush()
    test_db.add(RecipeHop(recipe_id=recipe.id, name="Citra", amount_grams=50, timing={"use": "dry_hop"}))
    batch = await _batch(test_db, recipe_id=recipe.id, dry_hop_trigger_sg=1.005,
                         dry_hop_done_at=T0 + timedelta(hours=50))  # dry hopped at FG
    at = await _run(test_db, batch, [1.010] * 49)  # 0-96 h: under 48 h since the dry hop
    assert await _alerts(test_db, batch) == []
    await _run(test_db, batch, [1.010], start=at)  # 98 h: 48 h after the dry hop
    assert len(await _alerts(test_db, batch)) == 1


@pytest.mark.asyncio
async def test_dismiss_via_api_is_final_and_survives_reload(client, test_db, _no_push):
    batch = await _batch(test_db)
    at = await _run(test_db, batch, [1.010] * 30)
    (alert,) = await _alerts(test_db, batch)
    await test_db.commit()
    r = await client.post(f"/api/batches/{batch.id}/alerts/{alert.id}/dismiss")
    assert r.status_code == 200, r.text
    test_db.expire_all()
    await test_db.refresh(batch)
    await _run(test_db, batch, [1.010] * 30, start=at)
    assert await _alerts(test_db, batch) == []
    assert len(_no_push) == 1


@pytest.mark.asyncio
async def test_rearm_wait_survives_reload(test_db, _no_push):
    batch = await _batch(test_db)
    at = await _run(test_db, batch, [1.013] * 30)
    at = await _run(test_db, batch, [1.013 - 0.0005 * i for i in range(1, 7)], start=at)
    await test_db.commit()
    test_db.expire_all()  # cleared_at and context now come back from SQLite
    await test_db.refresh(batch)
    at = await _run(test_db, batch, [1.010] * 23, start=at)  # 46 h: too soon
    assert await _alerts(test_db, batch) == []
    await _run(test_db, batch, [1.010] * 3, start=at)
    assert len(await _alerts(test_db, batch)) == 1


@pytest.mark.asyncio
async def test_fires_at_48h_not_52h(test_db):
    """The window is 48 h (old code looked back 52 h): flat from 6 h fires by 54 h."""
    batch = await _batch(test_db)
    at = await _run(test_db, batch, [1.020, 1.017, 1.014])  # still falling, 0-4 h
    at = await _run(test_db, batch, [1.010] * 23, start=at)  # flat 6-50 h
    assert await _alerts(test_db, batch) == []  # 50 h: oldest bucket still holds the fall
    await _run(test_db, batch, [1.010] * 2, start=at)  # 52-54 h
    assert len(await _alerts(test_db, batch)) == 1


@pytest.mark.asyncio
async def test_steady_slow_fall_blocked_on_first_raise(test_db):
    """0.9 pt/day: every bucket within 2 pt of now, but the slope says still fermenting."""
    batch = await _batch(test_db)
    await _run(test_db, batch, [1.0118 - 0.0000375 * 2 * i for i in range(30)])
    assert await _alerts(test_db, batch) == []


@pytest.mark.asyncio
async def test_one_outlier_does_not_block(test_db):
    batch = await _batch(test_db)
    sgs = [1.010] * 53
    sgs[44] = 0.990  # one bad hourly hit inside an otherwise flat window
    await _run(test_db, batch, sgs, step=timedelta(hours=1))
    assert len(await _alerts(test_db, batch)) == 1


@pytest.mark.asyncio
async def test_alert_at_fg_margin_does_not_flap(test_db):
    batch = await _batch(test_db)
    at = await _run(test_db, batch, [1.014] * 30)
    await _run(test_db, batch, [1.0142] * 3, start=at)
    assert len(await _alerts(test_db, batch)) == 1


@pytest.mark.asyncio
async def test_sparse_sensor_can_clear_on_hop_creep(test_db):
    """A 3 h reporter never has 3 readings in 4 h; its last 3 readings are used."""
    batch = await _batch(test_db)
    at = await _run(test_db, batch, [1.013] * 20, step=timedelta(hours=3))
    assert len(await _alerts(test_db, batch)) == 1
    await _run(test_db, batch, [1.010] * 3, start=at, step=timedelta(hours=3))
    assert await _alerts(test_db, batch) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("block", ["fg_removed", "dry_hop_done"])
async def test_plan_change_clears_active_alert_even_without_readings(test_db, block):
    batch = await _batch(test_db)
    at = await _run(test_db, batch, [1.010] * 30)
    assert len(await _alerts(test_db, batch)) == 1
    kw = {}
    if block == "fg_removed":
        kw["fg"] = None
    else:
        batch.dry_hop_done_at = at  # dry hopped now: hop creep may follow
    await _run(test_db, batch, [1.010], start=at + timedelta(hours=5), **kw)  # lone reading after a gap
    assert await _alerts(test_db, batch) == []


@pytest.mark.asyncio
async def test_rearm_without_rearm_from_uses_cleared_at(test_db):
    """Rows cleared by the first version of the rule carry no rearm_from."""
    batch = await _batch(test_db)
    test_db.add(FermentationAlert(
        batch_id=batch.id, device_id="BLUE", alert_type=AlertType.CRASH_READY, severity="info",
        message="old", context='{"sg": 1.013, "rearm": true}',
        first_detected_at=T0, last_seen_at=T0, cleared_at=T0 + timedelta(hours=10),
    ))
    await test_db.flush()
    at = await _run(test_db, batch, [1.010] * 29)  # 0-56 h: 46 h after the clear
    assert await _alerts(test_db, batch) == []
    await _run(test_db, batch, [1.010], start=at)  # 58 h: 48 h after
    assert len(await _alerts(test_db, batch)) == 1


@pytest.mark.asyncio
async def test_stale_readings_before_dropout_cannot_clear(test_db):
    """After a 7 h dropout the readings before it are too old to count as recent."""
    batch = await _batch(test_db)
    half = timedelta(minutes=30)
    at = await _run(test_db, batch, [1.010] * 110 + [1.0125, 1.0125], step=half)
    assert len(await _alerts(test_db, batch)) == 1  # two wobbles: the 4 h median is still 1.010
    await _run(test_db, batch, [1.013], start=at + timedelta(hours=7))
    assert len(await _alerts(test_db, batch)) == 1  # one reading back: too few to judge


@pytest.mark.asyncio
async def test_exact_slope_limit_still_fires(test_db):
    """Falling exactly 0.6 pt/day is the limit itself, not past it."""
    batch = await _batch(test_db)
    await _run(test_db, batch, [1.0112 - 0.0000025 * 20 * i for i in range(30)])  # 0.05 pt per 2 h
    assert len(await _alerts(test_db, batch)) == 1


@pytest.mark.asyncio
async def test_dry_hop_done_endpoint_takes_alert_down_and_rearms(client, test_db):
    batch = await _batch(test_db)
    at = await _run(test_db, batch, [1.010] * 30)
    assert len(await _alerts(test_db, batch)) == 1
    await test_db.commit()
    r = await client.post(f"/api/batches/{batch.id}/dry-hop-done")
    assert r.status_code == 200, r.text
    test_db.expire_all()
    await test_db.refresh(batch)
    assert await _alerts(test_db, batch) == []
    (old,) = await _alerts(test_db, batch, active_only=False)
    assert '"rearm": true' in old.context


@pytest.mark.asyncio
async def test_five_hour_reporter_still_judged(test_db):
    """A 5 h cadence has under 3 readings in any 6 h, but no gap over 6 h."""
    batch = await _batch(test_db)
    at = await _run(test_db, batch, [1.013] * 12, step=timedelta(hours=5))
    assert len(await _alerts(test_db, batch)) == 1
    await _run(test_db, batch, [1.010] * 3, start=at, step=timedelta(hours=5))
    assert await _alerts(test_db, batch) == []
