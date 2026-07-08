"""DB -> BrewSignal v2 exporter (tilt_ui-0jkg). In-memory ORM, no DB."""
import pytest

from backend.models import (
    Recipe, RecipeCulture, RecipeFermentable, RecipeFermentationStep,
    RecipeHop, RecipeMashStep, RecipeMisc, RecipeWaterAdjustment,
    RecipeWaterProfile,
)
from backend.services.converters.brewsignal_v2 import (
    RecipeToBrewSignalV2Converter, to_strict_beerjson,
)


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
        timing={"use": "add_to_mash"},
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
        timing={"use": "add_to_fermentation"},
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
    # timing is a lossless-export column (RecipeCulture.timing); must survive
    assert c0["timing"] == {"use": "add_to_fermentation"}


def test_fermentable_timing_survives_export():
    r = RecipeToBrewSignalV2Converter().convert(_full_recipe())["recipe"]
    ferm = r["ingredients"]["fermentable_additions"][0]
    assert ferm["timing"] == {"use": "add_to_mash"}


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


def test_style_id_column_wins_over_stale_extension_copy():
    """A real style_id FK must not be clobbered by a stale copy left over
    in format_extensions['brewsignal']['style_id'] (e.g. from an earlier
    export captured before the style was changed)."""
    recipe = Recipe(
        name="Restyled", og=1.050, fg=1.010, style_id="real-id",
        format_extensions={"brewsignal": {"style_id": "stale-id"}},
    )
    bs = RecipeToBrewSignalV2Converter().convert(recipe)["brewsignal"]
    assert bs["style_id"] == "real-id"


def test_style_id_extension_fallback_when_no_fk():
    """When there's no style_id FK, the leftover extension copy is still
    used as a fallback (existing behavior, must not regress)."""
    recipe = Recipe(
        name="No FK", og=1.050, fg=1.010,
        format_extensions={"brewsignal": {"style_id": "legacy-id"}},
    )
    bs = RecipeToBrewSignalV2Converter().convert(recipe)["brewsignal"]
    assert bs["style_id"] == "legacy-id"


class TestToStrictBeerJSON:
    """Unit tests for the /export/beerjson post-processor (Finding 1)."""

    def _minimal_recipe_block(self) -> dict:
        return {
            "name": "Minimal", "type": "extract", "author": "A",
            "ingredients": {
                "fermentable_additions": [{
                    "name": "Mystery Grain", "type": "grain",
                    "amount": {"value": 1.0, "unit": "kg"},
                    "color": {"value": 2.0, "unit": "SRM"},
                }],
                "hop_additions": [{
                    "name": "Mystery Extract", "form": "extract",
                    "amount": {"value": 10.0, "unit": "g"},
                    "timing": {"use": "add_to_boil"},
                    "is_extract": True, "amount_ml": 5.0,
                }],
                "culture_additions": [{
                    "name": "House Culture", "type": "ale", "form": "dry",
                }],
            },
            "mash": {
                "name": "Mash",
                "mash_steps": [{
                    "name": "Sacch", "type": "infusion",
                    "step_temperature": {"value": 68.0, "unit": "C"},
                    "step_time": {"value": 60, "unit": "min"},
                }],
            },
            "fermentation": {
                "name": "Fermentation",
                "fermentation_steps": [{
                    "name": "Primary", "step_type": "primary",
                    "step_temperature": {"value": 20.0, "unit": "C"},
                    "step_time": {"value": 6, "unit": "day"},
                }],
            },
        }

    def test_fermentation_step_renamed_and_step_type_dropped(self):
        strict = to_strict_beerjson(self._minimal_recipe_block())
        step = strict["fermentation"]["fermentation_steps"][0]
        assert "step_type" not in step
        assert "step_temperature" not in step
        assert step["start_temperature"] == {"value": 20.0, "unit": "C"}

    def test_hop_extract_keys_dropped_and_alpha_acid_placeholder(self):
        strict = to_strict_beerjson(self._minimal_recipe_block())
        hop = strict["ingredients"]["hop_additions"][0]
        assert "is_extract" not in hop
        assert "amount_ml" not in hop
        assert hop["alpha_acid"] == {"value": 0, "unit": "%"}

    def test_hop_alpha_acid_untouched_when_present(self):
        block = self._minimal_recipe_block()
        block["ingredients"]["hop_additions"][0]["alpha_acid"] = {
            "value": 11.0, "unit": "%",
        }
        strict = to_strict_beerjson(block)
        assert strict["ingredients"]["hop_additions"][0]["alpha_acid"] == {
            "value": 11.0, "unit": "%",
        }

    def test_culture_amount_placeholder_when_missing(self):
        strict = to_strict_beerjson(self._minimal_recipe_block())
        culture = strict["ingredients"]["culture_additions"][0]
        assert culture["amount"] == {"value": 1, "unit": "1"}

    def test_culture_amount_untouched_when_present(self):
        block = self._minimal_recipe_block()
        block["ingredients"]["culture_additions"][0]["amount"] = {
            "value": 2.0, "unit": "pkg",
        }
        strict = to_strict_beerjson(block)
        assert strict["ingredients"]["culture_additions"][0]["amount"] == {
            "value": 2.0, "unit": "pkg",
        }

    def test_fermentable_yield_placeholder_when_missing(self):
        strict = to_strict_beerjson(self._minimal_recipe_block())
        ferm = strict["ingredients"]["fermentable_additions"][0]
        assert ferm["yield"] == {"fine_grind": {"value": 0, "unit": "%"}}

    def test_fermentable_yield_untouched_when_present(self):
        block = self._minimal_recipe_block()
        block["ingredients"]["fermentable_additions"][0]["yield"] = {
            "fine_grind": {"value": 80.0, "unit": "%"},
        }
        strict = to_strict_beerjson(block)
        assert strict["ingredients"]["fermentable_additions"][0]["yield"] == {
            "fine_grind": {"value": 80.0, "unit": "%"},
        }

    def test_mash_grain_temperature_placeholder_when_missing(self):
        strict = to_strict_beerjson(self._minimal_recipe_block())
        assert strict["mash"]["grain_temperature"] == {"value": 20, "unit": "C"}

    def test_mash_grain_temperature_untouched_when_present(self):
        block = self._minimal_recipe_block()
        block["mash"]["grain_temperature"] = {"value": 22.0, "unit": "C"}
        strict = to_strict_beerjson(block)
        assert strict["mash"]["grain_temperature"] == {"value": 22.0, "unit": "C"}

    def test_incomplete_style_block_dropped(self):
        block = self._minimal_recipe_block()
        block["style"] = {"name": "Hazy IPA"}  # missing category/style_guide/type
        strict = to_strict_beerjson(block)
        assert "style" not in strict

    def test_complete_style_block_kept(self):
        block = self._minimal_recipe_block()
        block["style"] = {
            "name": "Hazy IPA", "category": "IPA", "style_guide": "BJCP 2021",
            "type": "beer",
        }
        strict = to_strict_beerjson(block)
        assert strict["style"] == block["style"]

    def test_notes_included_when_provided(self):
        strict = to_strict_beerjson(self._minimal_recipe_block(), notes="Tasting notes")
        assert strict["notes"] == "Tasting notes"

    def test_notes_omitted_when_none(self):
        strict = to_strict_beerjson(self._minimal_recipe_block(), notes=None)
        assert "notes" not in strict

    def test_original_recipe_block_not_mutated(self):
        block = self._minimal_recipe_block()
        block["style"] = {"name": "Hazy IPA"}
        to_strict_beerjson(block, notes="Should not leak into original")
        hop = block["ingredients"]["hop_additions"][0]
        ferm = block["ingredients"]["fermentable_additions"][0]
        step = block["fermentation"]["fermentation_steps"][0]
        assert hop["is_extract"] is True
        assert hop["amount_ml"] == 5.0
        assert "alpha_acid" not in hop
        assert "yield" not in ferm
        assert "step_temperature" in step
        assert "step_type" in step
        assert "grain_temperature" not in block["mash"]
        assert block["style"] == {"name": "Hazy IPA"}
        assert "notes" not in block
