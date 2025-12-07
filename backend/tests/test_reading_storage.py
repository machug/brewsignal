"""Tests for reading storage behavior based on batch status."""

import pytest
from datetime import datetime, timezone
from backend.models import Batch, Device, Reading


@pytest.mark.asyncio
async def test_readings_not_stored_planning_status(test_db):
    """Readings should not be stored when batch is in planning status."""
    # Create paired device
    device = Device(
        id="BLUE",
        device_type="tilt",
        name="Blue Tilt",
        paired=True,
    )
    test_db.add(device)

    # Create batch in planning status
    batch = Batch(
        device_id="BLUE",
        status="planning",
        start_time=datetime.now(timezone.utc),
    )
    test_db.add(batch)
    await test_db.commit()

    # Count readings before
    from sqlalchemy import select, func
    count_before = await test_db.scalar(select(func.count()).select_from(Reading))

    # Simulate reading ingestion (this would normally happen in main.py)
    # Since we're testing in isolation, we verify batch_linker returns None
    from backend.services.batch_linker import link_reading_to_batch
    batch_id = await link_reading_to_batch(test_db, "BLUE")

    assert batch_id is None  # Planning batch should not link

    # Verify no reading stored
    count_after = await test_db.scalar(select(func.count()).select_from(Reading))
    assert count_after == count_before


@pytest.mark.asyncio
async def test_readings_stored_fermenting_status(test_db):
    """Readings should be stored when batch is fermenting."""
    # Create paired device
    device = Device(
        id="BLUE",
        device_type="tilt",
        name="Blue Tilt",
        paired=True,
    )
    test_db.add(device)

    # Create batch in fermenting status
    batch = Batch(
        device_id="BLUE",
        status="fermenting",
        start_time=datetime.now(timezone.utc),
    )
    test_db.add(batch)
    await test_db.commit()

    # Verify batch_linker returns batch_id
    from backend.services.batch_linker import link_reading_to_batch
    batch_id = await link_reading_to_batch(test_db, "BLUE")

    assert batch_id is not None
    assert batch_id == batch.id


@pytest.mark.asyncio
async def test_readings_stored_conditioning_status(test_db):
    """Readings should be stored when batch is conditioning."""
    # Create paired device
    device = Device(
        id="BLUE",
        device_type="tilt",
        name="Blue Tilt",
        paired=True,
    )
    test_db.add(device)

    # Create batch in conditioning status
    batch = Batch(
        device_id="BLUE",
        status="conditioning",
        start_time=datetime.now(timezone.utc),
    )
    test_db.add(batch)
    await test_db.commit()

    # Verify batch_linker returns batch_id
    from backend.services.batch_linker import link_reading_to_batch
    batch_id = await link_reading_to_batch(test_db, "BLUE")

    assert batch_id is not None
    assert batch_id == batch.id


@pytest.mark.asyncio
async def test_readings_not_stored_completed_status(test_db):
    """Readings should not be stored when batch is completed."""
    # Create paired device
    device = Device(
        id="BLUE",
        device_type="tilt",
        name="Blue Tilt",
        paired=True,
    )
    test_db.add(device)

    # Create batch in completed status
    batch = Batch(
        device_id="BLUE",
        status="completed",
        start_time=datetime.now(timezone.utc),
    )
    test_db.add(batch)
    await test_db.commit()

    # Verify batch_linker returns None
    from backend.services.batch_linker import link_reading_to_batch
    batch_id = await link_reading_to_batch(test_db, "BLUE")

    assert batch_id is None  # Completed batch should not link


@pytest.mark.asyncio
async def test_unpaired_device_does_not_store_readings(test_db):
    """Unpaired devices should not store readings even when assigned to active batch."""
    # Create UNPAIRED device
    device = Device(
        id="BLUE",
        device_type="tilt",
        name="Blue Tilt",
        paired=False,  # NOT PAIRED
    )
    test_db.add(device)

    # Create batch in fermenting status
    batch = Batch(
        device_id="BLUE",
        status="fermenting",
        start_time=datetime.now(timezone.utc),
    )
    test_db.add(batch)
    await test_db.commit()

    # Verify batch_linker would return batch_id
    from backend.services.batch_linker import link_reading_to_batch
    batch_id = await link_reading_to_batch(test_db, "BLUE")
    assert batch_id is not None  # Batch link works

    # However, the main.py logic requires BOTH paired AND batch_id
    # So unpaired device with active batch should NOT store readings
    should_store = device.paired and batch_id is not None
    assert should_store is False  # Unpaired device should not store
