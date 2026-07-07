"""DB -> BrewSignal v2 exporter (tilt_ui-0jkg). In-memory ORM, no DB."""
import pytest

from backend.models import (
    Recipe, RecipeCulture, RecipeFermentable, RecipeFermentationStep,
    RecipeHop, RecipeMashStep, RecipeMisc, RecipeWaterAdjustment,
    RecipeWaterProfile,
)
from backend.services.converters.brewsignal_v2 import RecipeToBrewSignalV2Converter


def _full_recipe() -> Recipe:
    recipe = Recipe(
        name="Test DIPA", type="all grain", author="Hugh",
        batch_size_liters=19.0, boil_time_minutes=60, boil_size_l=26.0,
        efficiency_percent=72.0, og=1.067, fg=1.018, abv=6.5, ibu=53.0,
        color_srm=4.5, carbonation_vols=2.4, notes="envelope notes",
    )
    recipe.fermentables.append(RecipeFermentable(
        name="2-Row", type="grain", grain_group="base", amount_kg=4.66,
        color_srm=1.8, origin="United States", supplier="Rahr",
        yield_percent=80.0,
    ))
    recipe.hops.append(RecipeHop(
        name="Citra", origin="United States", form="pellet",
        alpha_acid_percent=11.0, amount_grams=162.0,
        timing={"use": "add_to_boil", "duration": {"value": 20, "unit": "min"}},
        format_extensions={"brewsignal": {
            "hop_use": "whirlpool", "purpose": "aroma",
            "temperature": {"value": 79.0, "unit": "C"},
        }},
    ))
    recipe.hops.append(RecipeHop(
        name="Incognito Citra", form="extract", amount_grams=0.0,
        amount_ml=50.0, is_extract=True,
        timing={"use": "add_to_boil", "duration": {"value": 0, "unit": "min"}},
    ))
    recipe.cultures.append(RecipeCulture(
        name="London Ale III", type="ale", form="liquid", producer="Wyeast",
        product_id="1318", temp_min_c=18.0, temp_max_c=23.0,
        attenuation_min_percent=73.0, attenuation_max_percent=75.0,
        amount=1.0, amount_unit="1",
    ))
    recipe.cultures.append(RecipeCulture(name="CBC-1", type="ale", form="dry"))
    recipe.miscs.append(RecipeMisc(
        name="Yeast Nutrient", type="other", use="boil",
        amount_kg=5.0, amount_unit="g",
        timing={"use": "add_to_boil", "duration": {"value": 10, "unit": "min"}},
    ))
    recipe.mash_steps.append(RecipeMashStep(
        step_number=1, name="Sacch", type="infusion", temp_c=68.0,
        time_minutes=60,
    ))
    recipe.fermentation_steps.append(RecipeFermentationStep(
        step_number=1, type="primary", temp_c=20.0, time_days=6,
    ))
    recipe.water_profiles.append(RecipeWaterProfile(
        profile_type="target", name="Hazy build", chloride_ppm=125.0,
        sulfate_ppm=75.0, format_extensions={"sulfate_chloride_ratio": 0.6},
    ))
    recipe.water_adjustments.append(RecipeWaterAdjustment(
        stage="mash", volume_liters=18.0, calcium_chloride_g=3.2,
        acid_type="lactic", acid_ml=2.0, acid_concentration_percent=88.0,
    ))
    recipe.format_extensions = {"brewsignal": {
        "process": {"lodo": True},
        "water": {"mash_ph_target": 5.2},
    }}
    return recipe


def test_envelope_and_vitals():
    doc = RecipeToBrewSignalV2Converter().convert(_full_recipe())
    assert doc["brewsignal_version"] == "2.0"
    assert doc["based_on"] == {"standard": "BeerJSON", "version": "1.0"}
    assert doc["notes"] == "envelope notes"
    r = doc["recipe"]
    assert r["name"] == "Test DIPA"
    assert r["original_gravity"] == {"value": 1.067, "unit": "sg"}
    assert r["alcohol_by_volume"] == {"value": 6.5, "unit": "%"}
    assert r["ibu_estimate"] == {"value": 53.0, "unit": "IBUs"}
    assert r["color_estimate"] == {"value": 4.5, "unit": "SRM"}
    assert r["batch_size"] == {"value": 19.0, "unit": "l"}
    assert r["boil"]["boil_time"] == {"value": 60, "unit": "min"}
    assert r["boil"]["pre_boil_size"] == {"value": 26.0, "unit": "l"}
    assert r["efficiency"]["brewhouse"] == {"value": 72.0, "unit": "%"}
    assert r["carbonation"] == 2.4


def test_all_cultures_exported_not_just_first():
    r = RecipeToBrewSignalV2Converter().convert(_full_recipe())["recipe"]
    cultures = r["ingredients"]["culture_additions"]
    assert len(cultures) == 2
    c0 = cultures[0]
    assert c0["product_id"] == "1318"
    assert c0["attenuation_range"]["minimum"] == {"value": 73.0, "unit": "%"}
    assert c0["attenuation_range"]["maximum"] == {"value": 75.0, "unit": "%"}
    assert c0["temperature_range"]["minimum"] == {"value": 18.0, "unit": "C"}
    assert c0["amount"] == {"value": 1.0, "unit": "1"}


def test_extract_hops_keep_ml_dosage():
    r = RecipeToBrewSignalV2Converter().convert(_full_recipe())["recipe"]
    extract = r["ingredients"]["hop_additions"][1]
    assert extract["is_extract"] is True
    assert extract["amount_ml"] == 50.0
    # non-extract hop has no alpha requirement bypass
    assert r["ingredients"]["hop_additions"][0]["alpha_acid"] == {"value": 11.0, "unit": "%"}


def test_brewsignal_block_water_and_hops_and_passthrough():
    bs = RecipeToBrewSignalV2Converter().convert(_full_recipe())["brewsignal"]
    profile = bs["water"]["profiles"][0]
    assert profile["profile_type"] == "target"
    assert profile["chloride_ppm"] == 125.0
    assert profile["sulfate_chloride_ratio"] == 0.6   # extras merged back
    adj = bs["water"]["adjustments"][0]
    assert adj["stage"] == "mash"
    assert adj["salts"]["calcium_chloride_g"] == 3.2
    assert adj["acid"] == {"type": "lactic", "ml": 2.0, "concentration_percent": 88.0}
    # water leftovers merged back into the water object
    assert bs["water"]["mash_ph_target"] == 5.2
    # per-hop extras with index alignment + name echo
    entry = bs["hop_additions"][0]
    assert entry["index"] == 0
    assert entry["name"] == "Citra"
    assert entry["hop_use"] == "whirlpool"
    # unhandled blocks pass through
    assert bs["process"]["lodo"] is True


def test_minimal_recipe_omits_empty_blocks():
    doc = RecipeToBrewSignalV2Converter().convert(Recipe(name="Bare", og=1.050, fg=1.010))
    assert doc["recipe"]["name"] == "Bare"
    assert "brewsignal" not in doc
    assert "ingredients" not in doc["recipe"] or doc["recipe"]["ingredients"]


@pytest.mark.asyncio
async def test_persistent_recipe_with_unloaded_collections_fails_loud(test_db):
    """A persisted recipe exported without eager loading must raise, not
    silently truncate (lossless-export contract)."""
    from backend.models import Recipe
    from sqlalchemy import select

    recipe = Recipe(name="Persisted", og=1.050, fg=1.010)
    test_db.add(recipe)
    await test_db.commit()
    recipe_id = recipe.id
    test_db.expire_all()
    result = await test_db.execute(select(Recipe).where(Recipe.id == recipe_id))
    fresh = result.scalar_one()

    with pytest.raises(RuntimeError, match="selectinload"):
        RecipeToBrewSignalV2Converter().convert(fresh)
