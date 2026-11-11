"""Reading storage stats.

Readings are kept permanently (no age-based purge) so past fermentations can
inform predictions and the assistant. Readings of user-deleted batches are
removed only via the maintenance endpoint.
"""

import logging

from sqlalchemy import func, select

from .database import async_session_factory
from .models import Reading, serialize_datetime_to_utc

logger = logging.getLogger(__name__)


async def get_reading_stats() -> dict:
    """Get statistics about stored readings."""
    async with async_session_factory() as session:
        # Total count
        total_result = await session.execute(
            select(func.count()).select_from(Reading)
        )
        total = total_result.scalar() or 0

        # Oldest reading
        oldest_result = await session.execute(
            select(func.min(Reading.timestamp))
        )
        oldest = oldest_result.scalar()

        # Newest reading
        newest_result = await session.execute(
            select(func.max(Reading.timestamp))
        )
        newest = newest_result.scalar()

        return {
            "total_readings": total,
            "oldest_reading": serialize_datetime_to_utc(oldest) if oldest else None,
            "newest_reading": serialize_datetime_to_utc(newest) if newest else None,
        }
