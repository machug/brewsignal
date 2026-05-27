"""Phase 1 schema migration tests for Abstrax extract support (tilt_ui-0l5)."""
import pytest
from sqlalchemy import text
from backend.database import async_session_factory, init_db


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
