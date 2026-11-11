"""Stall alert rule (tilt_ui-zbhm): 12 h slope, after a 4 pt drop, 4 pt above FG."""

import pytest
from sqlalchemy import select

from backend.models import Batch, FermentationAlert, Reading
from backend.services.alert_service import AlertType, detect_and_persist_alerts

FLAT = -1e-6  # SG/h
ACTIVE = -5e-4


async def _run(db, sg, slope, og=1.050, fg=1.011):
    batch = Batch(name="APA", status="fermenting")
    db.add(batch)
    await db.flush()
    reading = Reading(batch_id=batch.id, sg_raw=sg, sg_calibrated=sg)
    db.add(reading)
    await db.flush()
    await detect_and_persist_alerts(
        db=db, batch_id=batch.id, device_id="BLUE", reading=reading,
        live_reading={"sg": sg, "sg_slope_12h": slope}, og=og, fg=fg,
    )
    await db.flush()
    rows = (await db.execute(select(FermentationAlert).where(
        FermentationAlert.batch_id == batch.id,
        FermentationAlert.alert_type == AlertType.STALL,
        FermentationAlert.cleared_at.is_(None),
    ))).scalars().all()
    return rows


@pytest.mark.asyncio
async def test_lag_phase_is_not_a_stall(test_db):
    """Batch 16 case: 14 h in, 1 pt down, flat. Old rule alerted here."""
    assert await _run(test_db, sg=1.049, slope=FLAT) == []


@pytest.mark.asyncio
async def test_real_stall_warns(test_db):
    rows = await _run(test_db, sg=1.030, slope=FLAT)
    assert len(rows) == 1 and rows[0].severity == "warning"


@pytest.mark.asyncio
async def test_active_fermentation_is_not_a_stall(test_db):
    assert await _run(test_db, sg=1.030, slope=ACTIVE) == []


@pytest.mark.asyncio
async def test_near_fg_is_finished_not_stalled(test_db):
    assert await _run(test_db, sg=1.014, slope=FLAT) == []


@pytest.mark.asyncio
async def test_no_window_yet_no_judgement(test_db):
    assert await _run(test_db, sg=1.030, slope=None) == []


@pytest.mark.asyncio
async def test_unknown_fg_is_info_only(test_db):
    rows = await _run(test_db, sg=1.030, slope=FLAT, fg=None)
    assert len(rows) == 1 and rows[0].severity == "info"


@pytest.mark.asyncio
async def test_unknown_og_no_judgement(test_db):
    assert await _run(test_db, sg=1.030, slope=FLAT, og=None) == []


@pytest.mark.asyncio
async def test_startup_warms_active_batch_pipelines(test_db):
    from datetime import datetime, timedelta, timezone

    from sqlalchemy.ext.asyncio import async_sessionmaker

    from backend.ml.pipeline_manager import MLPipelineManager

    batch = Batch(name="APA", status="fermenting", device_id="BLUE")
    test_db.add(batch)
    await test_db.flush()
    start = datetime.now(timezone.utc) - timedelta(hours=14)
    for i in range(14 * 12):
        test_db.add(Reading(batch_id=batch.id, device_id="BLUE", sg_raw=1.030, sg_calibrated=1.030,
                            temp_calibrated=19.0, timestamp=start + timedelta(minutes=5 * i)))
    await test_db.commit()

    mgr = MLPipelineManager()
    assert await mgr.warm_active_batches(async_sessionmaker(test_db.bind, expire_on_commit=False)) == 1
    det = mgr.pipelines["BLUE"].anomaly_detector
    assert det.check_reading(1.030, 14.0)["sg_slope_12h"] is not None


@pytest.mark.asyncio
async def test_step_alert_stays_until_dismissed(test_db):
    """Side-agent catch: a once-per-event flag must not clear on the next reading."""
    batch = Batch(name="APA", status="fermenting")
    test_db.add(batch)
    await test_db.flush()
    for flagged in (True, False, False):
        reading = Reading(batch_id=batch.id, sg_raw=1.030, sg_calibrated=1.030)
        test_db.add(reading)
        await test_db.flush()
        await detect_and_persist_alerts(
            db=test_db, batch_id=batch.id, device_id="BLUE", reading=reading,
            live_reading={"sg": 1.030, "is_anomaly": flagged,
                          "anomaly_reasons": ["step_change_down"] if flagged else []},
        )
        await test_db.flush()
    rows = (await test_db.execute(select(FermentationAlert).where(
        FermentationAlert.batch_id == batch.id,
        FermentationAlert.alert_type == AlertType.ANOMALY,
        FermentationAlert.cleared_at.is_(None),
    ))).scalars().all()
    assert len(rows) == 1 and "lifted" in rows[0].message
