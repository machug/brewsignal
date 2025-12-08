"""Enhance ingredient tables with timing and format extensions.

This migration:
1. Adds timing JSON column to all ingredient tables (fermentables, hops, cultures, miscs)
2. Adds format_extensions JSON column for preserving format-specific data
3. Renames recipe_yeasts → recipe_cultures (BeerJSON terminology)
4. Migrates existing hop use/time to BeerJSON timing objects (with NULL preservation)
5. Renames columns to match BeerJSON (amount → amount_kg/amount_grams, alpha → alpha_acid_percent)
"""
import json
import logging
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection
from backend.services.hop_timing_converter import convert_hop_timing_safe

logger = logging.getLogger(__name__)

# Whitelist of allowed table names for PRAGMA queries
ALLOWED_TABLES = {
    'recipes', 'recipe_fermentables', 'recipe_hops', 'recipe_cultures',
    'recipe_miscs', 'recipe_mash_steps', 'recipe_fermentation_steps',
    'recipe_water_profiles', 'recipe_water_adjustments'
}


async def _check_column_exists(conn: AsyncConnection, table: str, column: str) -> bool:
    """Check if a column exists in a table.

    Args:
        conn: Database connection
        table: Table name (validated against whitelist)
        column: Column name to check

    Returns:
        True if column exists, False otherwise

    Raises:
        ValueError: If table name is not in whitelist
    """
    if table not in ALLOWED_TABLES:
        raise ValueError(f"Invalid table name: {table}")
    # SAFETY: f-string is safe here because table name is validated against whitelist above.
    # SQLite PRAGMA commands do not support parameter binding, so f-string is required.
    result = await conn.execute(text(f"PRAGMA table_info({table})"))
    columns = {row[1] for row in result}
    return column in columns


async def _check_table_exists(conn: AsyncConnection, table: str) -> bool:
    """Check if a table exists."""
    result = await conn.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' AND name=:table"),
        {"table": table}
    )
    return result.fetchone() is not None


async def migrate_enhance_ingredient_tables(conn: AsyncConnection) -> None:
    """Add timing and format_extensions to ingredient tables."""
    logger.info("Running migration: enhance_ingredient_tables")

    # 1. RecipeFermentable - add new columns
    if await _check_table_exists(conn, 'recipe_fermentables'):
        if not await _check_column_exists(conn, 'recipe_fermentables', 'grain_group'):
            await conn.execute(text(
                "ALTER TABLE recipe_fermentables ADD COLUMN grain_group VARCHAR(50)"
            ))

        if not await _check_column_exists(conn, 'recipe_fermentables', 'percentage'):
            await conn.execute(text(
                "ALTER TABLE recipe_fermentables ADD COLUMN percentage REAL"
            ))

        if not await _check_column_exists(conn, 'recipe_fermentables', 'timing'):
            await conn.execute(text(
                "ALTER TABLE recipe_fermentables ADD COLUMN timing JSON"
            ))

        if not await _check_column_exists(conn, 'recipe_fermentables', 'format_extensions'):
            await conn.execute(text(
                "ALTER TABLE recipe_fermentables ADD COLUMN format_extensions JSON"
            ))

        # Rename columns if needed (color_lovibond → color_srm)
        if await _check_column_exists(conn, 'recipe_fermentables', 'color_lovibond'):
            logger.info("Renaming recipe_fermentables.color_lovibond to color_srm")
            await conn.execute(text("""
                CREATE TABLE recipe_fermentables_new (
                    id INTEGER PRIMARY KEY,
                    recipe_id INTEGER NOT NULL,
                    name VARCHAR(100) NOT NULL,
                    type VARCHAR(50),
                    grain_group VARCHAR(50),
                    amount_kg REAL NOT NULL,
                    percentage REAL,
                    color_srm REAL,
                    yield_percent REAL,
                    origin VARCHAR(50),
                    supplier VARCHAR(100),
                    notes TEXT,
                    add_after_boil INTEGER DEFAULT 0,
                    coarse_fine_diff REAL,
                    moisture REAL,
                    diastatic_power REAL,
                    protein REAL,
                    max_in_batch REAL,
                    recommend_mash INTEGER,
                    timing JSON,
                    format_extensions JSON,
                    FOREIGN KEY (recipe_id) REFERENCES recipes(id) ON DELETE CASCADE
                )
            """))

            await conn.execute(text("""
                INSERT INTO recipe_fermentables_new (
                    id, recipe_id, name, type, amount_kg, color_srm,
                    yield_percent, origin, supplier, notes, add_after_boil,
                    coarse_fine_diff, moisture, diastatic_power, protein,
                    max_in_batch, recommend_mash
                )
                SELECT id, recipe_id, name, type, amount_kg, color_lovibond,
                       yield_percent, origin, supplier, notes, add_after_boil,
                       coarse_fine_diff, moisture, diastatic_power, protein,
                       max_in_batch, recommend_mash
                FROM recipe_fermentables
            """))

            await conn.execute(text("DROP TABLE recipe_fermentables"))
            await conn.execute(text("ALTER TABLE recipe_fermentables_new RENAME TO recipe_fermentables"))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_fermentables_recipe ON recipe_fermentables(recipe_id)"))
            logger.info("Renamed recipe_fermentables.color_lovibond to color_srm")

    # 2. RecipeHop - add new columns and rename existing ones
    if await _check_table_exists(conn, 'recipe_hops'):
        if not await _check_column_exists(conn, 'recipe_hops', 'beta_acid_percent'):
            await conn.execute(text(
                "ALTER TABLE recipe_hops ADD COLUMN beta_acid_percent REAL"
            ))

        if not await _check_column_exists(conn, 'recipe_hops', 'timing'):
            await conn.execute(text(
                "ALTER TABLE recipe_hops ADD COLUMN timing JSON"
            ))

        if not await _check_column_exists(conn, 'recipe_hops', 'format_extensions'):
            await conn.execute(text(
                "ALTER TABLE recipe_hops ADD COLUMN format_extensions JSON"
            ))

        # Rename hop columns if old schema exists
        if await _check_column_exists(conn, 'recipe_hops', 'alpha_percent'):
            logger.info("Renaming recipe_hops columns to BeerJSON schema")

            # Fetch all existing hops with their use/time data
            result = await conn.execute(text("""
                SELECT id, recipe_id, name, alpha_percent, amount_kg, use, time_min,
                       form, type, origin, substitutes, beta_percent,
                       hsi, humulene, caryophyllene, cohumulone, myrcene, notes
                FROM recipe_hops
            """))
            hops = result.fetchall()

            # Create new table with BeerJSON schema
            await conn.execute(text("""
                CREATE TABLE recipe_hops_new (
                    id INTEGER PRIMARY KEY,
                    recipe_id INTEGER NOT NULL,
                    name VARCHAR(100) NOT NULL,
                    origin VARCHAR(50),
                    form VARCHAR(20),
                    alpha_acid_percent REAL NOT NULL,
                    beta_acid_percent REAL,
                    amount_grams REAL NOT NULL,
                    timing JSON,
                    format_extensions JSON,
                    FOREIGN KEY (recipe_id) REFERENCES recipes(id) ON DELETE CASCADE
                )
            """))

            # Migrate data with safe timing conversion
            hops_with_timing = 0
            hops_without_timing = 0

            for hop in hops:
                hop_id, recipe_id, name, alpha_percent, amount_kg, use, time_min = hop[0:7]
                form, hop_type, origin, substitutes, beta_percent = hop[7:12]
                hsi, humulene, caryophyllene, cohumulone, myrcene, notes = hop[12:18]

                # Only build timing if we have valid use field
                timing_dict = None
                if use is not None and use != '':
                    timing_dict = convert_hop_timing_safe(use, time_min)
                    if timing_dict:
                        hops_with_timing += 1
                    else:
                        hops_without_timing += 1
                else:
                    hops_without_timing += 1

                # Convert kg to grams
                amount_grams = amount_kg * 1000 if amount_kg else 0

                # CRITICAL: text() queries require manual JSON encoding
                # (unlike ORM which auto-serializes JSON columns)
                timing_json = json.dumps(timing_dict) if timing_dict else None

                # Build format_extensions with hop metadata
                format_extensions = {}
                if hop_type:
                    format_extensions['type'] = hop_type
                if substitutes:
                    format_extensions['substitutes'] = substitutes
                if hsi is not None:
                    format_extensions['hsi'] = hsi
                if humulene is not None:
                    format_extensions['humulene'] = humulene
                if caryophyllene is not None:
                    format_extensions['caryophyllene'] = caryophyllene
                if cohumulone is not None:
                    format_extensions['cohumulone'] = cohumulone
                if myrcene is not None:
                    format_extensions['myrcene'] = myrcene
                if notes:
                    format_extensions['notes'] = notes

                format_extensions_json = json.dumps(format_extensions) if format_extensions else None

                await conn.execute(text("""
                    INSERT INTO recipe_hops_new (
                        id, recipe_id, name, origin, form,
                        alpha_acid_percent, beta_acid_percent, amount_grams, timing, format_extensions
                    )
                    VALUES (:id, :recipe_id, :name, :origin, :form,
                            :alpha, :beta, :amount, :timing, :format_ext)
                """), {
                    "id": hop_id,
                    "recipe_id": recipe_id,
                    "name": name,
                    "origin": origin,
                    "form": form or 'pellet',
                    "alpha": alpha_percent or 0,
                    "beta": beta_percent,
                    "amount": amount_grams,
                    "timing": timing_json,  # JSON string or None
                    "format_ext": format_extensions_json  # JSON string or None
                })

            await conn.execute(text("DROP TABLE recipe_hops"))
            await conn.execute(text("ALTER TABLE recipe_hops_new RENAME TO recipe_hops"))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_hops_recipe ON recipe_hops(recipe_id)"))

            logger.info(
                f"Migrated {len(hops)} hops to new schema: "
                f"{hops_with_timing} with timing, "
                f"{hops_without_timing} preserved NULL timing"
            )

    # 3. Rename recipe_yeasts → recipe_cultures
    if await _check_table_exists(conn, 'recipe_yeasts'):
        # Check if recipe_cultures already exists (from create_all)
        if await _check_table_exists(conn, 'recipe_cultures'):
            logger.info("recipe_cultures already exists, dropping to recreate from recipe_yeasts")
            await conn.execute(text("DROP TABLE recipe_cultures"))

        logger.info("Renaming recipe_yeasts → recipe_cultures")

        await conn.execute(text("""
            CREATE TABLE recipe_cultures (
                id INTEGER PRIMARY KEY,
                recipe_id INTEGER NOT NULL,
                name VARCHAR(100) NOT NULL,
                type VARCHAR(20),
                form VARCHAR(20),
                producer VARCHAR(100),
                product_id VARCHAR(50),
                temp_min_c REAL,
                temp_max_c REAL,
                attenuation_min_percent REAL,
                attenuation_max_percent REAL,
                amount REAL,
                amount_unit VARCHAR(10),
                timing JSON,
                format_extensions JSON,
                FOREIGN KEY (recipe_id) REFERENCES recipes(id) ON DELETE CASCADE
            )
        """))

        # Copy existing yeasts data (map lab → producer, attenuation_percent → attenuation_min/max)
        await conn.execute(text("""
            INSERT INTO recipe_cultures (
                id, recipe_id, name, type, form, producer, product_id,
                temp_min_c, temp_max_c, attenuation_min_percent, attenuation_max_percent,
                amount, amount_unit
            )
            SELECT id, recipe_id, name, type, form, lab, product_id,
                   temp_min_c, temp_max_c, attenuation_percent, attenuation_percent,
                   COALESCE(amount_l, amount_kg),
                   CASE WHEN amount_l IS NOT NULL THEN 'ml' ELSE 'pkg' END
            FROM recipe_yeasts
        """))

        await conn.execute(text("DROP TABLE recipe_yeasts"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_cultures_recipe ON recipe_cultures(recipe_id)"))
        logger.info("Renamed recipe_yeasts to recipe_cultures")

    # 4. RecipeMisc - add new columns
    if await _check_table_exists(conn, 'recipe_miscs'):
        if not await _check_column_exists(conn, 'recipe_miscs', 'amount_unit'):
            await conn.execute(text(
                "ALTER TABLE recipe_miscs ADD COLUMN amount_unit VARCHAR(10)"
            ))

        if not await _check_column_exists(conn, 'recipe_miscs', 'timing'):
            await conn.execute(text(
                "ALTER TABLE recipe_miscs ADD COLUMN timing JSON"
            ))

        if not await _check_column_exists(conn, 'recipe_miscs', 'format_extensions'):
            await conn.execute(text(
                "ALTER TABLE recipe_miscs ADD COLUMN format_extensions JSON"
            ))

    logger.info("Migration enhance_ingredient_tables completed")
