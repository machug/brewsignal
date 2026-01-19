"""Service for linking readings to active batches."""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Batch


async def get_active_batch_for_device(
    db: AsyncSession,
    device_id: str,
    include_paused: bool = True,
) -> Optional[Batch]:
    """Find the active (fermenting or conditioning) batch for a device.

    Args:
        db: Database session
        device_id: Device ID to find batch for
        include_paused: If False, exclude batches with readings_paused=True

    Returns:
        Active Batch if found, None otherwise
    """
    query = (
        select(Batch)
        .where(Batch.device_id == device_id)
        .where(Batch.status.in_(["fermenting", "conditioning"]))
    )
    if not include_paused:
        query = query.where(Batch.readings_paused == False)  # noqa: E712
    query = query.order_by(Batch.start_time.desc()).limit(1)
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def link_reading_to_batch(
    db: AsyncSession,
    device_id: str,
) -> Optional[int]:
    """Get batch_id to link a new reading to.

    Excludes batches with readings_paused=True to allow manual gravity
    checks without storing erroneous readings from moving the hydrometer.

    Args:
        db: Database session
        device_id: Device ID of the reading

    Returns:
        batch_id if active (non-paused) batch exists, None otherwise
    """
    batch = await get_active_batch_for_device(db, device_id, include_paused=False)
    return batch.id if batch else None
