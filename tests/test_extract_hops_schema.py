"""Phase 1 schema migration tests for Abstrax extract support (tilt_ui-0l5)."""
import pytest
from sqlalchemy import text
from backend.database import async_session_factory, engine, init_db, _migrate_add_extract_columns


@pytest.fixture(scope="module", autouse=True)
async def setup_db():
    await init_db()


@pytest.mark.asyncio
async def test_recipe_hops_has_extract_columns():
    """Migration adds is_extract + amount_ml; alpha_acid_percent is nullable."""
    async with async_session_factory() as db:
        rows = (await db.execute(text("PRAGMA table_info(recipe_hops)"))).fetchall()
    cols = {r[1]: {"type": r[2], "notnull": r[3]} for r in rows}
    assert "is_extract" in cols, f"is_extract missing; cols={list(cols)}"
    assert "amount_ml" in cols, f"amount_ml missing; cols={list(cols)}"
    assert cols["alpha_acid_percent"]["notnull"] == 0, (
        "alpha_acid_percent must be NULLable for extracts"
    )


@pytest.mark.asyncio
async def test_migration_preserves_existing_hop_rows():
    """Table-recreate path must not lose data.

    Forces a pre-migration schema (alpha_acid_percent NOT NULL, no is_extract /
    amount_ml columns), inserts a fixture row, runs the migration, and asserts
    the row survives with the new columns defaulted correctly.
    """
    async with engine.begin() as conn:
        # Force pre-migration schema state. SQLite defaults to FK off, so
        # dropping/recreating recipe_hops without inserting a parent recipe row
        # is safe; if a future config enables FKs, disable them for this test.
        await conn.execute(text("PRAGMA foreign_keys = OFF"))
        await conn.execute(text("DROP TABLE IF EXISTS recipe_hops"))
        await conn.execute(text(
            """
            CREATE TABLE recipe_hops (
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
            """
        ))
        await conn.execute(text(
            "INSERT INTO recipe_hops "
            "(id, recipe_id, name, origin, form, alpha_acid_percent, "
            " beta_acid_percent, amount_grams, timing, format_extensions) "
            "VALUES (9999, 1, 'Fixture Hop', 'US', 'Pellet', 5.5, "
            "        3.2, 20.0, NULL, NULL)"
        ))

        # Run the migration under test.
        await conn.run_sync(_migrate_add_extract_columns)

        row = (await conn.execute(text(
            "SELECT id, name, origin, form, alpha_acid_percent, "
            "       beta_acid_percent, amount_grams, is_extract, amount_ml "
            "FROM recipe_hops WHERE id = 9999"
        ))).fetchone()

    assert row is not None, "fixture row lost during migration"
    assert row[1] == "Fixture Hop"
    assert row[2] == "US"
    assert row[3] == "Pellet"
    assert row[4] == 5.5
    assert row[5] == 3.2
    assert row[6] == 20.0
    assert row[7] == 0, f"is_extract should default to 0, got {row[7]}"
    assert row[8] is None, f"amount_ml should default to NULL, got {row[8]}"

    # Verify the new schema shape: alpha_acid_percent is now NULLable and the
    # extract columns are present.
    async with engine.begin() as conn:
        info = (await conn.execute(text("PRAGMA table_info(recipe_hops)"))).fetchall()
    cols = {r[1]: {"type": r[2], "notnull": r[3]} for r in info}
    assert cols["alpha_acid_percent"]["notnull"] == 0
    assert "is_extract" in cols
    assert "amount_ml" in cols
