"""Export endpoints for BrewSignal v2 and BeerJSON (tilt_ui-0jkg)."""
import json
from pathlib import Path

import pytest

from backend.routers.recipes import _safe_filename
from backend.services.importers.recipe_importer import RecipeImporter
from backend.services.validators.beerjson_validator import BeerJSONValidator

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
async def test_export_beerjson_is_schema_strict_and_reimportable(client, test_db):
    """Finding 1 (critical): /export/beerjson must emit strict BeerJSON 1.0
    that the project's own validator accepts, and that re-imports cleanly —
    otherwise it's a lossy export other BeerJSON tools (and BrewSignal
    itself) reject. Jasper exercises fermentation-step renames (4 steps,
    each carrying serializer-dialect step_temperature/step_type) and
    envelope notes; its hop bill has no extract hops, so the alpha_acid
    placeholder path is covered separately in test_brewsignal_v2_export.py.
    """
    recipe_id = await _import_jasper(test_db)
    resp = await client.get(f"/api/recipes/{recipe_id}/export/beerjson")
    assert resp.status_code == 200
    body = resp.json()

    is_valid, errors = BeerJSONValidator().validate(body)
    assert is_valid, errors

    recipe = body["beerjson"]["recipes"][0]
    assert recipe.get("notes")
    for step in recipe["fermentation"]["fermentation_steps"]:
        assert "step_temperature" not in step
        assert "step_type" not in step
        assert "start_temperature" in step

    reimport = await RecipeImporter().import_recipe(json.dumps(body), None, test_db)
    assert reimport.success, reimport.errors


@pytest.mark.asyncio
async def test_export_404_for_missing_recipe(client, test_db):
    resp = await client.get("/api/recipes/999999/export/brewsignal")
    assert resp.status_code == 404


class TestSafeFilename:
    """Finding 5: Content-Disposition filenames must be ASCII-safe so a
    malicious/unicode recipe name can't break the header or 500 the
    endpoint."""

    def test_quotes_and_hash_sanitized(self):
        assert _safe_filename('IPA "hazy" #1') == "IPA_hazy_1"

    def test_emoji_and_non_latin1_sanitized(self):
        result = _safe_filename("🍺 Bière")
        result.encode("latin-1")  # must not raise
        assert result == "Bi_re"

    def test_all_unsafe_chars_falls_back_to_recipe(self):
        assert _safe_filename("🍺🍺🍺") == "recipe"

    def test_empty_string_falls_back_to_recipe(self):
        assert _safe_filename("") == "recipe"

    def test_normal_name_untouched(self):
        assert _safe_filename("Jasper_Clone.json") == "Jasper_Clone.json"


@pytest.mark.asyncio
async def test_export_download_header_survives_unsafe_recipe_name(client, test_db):
    """End-to-end: a recipe renamed to contain quote + emoji characters must
    not break the Content-Disposition header or 500 the download."""
    recipe_id = await _import_jasper(test_db)
    resp = await client.put(
        f"/api/recipes/{recipe_id}",
        json={"name": 'IPA "hazy" 🍺 #1'},
    )
    assert resp.status_code == 200

    resp = await client.get(
        f"/api/recipes/{recipe_id}/export/brewsignal?download=true"
    )
    assert resp.status_code == 200
    disposition = resp.headers["content-disposition"]
    # header must be encodable as a real HTTP header (latin-1) with no raw
    # quote/emoji from the recipe name leaking into the filename
    disposition.encode("latin-1")
    assert "🍺" not in disposition
    filename = disposition.split("filename=", 1)[1].strip('"')
    assert '"' not in filename
