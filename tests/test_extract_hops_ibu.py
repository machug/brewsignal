"""Extract hops contribute zero IBU (tilt_ui-0l5 phase 1)."""
import math
import pytest


class _FakeHop:
    """Minimal stand-in for the SQLAlchemy RecipeHop row in IBU math.

    Only the attributes the calculator reads need to be set.
    """
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


def _ibu_for_hops(hops, og=1.055, batch_liters=20):
    """Locate the canonical IBU calculator and invoke it.

    The brewing module exposes IBU via _calculate_ibu(hops, og, batch_liters)
    or via calculate_recipe_stats. Prefer the helper for unit testing.
    """
    from backend.services.brewing import _calculate_ibu
    return _calculate_ibu(hops, og=og, batch_liters=batch_liters)


def test_pellet_baseline_registers_ibu():
    pellet = _FakeHop(
        amount_grams=20, alpha_acid_percent=12,
        is_extract=False, amount_ml=None,
        timing={"use": "boil", "duration": {"value": 60}},
    )
    assert _ibu_for_hops([pellet]) > 0


def test_extract_only_recipe_has_zero_ibu():
    extract = _FakeHop(
        amount_grams=0, alpha_acid_percent=None,
        is_extract=True, amount_ml=2.5,
        timing={"use": "dry_hop", "duration": {"value": 0}},
    )
    assert _ibu_for_hops([extract]) == 0


def test_extract_does_not_perturb_traditional_ibu():
    pellet = _FakeHop(
        amount_grams=20, alpha_acid_percent=12,
        is_extract=False, amount_ml=None,
        timing={"use": "boil", "duration": {"value": 60}},
    )
    extract = _FakeHop(
        amount_grams=0, alpha_acid_percent=None,
        is_extract=True, amount_ml=2.5,
        timing={"use": "dry_hop", "duration": {"value": 0}},
    )
    pellet_only = _ibu_for_hops([pellet])
    mixed = _ibu_for_hops([pellet, extract])
    assert mixed == pytest.approx(pellet_only), (
        f"extract should not change IBU; only_pellet={pellet_only} mixed={mixed}"
    )


def test_extract_with_null_alpha_does_not_crash():
    """Regression guard: pre-fix this would crash on None * 0 / float math."""
    extract = _FakeHop(
        amount_grams=0, alpha_acid_percent=None,
        is_extract=True, amount_ml=2.5,
        timing={"use": "dry_hop", "duration": {"value": 0}},
    )
    # Must not raise.
    _ibu_for_hops([extract])


def test_normalize_preserves_extract_marker():
    """Normalization must carry is_extract through, otherwise the LLM-side
    IBU calculator can't skip the extract row (tilt_ui-0l5)."""
    from backend.services.llm.tools.recipe import normalize_recipe_to_beerjson
    recipe = {
        "name": "Extract LLM Test",
        "batch_size_liters": 20,
        "hops": [
            {"name": "Quantum MOS", "is_extract": True, "amount_ml": 2.5, "use": "dry_hop"},
            {"name": "Mosaic", "amount": 20, "alpha_acid": 12, "use": "boil", "time": 60},
        ],
    }
    normalized = normalize_recipe_to_beerjson(recipe)
    hops = normalized.get("ingredients", {}).get("hop_additions") or []
    assert len(hops) == 2
    extract = next(h for h in hops if h["name"] == "Quantum MOS")
    assert extract.get("is_extract") is True
    assert extract.get("amount_ml") == 2.5
    pellet = next(h for h in hops if h["name"] == "Mosaic")
    assert not pellet.get("is_extract"), "non-extract must not be marked"


def test_llm_calculate_recipe_stats_skips_extract_ibu():
    """End-to-end: an extract added via the LLM normalization+stats path
    must not contribute IBU. Without preserving is_extract, the duplicate
    IBU calculator at recipe.py:612 would never short-circuit."""
    from backend.services.llm.tools.recipe import (
        normalize_recipe_to_beerjson,
        calculate_recipe_stats,
    )

    pellet_only = normalize_recipe_to_beerjson({
        "name": "Pellet Only",
        "batch_size_liters": 20,
        "hops": [
            {"name": "Mosaic", "amount": 20, "alpha_acid": 12, "use": "boil", "time": 60},
        ],
    })
    mixed = normalize_recipe_to_beerjson({
        "name": "Mixed",
        "batch_size_liters": 20,
        "hops": [
            {"name": "Mosaic", "amount": 20, "alpha_acid": 12, "use": "boil", "time": 60},
            {"name": "Quantum MOS", "is_extract": True, "amount_ml": 2.5, "use": "dry_hop"},
        ],
    })
    pellet_ibu = calculate_recipe_stats(pellet_only)["ibu"]
    mixed_ibu = calculate_recipe_stats(mixed)["ibu"]
    assert pellet_ibu > 0
    assert mixed_ibu == pytest.approx(pellet_ibu), (
        f"extract perturbed LLM IBU: pellet={pellet_ibu} mixed={mixed_ibu}"
    )


def test_serializer_persists_extract_fields():
    """RecipeSerializer must write is_extract + amount_ml to the RecipeHop
    ORM object — otherwise the marker is lost on save and IBU calc is wrong
    post-reload (tilt_ui-0l5)."""
    from backend.services.serializers.recipe_serializer import RecipeSerializer
    from backend.models import RecipeHop

    serializer = RecipeSerializer()
    # The normalizer produces hop_additions entries shaped roughly like this:
    extract_dict = {
        "name": "Quantum MOS",
        "is_extract": True,
        "amount_ml": 2.5,
        "timing": {"use": "dry_hop", "duration": {"value": 0}},
    }
    hop = serializer._create_hop(extract_dict)
    assert isinstance(hop, RecipeHop)
    assert hop.is_extract is True
    assert hop.amount_ml == 2.5
    assert hop.name == "Quantum MOS"


def test_serializer_leaves_extract_false_for_pellets():
    """Default path: non-extract hops persist is_extract=False (the column
    default) and amount_ml stays None."""
    from backend.services.serializers.recipe_serializer import RecipeSerializer
    serializer = RecipeSerializer()
    # Match the normalized dict shape produced by normalize_recipe_to_beerjson:
    # alpha_acid is a BeerJSON unit object ({"value", "unit"}), not a raw float.
    pellet_dict = {
        "name": "Mosaic",
        "alpha_acid": {"value": 0.12, "unit": "%"},
        "amount": {"value": 20, "unit": "g"},
        "timing": {"use": "boil", "duration": {"value": 60}},
    }
    hop = serializer._create_hop(pellet_dict)
    # SQLAlchemy default applies on flush; in-memory the attribute may still be
    # unset/falsy. Either way it must not be coerced to True.
    assert not getattr(hop, "is_extract", False)
    assert getattr(hop, "amount_ml", None) is None
