"""Add BeerJSON support to Recipe table.

This migration:
1. Renames columns to match BeerJSON schema (og_target → og, etc.)
2. Adds BeerJSON metadata columns (beerjson_version, format_extensions)
3. Preserves all existing recipe data
"""
import logging
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

logger = logging.getLogger(__name__)


async def _check_column_exists(conn: AsyncConnection, table: str, column: str) -> bool:
    """Check if a column exists in a table using PRAGMA."""
    result = await conn.execute(text(f"PRAGMA table_info({table})"))
    rows = result.fetchall()
    columns = {row[1] for row in rows}
    return column in columns


async def migrate_add_beerjson_support(conn: AsyncConnection) -> None:
    """Add BeerJSON fields to Recipe table."""
    logger.info("Running migration: add_beerjson_support")

    # Check if recipes table exists
    result = await conn.execute(text(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='recipes'"
    ))
    if not result.fetchone():
        logger.info("Recipes table doesn't exist yet, skipping migration")
        return

    # Check if migration already applied (check for renamed column)
    if await _check_column_exists(conn, 'recipes', 'og'):
        logger.info("BeerJSON migration already applied, skipping")
        return

    # Check if we need to migrate (old column exists)
    if not await _check_column_exists(conn, 'recipes', 'og_target'):
        logger.info("No og_target column found, skipping migration")
        return

    logger.info("Migrating recipes table to BeerJSON schema")

    # Get existing data count for logging
    result = await conn.execute(text("SELECT COUNT(*) FROM recipes"))
    recipe_count = result.scalar()

    # Create new table with BeerJSON schema
    await conn.execute(text("""
        CREATE TABLE recipes_new (
            id INTEGER PRIMARY KEY,
            name VARCHAR(200) NOT NULL,
            type VARCHAR(50),
            author VARCHAR(100),

            -- BeerJSON core fields
            batch_size_liters REAL,
            boil_time_minutes INTEGER,
            efficiency_percent REAL,

            -- Gravity targets (renamed from *_target)
            og REAL,
            fg REAL,
            abv REAL,
            ibu REAL,
            color_srm REAL,
            carbonation_vols REAL,

            -- Style reference
            style_id VARCHAR(50),

            -- BeerJSON version tracking
            beerjson_version VARCHAR(10) DEFAULT '1.0',

            -- Format-specific extensions (JSON)
            format_extensions JSON,

            -- Yeast info (from BeerXML, preserved)
            yeast_name VARCHAR(100),
            yeast_lab VARCHAR(100),
            yeast_product_id VARCHAR(50),
            yeast_temp_min REAL,
            yeast_temp_max REAL,
            yeast_attenuation REAL,

            -- Expanded BeerXML fields (preserved)
            brewer VARCHAR(100),
            asst_brewer VARCHAR(100),
            boil_size_l REAL,

            -- Fermentation stages
            primary_age_days INTEGER,
            primary_temp_c REAL,
            secondary_age_days INTEGER,
            secondary_temp_c REAL,
            tertiary_age_days INTEGER,
            tertiary_temp_c REAL,

            -- Aging
            age_days INTEGER,
            age_temp_c REAL,

            -- Carbonation details
            forced_carbonation INTEGER,
            priming_sugar_name VARCHAR(50),
            priming_sugar_amount_kg REAL,

            -- Tasting
            taste_notes TEXT,
            taste_rating REAL,

            -- Dates
            date VARCHAR(50),

            -- Notes and legacy
            notes TEXT,
            beerxml_content TEXT,

            -- Timestamps
            created_at TIMESTAMP,
            updated_at TIMESTAMP,

            FOREIGN KEY (style_id) REFERENCES styles(id)
        )
    """))

    # Copy data with column renames and defaults
    await conn.execute(text("""
        INSERT INTO recipes_new (
            id, name, type, author,
            batch_size_liters, boil_time_minutes, efficiency_percent,
            og, fg, abv, ibu, color_srm, carbonation_vols,
            style_id,
            beerjson_version,
            format_extensions,
            yeast_name, yeast_lab, yeast_product_id,
            yeast_temp_min, yeast_temp_max, yeast_attenuation,
            brewer, asst_brewer, boil_size_l,
            primary_age_days, primary_temp_c,
            secondary_age_days, secondary_temp_c,
            tertiary_age_days, tertiary_temp_c,
            age_days, age_temp_c,
            forced_carbonation, priming_sugar_name, priming_sugar_amount_kg,
            taste_notes, taste_rating,
            date,
            notes, beerxml_content,
            created_at, updated_at
        )
        SELECT
            id, name, type, author,
            batch_size, boil_time_min, efficiency_percent,
            og_target, fg_target, abv_target, ibu_target, srm_target, carbonation_vols,
            style_id,
            '1.0',
            NULL,
            yeast_name, yeast_lab, yeast_product_id,
            yeast_temp_min, yeast_temp_max, yeast_attenuation,
            brewer, asst_brewer, boil_size_l,
            primary_age_days, primary_temp_c,
            secondary_age_days, secondary_temp_c,
            tertiary_age_days, tertiary_temp_c,
            age_days, age_temp_c,
            forced_carbonation, priming_sugar_name, priming_sugar_amount_kg,
            taste_notes, taste_rating,
            date,
            notes, beerxml_content,
            created_at, updated_at
        FROM recipes
    """))

    # Drop old table and rename new one
    await conn.execute(text("DROP TABLE recipes"))
    await conn.execute(text("ALTER TABLE recipes_new RENAME TO recipes"))

    logger.info(f"Migrated {recipe_count} recipes to BeerJSON schema")
    # Note: commit is handled by the caller (init_db() transaction context)
    logger.info("Migration add_beerjson_support completed")
