"""Fermentation step type inference (tilt_ui-psa).

Recipe 21 in production has every fermentation step stored as 'primary'
because the inference only recognized primary/secondary/conditioning.
Diacetyl rests and cold crashes were silently flattened, losing the
process intent that the fermentation phase UI and temp control rely on.
"""

import pytest

from backend.services.serializers.recipe_serializer import RecipeSerializer


@pytest.fixture
def serializer() -> RecipeSerializer:
    return RecipeSerializer()


@pytest.mark.parametrize(
    "name,expected",
    [
        ("Primary Fermentation", "primary"),
        ("primary", "primary"),
        ("Secondary", "secondary"),
        ("Conditioning", "conditioning"),
        ("Bottle Conditioning", "conditioning"),
        ("Keg Conditioning", "conditioning"),
        ("Diacetyl Rest", "diacetyl_rest"),
        ("D-Rest", "diacetyl_rest"),
        ("D Rest", "diacetyl_rest"),
        ("diacetyl rest", "diacetyl_rest"),
        ("Cold Crash", "cold_crash"),
        ("Crash", "cold_crash"),
        ("cold crash to 2C", "cold_crash"),
        ("", "primary"),
        ("Some unknown step", "primary"),
    ],
)
def test_infer_fermentation_type(serializer, name, expected):
    assert serializer._infer_fermentation_type({"name": name}) == expected


def test_diacetyl_rest_not_misclassified_as_primary(serializer):
    """Names containing 'rest' but not 'd-rest' should not be diacetyl."""
    # "rest" alone should not match diacetyl. Only diacetyl/d-rest/d rest.
    assert serializer._infer_fermentation_type({"name": "Rest period"}) == "primary"


class TestExplicitStepType:
    """tilt_ui-4bwa item 9: v2 export emits `step_type`; the importer must
    prefer that explicit value over name inference so oddly-named steps
    round-trip (e.g. a cold crash step someone named 'Lager it')."""

    def test_valid_step_type_preferred_over_name(self, serializer):
        step = {"name": "Lager it", "step_type": "cold_crash"}
        assert serializer._infer_fermentation_type(step) == "cold_crash"

    @pytest.mark.parametrize("step_type", [
        "primary", "secondary", "conditioning", "diacetyl_rest", "cold_crash",
    ])
    def test_all_known_types_accepted(self, serializer, step_type):
        step = {"name": "Anything", "step_type": step_type}
        assert serializer._infer_fermentation_type(step) == step_type

    def test_unknown_step_type_falls_back_to_name_inference(self, serializer):
        step = {"name": "Cold Crash", "step_type": "lagering"}
        assert serializer._infer_fermentation_type(step) == "cold_crash"

    def test_non_string_step_type_falls_back(self, serializer):
        step = {"name": "Secondary", "step_type": 42}
        assert serializer._infer_fermentation_type(step) == "secondary"
