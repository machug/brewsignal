"""Ready-to-cold-crash alert (tilt_ui-v25i): gravity flat for 48 h at the expected FG."""

import json
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


async def _run(db, batch, sgs, step=timedelta(hours=2), start=T0, status="valid", temp=None, **kw):
    """Store one reading per ``step`` with the given SGs, running detection after each."""
    at = start
    for sg in sgs:
        reading = Reading(batch_id=batch.id, device_id="BLUE", sg_calibrated=sg, timestamp=at, status=status,
                          temp_calibrated=temp)
        db.add(reading)
        await db.flush()
        await detect_and_persist_alerts(
            db=db, batch_id=batch.id, device_id="BLUE", reading=reading,
            live_reading={"sg": sg, "temp": temp}, og=OG, now=at, **{"fg": FG, **kw},
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
    assert [t for t, *_ in _no_push] == ["Ready to cold crash: APA", "Not ready to cold crash after all: APA", "Ready to cold crash: APA"]


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
    assert [t for t, *_ in _no_push] == ["Ready to cold crash: APA", "Not ready to cold crash after all: APA"]


@pytest.mark.asyncio
async def test_crash_cancels_pending_rearm(test_db, _no_push):
    batch = await _batch(test_db)
    at = await _run(test_db, batch, [1.013] * 30, temp_target=19.0)
    at = await _run(test_db, batch, [1.013 - 0.0005 * i for i in range(1, 7)], start=at, temp_target=19.0)
    assert await _alerts(test_db, batch) == []  # cleared by hop creep, re-raise pending
    at = await _run(test_db, batch, [1.010], start=at, temp_target=2.0)  # brewer crashes anyway
    await _run(test_db, batch, [1.010] * 40, start=at, temp_target=19.0)  # then warms it back up
    assert await _alerts(test_db, batch) == []
    assert [t for t, *_ in _no_push] == ["Ready to cold crash: APA", "Not ready to cold crash after all: APA"]


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


async def _not_ready(db, batch):
    return (await db.execute(select(FermentationAlert).where(
        FermentationAlert.batch_id == batch.id,
        FermentationAlert.alert_type == AlertType.CRASH_NOT_READY,
        FermentationAlert.cleared_at.is_(None),
    ))).scalars().all()


@pytest.mark.asyncio
@pytest.mark.parametrize("after,word", [(1.0105, "fell"), (1.0155, "rose")])
async def test_gravity_move_says_why_the_alert_went(test_db, after, word):
    batch = await _batch(test_db)
    at = await _run(test_db, batch, [1.013] * 30)
    assert await _not_ready(test_db, batch) == []
    await _run(test_db, batch, [after] * 3, start=at)
    (alert,) = await _not_ready(test_db, batch)
    assert alert.severity == "warning"
    assert f"Gravity {word} 2.5 points after holding at 1.013" in alert.message


@pytest.mark.asyncio
async def test_not_ready_clears_when_ready_again(test_db):
    batch = await _batch(test_db)
    at = await _run(test_db, batch, [1.013] * 30)
    at = await _run(test_db, batch, [1.010] * 3, start=at)
    assert len(await _not_ready(test_db, batch)) == 1
    await _run(test_db, batch, [1.010] * 25, start=at)
    assert len(await _alerts(test_db, batch)) == 1
    assert await _not_ready(test_db, batch) == []


@pytest.mark.asyncio
async def test_not_ready_ends_with_the_crash(test_db):
    batch = await _batch(test_db)
    at = await _run(test_db, batch, [1.013] * 30, temp_target=19.0)
    at = await _run(test_db, batch, [1.010] * 3, start=at, temp_target=19.0)
    assert len(await _not_ready(test_db, batch)) == 1
    await _run(test_db, batch, [1.010], start=at, temp_target=2.0)
    assert await _not_ready(test_db, batch) == []


@pytest.mark.asyncio
async def test_plan_change_gives_no_not_ready_notice(test_db, _no_push):
    batch = await _batch(test_db)
    at = await _run(test_db, batch, [1.010] * 30)
    await _run(test_db, batch, [1.010] * 3, start=at, fg=None)  # brewer cleared the FG
    assert await _alerts(test_db, batch) == []
    assert await _not_ready(test_db, batch) == []
    assert len(_no_push) == 1



@pytest.mark.asyncio
@pytest.mark.parametrize("cold", [14.0, 3.0])  # fermenter moved to a fridge; target left alone
async def test_unseen_crash_ends_it_without_a_rise_warning(test_db, _no_push, cold):
    batch = await _batch(test_db)
    at = await _run(test_db, batch, [1.010] * 30, temp=19.0)
    assert len(await _alerts(test_db, batch)) == 1
    await _run(test_db, batch, [1.015] * 3, start=at, temp=cold)  # cold reads the hydrometer high
    assert await _alerts(test_db, batch) == []
    assert await _not_ready(test_db, batch) == []
    assert len(_no_push) == 1


@pytest.mark.asyncio
async def test_fg_cleared_takes_the_warning_down(test_db):
    batch = await _batch(test_db)
    at = await _run(test_db, batch, [1.013] * 30)
    at = await _run(test_db, batch, [1.010] * 3, start=at)
    assert len(await _not_ready(test_db, batch)) == 1
    await _run(test_db, batch, [1.010], start=at, fg=None)
    assert await _not_ready(test_db, batch) == []


@pytest.mark.asyncio
async def test_settles_flat_above_fg_clears_warning(test_db):
    """Rose and then held high for 48 h: a stall, not a wait for crash."""
    batch = await _batch(test_db)
    at = await _run(test_db, batch, [1.012] * 30)
    at = await _run(test_db, batch, [1.016] * 3, start=at)
    assert len(await _not_ready(test_db, batch)) == 1
    await _run(test_db, batch, [1.016] * 26, start=at)
    assert await _not_ready(test_db, batch) == []
    assert await _alerts(test_db, batch) == []


@pytest.mark.asyncio
async def test_own_plan_change_with_a_move_gives_no_warning(test_db, _no_push):
    batch = await _batch(test_db)
    at = await _run(test_db, batch, [1.010] * 30)
    batch.dry_hop_done_at = at  # dry hop went in; the hops shift the reading too
    await _run(test_db, batch, [1.0135] * 3, start=at)
    assert await _alerts(test_db, batch) == []
    assert await _not_ready(test_db, batch) == []
    assert len(_no_push) == 1


@pytest.mark.asyncio
async def test_warning_numbers_follow_gravity_without_more_pushes(test_db, _no_push):
    batch = await _batch(test_db)
    at = await _run(test_db, batch, [1.013] * 30)
    at = await _run(test_db, batch, [1.0105] * 3, start=at)
    await _run(test_db, batch, [1.007] * 3, start=at)
    (alert,) = await _not_ready(test_db, batch)
    assert "fell 6.0 points" in alert.message and "now 1.007" in alert.message
    assert len(_no_push) == 2


@pytest.mark.asyncio
async def test_hop_creep_named_only_after_a_dry_hop(test_db):
    batch = await _batch(test_db, dry_hop_done_at=T0 - timedelta(hours=60))
    at = await _run(test_db, batch, [1.013] * 30)
    await _run(test_db, batch, [1.010] * 3, start=at)
    (alert,) = await _not_ready(test_db, batch)
    assert "hop creep after the dry hop" in alert.message


@pytest.mark.asyncio
async def test_no_dry_hop_says_late_fermentation(test_db):
    batch = await _batch(test_db)
    at = await _run(test_db, batch, [1.013] * 30)
    await _run(test_db, batch, [1.010] * 3, start=at)
    (alert,) = await _not_ready(test_db, batch)
    assert "late fermentation" in alert.message and "hop creep" not in alert.message


@pytest.mark.asyncio
async def test_leaving_fermenting_clears_warning(client, test_db):
    batch = await _batch(test_db)
    at = await _run(test_db, batch, [1.013] * 30)
    await _run(test_db, batch, [1.010] * 3, start=at)
    await test_db.commit()
    assert len(await _not_ready(test_db, batch)) == 1
    r = await client.put(f"/api/batches/{batch.id}", json={"status": "conditioning"})
    assert r.status_code == 200, r.text
    test_db.expire_all()
    await test_db.refresh(batch)
    assert await _not_ready(test_db, batch) == []



@pytest.mark.asyncio
async def test_normal_cool_down_does_not_end_it(test_db):
    """Raised warm (22 C), wort later settles 5 C cooler: not a crash, alert stays."""
    batch = await _batch(test_db)
    at = await _run(test_db, batch, [1.010] * 30, temp=22.0)
    await _run(test_db, batch, [1.010] * 6, start=at, temp=17.0)
    assert len(await _alerts(test_db, batch)) == 1


@pytest.mark.asyncio
async def test_one_bad_temperature_cannot_end_it(test_db):
    batch = await _batch(test_db)
    at = await _run(test_db, batch, [1.010] * 30, temp=19.0)
    at = await _run(test_db, batch, [1.010], start=at, temp=-10.0)  # one glitch
    await _run(test_db, batch, [1.010] * 3, start=at, temp=19.0)
    assert len(await _alerts(test_db, batch)) == 1


@pytest.mark.asyncio
async def test_cooling_hard_with_a_rise_rearms_quietly(test_db, _no_push):
    """Crash started at 14 C (target left alone): the alert comes down, no "rose" push,
    and it is not ended for good (14 C could be a cellar, not a crash)."""
    batch = await _batch(test_db)
    at = await _run(test_db, batch, [1.010] * 30, temp=19.0)
    await _run(test_db, batch, [1.0135] * 3, start=at, temp=14.0)
    assert await _alerts(test_db, batch) == []
    assert await _not_ready(test_db, batch) == []
    (old,) = await _alerts(test_db, batch, active_only=False)
    assert '"rearm": true' in old.context
    assert len(_no_push) == 1


@pytest.mark.asyncio
async def test_warning_value_follows_gravity_back_toward_held(test_db):
    batch = await _batch(test_db)
    at = await _run(test_db, batch, [1.013] * 30)
    at = await _run(test_db, batch, [1.016] * 3, start=at)
    await _run(test_db, batch, [1.014] * 3, start=at)
    (alert,) = await _not_ready(test_db, batch)
    assert "now 1.014" in alert.message and "rose 1.0" not in alert.message
    assert "Gravity moved after holding at 1.013" in alert.message


@pytest.mark.asyncio
async def test_active_warning_returned_while_waiting(test_db):
    batch = await _batch(test_db)
    at = await _run(test_db, batch, [1.013] * 30)
    at = await _run(test_db, batch, [1.010] * 3, start=at)
    reading = Reading(batch_id=batch.id, device_id="BLUE", sg_calibrated=1.010, timestamp=at, status="valid")
    test_db.add(reading)
    await test_db.flush()
    out = await detect_and_persist_alerts(db=test_db, batch_id=batch.id, device_id="BLUE", reading=reading,
                                          live_reading={"sg": 1.010}, og=OG, fg=FG, now=at)
    assert AlertType.CRASH_NOT_READY in [a.alert_type for a in out]



@pytest.mark.asyncio
async def test_cooling_does_not_hide_a_fall(test_db):
    """Cold reads high, so a fall while cooling is real fermentation: warn."""
    batch = await _batch(test_db)
    at = await _run(test_db, batch, [1.013] * 30, temp=22.0)
    await _run(test_db, batch, [1.010] * 3, start=at, temp=17.0)
    (alert,) = await _not_ready(test_db, batch)
    assert "fell" in alert.message


@pytest.mark.asyncio
async def test_sparse_reporter_crash_in_fridge_ends_it(test_db, _no_push):
    """A 5 h reporter still gets a wort temperature, so a fridge crash ends the alert."""
    batch = await _batch(test_db)
    at = await _run(test_db, batch, [1.013] * 12, step=timedelta(hours=5), temp=19.0)
    assert len(await _alerts(test_db, batch)) == 1
    await _run(test_db, batch, [1.016] * 3, start=at, step=timedelta(hours=5), temp=2.0)
    assert await _alerts(test_db, batch) == []
    assert await _not_ready(test_db, batch) == []
    assert len(_no_push) == 1


@pytest.mark.asyncio
async def test_active_warning_returned_after_the_wait_too(test_db):
    """Past the 48 h wait but still falling: the warning is still reported."""
    batch = await _batch(test_db)
    at = await _run(test_db, batch, [1.013] * 30)
    at = await _run(test_db, batch, [1.010 - 0.0005 * i for i in range(30)], start=at)  # keeps falling 58 h
    reading = Reading(batch_id=batch.id, device_id="BLUE", sg_calibrated=0.995, timestamp=at, status="valid")
    test_db.add(reading)
    await test_db.flush()
    out = await detect_and_persist_alerts(db=test_db, batch_id=batch.id, device_id="BLUE", reading=reading,
                                          live_reading={"sg": 0.995}, og=OG, fg=FG, now=at)
    assert AlertType.CRASH_NOT_READY in [a.alert_type for a in out]



@pytest.mark.asyncio
async def test_fg_edit_with_a_move_gives_no_warning(test_db, _no_push):
    batch = await _batch(test_db)
    at = await _run(test_db, batch, [1.013] * 30)
    await _run(test_db, batch, [1.010] * 3, start=at, fg=1.008)  # brewer lowered the FG
    assert await _alerts(test_db, batch) == []
    assert await _not_ready(test_db, batch) == []
    assert len(_no_push) == 1


# --- diacetyl rest gate (tilt_ui-n8n5) ---

async def _control(db, on=True, ha_set_up=True):
    from backend.routers.config import set_config_value
    await set_config_value(db, "ha_enabled", on)
    await set_config_value(db, "temp_control_enabled", on)
    await set_config_value(db, "ha_url", "http://ha.local:8123" if ha_set_up else "")
    await set_config_value(db, "ha_token", "t0ken" if ha_set_up else "")


def _armed(**kw):
    return dict(rest_trigger_percent=75.0, rest_temp_target=21.0, heater_entity_id="switch.heat",
                temp_target=19.0, expected_og=OG, expected_fg=FG, **kw)


async def _rest_start_event(db, batch, at):
    from backend.models import ControlEvent
    db.add(ControlEvent(batch_id=batch.id, action="rest_start", timestamp=at, target_temp=21.0))
    await db.flush()


@pytest.mark.asyncio
async def test_rest_started_recently_holds_it_back(test_db):
    batch = await _batch(test_db, rest_trigger_percent=75.0, rest_temp_target=21.0, temp_target=21.0,
                         rest_fired_at=T0 + timedelta(hours=10))
    await _rest_start_event(test_db, batch, T0 + timedelta(hours=10))
    at = await _run(test_db, batch, [1.010] * 29)  # 0-56 h: rest is 46 h old
    assert await _alerts(test_db, batch) == []
    await _run(test_db, batch, [1.010], start=at)  # 58 h: 48 h of rest
    assert len(await _alerts(test_db, batch)) == 1


@pytest.mark.asyncio
async def test_rest_still_to_come_holds_it_back(test_db):
    await _control(test_db)
    batch = await _batch(test_db, **_armed())
    await _run(test_db, batch, [1.010] * 30)
    assert await _alerts(test_db, batch) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("why", ["control_off", "no_actuator", "ha_not_set_up", "crash_target", "no_og",
                                 "already_warm"])
async def test_rest_the_controller_will_not_run_does_not_block(test_db, why):
    await _control(test_db, on=why != "control_off", ha_set_up=why != "ha_not_set_up")
    kw = _armed()
    if why == "no_actuator":
        kw["heater_entity_id"] = None
    if why == "already_warm":
        kw["temp_target"] = 21.0  # at the rest temperature: the rule would not raise it
    if why == "no_og":
        kw["expected_og"] = None  # rule blocked: it can never work out its trigger
    batch = await _batch(test_db, **kw)
    if why == "crash_target":
        # Target in crash range: the rule does not run, and the crash itself ends the notice.
        batch.temp_target = 2.0
        await _run(test_db, batch, [1.010] * 30, temp_target=2.0)
        assert await _alerts(test_db, batch) == []
        return
    await _run(test_db, batch, [1.010] * 30)
    assert len(await _alerts(test_db, batch)) == 1


@pytest.mark.asyncio
async def test_rest_starting_takes_alert_down_quietly(test_db, _no_push):
    batch = await _batch(test_db, rest_trigger_percent=75.0, rest_temp_target=21.0, temp_target=21.0)
    at = await _run(test_db, batch, [1.010] * 30)
    assert len(await _alerts(test_db, batch)) == 1
    batch.rest_fired_at = at  # controller started the rest late (raised the target)
    await _rest_start_event(test_db, batch, at)
    at = await _run(test_db, batch, [1.010], start=at)
    assert await _alerts(test_db, batch) == []
    assert await _not_ready(test_db, batch) == []
    assert len(_no_push) == 1
    await _run(test_db, batch, [1.010] * 24, start=at)  # 48 h of rest
    assert len(await _alerts(test_db, batch)) == 1



@pytest.mark.asyncio
async def test_flat_above_rest_trigger_does_not_block(test_db):
    """Trigger at 95% is 1.012; gravity holds at 1.013, inside the 4 pt FG allowance:
    the rule can never fire, so the notice must not wait for it."""
    await _control(test_db)
    batch = await _batch(test_db, **{**_armed(), "rest_trigger_percent": 95.0})
    await _run(test_db, batch, [1.013] * 30)
    assert len(await _alerts(test_db, batch)) == 1


@pytest.mark.asyncio
async def test_rest_holding_blocks(test_db):
    """At or below the trigger the controller is holding before it fires: wait."""
    await _control(test_db)
    batch = await _batch(test_db, **_armed(rest_below_since=T0))
    await _run(test_db, batch, [1.010] * 30)
    assert await _alerts(test_db, batch) == []



@pytest.mark.asyncio
async def test_cooler_only_batch_waits_for_rest(test_db):
    await _control(test_db)
    batch = await _batch(test_db, **{**_armed(), "heater_entity_id": None, "cooler_entity_id": "switch.cool"})
    await _run(test_db, batch, [1.010] * 30)
    assert await _alerts(test_db, batch) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["rule_off", "target_lowered"])
async def test_rest_ended_early_stops_the_wait(test_db, change):
    kw = dict(rest_trigger_percent=75.0, rest_temp_target=21.0, temp_target=21.0,
              rest_fired_at=T0 + timedelta(hours=40))
    if change == "rule_off":
        kw["rest_trigger_percent"] = None
    else:
        kw["temp_target"] = 18.0  # brewer dropped back after a clean forced VDK test
    batch = await _batch(test_db, **kw)
    await _rest_start_event(test_db, batch, T0 + timedelta(hours=40))  # a real rest, so only the guard can free it
    await _run(test_db, batch, [1.010] * 30)
    assert len(await _alerts(test_db, batch)) == 1



@pytest.mark.asyncio
async def test_stale_holding_above_trigger_does_not_block(test_db):
    """One noisy dip set rest_below_since; gravity then settled above the trigger."""
    await _control(test_db)
    batch = await _batch(test_db, **{**_armed(rest_below_since=T0), "rest_trigger_percent": 95.0})
    await _run(test_db, batch, [1.013] * 30)
    assert len(await _alerts(test_db, batch)) == 1


@pytest.mark.asyncio
async def test_no_op_rest_firing_does_not_start_a_wait(test_db, _no_push):
    """Already warm: the rule fires without raising (no rest_start event), so nothing changed."""
    batch = await _batch(test_db, rest_trigger_percent=75.0, rest_temp_target=21.0, temp_target=21.0)
    at = await _run(test_db, batch, [1.010] * 30)
    assert len(await _alerts(test_db, batch)) == 1
    batch.rest_fired_at = at  # fired as a no-op
    await _run(test_db, batch, [1.010] * 3, start=at)
    assert len(await _alerts(test_db, batch)) == 1


@pytest.mark.asyncio
async def test_noise_at_trigger_cannot_pull_an_up_alert(test_db):
    """Up alert, armed rule, gravity wobbling across the trigger: the pending rest is not re-checked."""
    await _control(test_db)
    batch = await _batch(test_db, **{**_armed(), "rest_trigger_percent": 95.0})  # trigger 1.012
    at = await _run(test_db, batch, [1.013] * 30)
    assert len(await _alerts(test_db, batch)) == 1
    await _run(test_db, batch, [1.012] * 3, start=at)
    assert len(await _alerts(test_db, batch)) == 1



@pytest.mark.asyncio
async def test_old_rest_start_does_not_count_for_a_later_firing(test_db):
    """Rest raised once, then re-armed and fired again with nothing to raise."""
    batch = await _batch(test_db, rest_trigger_percent=75.0, rest_temp_target=21.0, temp_target=21.0,
                         rest_fired_at=T0 + timedelta(hours=40))
    await _rest_start_event(test_db, batch, T0 - timedelta(hours=30))  # the first, real rest
    await _run(test_db, batch, [1.010] * 30)
    assert len(await _alerts(test_db, batch)) == 1



@pytest.mark.asyncio
async def test_not_yet_takes_it_down_and_it_returns_48h_later(client, test_db, _no_push):
    batch = await _batch(test_db)
    at = await _run(test_db, batch, [1.010] * 30)
    await test_db.commit()
    r = await client.post(f"/api/batches/{batch.id}/crash-ready/not-yet")
    assert r.status_code == 200, r.text
    test_db.expire_all()
    await test_db.refresh(batch)
    assert await _alerts(test_db, batch) == []
    (old,) = await _alerts(test_db, batch, active_only=False)
    rearm_from = datetime.fromisoformat(json.loads(old.context)["rearm_from"])
    # Flat readings from just before "Not yet": back only at the reading 48 h after it.
    start = rearm_from.replace(tzinfo=timezone.utc) - timedelta(hours=2)
    at = await _run(test_db, batch, [1.010] * 25, start=start)  # up to 46 h after
    assert await _alerts(test_db, batch) == []
    await _run(test_db, batch, [1.010], start=at)  # 48 h after
    assert len(await _alerts(test_db, batch)) == 1
    assert len(_no_push) == 2


@pytest.mark.asyncio
async def test_start_crash_via_target_ends_it(client, test_db):
    batch = await _batch(test_db, heater_entity_id="switch.heat", cooler_entity_id="switch.cool", temp_target=19.0)
    await _run(test_db, batch, [1.010] * 30)
    await test_db.commit()
    r = await client.put(f"/api/batches/{batch.id}", json={"temp_target": 2.0})
    assert r.status_code == 200, r.text
    test_db.expire_all()
    await test_db.refresh(batch)
    assert await _alerts(test_db, batch) == []


# --- final gravity latch (tilt_ui-r1hq) ---

@pytest.mark.asyncio
async def test_crash_start_saves_the_held_sg_as_fg(client, test_db):
    batch = await _batch(test_db, measured_og=1.050, heater_entity_id="h", cooler_entity_id="c", temp_target=19.0)
    await _run(test_db, batch, [1.011] * 30)
    await test_db.commit()
    r = await client.put(f"/api/batches/{batch.id}", json={"temp_target": 2.0})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["measured_fg"] == pytest.approx(1.011)
    assert body["measured_abv"] == pytest.approx((1.050 - 1.011) * 131.25)


@pytest.mark.asyncio
async def test_unseen_crash_saves_fg_not_the_cold_reading(test_db):
    batch = await _batch(test_db, measured_og=1.050)
    at = await _run(test_db, batch, [1.011] * 30, temp=19.0)
    await _run(test_db, batch, [1.015] * 3, start=at, temp=2.0)  # fridge: reads high
    assert batch.measured_fg == pytest.approx(1.011)


@pytest.mark.asyncio
async def test_own_fg_is_never_overwritten(test_db):
    batch = await _batch(test_db, measured_og=1.050, measured_fg=1.009)
    await _run(test_db, batch, [1.011] * 30)
    await _run(test_db, batch, [1.011], temp_target=2.0)
    assert batch.measured_fg == pytest.approx(1.009)


@pytest.mark.asyncio
async def test_completing_with_ready_up_uses_held_sg_not_last_reading(client, test_db):
    batch = await _batch(test_db, measured_og=1.050)
    at = await _run(test_db, batch, [1.011] * 30)
    test_db.add(Reading(batch_id=batch.id, device_id="BLUE", sg_calibrated=1.016, timestamp=at, status="valid"))
    await test_db.commit()  # a cold, high last reading that never ran through detection
    r = await client.put(f"/api/batches/{batch.id}", json={"status": "completed"})
    assert r.status_code == 200, r.text
    assert r.json()["measured_fg"] == pytest.approx(1.011)


@pytest.mark.asyncio
async def test_no_ready_alert_keeps_old_completion_behaviour(client, test_db):
    batch = await _batch(test_db, measured_og=1.050)
    await _run(test_db, batch, [1.020] * 3)  # never ready
    await test_db.commit()
    r = await client.put(f"/api/batches/{batch.id}", json={"status": "completed"})
    assert r.json()["measured_fg"] == pytest.approx(1.020)



@pytest.mark.asyncio
async def test_gradual_unseen_crash_still_saves_fg(test_db):
    """19 C to 2 C over hours; the cold rise passes 2 pt before the wort is below 5 C."""
    batch = await _batch(test_db, measured_og=1.050)
    at = await _run(test_db, batch, [1.011] * 30, temp=19.0)
    for temp, sg in [(15.0, 1.012), (12.0, 1.0135), (9.0, 1.0145), (6.0, 1.015), (3.0, 1.015), (2.0, 1.015)]:
        at = await _run(test_db, batch, [sg], start=at, temp=temp, step=timedelta(hours=1))
    assert batch.measured_fg == pytest.approx(1.011)



@pytest.mark.asyncio
async def test_own_fg_in_the_completing_put_wins(client, test_db):
    batch = await _batch(test_db, measured_og=1.050)
    await _run(test_db, batch, [1.011] * 30)
    await test_db.commit()
    r = await client.put(f"/api/batches/{batch.id}", json={"status": "completed", "measured_fg": 1.009})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["measured_fg"] == pytest.approx(1.009)
    assert body["measured_attenuation"] == pytest.approx((1.050 - 1.009) / 0.050 * 100)


@pytest.mark.asyncio
async def test_latched_fg_survives_cold_conditioning_then_completion(client, test_db):
    batch = await _batch(test_db, measured_og=1.050)
    await _run(test_db, batch, [1.011] * 30)
    await test_db.commit()
    r = await client.put(f"/api/batches/{batch.id}", json={"status": "conditioning"})
    assert r.json()["measured_fg"] == pytest.approx(1.011)
    test_db.add(Reading(batch_id=batch.id, device_id="BLUE", sg_calibrated=1.016,
                        timestamp=T0 + timedelta(hours=80), status="valid"))  # cold, high
    await test_db.commit()
    r = await client.put(f"/api/batches/{batch.id}", json={"status": "completed"})
    body = r.json()
    assert body["measured_fg"] == pytest.approx(1.011)
    assert body["measured_attenuation"] == pytest.approx((1.050 - 1.011) / 0.050 * 100)


@pytest.mark.asyncio
async def test_going_back_to_planning_does_not_latch(client, test_db):
    batch = await _batch(test_db, measured_og=1.050)
    await _run(test_db, batch, [1.011] * 30)
    await test_db.commit()
    r = await client.put(f"/api/batches/{batch.id}", json={"status": "planning"})
    assert r.status_code == 200, r.text
    assert r.json()["measured_fg"] is None



@pytest.mark.asyncio
async def test_cool_night_then_more_fermentation_does_not_lock_an_old_fg(test_db):
    """Uncontrolled batch: held at 1.016, a cool night reads +2.5 pt, then it warms,
    ferments on to 1.010 and becomes ready there. FG must be 1.010, not 1.016."""
    batch = await _batch(test_db, measured_og=1.050)
    at = await _run(test_db, batch, [1.016] * 30, temp=22.0)
    at = await _run(test_db, batch, [1.0185] * 3, start=at, temp=16.0)  # cool night
    assert batch.measured_fg is None
    at = await _run(test_db, batch, [1.013, 1.011] + [1.010] * 30, start=at, temp=21.0)
    assert len(await _alerts(test_db, batch)) == 1  # ready again, at 1.010
    await _run(test_db, batch, [1.014] * 3, start=at, temp=2.0)  # now the real crash
    assert batch.measured_fg == pytest.approx(1.010)


@pytest.mark.asyncio
async def test_archiving_does_not_latch_fg(client, test_db):
    batch = await _batch(test_db, measured_og=1.050)
    await _run(test_db, batch, [1.011] * 30)
    await test_db.commit()
    r = await client.put(f"/api/batches/{batch.id}", json={"status": "archived"})
    assert r.status_code == 200, r.text
    assert r.json()["measured_fg"] is None


@pytest.mark.asyncio
async def test_og_with_completion_and_later_og_edit_recompute_abv(client, test_db):
    batch = await _batch(test_db)
    await _run(test_db, batch, [1.011] * 30)
    await test_db.commit()
    r = await client.put(f"/api/batches/{batch.id}", json={"status": "completed", "measured_og": 1.050})
    body = r.json()
    assert body["measured_fg"] == pytest.approx(1.011)
    assert body["measured_abv"] == pytest.approx((1.050 - 1.011) * 131.25)
    r = await client.put(f"/api/batches/{batch.id}", json={"measured_og": 1.052})
    assert r.json()["measured_abv"] == pytest.approx((1.052 - 1.011) * 131.25)


@pytest.mark.asyncio
async def test_cooled_fg_dropped_if_fermentation_went_on_before_the_crash(test_db):
    """Cool night tags the alert; beer warms and ferments 1.016 -> 1.010; crashed before
    a new 48 h window: the old 1.016 must not become the FG."""
    batch = await _batch(test_db, measured_og=1.050)
    at = await _run(test_db, batch, [1.016] * 30, temp=22.0)
    at = await _run(test_db, batch, [1.0185] * 3, start=at, temp=16.0)
    at = await _run(test_db, batch, [1.013, 1.011, 1.010, 1.010], start=at, temp=21.0)
    await _run(test_db, batch, [1.013] * 3, start=at, temp=2.0)  # crash now
    assert batch.measured_fg is None


@pytest.mark.asyncio
@pytest.mark.parametrize("change", [{"status": "conditioning"}, {"status": "completed"}])
async def test_cooled_fg_used_when_brewer_moves_on_above_5c(client, test_db, change):
    """Moved to a 6-8 C garage (alert came down as 'cooled'), then marked on: use the held SG."""
    batch = await _batch(test_db, measured_og=1.050)
    at = await _run(test_db, batch, [1.011] * 30, temp=19.0)
    await _run(test_db, batch, [1.012, 1.0135, 1.0145, 1.015], start=at, temp=7.0, step=timedelta(hours=1))
    assert await _alerts(test_db, batch) == []  # came down while cooling
    await test_db.commit()
    r = await client.put(f"/api/batches/{batch.id}", json=change)
    assert r.status_code == 200, r.text
    assert r.json()["measured_fg"] == pytest.approx(1.011)


async def _wait(db, batch, active_only=True):
    q = select(FermentationAlert).where(
        FermentationAlert.batch_id == batch.id,
        FermentationAlert.alert_type == AlertType.CRASH_WAIT_DRY_HOP,
    )
    if active_only:
        q = q.where(FermentationAlert.cleared_at.is_(None))
    return (await db.execute(q)).scalars().all()


async def _dry_hop_batch(db, **kw):
    recipe = Recipe(name="APA", target_og=OG, target_fg=FG)
    db.add(recipe)
    await db.flush()
    db.add(RecipeHop(recipe_id=recipe.id, name="Citra", amount_grams=50, timing={"use": "dry_hop"}))
    # Trigger below where gravity sits, so the dry hop reminder never fires.
    return await _batch(db, recipe_id=recipe.id, dry_hop_trigger_sg=1.005, **kw)


@pytest.mark.asyncio
async def test_unmarked_dry_hop_says_why_crash_ready_waits(test_db, _no_push):
    """tilt_ui-8ih3: flat for 48 h, only the unmarked dry hop blocks: say so, once."""
    batch = await _dry_hop_batch(test_db)
    await _run(test_db, batch, [1.010] * 24)  # 0-46 h: not 48 h yet
    assert await _wait(test_db, batch) == []
    await _run(test_db, batch, [1.010] * 6, start=T0 + timedelta(hours=48))
    (wait,) = await _wait(test_db, batch)
    assert wait.severity == "info"
    assert "dry hop" in wait.message and "1.010" in wait.message
    assert await _alerts(test_db, batch) == []
    assert [t for t, *_ in _no_push] == ["Ready to cold crash once dry hopped: APA"]


@pytest.mark.asyncio
@pytest.mark.parametrize("sgs", [
    [1.016 - 0.0002 * i for i in range(30)],  # still fermenting
    [1.020] * 30,  # flat but well above FG: a stall
])
async def test_no_wait_notice_unless_otherwise_ready(test_db, sgs):
    batch = await _dry_hop_batch(test_db)
    await _run(test_db, batch, sgs)
    assert await _wait(test_db, batch) == []


@pytest.mark.asyncio
async def test_no_wait_notice_without_fg(test_db):
    batch = await _dry_hop_batch(test_db)
    await _run(test_db, batch, [1.010] * 30, fg=None)
    assert await _wait(test_db, batch) == []


@pytest.mark.asyncio
async def test_wait_notice_stays_through_gravity_noise(test_db, _no_push):
    batch = await _dry_hop_batch(test_db)
    at = await _run(test_db, batch, [1.010] * 30)
    await _run(test_db, batch, [1.016] * 3, start=at)  # moved: still waits for the mark
    assert len(await _wait(test_db, batch)) == 1
    assert len(_no_push) == 1


@pytest.mark.asyncio
async def test_mark_dry_hopped_clears_wait_then_crash_ready_follows(client, test_db):
    batch = await _dry_hop_batch(test_db)
    at = await _run(test_db, batch, [1.010] * 30)
    await test_db.commit()
    r = await client.post(f"/api/batches/{batch.id}/dry-hop-done")
    assert r.status_code == 200, r.text
    test_db.expire_all()
    await test_db.refresh(batch)
    assert await _wait(test_db, batch) == []
    batch.dry_hop_done_at = at  # deterministic: dry hopped at the next reading
    at = await _run(test_db, batch, [1.010] * 24, start=at)  # under 48 h since the dry hop
    assert await _alerts(test_db, batch) == [] and await _wait(test_db, batch) == []
    await _run(test_db, batch, [1.010], start=at)
    assert len(await _alerts(test_db, batch)) == 1
    assert await _wait(test_db, batch) == []


@pytest.mark.asyncio
async def test_wait_notice_ends_when_batch_leaves_fermenting(client, test_db):
    batch = await _dry_hop_batch(test_db)
    await _run(test_db, batch, [1.010] * 30)
    await test_db.commit()
    r = await client.put(f"/api/batches/{batch.id}", json={"status": "completed"})
    assert r.status_code == 200, r.text
    assert await _wait(test_db, batch) == []


@pytest.mark.asyncio
async def test_dismiss_all_keeps_wait_notice(client, test_db):
    batch = await _dry_hop_batch(test_db)
    await _run(test_db, batch, [1.010] * 30)
    await test_db.commit()
    r = await client.post(f"/api/batches/{batch.id}/alerts/dismiss-all")
    assert r.status_code == 200, r.text
    assert len(await _wait(test_db, batch)) == 1


@pytest.mark.asyncio
async def test_wait_notice_final_after_crash_then_warm(test_db, _no_push):
    """Fable F1: a crash target ends it; raising the target again must not re-push."""
    batch = await _dry_hop_batch(test_db)
    at = await _run(test_db, batch, [1.010] * 30)
    at = await _run(test_db, batch, [1.010] * 2, start=at, temp_target=2.0)
    assert await _wait(test_db, batch) == []
    await _run(test_db, batch, [1.010] * 30, start=at, temp_target=18.0)
    assert await _wait(test_db, batch) == []
    assert len(_no_push) == 1


@pytest.mark.asyncio
async def test_wait_notice_clears_when_dry_hop_reminder_raised(test_db):
    batch = await _dry_hop_batch(test_db)
    await _run(test_db, batch, [1.010] * 30)
    assert len(await _wait(test_db, batch)) == 1
    batch.dry_hop_trigger_sg = 1.012  # reminder fires now: "due" replaces "planned"
    await _run(test_db, batch, [1.010], start=T0 + timedelta(hours=60))
    assert await _wait(test_db, batch) == []


@pytest.mark.asyncio
async def test_wait_notice_clears_when_fg_removed(test_db):
    """Gemini: its message names the FG, so it must not outlive it."""
    batch = await _dry_hop_batch(test_db)
    at = await _run(test_db, batch, [1.010] * 30)
    assert len(await _wait(test_db, batch)) == 1
    at = await _run(test_db, batch, [1.010], start=at, fg=None)
    assert await _wait(test_db, batch) == []


@pytest.mark.asyncio
async def test_wait_notice_returns_when_fg_set_again(test_db, _no_push):
    """Fable round 2: a plan change is not an ending; restoring the FG brings it back."""
    batch = await _dry_hop_batch(test_db)
    at = await _run(test_db, batch, [1.010] * 30)
    at = await _run(test_db, batch, [1.010], start=at, fg=None)
    assert await _wait(test_db, batch) == []
    await _run(test_db, batch, [1.010] * 3, start=at)
    assert len(await _wait(test_db, batch)) == 1
    assert len(_no_push) == 2  # a new plan: a new push


@pytest.mark.asyncio
async def test_wait_notice_dismissed_via_api_is_final(client, test_db, _no_push):
    batch = await _dry_hop_batch(test_db)
    at = await _run(test_db, batch, [1.010] * 30)
    (wait,) = await _wait(test_db, batch)
    await test_db.commit()
    r = await client.post(f"/api/batches/{batch.id}/alerts/{wait.id}/dismiss")
    assert r.status_code == 200, r.text
    test_db.expire_all()
    await test_db.refresh(batch)
    await _run(test_db, batch, [1.010] * 3, start=at)
    assert await _wait(test_db, batch) == []
    assert len(_no_push) == 1


@pytest.mark.asyncio
async def test_crash_makes_a_plan_cleared_wait_notice_final(test_db, _no_push):
    """Fable round 3: FG removed (replan), then the crash, then FG back and warm: no return."""
    batch = await _dry_hop_batch(test_db)
    at = await _run(test_db, batch, [1.010] * 30)
    at = await _run(test_db, batch, [1.010], start=at, fg=None)
    at = await _run(test_db, batch, [1.010], start=at, fg=None, temp_target=2.0)
    await _run(test_db, batch, [1.010] * 30, start=at, temp_target=18.0)
    assert await _wait(test_db, batch) == []
    assert len(_no_push) == 1


@pytest.mark.asyncio
async def test_fg_lowered_to_a_stall_clears_wait_notice(test_db):
    """Fable round 4: FG edited 6 pt down, gravity now 'flat and high': not a wait."""
    batch = await _dry_hop_batch(test_db)
    at = await _run(test_db, batch, [1.010] * 30)
    assert len(await _wait(test_db, batch)) == 1
    await _run(test_db, batch, [1.010], start=at, fg=1.004)
    assert await _wait(test_db, batch) == []


@pytest.mark.asyncio
async def test_fg_lowered_after_a_gap_still_clears_wait_notice(test_db):
    """Codex round 5: a reading gap returns early; the FG check must come first."""
    batch = await _dry_hop_batch(test_db)
    at = await _run(test_db, batch, [1.010] * 30)
    await _run(test_db, batch, [1.010], start=at + timedelta(hours=10), fg=1.004)
    assert await _wait(test_db, batch) == []


@pytest.mark.asyncio
async def test_gravity_drifting_up_and_back_keeps_wait_notice(test_db, _no_push):
    """Codex round 5: same FG, gravity sits 5 pt high for a while, then settles: one notice."""
    batch = await _dry_hop_batch(test_db)
    at = await _run(test_db, batch, [1.010] * 30)
    at = await _run(test_db, batch, [1.015] * 30, start=at)
    await _run(test_db, batch, [1.010] * 30, start=at)
    assert len(await _wait(test_db, batch)) == 1
    assert len(_no_push) == 1


@pytest.mark.asyncio
async def test_noise_at_fg_margin_gives_one_wait_push(test_db, _no_push):
    """Fable round 5: flat at 1.014 (FG 1.010), then jitter across the margin: one push."""
    batch = await _dry_hop_batch(test_db)
    at = await _run(test_db, batch, [1.014] * 30)
    assert len(await _wait(test_db, batch)) == 1
    await _run(test_db, batch, [1.015, 1.015, 1.014, 1.014] * 3, start=at)
    assert len(await _wait(test_db, batch)) == 1
    assert len(_no_push) == 1
