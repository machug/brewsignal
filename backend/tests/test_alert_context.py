"""Regression: get_alert_context loaded Recipe.yeast (removed), so alert detection always crashed."""

import pytest

from backend.services.alert_service import get_alert_context
from backend.models import Batch, Recipe, RecipeCulture


@pytest.mark.asyncio
async def test_alert_context_uses_recipe_culture_range(test_db):
    recipe = Recipe(name="APA", og=1.050, fg=1.010)
    recipe.cultures.append(RecipeCulture(name="US-05", temp_min_c=18.0, temp_max_c=22.0))
    test_db.add(recipe)
    await test_db.flush()
    batch = Batch(name="B", status="fermenting", recipe_id=recipe.id)
    test_db.add(batch)
    await test_db.commit()

    ctx = await get_alert_context(test_db, batch.id, 1.030)

    assert ctx["yeast_temp_min"] == 18.0 and ctx["yeast_temp_max"] == 22.0
    assert ctx["progress_percent"] == pytest.approx(50.0)


@pytest.mark.asyncio
async def test_alert_context_without_recipe(test_db):
    batch = Batch(name="C", status="fermenting")
    test_db.add(batch)
    await test_db.commit()
    ctx = await get_alert_context(test_db, batch.id, None)
    assert ctx["yeast_temp_min"] is None
