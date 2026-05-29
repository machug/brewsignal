"""Tests for the legacy NULL style_id backfill (tilt_ui-ru9, fix #4).

Historical recipes (imported before the import-path fix, or where the style
was only ever recorded in the free-text `type` field) carry style_id=NULL.
The backfill resolves recipe.type through resolve_style_id and fills style_id
when it maps to a known BJCP style. Types that are not styles ("all-grain",
"extract") resolve to nothing and are left NULL — the backfill never guesses.
"""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Recipe
from backend.migrations.backfill_recipe_style_id import backfill_null_style_ids


async def _add(db: AsyncSession, name: str, type_: str, style_id=None) -> int:
    r = Recipe(name=name, type=type_, style_id=style_id, batch_size_liters=20)
    db.add(r)
    await db.flush()
    rid = r.id
    await db.commit()
    return rid


class TestBackfillNullStyleIds:
    @pytest.mark.asyncio
    async def test_type_holding_style_name_is_resolved(self, test_db: AsyncSession):
        rid = await _add(test_db, "Guinness Clone", "Irish Stout")
        count = await backfill_null_style_ids(test_db)
        recipe = (
            await test_db.execute(select(Recipe).where(Recipe.id == rid))
        ).scalar_one()
        assert recipe.style_id == "bjcp-2021-15b"
        assert count >= 1

    @pytest.mark.asyncio
    async def test_type_alias_is_resolved(self, test_db: AsyncSession):
        rid = await _add(test_db, "Dream Haze", "NEIPA")
        await backfill_null_style_ids(test_db)
        recipe = (
            await test_db.execute(select(Recipe).where(Recipe.id == rid))
        ).scalar_one()
        assert recipe.style_id == "bjcp-2021-21c"

    @pytest.mark.asyncio
    async def test_non_style_type_left_null(self, test_db: AsyncSession):
        rid = await _add(test_db, "Mystery Brew", "all-grain")
        await backfill_null_style_ids(test_db)
        recipe = (
            await test_db.execute(select(Recipe).where(Recipe.id == rid))
        ).scalar_one()
        assert recipe.style_id is None

    @pytest.mark.parametrize("noisy_type", ["IPA", "Ale", "Stout", "Pale", "Wheat"])
    @pytest.mark.asyncio
    async def test_ambiguous_substring_type_left_null(
        self, test_db: AsyncSession, noisy_type
    ):
        """Backfill uses the strict resolver (no substring), so a bare "IPA"
        must NOT silently resolve to e.g. "English IPA"."""
        rid = await _add(test_db, f"Brew {noisy_type}", noisy_type)
        await backfill_null_style_ids(test_db)
        recipe = (
            await test_db.execute(select(Recipe).where(Recipe.id == rid))
        ).scalar_one()
        assert recipe.style_id is None

    @pytest.mark.asyncio
    async def test_existing_style_id_untouched(self, test_db: AsyncSession):
        rid = await _add(test_db, "Already Styled", "Irish Stout",
                         style_id="bjcp-2021-21a")
        await backfill_null_style_ids(test_db)
        recipe = (
            await test_db.execute(select(Recipe).where(Recipe.id == rid))
        ).scalar_one()
        # Backfill only touches NULLs; a wrong-but-present FK is left alone.
        assert recipe.style_id == "bjcp-2021-21a"

    @pytest.mark.asyncio
    async def test_idempotent_second_run_changes_nothing(self, test_db: AsyncSession):
        await _add(test_db, "Guinness Clone", "Irish Stout")
        first = await backfill_null_style_ids(test_db)
        second = await backfill_null_style_ids(test_db)
        assert first >= 1
        assert second == 0
