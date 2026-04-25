"""Add target_* columns to recipes for imported brewer-declared stats.

Imported recipes carry brewer-declared OG/FG/ABV/IBU/SRM targets that
frequently disagree with the calculated values. Storing both (target_*
and the existing og/fg/abv/ibu/color_srm) lets the UI show source-of-truth
imported values while still surfacing the live calculation. Without this
split they fight for the same column and one always loses (tilt_ui-ak6).

The existing columns (og/fg/abv/ibu/color_srm) keep their meaning as the
displayed/canonical values that the recipe edit form binds to. The new
target_* columns are populated by importers from the source recipe's
declared values and are read-only from the calculator's perspective.
"""
import logging
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

logger = logging.getLogger(__name__)

_NEW_COLUMNS = ("target_og", "target_fg", "target_abv", "target_ibu", "target_srm")


async def _check_column_exists(conn: AsyncConnection, column: str) -> bool:
    result = await conn.execute(text("PRAGMA table_info(recipes)"))
    rows = result.fetchall()
    columns = {row[1] for row in rows}
    return column in columns


async def migrate_add_recipe_target_stats(conn: AsyncConnection) -> None:
    """Add target_og/target_fg/target_abv/target_ibu/target_srm to recipes."""
    logger.info("Running migration: add_recipe_target_stats")

    # Skip if recipes table doesn't exist yet (fresh install)
    result = await conn.execute(text(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='recipes'"
    ))
    if not result.fetchone():
        logger.info("Recipes table doesn't exist yet, skipping migration")
        return

    for column in _NEW_COLUMNS:
        if await _check_column_exists(conn, column):
            logger.info("%s column already exists, skipping", column)
            continue
        logger.info("Adding %s column to recipes table", column)
        await conn.execute(text(f"ALTER TABLE recipes ADD COLUMN {column} REAL"))

    logger.info("Migration add_recipe_target_stats completed")
