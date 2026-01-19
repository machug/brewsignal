"""Add readings_paused column to batches table.

This migration adds a boolean column to allow pausing reading storage
during manual gravity checks (e.g., when moving the fermenter).
"""
import logging
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

logger = logging.getLogger(__name__)


async def _check_column_exists(conn: AsyncConnection, table: str, column: str) -> bool:
    """Check if a column exists in a table using PRAGMA.

    Args:
        conn: Database connection
        table: Table name (must be 'batches')
        column: Column name to check

    Returns:
        True if column exists, False otherwise
    """
    if table != 'batches':
        raise ValueError(f"Invalid table name: {table}")
    result = await conn.execute(text("PRAGMA table_info(batches)"))
    rows = result.fetchall()
    columns = {row[1] for row in rows}
    return column in columns


async def migrate_add_readings_paused(conn: AsyncConnection) -> None:
    """Add readings_paused column to batches table."""
    logger.info("Running migration: add_readings_paused")

    # Check if batches table exists
    result = await conn.execute(text(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='batches'"
    ))
    if not result.fetchone():
        logger.info("Batches table doesn't exist yet, skipping migration")
        return

    # Check if migration already applied
    if await _check_column_exists(conn, 'batches', 'readings_paused'):
        logger.info("readings_paused column already exists, skipping migration")
        return

    logger.info("Adding readings_paused column to batches table")

    # Add the column with default value of 0 (False)
    await conn.execute(text(
        "ALTER TABLE batches ADD COLUMN readings_paused BOOLEAN DEFAULT 0 NOT NULL"
    ))

    logger.info("Successfully added readings_paused column")
