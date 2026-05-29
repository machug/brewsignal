"""Tests for the color_srm repair backfill (tilt_ui-81n).

Existing recipes carry a color_srm that was computed when a dark grain's color
was missing (defaulted to pale), so e.g. a stout shows ~3.5 SRM. The backfill
enriches missing fermentable colors from the reference table and recomputes
color_srm from the (now colored) grain bill. It only updates color_srm; IBU and
gravity are left alone.
"""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Recipe, RecipeFermentable
from backend.migrations.backfill_recipe_color_srm import backfill_recipe_color_srm


async def _stout(db: AsyncSession, *, color_srm, roasted_color) -> int:
    r = Recipe(name="Repair Stout", type="all-grain",
               batch_size_liters=23, color_srm=color_srm, ibu=42.0)
    r.fermentables = [
        RecipeFermentable(name="Maris Otter", amount_kg=3.8, color_srm=3.0),
        RecipeFermentable(name="Roasted Barley", amount_kg=0.4,
                          color_srm=roasted_color),
    ]
    db.add(r)
    await db.flush()
    rid = r.id
    await db.commit()
    return rid


class TestBackfillColorSrm:
    @pytest.mark.asyncio
    async def test_recomputes_wrong_low_srm(self, test_db: AsyncSession):
        # color_srm stored as 3.5, roasted barley color already present (550).
        rid = await _stout(test_db, color_srm=3.5, roasted_color=550.0)
        changed = await backfill_recipe_color_srm(test_db)
        recipe = (
            await test_db.execute(select(Recipe).where(Recipe.id == rid))
        ).scalar_one()
        assert changed >= 1
        assert recipe.color_srm > 25  # a real dry-stout SRM, not 3.5

    @pytest.mark.asyncio
    async def test_enriches_missing_ferm_color_then_recomputes(
        self, test_db: AsyncSession
    ):
        # Roasted barley row has NO color -> must be enriched from reference
        # (500) before recompute.
        rid = await _stout(test_db, color_srm=3.5, roasted_color=None)
        await backfill_recipe_color_srm(test_db)
        recipe = (
            await test_db.execute(
                select(Recipe).where(Recipe.id == rid)
            )
        ).scalar_one()
        roasted = next(f for f in recipe.fermentables if f.name == "Roasted Barley")
        assert roasted.color_srm == 500
        assert recipe.color_srm > 25

    @pytest.mark.asyncio
    async def test_ibu_untouched(self, test_db: AsyncSession):
        rid = await _stout(test_db, color_srm=3.5, roasted_color=550.0)
        await backfill_recipe_color_srm(test_db)
        recipe = (
            await test_db.execute(select(Recipe).where(Recipe.id == rid))
        ).scalar_one()
        assert recipe.ibu == 42.0  # backfill only touches color_srm

    @pytest.mark.asyncio
    async def test_already_correct_not_rewritten(self, test_db: AsyncSession):
        # color_srm already matches the grain bill -> no change on 2nd run.
        await _stout(test_db, color_srm=3.5, roasted_color=550.0)
        await backfill_recipe_color_srm(test_db)
        second = await backfill_recipe_color_srm(test_db)
        assert second == 0

    @pytest.mark.asyncio
    async def test_declared_higher_color_not_lowered(self, test_db: AsyncSession):
        # Brewer-declared color_srm (35) sits above the simplified grain-bill
        # calc (~29). The bug only understates SRM, so a higher stored value
        # must be left alone — never clobbered downward.
        rid = await _stout(test_db, color_srm=35.0, roasted_color=550.0)
        changed = await backfill_recipe_color_srm(test_db)
        recipe = (
            await test_db.execute(select(Recipe).where(Recipe.id == rid))
        ).scalar_one()
        assert recipe.color_srm == 35.0
        assert changed == 0

    @pytest.mark.asyncio
    async def test_recipe_without_fermentables_skipped(self, test_db: AsyncSession):
        r = Recipe(name="No Grain", type="extract", batch_size_liters=20,
                   color_srm=5.0)
        test_db.add(r)
        await test_db.commit()
        # Should not raise and should not touch the grain-less recipe.
        await backfill_recipe_color_srm(test_db)
        recipe = (
            await test_db.execute(select(Recipe).where(Recipe.id == r.id))
        ).scalar_one()
        assert recipe.color_srm == 5.0
