"""Export endpoints for BrewSignal v2 and BeerJSON (tilt_ui-0jkg)."""
from pathlib import Path

import pytest

from backend.services.importers.recipe_importer import RecipeImporter

JASPER = Path(__file__).resolve().parents[2] / "docs" / "examples" / "jasper-clone.v2.brewsignal"


async def _import_jasper(test_db) -> int:
    result = await RecipeImporter().import_recipe(JASPER.read_text(), None, test_db)
    assert result.success, result.errors
    await test_db.commit()
    return result.recipe.id


@pytest.mark.asyncio
async def test_export_brewsignal_v2(client, test_db):
    recipe_id = await _import_jasper(test_db)
    resp = await client.get(f"/api/recipes/{recipe_id}/export/brewsignal")
    assert resp.status_code == 200
    doc = resp.json()
    assert doc["brewsignal_version"] == "2.0"
    assert doc["recipe"]["name"] == "Jasper Clone (Fidens DIPA)"
    assert doc["brewsignal"]["water"]["profiles"]


@pytest.mark.asyncio
async def test_export_brewsignal_download_header(client, test_db):
    recipe_id = await _import_jasper(test_db)
    resp = await client.get(
        f"/api/recipes/{recipe_id}/export/brewsignal?download=true"
    )
    assert resp.status_code == 200
    assert ".brewsignal" in resp.headers["content-disposition"]


@pytest.mark.asyncio
async def test_export_beerjson(client, test_db):
    recipe_id = await _import_jasper(test_db)
    resp = await client.get(f"/api/recipes/{recipe_id}/export/beerjson")
    assert resp.status_code == 200
    doc = resp.json()
    assert doc["beerjson"]["version"] == 1.0
    recipe = doc["beerjson"]["recipes"][0]
    assert recipe["name"] == "Jasper Clone (Fidens DIPA)"
    # vanilla BeerJSON: no brewsignal namespace at the envelope
    assert "brewsignal" not in doc


@pytest.mark.asyncio
async def test_export_404_for_missing_recipe(client, test_db):
    resp = await client.get("/api/recipes/999999/export/brewsignal")
    assert resp.status_code == 404
