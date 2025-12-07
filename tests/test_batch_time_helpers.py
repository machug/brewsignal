"""Test batch time calculation helpers."""
import pytest
from datetime import datetime, timezone, timedelta
from backend.main import calculate_time_since_batch_start
from backend.models import Batch
from backend.database import async_session_factory


@pytest.mark.asyncio
async def test_calculate_time_since_batch_start():
    """Calculate hours since batch start."""
    async with async_session_factory() as session:
        # Create test batch
        start_time = datetime.now(timezone.utc) - timedelta(hours=48)
        batch = Batch(
            name="Test Batch",
            status="fermenting",
            start_time=start_time
        )
        session.add(batch)
        await session.commit()
        await session.refresh(batch)

        # Calculate time (device_id not used when batch has start_time)
        hours = await calculate_time_since_batch_start(session, batch.id, "TEST_DEVICE")

        # Should be approximately 48 hours (allow 1 minute tolerance)
        assert 47.9 <= hours <= 48.1


@pytest.mark.asyncio
async def test_calculate_time_returns_zero_for_no_batch():
    """Returns 0.0 when batch_id is None and no readings exist."""
    async with async_session_factory() as session:
        hours = await calculate_time_since_batch_start(session, None, "NONEXISTENT_DEVICE")
        assert hours == 0.0


@pytest.mark.asyncio
async def test_calculate_time_returns_zero_for_no_start_time():
    """Returns 0.0 when batch has no start_time and no readings exist."""
    async with async_session_factory() as session:
        batch = Batch(
            name="Test Batch",
            status="planning",
            start_time=None
        )
        session.add(batch)
        await session.commit()
        await session.refresh(batch)

        hours = await calculate_time_since_batch_start(session, batch.id, "NONEXISTENT_DEVICE")
        assert hours == 0.0
