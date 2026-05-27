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
