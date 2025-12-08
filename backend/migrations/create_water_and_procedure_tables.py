"""Create water chemistry and procedure tables."""
import logging
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

logger = logging.getLogger(__name__)


async def _check_table_exists(conn: AsyncConnection, table: str) -> bool:
    """Check if a table exists."""
    result = await conn.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' AND name=:table"),
        {"table": table}
    )
    return result.fetchone() is not None


async def migrate_create_water_and_procedure_tables(conn: AsyncConnection) -> None:
    """Create tables for water chemistry and brewing procedures."""
    logger.info("Running migration: create_water_and_procedure_tables")

    # 1. Create recipe_water_profiles table
    if not await _check_table_exists(conn, 'recipe_water_profiles'):
        await conn.execute(text("""
            CREATE TABLE recipe_water_profiles (
                id INTEGER PRIMARY KEY,
                recipe_id INTEGER NOT NULL,
                profile_type VARCHAR(20) NOT NULL,
                name VARCHAR(100),
                calcium_ppm REAL,
                magnesium_ppm REAL,
                sodium_ppm REAL,
                chloride_ppm REAL,
                sulfate_ppm REAL,
                bicarbonate_ppm REAL,
                ph REAL,
                alkalinity REAL,
                format_extensions JSON,
                FOREIGN KEY (recipe_id) REFERENCES recipes(id) ON DELETE CASCADE
            )
        """))
        logger.info("Created recipe_water_profiles table")

    # 2. Create recipe_water_adjustments table
    if not await _check_table_exists(conn, 'recipe_water_adjustments'):
        await conn.execute(text("""
            CREATE TABLE recipe_water_adjustments (
                id INTEGER PRIMARY KEY,
                recipe_id INTEGER NOT NULL,
                stage VARCHAR(20) NOT NULL,
                volume_liters REAL,
                calcium_sulfate_g REAL,
                calcium_chloride_g REAL,
                magnesium_sulfate_g REAL,
                sodium_bicarbonate_g REAL,
                calcium_carbonate_g REAL,
                calcium_hydroxide_g REAL,
                magnesium_chloride_g REAL,
                sodium_chloride_g REAL,
                acid_type VARCHAR(20),
                acid_ml REAL,
                acid_concentration_percent REAL,
                format_extensions JSON,
                FOREIGN KEY (recipe_id) REFERENCES recipes(id) ON DELETE CASCADE
            )
        """))
        logger.info("Created recipe_water_adjustments table")

    # 3. Create recipe_mash_steps table
    if not await _check_table_exists(conn, 'recipe_mash_steps'):
        await conn.execute(text("""
            CREATE TABLE recipe_mash_steps (
                id INTEGER PRIMARY KEY,
                recipe_id INTEGER NOT NULL,
                step_number INTEGER NOT NULL,
                name VARCHAR(100) NOT NULL,
                type VARCHAR(20) NOT NULL,
                temp_c REAL NOT NULL,
                time_minutes INTEGER NOT NULL,
                infusion_amount_liters REAL,
                infusion_temp_c REAL,
                ramp_time_minutes INTEGER,
                format_extensions JSON,
                FOREIGN KEY (recipe_id) REFERENCES recipes(id) ON DELETE CASCADE
            )
        """))
        logger.info("Created recipe_mash_steps table")

    # 4. Create recipe_fermentation_steps table
    if not await _check_table_exists(conn, 'recipe_fermentation_steps'):
        await conn.execute(text("""
            CREATE TABLE recipe_fermentation_steps (
                id INTEGER PRIMARY KEY,
                recipe_id INTEGER NOT NULL,
                step_number INTEGER NOT NULL,
                type VARCHAR(20) NOT NULL,
                temp_c REAL NOT NULL,
                time_days INTEGER NOT NULL,
                format_extensions JSON,
                FOREIGN KEY (recipe_id) REFERENCES recipes(id) ON DELETE CASCADE
            )
        """))
        logger.info("Created recipe_fermentation_steps table")

    logger.info("Migration create_water_and_procedure_tables completed")
