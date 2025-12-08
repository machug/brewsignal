"""Test BeerJSON migration adds required columns to Recipe table."""
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
