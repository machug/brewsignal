"""Regression tests for recipe POST/PUT style resolution (tilt_ui-tre).

The edit form previously sent free-text "American IPA" into recipes.type and
never set style_id, so get_recipe (and any consumer that joins via the FK)
saw style=null. These tests pin the new resolver behavior: free-text "style"
on RecipeCreate/RecipeUpdate is resolved to a styles.id FK via
_resolve_style_id, mirroring the LLM save_recipe path. Explicit style_id
from the payload wins; the resolver only kicks in when style_id wasn't sent.
"""
import pytest
from httpx import AsyncClient, ASGITransport

from backend.main import app
from backend.database import init_db


@pytest.fixture(scope="module", autouse=True)
async def setup_db():
    await init_db()


async def _client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_post_recipe_resolves_free_text_style_to_bjcp_id():
    """POST /recipes with style='American IPA' sets style_id=bjcp-2021-21a."""
    async with await _client() as client:
        r = await client.post(
            "/api/recipes",
            json={"name": "Style Resolver Create Test", "style": "American IPA"},
        )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["style_id"] == "bjcp-2021-21a"
    assert body["style"]["name"] == "American IPA"


@pytest.mark.asyncio
async def test_put_recipe_resolves_free_text_style_to_bjcp_id():
    """PUT /recipes/{id} with style='American IPA' sets style_id=bjcp-2021-21a."""
    async with await _client() as client:
        created = await client.post(
            "/api/recipes",
            json={"name": "Style Resolver Update Test"},
        )
        assert created.status_code == 201
        rid = created.json()["id"]
        assert created.json()["style_id"] is None

        updated = await client.put(
            f"/api/recipes/{rid}",
            json={"style": "American IPA"},
        )
    assert updated.status_code == 200, updated.text
    body = updated.json()
    assert body["style_id"] == "bjcp-2021-21a"
    assert body["style"]["name"] == "American IPA"


@pytest.mark.asyncio
async def test_put_recipe_explicit_style_id_wins_over_free_text():
    """If client sends both style_id and style, style_id is authoritative."""
    async with await _client() as client:
        created = await client.post(
            "/api/recipes",
            json={"name": "Style Conflict Test"},
        )
        rid = created.json()["id"]

        # style="American IPA" would resolve to 21a; style_id explicitly says 1a.
        updated = await client.put(
            f"/api/recipes/{rid}",
            json={"style_id": "bjcp-2021-1a", "style": "American IPA"},
        )
    assert updated.status_code == 200, updated.text
    assert updated.json()["style_id"] == "bjcp-2021-1a"


@pytest.mark.asyncio
async def test_put_recipe_null_style_id_with_free_text_resolves():
    """Typed-into-autocomplete-without-selecting case.

    RecipeBuilder emits style_id=null + style="American IPA" when the user
    typed the name but never clicked an option in the dropdown. The
    resolver must still kick in — null style_id alone is NOT a hard
    "explicit clear" when accompanied by a non-empty style text.
    """
    async with await _client() as client:
        created = await client.post(
            "/api/recipes",
            json={"name": "Typed Without Selecting Test"},
        )
        rid = created.json()["id"]
        assert created.json()["style_id"] is None

        updated = await client.put(
            f"/api/recipes/{rid}",
            json={"style_id": None, "style": "American IPA"},
        )
    assert updated.status_code == 200
    assert updated.json()["style_id"] == "bjcp-2021-21a"


@pytest.mark.asyncio
async def test_put_recipe_explicit_null_style_id_clears_fk():
    """User clearing the style picker sends style_id=null; FK must clear.

    Regression: pages used to collapse null to undefined, dropping the
    clear path silently.
    """
    async with await _client() as client:
        created = await client.post(
            "/api/recipes",
            json={"name": "Style Clear Test", "style": "American IPA"},
        )
        rid = created.json()["id"]
        assert created.json()["style_id"] == "bjcp-2021-21a"

        updated = await client.put(
            f"/api/recipes/{rid}",
            json={"style_id": None},
        )
    assert updated.status_code == 200
    assert updated.json()["style_id"] is None
    assert updated.json()["style"] is None


@pytest.mark.asyncio
async def test_put_recipe_unknown_style_clears_style_id():
    """PUT with style='Nonsense Brew' leaves style_id NULL (not crash)."""
    async with await _client() as client:
        created = await client.post(
            "/api/recipes",
            json={"name": "Style Unknown Test", "style": "American IPA"},
        )
        rid = created.json()["id"]
        assert created.json()["style_id"] == "bjcp-2021-21a"

        updated = await client.put(
            f"/api/recipes/{rid}",
            json={"style": "Definitely Not A Real Style"},
        )
    assert updated.status_code == 200
    assert updated.json()["style_id"] is None
