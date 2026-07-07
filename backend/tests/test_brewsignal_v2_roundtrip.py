"""Acceptance: Jasper v2 worked example round-trips losslessly (tilt_ui-0jkg).

Import the v2 doc -> ORM -> export a v2 doc; the richness v1 dropped
(water chemistry, hop technique extras, culture detail) must survive.
"""
import json
from pathlib import Path

import pytest

from backend.services.importers.recipe_importer import RecipeImporter
from backend.services.converters.brewsignal_v2 import RecipeToBrewSignalV2Converter

JASPER = Path(__file__).resolve().parents[2] / "docs" / "examples" / "jasper-clone.v2.brewsignal"


@pytest.mark.asyncio
async def test_jasper_v2_roundtrip(test_db):
    result = await RecipeImporter().import_recipe(JASPER.read_text(), None, test_db)
    assert result.success, result.errors
    recipe = result.recipe

    # -- import side: DB richness landed --
    assert recipe.name == "Jasper Clone (Fidens DIPA)"
    assert len(recipe.fermentables) == 3
    assert len(recipe.hops) == 3
    assert len(recipe.cultures) == 1
    culture = recipe.cultures[0]
    assert culture.product_id == "1318"
    assert culture.attenuation_min_percent == 73.0
    assert recipe.boil_size_l == 26.0

    profiles = {p.profile_type: p for p in recipe.water_profiles}
    assert profiles["target"].chloride_ppm == 125
    assert profiles["target"].sulfate_ppm == 75
    assert len(recipe.water_adjustments) == 1
    assert recipe.water_adjustments[0].stage == "mash"

    # hop technique extras preserved per-hop
    whirlpool_ext = (recipe.hops[1].format_extensions or {}).get("brewsignal") or {}
    assert whirlpool_ext.get("hop_use") == "whirlpool"

    # -- export side --
    doc = RecipeToBrewSignalV2Converter().convert(recipe)

    assert doc["brewsignal_version"] == "2.0"
    r = doc["recipe"]
    assert r["original_gravity"] == {"value": 1.067, "unit": "sg"}
    assert r["final_gravity"] == {"value": 1.018, "unit": "sg"}
    assert r["batch_size"] == {"value": 19.0, "unit": "l"}
    assert r["boil"]["pre_boil_size"] == {"value": 26.0, "unit": "l"}
    assert len(r["ingredients"]["fermentable_additions"]) == 3
    assert len(r["ingredients"]["hop_additions"]) == 3
    assert len(r["ingredients"]["culture_additions"]) == 1
    cult_out = r["ingredients"]["culture_additions"][0]
    assert cult_out["attenuation_range"]["minimum"] == {"value": 73.0, "unit": "%"}
    assert len(r["fermentation"]["fermentation_steps"]) == 4

    bs = doc["brewsignal"]
    target = next(p for p in bs["water"]["profiles"] if p["profile_type"] == "target")
    assert target["chloride_ppm"] == 125
    assert target["sulfate_ppm"] == 75
    assert bs["water"]["adjustments"][0]["stage"] == "mash"

    hop_ext = {h["index"]: h for h in bs["hop_additions"]}
    assert hop_ext[1]["hop_use"] == "whirlpool"
    assert hop_ext[1]["temperature"] == {"value": 79.0, "unit": "C"}
    assert hop_ext[2]["purpose"] == "biotransformation"

    # blocks without DB homes survive via format_extensions passthrough
    assert bs["process"]["lodo"] is True

    # exported doc is itself importable JSON (sanity)
    json.dumps(doc)
