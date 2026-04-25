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
