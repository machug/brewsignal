"""Test BeerJSON migration adds required columns to Recipe table."""
import pytest
from sqlalchemy import text
from backend import models  # noqa: F401 - Import to register models with Base
from backend.database import init_db, engine


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
