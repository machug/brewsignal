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

# Whitelist of allowed table names for PRAGMA queries
ALLOWED_TABLES = {
    'recipes', 'recipe_fermentables', 'recipe_hops', 'recipe_cultures',
    'recipe_miscs', 'recipe_mash_steps', 'recipe_fermentation_steps',
    'recipe_water_profiles', 'recipe_water_adjustments'
}


async def _check_column_exists(conn: AsyncConnection, table: str, column: str) -> bool:
    """Check if a column exists in a table using PRAGMA.

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

    # Clean up any leftover recipes_new table from interrupted migration
    await conn.execute(text("DROP TABLE IF EXISTS recipes_new"))

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

    # Detect which columns exist in old schema
    result = await conn.execute(text("PRAGMA table_info(recipes)"))
    rows = result.fetchall()
    existing_columns = {row[1] for row in rows}  # row[1] is column name

    # Define column mapping: new_column -> (old_column, default_value)
    column_mapping = {
        # Core fields (always required)
        'id': ('id', None),
        'name': ('name', None),

        # Optional fields with potential renames
        'type': ('type', "''"),
        'author': ('author', "''"),
        'batch_size_liters': ('batch_size', 'NULL'),
        'boil_time_minutes': ('boil_time_min', 'NULL'),
        'efficiency_percent': ('efficiency_percent', 'NULL'),

        # Renamed gravity fields
        'og': ('og_target', 'NULL'),
        'fg': ('fg_target', 'NULL'),
        'abv': ('abv_target', 'NULL'),
        'ibu': ('ibu_target', 'NULL'),
        'color_srm': ('srm_target', 'NULL'),
        'carbonation_vols': ('carbonation_vols', 'NULL'),

        'style_id': ('style_id', 'NULL'),

        # New BeerJSON fields
        'beerjson_version': (None, "'1.0'"),  # Always default
        'format_extensions': (None, 'NULL'),

        # Yeast info
        'yeast_name': ('yeast_name', 'NULL'),
        'yeast_lab': ('yeast_lab', 'NULL'),
        'yeast_product_id': ('yeast_product_id', 'NULL'),
        'yeast_temp_min': ('yeast_temp_min', 'NULL'),
        'yeast_temp_max': ('yeast_temp_max', 'NULL'),
        'yeast_attenuation': ('yeast_attenuation', 'NULL'),

        # BeerXML fields
        'brewer': ('brewer', 'NULL'),
        'asst_brewer': ('asst_brewer', 'NULL'),
        'boil_size_l': ('boil_size_l', 'NULL'),

        # Fermentation stages
        'primary_age_days': ('primary_age_days', 'NULL'),
        'primary_temp_c': ('primary_temp_c', 'NULL'),
        'secondary_age_days': ('secondary_age_days', 'NULL'),
        'secondary_temp_c': ('secondary_temp_c', 'NULL'),
        'tertiary_age_days': ('tertiary_age_days', 'NULL'),
        'tertiary_temp_c': ('tertiary_temp_c', 'NULL'),

        # Aging
        'age_days': ('age_days', 'NULL'),
        'age_temp_c': ('age_temp_c', 'NULL'),

        # Carbonation
        'forced_carbonation': ('forced_carbonation', 'NULL'),
        'priming_sugar_name': ('priming_sugar_name', 'NULL'),
        'priming_sugar_amount_kg': ('priming_sugar_amount_kg', 'NULL'),

        # Tasting
        'taste_notes': ('taste_notes', 'NULL'),
        'taste_rating': ('taste_rating', 'NULL'),

        # Dates
        'date': ('date', 'NULL'),

        # Notes
        'notes': ('notes', 'NULL'),
        'beerxml_content': ('beerxml_content', 'NULL'),

        # Timestamps
        'created_at': ('created_at', 'NULL'),
        'updated_at': ('updated_at', 'NULL'),
    }

    # Build SELECT clause based on existing columns
    select_parts = []
    insert_columns = []

    for new_col, (old_col, default_val) in column_mapping.items():
        insert_columns.append(new_col)

        if old_col is None:
            # New column, use default
            select_parts.append(default_val)
        elif old_col in existing_columns:
            # Column exists, copy it
            select_parts.append(old_col)
        else:
            # Column doesn't exist, use default
            select_parts.append(default_val)

    # Build and execute dynamic INSERT statement
    insert_sql = f"""
        INSERT INTO recipes_new ({', '.join(insert_columns)})
        SELECT {', '.join(select_parts)}
        FROM recipes
    """

    logger.info(f"Copying data with column mapping for {len(existing_columns)} existing columns")
    await conn.execute(text(insert_sql))

    # Drop old table and rename new one
    await conn.execute(text("DROP TABLE recipes"))
    await conn.execute(text("ALTER TABLE recipes_new RENAME TO recipes"))

    logger.info(f"Migrated {recipe_count} recipes to BeerJSON schema")
    # Note: commit is handled by the caller (init_db() transaction context)
    logger.info("Migration add_beerjson_support completed")
