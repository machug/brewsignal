"""apply_v2_extensions maps the brewsignal block onto ORM columns (tilt_ui-0jkg)."""
import pytest

from backend.models import Recipe, RecipeHop
from backend.services.converters.brewsignal_v2 import apply_v2_extensions


def _recipe_with_hops(n: int) -> Recipe:
    recipe = Recipe(name="T")
    for i in range(n):
        recipe.hops.append(RecipeHop(name=f"H{i}", amount_grams=10.0))
    return recipe


def test_none_block_is_noop():
    recipe = Recipe(name="T")
    apply_v2_extensions(recipe, None)
    assert recipe.format_extensions is None
    assert recipe.water_profiles == []


def test_target_profile_sugar_becomes_target_row():
    recipe = Recipe(name="T")
    apply_v2_extensions(recipe, {"water": {"target_profile": {
        "name": "Hazy build", "chloride_ppm": 125, "sulfate_ppm": 75,
        "sulfate_chloride_ratio": 0.6, "_note": "chloride-forward",
    }}})
    assert len(recipe.water_profiles) == 1
    p = recipe.water_profiles[0]
    assert p.profile_type == "target"
    assert p.chloride_ppm == 125
    assert p.sulfate_ppm == 75
    # non-column keys preserved on the profile
    assert p.format_extensions["sulfate_chloride_ratio"] == 0.6


def test_profiles_array_and_adjustments():
    recipe = Recipe(name="T")
    apply_v2_extensions(recipe, {"water": {
        "profiles": [
            {"profile_type": "source", "calcium_ppm": 20, "ph": 7.4},
            {"profile_type": "target", "chloride_ppm": 150},
        ],
        "adjustments": [{
            "stage": "mash", "volume_liters": 18.0,
            "salts": {"calcium_chloride_g": 3.2, "calcium_sulfate_g": 1.1,
                      "unobtainium_g": 9.9},
            "acid": {"type": "lactic", "ml": 2.0, "concentration_percent": 88},
            "computed_by": "water_tool",
        }],
        "mash_ph_target": 5.2,
    }})
    assert {p.profile_type for p in recipe.water_profiles} == {"source", "target"}
    assert recipe.water_profiles[0].ph == 7.4
    adj = recipe.water_adjustments[0]
    assert adj.stage == "mash"
    assert adj.volume_liters == 18.0
    assert adj.calcium_chloride_g == 3.2
    assert adj.calcium_sulfate_g == 1.1
    assert adj.acid_type == "lactic"
    assert adj.acid_ml == 2.0
    assert adj.acid_concentration_percent == 88
    # unknown salt preserved, not silently dropped
    assert adj.format_extensions["salts"]["unobtainium_g"] == 9.9
    # water keys without a column home preserved at recipe level
    assert recipe.format_extensions["brewsignal"]["water"]["mash_ph_target"] == 5.2


def test_hop_extras_land_by_index():
    recipe = _recipe_with_hops(3)
    apply_v2_extensions(recipe, {"hop_additions": [
        {"index": 1, "name": "Citra", "ref_use": "add_to_boil",
         "hop_use": "whirlpool", "temperature": {"value": 79.0, "unit": "C"}},
        {"index": 99, "hop_use": "dropped-out-of-range"},
    ]})
    ext = recipe.hops[1].format_extensions["brewsignal"]
    assert ext["hop_use"] == "whirlpool"
    assert ext["temperature"] == {"value": 79.0, "unit": "C"}
    # index/name/ref_use are alignment metadata, not payload
    assert "index" not in ext and "name" not in ext and "ref_use" not in ext
    assert recipe.hops[0].format_extensions is None


def test_duplicate_hop_index_merges_instead_of_clobbering():
    """tilt_ui-4bwa item 3: two entries targeting the same hop index used
    to last-write-win, silently dropping the first entry's extras."""
    recipe = _recipe_with_hops(1)
    apply_v2_extensions(recipe, {"hop_additions": [
        {"index": 0, "hop_use": "whirlpool"},
        {"index": 0, "temperature": {"value": 79.0, "unit": "C"}},
    ]})
    ext = recipe.hops[0].format_extensions["brewsignal"]
    assert ext["hop_use"] == "whirlpool"
    assert ext["temperature"] == {"value": 79.0, "unit": "C"}


@pytest.mark.parametrize("water_block,path", [
    ({"profiles": ["bogus"]}, "brewsignal.water.profiles[0]"),
    ({"profiles": [{"profile_type": "source"}, 42]}, "brewsignal.water.profiles[1]"),
    ({"adjustments": ["nope"]}, "brewsignal.water.adjustments[0]"),
    ({"target_profile": {"ph": 7.0}, "adjustments": [None]},
     "brewsignal.water.adjustments[0]"),
])
def test_non_dict_water_entries_raise_clear_error(water_block, path):
    """tilt_ui-4bwa item 3: a non-dict entry used to blow up deep inside
    _profile_from_dict with an AttributeError the importer surfaced as a
    cryptic 'Serialization error'. Name the offending path instead."""
    recipe = Recipe(name="T")
    with pytest.raises(ValueError, match=path.replace("[", r"\[").replace("]", r"\]")):
        apply_v2_extensions(recipe, {"water": water_block})


def test_unknown_blocks_preserved():
    recipe = Recipe(name="T")
    apply_v2_extensions(recipe, {
        "schema": "brewsignal/2.0",
        "style_id": "bjcp-2021-21c",
        "process": {"lodo": True},
    })
    bs = recipe.format_extensions["brewsignal"]
    assert bs["process"]["lodo"] is True
    assert bs["style_id"] == "bjcp-2021-21c"
    assert bs["schema"] == "brewsignal/2.0"
