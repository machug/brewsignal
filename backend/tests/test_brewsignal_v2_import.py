"""v2 documents import through the BeerJSON serializer + extension applier."""
from pathlib import Path

import pytest

from backend.services.importers.recipe_importer import RecipeImporter

JASPER = Path(__file__).resolve().parents[2] / "docs" / "examples" / "jasper-clone.v2.brewsignal"


@pytest.mark.asyncio
async def test_jasper_v2_imports(test_db):
    result = await RecipeImporter().import_recipe(JASPER.read_text(), None, test_db)
    assert result.success, result.errors
    assert result.format == "brewsignal"
    recipe = result.recipe

    assert recipe.og == 1.067
    assert recipe.abv == 6.5
    assert recipe.batch_size_liters == 19.0
    assert recipe.boil_size_l == 26.0          # pre_boil_size fallback
    assert recipe.efficiency_percent == 72.0

    assert len(recipe.hops) == 3
    assert recipe.hops[2].timing["use"] == "add_to_fermentation"

    culture = recipe.cultures[0]
    assert culture.name == "London Ale III"
    assert culture.attenuation_min_percent == 73.0   # flat PercentType fallback
    assert culture.attenuation_max_percent == 73.0
    # legacy top-level mirror must also pick up the flat PercentType shape
    # (Jasper's first culture uses attenuation: {value: 73.0}, not a range)
    assert recipe.yeast_attenuation == 73.0

    profiles = {p.profile_type: p for p in recipe.water_profiles}
    assert profiles["target"].chloride_ppm == 125
    assert len(recipe.water_adjustments) == 1

    hop_ext = (recipe.hops[1].format_extensions or {}).get("brewsignal") or {}
    assert hop_ext.get("hop_use") == "whirlpool"

    # envelope notes carried onto the recipe
    assert "Jasper" in (recipe.notes or "")

    # non-column brewsignal blocks preserved
    assert recipe.format_extensions["brewsignal"]["process"]["lodo"] is True


@pytest.mark.asyncio
async def test_v1_brewsignal_import_still_works(test_db):
    """The v1 path must be untouched by v2 routing."""
    import json
    v1 = {
        "_format": "brewsignal",
        "name": "V1 Pale", "og": 1.050, "fg": 1.010,
        "batch_size_liters": 20.0,
        "fermentables": [{"name": "Pale Malt", "type": "grain",
                          "amount_kg": 4.0, "yield_percent": 80}],
        "yeast": {"name": "US-05", "type": "ale", "form": "dry"},
    }
    result = await RecipeImporter().import_recipe(json.dumps(v1), None, test_db)
    assert result.success, result.errors
    assert result.recipe.name == "V1 Pale"


@pytest.mark.asyncio
async def test_minimal_v2_doc_without_brewsignal_block_exports_after_import(test_db):
    """A v2 doc with no brewsignal block must import AND export without the
    unloaded-collection guard false-positiving on legitimately empty collections."""
    import json
    from backend.services.converters.brewsignal_v2 import RecipeToBrewSignalV2Converter

    doc = {
        "brewsignal_version": "2.0",
        "recipe": {
            "name": "Bare v2",
            "type": "all grain",
            "original_gravity": {"value": 1.050, "unit": "sg"},
            "final_gravity": {"value": 1.010, "unit": "sg"},
        },
    }
    result = await RecipeImporter().import_recipe(json.dumps(doc), None, test_db)
    assert result.success, result.errors
    out = RecipeToBrewSignalV2Converter().convert(result.recipe)
    assert out["recipe"]["name"] == "Bare v2"
