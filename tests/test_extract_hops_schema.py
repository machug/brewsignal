"""Phase 1 schema migration tests for Abstrax extract support (tilt_ui-0l5)."""
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from backend.database import async_session_factory, init_db, _migrate_add_extract_columns


@pytest.fixture(scope="module", autouse=True)
async def setup_db():
    await init_db()


async def _make_isolated_engine_with_pre_migration_schema():
    """Return a fresh in-memory engine with the pre-migration recipe_hops shape.

    Used by data-preservation tests so they don't mutate data/fermentation.db.
    """
    eng = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with eng.begin() as conn:
        # No FK to recipes(id) here — we don't materialise the recipes table
        # in this isolated engine, and we don't need cascade behaviour for the
        # migration unit-under-test.
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
                format_extensions JSON
            )
            """
        ))
    return eng


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

    Builds a fresh in-memory engine with the pre-migration schema, inserts a
    fixture row, runs the migration, and asserts the row survives with the
    new columns defaulted correctly. Uses an isolated engine so the shared
    data/fermentation.db is never touched.
    """
    eng = await _make_isolated_engine_with_pre_migration_schema()
    try:
        async with eng.begin() as conn:
            await conn.execute(text(
                "INSERT INTO recipe_hops "
                "(id, recipe_id, name, origin, form, alpha_acid_percent, "
                " beta_acid_percent, amount_grams, timing, format_extensions) "
                "VALUES (1, 1, 'Fixture Hop', 'US', 'Pellet', 5.5, "
                "        3.2, 20.0, NULL, NULL)"
            ))

            # Run the migration under test.
            await conn.run_sync(_migrate_add_extract_columns)

            row = (await conn.execute(text(
                "SELECT id, name, origin, form, alpha_acid_percent, "
                "       beta_acid_percent, amount_grams, is_extract, amount_ml "
                "FROM recipe_hops WHERE id = 1"
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

            # Verify the new schema shape: alpha_acid_percent is now NULLable
            # and the extract columns are present.
            info = (await conn.execute(text("PRAGMA table_info(recipe_hops)"))).fetchall()
            cols = {r[1]: {"type": r[2], "notnull": r[3]} for r in info}
            assert cols["alpha_acid_percent"]["notnull"] == 0
            assert "is_extract" in cols
            assert "amount_ml" in cols
    finally:
        await eng.dispose()


@pytest.mark.asyncio
async def test_migration_recovers_orphaned_table_without_data_loss():
    """If a prior migration crashed between RENAME and INSERT-SELECT, the
    orphan table holds the only copy of the data. Re-running the migration
    must restore rows, not drop them.

    Runs against a fresh in-memory engine; the shared data/fermentation.db is
    never touched.
    """
    eng = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with eng.begin() as conn:
            # Simulate post-crash state: live new-shape recipe_hops empty +
            # orphan table holds the original rows.
            await conn.execute(text(
                """
                CREATE TABLE recipe_hops (
                    id INTEGER PRIMARY KEY,
                    recipe_id INTEGER NOT NULL,
                    name VARCHAR(100) NOT NULL,
                    origin VARCHAR(50),
                    form VARCHAR(20),
                    alpha_acid_percent REAL,
                    beta_acid_percent REAL,
                    amount_grams REAL NOT NULL,
                    amount_ml REAL,
                    is_extract BOOLEAN NOT NULL DEFAULT 0,
                    timing JSON,
                    format_extensions JSON
                )
                """
            ))
            await conn.execute(text(
                """
                CREATE TABLE recipe_hops_old_alpha (
                    id INTEGER PRIMARY KEY,
                    recipe_id INTEGER NOT NULL,
                    name VARCHAR(100) NOT NULL,
                    origin VARCHAR(50),
                    form VARCHAR(20),
                    alpha_acid_percent REAL NOT NULL,
                    beta_acid_percent REAL,
                    amount_grams REAL NOT NULL,
                    timing JSON,
                    format_extensions JSON
                )
                """
            ))
            await conn.execute(text(
                "INSERT INTO recipe_hops_old_alpha "
                "(id, recipe_id, name, alpha_acid_percent, amount_grams) "
                "VALUES (9998, 1, 'Crash Survivor', 4.4, 30.0)"
            ))

            # Run the migration — should recover orphan rows before drop.
            await conn.run_sync(_migrate_add_extract_columns)

            row = (await conn.execute(text(
                "SELECT id, name, alpha_acid_percent, amount_grams, is_extract, amount_ml "
                "FROM recipe_hops WHERE id = 9998"
            ))).fetchone()
            assert row is not None, "orphan row lost during recovery"
            assert row[1] == "Crash Survivor"
            assert row[2] == 4.4
            assert row[3] == 30.0
            assert row[4] == 0, f"is_extract should default to 0, got {row[4]}"
            assert row[5] is None, f"amount_ml should default to NULL, got {row[5]}"

            # Orphan must be cleaned up after recovery.
            orphan = (await conn.execute(text(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name='recipe_hops_old_alpha'"
            ))).fetchone()
            assert orphan is None, "orphan table should be dropped after recovery"
    finally:
        await eng.dispose()


@pytest.mark.asyncio
async def test_migration_recovers_when_only_orphan_exists():
    """Crash between RENAME and CREATE TABLE recipe_hops: orphan is the
    only table, recipe_hops missing. Migration must rename orphan back
    and complete normally without losing data.
    """
    eng = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with eng.begin() as conn:
            # Only the orphan exists — recipe_hops was renamed away and
            # the process crashed before the new recipe_hops was created.
            await conn.execute(text(
                """
                CREATE TABLE recipe_hops_old_alpha (
                    id INTEGER PRIMARY KEY,
                    recipe_id INTEGER NOT NULL,
                    name VARCHAR(100) NOT NULL,
                    origin VARCHAR(50),
                    form VARCHAR(20),
                    alpha_acid_percent REAL NOT NULL,
                    beta_acid_percent REAL,
                    amount_grams REAL NOT NULL,
                    timing JSON,
                    format_extensions JSON
                )
                """
            ))
            await conn.execute(text(
                "INSERT INTO recipe_hops_old_alpha "
                "(id, recipe_id, name, alpha_acid_percent, amount_grams) "
                "VALUES (1, 1, 'Rescued From Orphan', 6.5, 25.0)"
            ))

            await conn.run_sync(_migrate_add_extract_columns)

            row = (await conn.execute(text(
                "SELECT name, alpha_acid_percent, amount_grams, is_extract, amount_ml "
                "FROM recipe_hops WHERE id = 1"
            ))).fetchone()
            assert row is not None, "rescued row missing after orphan-only recovery"
            assert row[0] == "Rescued From Orphan"
            assert row[1] == 6.5
            assert row[2] == 25.0
            assert row[3] == 0, f"is_extract should default to 0, got {row[3]}"
            assert row[4] is None, f"amount_ml should default to NULL, got {row[4]}"

            # Orphan must be cleaned up.
            orphan = (await conn.execute(text(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name='recipe_hops_old_alpha'"
            ))).fetchone()
            assert orphan is None, "orphan table should be dropped after recovery"
    finally:
        await eng.dispose()


@pytest.mark.asyncio
async def test_migration_creates_index_after_full_run():
    """Index ix_hops_recipe must exist after a fresh migration run."""
    eng = await _make_isolated_engine_with_pre_migration_schema()
    try:
        async with eng.begin() as conn:
            await conn.run_sync(_migrate_add_extract_columns)
            idx = (await conn.execute(text(
                "SELECT name FROM sqlite_master "
                "WHERE type='index' AND name='ix_hops_recipe'"
            ))).fetchone()
            assert idx is not None, "ix_hops_recipe index should exist after migration"
    finally:
        await eng.dispose()
