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
