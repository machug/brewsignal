"""Test BeerJSON migration adds required columns to Recipe table."""
import json
import pytest
import os
from sqlalchemy import text
from backend import models  # noqa: F401 - Import to register models with Base
from backend.database import init_db, engine


@pytest.fixture(autouse=True)
async def cleanup_db():
    """Clean up database before each test."""
    # Dispose all engine connections to release the database file
    await engine.dispose()

    # Remove database file
    test_db_path = 'data/fermentation.db'
    if os.path.exists(test_db_path):
        os.remove(test_db_path)

    yield

    # Cleanup after test
    await engine.dispose()
    if os.path.exists(test_db_path):
        os.remove(test_db_path)


@pytest.mark.asyncio
async def test_recipe_table_has_beerjson_columns():
    """Test that Recipe table has BeerJSON columns after migration."""
    await init_db()

    async with engine.connect() as conn:
        # Use PRAGMA table_info (SQLite-specific but reliable)
        result = await conn.execute(text("PRAGMA table_info(recipes)"))
        rows = result.fetchall()
        columns = {row[1] for row in rows}  # row[1] is column name

        # New BeerJSON columns
        assert 'batch_size_liters' in columns
        assert 'boil_time_minutes' in columns
        assert 'efficiency_percent' in columns
        assert 'beerjson_version' in columns
        assert 'format_extensions' in columns
        assert 'carbonation_vols' in columns

        # Renamed columns
        assert 'og' in columns
        assert 'fg' in columns
        assert 'color_srm' in columns

        # Old names should not exist
        assert 'og_target' not in columns
        assert 'fg_target' not in columns
        assert 'srm_target' not in columns


@pytest.mark.asyncio
async def test_migration_preserves_recipe_data():
    """Test that migration preserves existing recipe data with column renames."""
    # Create old schema with minimal columns (just id, name, og_target, fg_target)
    async with engine.begin() as conn:
        await conn.execute(text("""
            CREATE TABLE recipes (
                id INTEGER PRIMARY KEY,
                name VARCHAR(200) NOT NULL,
                og_target REAL,
                fg_target REAL,
                batch_size REAL,
                notes TEXT,
                created_at TIMESTAMP
            )
        """))

        # Insert test data
        await conn.execute(text("""
            INSERT INTO recipes (id, name, og_target, fg_target, batch_size, notes)
            VALUES
                (1, 'Test IPA', 1.065, 1.012, 20.0, 'Test recipe 1'),
                (2, 'Test Stout', 1.072, 1.018, 23.0, 'Test recipe 2'),
                (3, 'Test Lager', 1.050, 1.010, 19.0, 'Test recipe 3')
        """))

    # Run full init_db which should trigger migration
    await init_db()

    # Verify data was preserved and columns renamed
    async with engine.connect() as conn:
        result = await conn.execute(text("""
            SELECT id, name, og, fg, batch_size_liters, notes, beerjson_version
            FROM recipes
            ORDER BY id
        """))
        recipes = result.fetchall()

        assert len(recipes) == 3

        # Check first recipe
        assert recipes[0][0] == 1  # id
        assert recipes[0][1] == 'Test IPA'  # name
        assert recipes[0][2] == 1.065  # og (renamed from og_target)
        assert recipes[0][3] == 1.012  # fg (renamed from fg_target)
        assert recipes[0][4] == 20.0  # batch_size_liters (renamed from batch_size)
        assert recipes[0][5] == 'Test recipe 1'  # notes
        assert recipes[0][6] == '1.0'  # beerjson_version (new default)

        # Check second recipe
        assert recipes[1][0] == 2
        assert recipes[1][1] == 'Test Stout'
        assert recipes[1][2] == 1.072
        assert recipes[1][3] == 1.018
        assert recipes[1][4] == 23.0
        assert recipes[1][5] == 'Test recipe 2'
        assert recipes[1][6] == '1.0'

        # Check third recipe
        assert recipes[2][0] == 3
        assert recipes[2][1] == 'Test Lager'
        assert recipes[2][2] == 1.050
        assert recipes[2][3] == 1.010
        assert recipes[2][4] == 19.0
        assert recipes[2][5] == 'Test recipe 3'
        assert recipes[2][6] == '1.0'

        # Verify new schema has expected columns
        result = await conn.execute(text("PRAGMA table_info(recipes)"))
        rows = result.fetchall()
        columns = {row[1] for row in rows}

        # Verify renamed columns exist
        assert 'og' in columns
        assert 'fg' in columns
        assert 'batch_size_liters' in columns

        # Verify old columns are gone
        assert 'og_target' not in columns
        assert 'fg_target' not in columns
        assert 'batch_size' not in columns

        # Verify new BeerJSON columns exist
        assert 'beerjson_version' in columns
        assert 'format_extensions' in columns


@pytest.mark.asyncio
async def test_ingredient_tables_have_timing_columns():
    """Test that ingredient tables have timing and format_extensions columns."""
    await init_db()

    async with engine.connect() as conn:
        # RecipeFermentable
        result = await conn.execute(text("PRAGMA table_info(recipe_fermentables)"))
        rows = result.fetchall()
        ferm_cols = {row[1] for row in rows}  # row[1] is column name

        assert 'grain_group' in ferm_cols
        assert 'percentage' in ferm_cols
        assert 'timing' in ferm_cols
        assert 'format_extensions' in ferm_cols
        assert 'amount_kg' in ferm_cols
        assert 'color_srm' in ferm_cols

        # RecipeHop
        result = await conn.execute(text("PRAGMA table_info(recipe_hops)"))
        rows = result.fetchall()
        hop_cols = {row[1] for row in rows}

        assert 'timing' in hop_cols
        assert 'format_extensions' in hop_cols
        assert 'beta_acid_percent' in hop_cols
        assert 'alpha_acid_percent' in hop_cols
        assert 'amount_grams' in hop_cols

        # RecipeCulture (renamed from RecipeYeast)
        result = await conn.execute(text("PRAGMA table_info(recipe_cultures)"))
        rows = result.fetchall()
        culture_cols = {row[1] for row in rows}

        assert 'timing' in culture_cols
        assert 'format_extensions' in culture_cols

        # RecipeMisc
        result = await conn.execute(text("PRAGMA table_info(recipe_miscs)"))
        rows = result.fetchall()
        misc_cols = {row[1] for row in rows}

        assert 'amount_unit' in misc_cols
        assert 'timing' in misc_cols
        assert 'format_extensions' in misc_cols


@pytest.mark.asyncio
async def test_hop_timing_data_migration():
    """Test that hop timing is correctly migrated from BeerXML use/time to BeerJSON timing JSON."""
    # Create old schema with BeerXML hop columns
    async with engine.begin() as conn:
        # Create minimal recipes table
        await conn.execute(text("""
            CREATE TABLE recipes (
                id INTEGER PRIMARY KEY,
                name VARCHAR(200) NOT NULL
            )
        """))

        await conn.execute(text("""
            INSERT INTO recipes (id, name)
            VALUES (1, 'Test Recipe')
        """))

        # Create old hop schema with BeerXML fields
        await conn.execute(text("""
            CREATE TABLE recipe_hops (
                id INTEGER PRIMARY KEY,
                recipe_id INTEGER NOT NULL,
                name VARCHAR(100) NOT NULL,
                alpha_percent REAL NOT NULL,
                amount_kg REAL NOT NULL,
                use VARCHAR(20),
                time_min REAL,
                form VARCHAR(20),
                type VARCHAR(50),
                origin VARCHAR(50),
                substitutes TEXT,
                beta_percent REAL,
                hsi REAL,
                humulene REAL,
                caryophyllene REAL,
                cohumulone REAL,
                myrcene REAL,
                notes TEXT,
                FOREIGN KEY (recipe_id) REFERENCES recipes(id) ON DELETE CASCADE
            )
        """))

        # Insert test hops with various use/time combinations
        await conn.execute(text("""
            INSERT INTO recipe_hops (
                id, recipe_id, name, alpha_percent, amount_kg, use, time_min, form, origin
            )
            VALUES
                (1, 1, 'Cascade', 5.5, 0.028, 'Boil', 60.0, 'Pellet', 'US'),
                (2, 1, 'Citra', 12.0, 0.014, 'Dry Hop', 10080.0, 'Pellet', 'US'),
                (3, 1, 'Magnum', 14.0, 0.014, 'First Wort', 0.0, 'Pellet', 'Germany'),
                (4, 1, 'Saaz', 3.5, 0.028, 'Aroma', 5.0, 'Whole', 'Czech'),
                (5, 1, 'Unknown Use', 6.0, 0.014, '', NULL, 'Pellet', 'US'),
                (6, 1, 'Null Use', 6.0, 0.014, NULL, NULL, 'Pellet', 'US')
        """))

    # Run migration
    await init_db()

    # Verify hop timing conversion
    async with engine.connect() as conn:
        result = await conn.execute(text("""
            SELECT id, name, alpha_acid_percent, amount_grams, timing, origin, form
            FROM recipe_hops
            ORDER BY id
        """))
        hops = result.fetchall()

        assert len(hops) == 6

        # Hop 1: Boil 60 min → add_to_boil with duration
        hop1 = hops[0]
        assert hop1[0] == 1
        assert hop1[1] == 'Cascade'
        assert hop1[2] == 5.5  # alpha_acid_percent
        assert hop1[3] == 28.0  # amount_grams (0.028 kg * 1000)
        timing1 = json.loads(hop1[4]) if hop1[4] else None
        assert timing1 is not None
        assert timing1['use'] == 'add_to_boil'
        assert timing1['continuous'] is False
        assert timing1['duration']['value'] == 60.0
        assert timing1['duration']['unit'] == 'min'

        # Hop 2: Dry Hop 10080 min (7 days) → add_to_fermentation with duration in days
        hop2 = hops[1]
        assert hop2[0] == 2
        assert hop2[1] == 'Citra'
        assert hop2[3] == 14.0  # amount_grams
        timing2 = json.loads(hop2[4]) if hop2[4] else None
        assert timing2 is not None
        assert timing2['use'] == 'add_to_fermentation'
        assert timing2['continuous'] is False
        assert timing2['duration']['value'] == 7  # 10080 min / 1440 = 7 days
        assert timing2['duration']['unit'] == 'day'
        assert timing2['phase'] == 'primary'

        # Hop 3: First Wort 0 min → add_to_boil without duration (FWH has no time component)
        hop3 = hops[2]
        assert hop3[0] == 3
        assert hop3[1] == 'Magnum'
        assert hop3[3] == 14.0  # amount_grams
        timing3 = json.loads(hop3[4]) if hop3[4] else None
        assert timing3 is not None
        assert timing3['use'] == 'add_to_boil'
        assert timing3['continuous'] is False
        # No duration key for 0 time
        assert 'duration' not in timing3

        # Hop 4: Aroma 5 min → add_to_boil with duration
        hop4 = hops[3]
        assert hop4[0] == 4
        assert hop4[1] == 'Saaz'
        assert hop4[3] == 28.0  # amount_grams
        timing4 = json.loads(hop4[4]) if hop4[4] else None
        assert timing4 is not None
        assert timing4['use'] == 'add_to_boil'
        assert timing4['duration']['value'] == 5.0
        assert timing4['duration']['unit'] == 'min'

        # Hop 5: Empty use string → NULL timing preserved
        hop5 = hops[4]
        assert hop5[0] == 5
        assert hop5[1] == 'Unknown Use'
        assert hop5[3] == 14.0  # amount_grams
        assert hop5[4] is None  # timing should be NULL

        # Hop 6: NULL use → NULL timing preserved
        hop6 = hops[5]
        assert hop6[0] == 6
        assert hop6[1] == 'Null Use'
        assert hop6[3] == 14.0  # amount_grams
        assert hop6[4] is None  # timing should be NULL


@pytest.mark.asyncio
async def test_water_and_procedure_tables_exist():
    """Test that water chemistry and procedure tables exist."""
    await init_db()

    async with engine.connect() as conn:
        # Use PRAGMA table_info (SQLite-specific but reliable)
        # Verify water profile table exists
        result = await conn.execute(text("PRAGMA table_info(recipe_water_profiles)"))
        rows = result.fetchall()
        water_cols = {row[1] for row in rows}  # row[1] is column name

        assert len(rows) > 0, "recipe_water_profiles table should exist"
        assert 'profile_type' in water_cols
        assert 'calcium_ppm' in water_cols
        assert 'sulfate_ppm' in water_cols

        # Verify water adjustments table exists
        result = await conn.execute(text("PRAGMA table_info(recipe_water_adjustments)"))
        rows = result.fetchall()
        adjustment_cols = {row[1] for row in rows}

        assert len(rows) > 0, "recipe_water_adjustments table should exist"
        assert 'stage' in adjustment_cols
        assert 'calcium_sulfate_g' in adjustment_cols
        assert 'acid_type' in adjustment_cols

        # Verify mash step table exists
        result = await conn.execute(text("PRAGMA table_info(recipe_mash_steps)"))
        rows = result.fetchall()
        mash_cols = {row[1] for row in rows}

        assert len(rows) > 0, "recipe_mash_steps table should exist"
        assert 'step_number' in mash_cols
        assert 'temp_c' in mash_cols
        assert 'time_minutes' in mash_cols

        # Verify fermentation step table exists
        result = await conn.execute(text("PRAGMA table_info(recipe_fermentation_steps)"))
        rows = result.fetchall()
        ferm_cols = {row[1] for row in rows}

        assert len(rows) > 0, "recipe_fermentation_steps table should exist"
        assert 'step_number' in ferm_cols
        assert 'type' in ferm_cols
        assert 'temp_c' in ferm_cols
        assert 'time_days' in ferm_cols
