"""Saved AI reviews: history, scores, fingerprint, full-recipe prompt (tilt_ui-de6v, de6v.1)."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.models import RecipeHop
from backend.services.recipe_reviews import parse_score
from backend.tests.test_recipe_review_tool import recipe_with_style, style_apa  # noqa: F401 (fixtures)

REVIEW = "### Style Fit Score: 8/10\nScore breakdown:\n- IBU low: -1\n\n### The Good Stuff\nNice."


def _service(text=REVIEW):
    svc = MagicMock()
    svc.chat = AsyncMock(return_value=text)
    svc.config.effective_model = "test-model"
    svc.config.is_configured.return_value = True
    return svc


def test_parse_score():
    assert parse_score(REVIEW) == 8
    assert parse_score("### Style Fit Score: **7.5/10**") == 7.5
    assert parse_score("no score here") is None
    assert parse_score("Style Fit Score: 42/10") is None


@pytest.mark.asyncio
async def test_review_is_saved_and_listed(client, test_db, recipe_with_style):  # noqa: F811
    svc = _service()
    with patch("backend.services.llm.tools.recipe.LLMService", return_value=svc):
        r = await client.post(f"/api/recipes/{recipe_with_style.id}/reviews")
    assert r.status_code == 200, r.text
    saved = r.json()
    assert saved["score"] == 8 and saved["review"] == REVIEW
    assert saved["stats_score"] is not None and saved["compliance"]["og"]["status"] == "in_range"

    # The judge got the full document, not the old grain/hop/yeast summaries
    prompt = str(svc.chat.call_args.kwargs.get("messages") or svc.chat.call_args.args[0])
    assert "batch_size" in prompt and "Centennial" in prompt
    assert svc.chat.call_args.kwargs.get("temperature") == 0

    history = (await client.get(f"/api/recipes/{recipe_with_style.id}/reviews")).json()
    assert [h["id"] for h in history["reviews"]] == [saved["id"]]
    assert history["current_fingerprint"] == saved["fingerprint"]  # unchanged recipe: not stale

    full = (await client.get(f"/api/recipes/{recipe_with_style.id}/reviews/{saved['id']}")).json()
    assert full["review"] == REVIEW


@pytest.mark.asyncio
async def test_changing_the_recipe_changes_the_fingerprint(client, test_db, recipe_with_style):  # noqa: F811
    rid = recipe_with_style.id
    with patch("backend.services.llm.tools.recipe.LLMService", return_value=_service()):
        saved = (await client.post(f"/api/recipes/{rid}/reviews")).json()
    test_db.add(RecipeHop(recipe_id=rid, name="Citra", amount_grams=50, alpha_acid_percent=12.0,
                          timing={"use": "add_to_fermentation", "duration": {"value": 3, "unit": "day"}}))
    await test_db.commit()
    test_db.expire_all()  # the test client shares this session; a real request loads fresh
    history = (await client.get(f"/api/recipes/{rid}/reviews")).json()
    assert history["current_fingerprint"] != saved["fingerprint"]


@pytest.mark.asyncio
async def test_missing_review_and_deleting_the_recipe(client, test_db, recipe_with_style):  # noqa: F811
    assert (await client.get(f"/api/recipes/{recipe_with_style.id}/reviews/999")).status_code == 404
    with patch("backend.services.llm.tools.recipe.LLMService", return_value=_service()):
        saved = (await client.post(f"/api/recipes/{recipe_with_style.id}/reviews")).json()
    assert (await client.delete(f"/api/recipes/{recipe_with_style.id}")).status_code == 200
    from sqlalchemy import select
    from backend.models import RecipeReview
    assert (await test_db.execute(select(RecipeReview).where(RecipeReview.id == saved["id"]))).first() is None
