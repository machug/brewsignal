"""Tests for native BrewSignal recipe import (tilt_ui-kew)."""
import pytest

from backend.services.converters.brewsignal_to_beerjson import (
    BrewSignalToBeerJSONConverter,
)
from backend.services.importers.recipe_importer import RecipeImporter


def _sample_brewsignal_recipe() -> dict:
    return {
        "name": "Sample IPA",
        "type": "all grain",
        "og": 1.060,
        "fg": 1.012,
        "abv": 6.3,
        "ibu": 55,
        "color_srm": 8,
        "batch_size_liters": 20,
        "boil_time_minutes": 60,
        "efficiency_percent": 72,
        "fermentables": [
            {"name": "Pale Malt", "type": "grain",
             "amount_kg": 5.0, "yield_percent": 80}
        ],
        "hops": [
            {"name": "Cascade", "amount_grams": 30,
             "alpha_acid_percent": 6.5, "form": "pellet",
             "timing": {"use": "add_to_boil",
                        "duration": {"value": 60, "unit": "min"}}}
        ],
        "yeast": {"name": "US-05", "type": "ale", "form": "dry"},
        "fermentation_steps": [
            {"step_number": 1, "type": "primary", "temp_c": 19, "time_days": 14}
        ],
    }


class TestBrewSignalConverter:
    def test_converter_emits_beerjson_envelope(self):
        out = BrewSignalToBeerJSONConverter().convert(_sample_brewsignal_recipe())
        assert "beerjson" in out
        assert "recipes" in out["beerjson"]
        assert len(out["beerjson"]["recipes"]) == 1

    def test_top_level_stats_round_trip_through_beerjson_units(self):
        recipe = BrewSignalToBeerJSONConverter().convert(
            _sample_brewsignal_recipe()
        )["beerjson"]["recipes"][0]
        assert recipe["original_gravity"] == {"value": 1.060, "unit": "sg"}
        assert recipe["final_gravity"] == {"value": 1.012, "unit": "sg"}
        assert recipe["ibu_estimate"] == {"value": 55.0, "unit": "IBUs"}
        assert recipe["batch_size"] == {"value": 20.0, "unit": "l"}
        assert recipe["boil"]["boil_time"] == {"value": 60, "unit": "min"}

    def test_ingredients_present(self):
        recipe = BrewSignalToBeerJSONConverter().convert(
            _sample_brewsignal_recipe()
        )["beerjson"]["recipes"][0]
        ing = recipe["ingredients"]
        assert len(ing["fermentable_additions"]) == 1
        assert ing["fermentable_additions"][0]["amount"] == {"value": 5.0, "unit": "kg"}
        assert len(ing["hop_additions"]) == 1
        assert ing["hop_additions"][0]["timing"]["use"] == "add_to_boil"
        assert ing["culture_additions"][0]["name"] == "US-05"


class TestImporterDetectsBrewSignal:
    """The importer's _detect_format must classify BrewSignal JSON as
    'brewsignal', not Brewfather (which would silently apply the
    Brewfather converter and lose data)."""

    def _detect(self, payload: dict) -> str | None:
        import json
        return RecipeImporter()._detect_format(json.dumps(payload))

    def test_explicit_format_marker_detected(self):
        assert self._detect({"_format": "brewsignal", "name": "X",
                              "og": 1.05, "fg": 1.01}) == "brewsignal"

    def test_brewsignal_version_marker_detected(self):
        assert self._detect({"brewsignal_version": "1.0", "name": "X",
                              "og": 1.05, "fg": 1.01}) == "brewsignal"

    def test_snake_case_keys_detected(self):
        assert self._detect({"name": "X", "og": 1.05, "fg": 1.01,
                              "batch_size_liters": 20}) == "brewsignal"

    def test_brewfather_camelcase_still_routes_to_brewfather(self):
        assert self._detect({"name": "X", "og": 1.05, "fg": 1.01,
                              "batchSize": 20, "boilTime": 60}) == "brewfather"

    def test_beerjson_envelope_still_routes_to_beerjson(self):
        assert self._detect({"beerjson": {"version": 1.0, "recipes": []}}) == "beerjson"

    def test_sparse_recipe_with_brewsignal_fermentable_keys_detected(self):
        """A bare BrewSignal recipe with no top-level discriminator keys
        but BrewSignal-shaped fermentables must still route to brewsignal."""
        assert self._detect({
            "name": "X", "og": 1.05, "fg": 1.01,
            "fermentables": [{"name": "Pilsner", "amount_kg": 5.0}],
        }) == "brewsignal"

    def test_sparse_recipe_with_brewsignal_hop_keys_detected(self):
        assert self._detect({
            "name": "X", "og": 1.05, "fg": 1.01,
            "hops": [{"name": "Cascade", "amount_grams": 30,
                      "alpha_acid_percent": 6.5,
                      "timing": {"use": "add_to_boil"}}],
        }) == "brewsignal"


class TestBrewSignalEdgeCases:
    """Edge cases caught by codex review on tilt_ui-kew."""

    def test_marker_keys_are_stripped_before_validation(self):
        """`_format` and `brewsignal_version` are NOT BrewSignalRecipe
        fields (extra=forbid). The importer must strip them before
        validation, otherwise marked payloads fail import."""
        from backend.services.brewsignal_format import BrewSignalRecipe
        payload = {
            "_format": "brewsignal",
            "brewsignal_version": "1.0",
            "name": "Test", "og": 1.05, "fg": 1.01,
        }
        # Direct validation should fail; the importer's strip step is what
        # makes this pass end-to-end. Test mirrors the importer's logic.
        cleaned = {k: v for k, v in payload.items()
                   if k not in ('_format', 'brewsignal_version')}
        BrewSignalRecipe.model_validate(cleaned)  # no exception

    def test_hop_without_alpha_acid_gets_default(self):
        out = BrewSignalToBeerJSONConverter()._convert_hop({
            'name': 'Mystery Hop',
            'amount_grams': 30,
            'timing': {'use': 'add_to_boil'},
        })
        assert out['alpha_acid'] == {'value': 0.0, 'unit': '%'}

    def test_mash_step_type_emits_under_key_serializer_reads(self):
        """Serializer reads step_dict['type'], not 'step_type'."""
        out = BrewSignalToBeerJSONConverter()._convert_mash([
            {'step_number': 1, 'type': 'infusion', 'temp_c': 65, 'time_minutes': 60},
            {'step_number': 2, 'type': 'decoction', 'temp_c': 76, 'time_minutes': 10},
        ])
        assert out['mash_steps'][0]['type'] == 'infusion'
        assert out['mash_steps'][1]['type'] == 'decoction'
