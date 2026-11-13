"""Sensing alerts (tilt_ui-lgtu): debounced temperature, runaway, battery, offline, anomaly score."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from backend.ml.anomaly.detector import FermentationAnomalyDetector
from backend.ml.pipeline_manager import MLPipelineManager
from backend.models import Batch, FermentationAlert, Reading
from backend.services import alert_service
from backend.services.alert_service import AlertType, check_offline_sensors, detect_and_persist_alerts

T0 = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _fresh_debounce():
    alert_service._temp_out_since.clear()


async def _batch(db, **kw):
    batch = Batch(name="APA", status="fermenting", device_id="BLUE", **kw)
    db.add(batch)
    await db.flush()
    return batch


async def _feed(db, batch, at, temp=None, **kw):
    """Store one reading at ``at`` and run alert detection as ingest does."""
    live = kw.pop("live", {})
    reading = Reading(batch_id=batch.id, device_id="BLUE", sg_calibrated=1.040,
                      temp_calibrated=temp, timestamp=at)
    db.add(reading)
    await db.flush()
    await detect_and_persist_alerts(
        db=db, batch_id=batch.id, device_id="BLUE", reading=reading,
        live_reading={"temp": temp, **live}, now=at, **kw,
    )
    await db.flush()


async def _active(db, batch):
    rows = (await db.execute(select(FermentationAlert).where(
        FermentationAlert.batch_id == batch.id, FermentationAlert.cleared_at.is_(None),
    ))).scalars().all()
    return {r.alert_type: r for r in rows}


@pytest.mark.asyncio
async def test_temperature_alert_waits_30_minutes(test_db):
    batch = await _batch(test_db)
    rng = dict(yeast_temp_min=18.0, yeast_temp_max=22.0)
    await _feed(test_db, batch, T0, temp=23.0, **rng)
    await _feed(test_db, batch, T0 + timedelta(minutes=29), temp=23.0, **rng)
    assert await _active(test_db, batch) == {}
    await _feed(test_db, batch, T0 + timedelta(minutes=30), temp=23.0, **rng)
    assert list(await _active(test_db, batch)) == [AlertType.TEMPERATURE_HIGH]
    await _feed(test_db, batch, T0 + timedelta(minutes=35), temp=21.0, **rng)
    assert await _active(test_db, batch) == {}


@pytest.mark.asyncio
async def test_brief_swing_restarts_the_wait(test_db):
    batch = await _batch(test_db)
    rng = dict(yeast_temp_min=18.0, yeast_temp_max=22.0)
    await _feed(test_db, batch, T0, temp=23.0, **rng)
    await _feed(test_db, batch, T0 + timedelta(minutes=20), temp=21.0, **rng)
    await _feed(test_db, batch, T0 + timedelta(minutes=40), temp=23.0, **rng)
    assert await _active(test_db, batch) == {}


@pytest.mark.asyncio
async def test_one_sided_yeast_range_still_alerts(test_db):
    batch = await _batch(test_db)
    await _feed(test_db, batch, T0, temp=16.0, yeast_temp_min=18.0)
    await _feed(test_db, batch, T0 + timedelta(minutes=31), temp=16.0, yeast_temp_min=18.0)
    assert list(await _active(test_db, batch)) == [AlertType.TEMPERATURE_LOW]


@pytest.mark.asyncio
async def test_runaway_needs_hot_and_rising(test_db):
    batch = await _batch(test_db)
    await _feed(test_db, batch, T0, temp=21.0, temp_target=19.0)
    # 30 min later: 2.5 C above target, +1.5 C in 0.5 h = 3 C/h
    await _feed(test_db, batch, T0 + timedelta(minutes=30), temp=22.5, temp_target=19.0)
    alerts = await _active(test_db, batch)
    assert alerts[AlertType.TEMP_RUNAWAY].severity == "critical"
    # Plateau while still hot: alert stays. Back near target: clears.
    await _feed(test_db, batch, T0 + timedelta(minutes=60), temp=22.5, temp_target=19.0)
    assert AlertType.TEMP_RUNAWAY in await _active(test_db, batch)
    await _feed(test_db, batch, T0 + timedelta(minutes=90), temp=20.0, temp_target=19.0)
    assert await _active(test_db, batch) == {}


@pytest.mark.asyncio
async def test_runaway_clears_when_target_removed(test_db):
    batch = await _batch(test_db)
    await _feed(test_db, batch, T0, temp=21.0, temp_target=19.0)
    await _feed(test_db, batch, T0 + timedelta(minutes=30), temp=22.5, temp_target=19.0)
    assert AlertType.TEMP_RUNAWAY in await _active(test_db, batch)
    await _feed(test_db, batch, T0 + timedelta(minutes=35), temp=22.5)
    assert await _active(test_db, batch) == {}


@pytest.mark.asyncio
async def test_cold_crash_is_not_a_runaway(test_db):
    batch = await _batch(test_db)
    await _feed(test_db, batch, T0, temp=18.0, temp_target=2.0)
    await _feed(test_db, batch, T0 + timedelta(minutes=30), temp=16.0, temp_target=2.0)
    assert await _active(test_db, batch) == {}


@pytest.mark.asyncio
async def test_battery_low_with_clear_gap(test_db):
    batch = await _batch(test_db)
    await _feed(test_db, batch, T0, live={"battery_percent": 19})
    assert list(await _active(test_db, batch)) == [AlertType.BATTERY_LOW]
    await _feed(test_db, batch, T0 + timedelta(minutes=5), live={"battery_percent": 22})
    assert list(await _active(test_db, batch)) == [AlertType.BATTERY_LOW]
    await _feed(test_db, batch, T0 + timedelta(minutes=10), live={"battery_percent": 25})
    assert await _active(test_db, batch) == {}


@pytest.mark.asyncio
async def test_offline_alert_raised_and_cleared_by_next_reading(test_db):
    batch = await _batch(test_db)
    for i in range(10):  # Tilt-like: every 5 min, so the limit is the 30 min floor
        test_db.add(Reading(batch_id=batch.id, device_id="BLUE", sg_calibrated=1.040,
                            timestamp=T0 + timedelta(minutes=5 * i)))
    await test_db.flush()
    last = T0 + timedelta(minutes=45)
    assert await check_offline_sensors(test_db, now=last + timedelta(minutes=29)) == 0
    assert await check_offline_sensors(test_db, now=last + timedelta(minutes=31)) == 1
    assert list(await _active(test_db, batch)) == [AlertType.SENSOR_OFFLINE]
    await _feed(test_db, batch, last + timedelta(minutes=40))
    assert await _active(test_db, batch) == {}


@pytest.mark.asyncio
async def test_offline_alert_cleared_when_batch_finishes(test_db):
    batch = await _batch(test_db)
    test_db.add(Reading(batch_id=batch.id, device_id="BLUE", sg_calibrated=1.040, timestamp=T0))
    await test_db.flush()
    assert await check_offline_sensors(test_db, now=T0 + timedelta(hours=2)) == 1
    batch.status = "completed"
    await test_db.flush()
    assert await check_offline_sensors(test_db, now=T0 + timedelta(hours=3)) == 0
    assert await _active(test_db, batch) == {}


@pytest.mark.asyncio
async def test_offline_limit_scales_for_slow_reporters(test_db):
    batch = await _batch(test_db)
    for i in range(10):  # iSpindel-like: every 15 min, so the limit is 90 min
        test_db.add(Reading(batch_id=batch.id, device_id="BLUE", sg_calibrated=1.040,
                            timestamp=T0 + timedelta(minutes=15 * i)))
    await test_db.flush()
    last = T0 + timedelta(minutes=135)
    assert await check_offline_sensors(test_db, now=last + timedelta(minutes=80)) == 0
    assert await check_offline_sensors(test_db, now=last + timedelta(minutes=95)) == 1


@pytest.mark.asyncio
async def test_offline_defers_to_controller_stale_alert(test_db):
    batch = await _batch(test_db)
    test_db.add(Reading(batch_id=batch.id, device_id="BLUE", sg_calibrated=1.040, timestamp=T0))
    test_db.add(FermentationAlert(batch_id=batch.id, alert_type=AlertType.SENSOR_STALE,
                                  severity="critical", message="stale"))
    await test_db.flush()
    assert await check_offline_sensors(test_db, now=T0 + timedelta(hours=2)) == 0
    assert list(await _active(test_db, batch)) == [AlertType.SENSOR_STALE]


def test_anomaly_score_is_reported():
    det = FermentationAnomalyDetector()
    out = None
    for i in range(12):  # flat baseline
        out = det.check_reading(1.040, i * 5 / 60)
    assert out["score"] == pytest.approx(0.0, abs=1e-6) and not out["is_anomaly"]
    flagged = []
    for i in range(12, 18):  # +3 pt step, held
        out = det.check_reading(1.043, i * 5 / 60)
        flagged.append(out["is_anomaly"])
    assert flagged == [False] * 5 + [True] and out["score"] == 1.0

    mgr = MLPipelineManager()
    flat = [mgr.process_reading("BLUE", 1.040, 19.0, -60, i * 5 / 60, batch_id=1) for i in range(12)]
    assert flat[0]["anomaly_score"] is None and flat[-1]["anomaly_score"] is not None
