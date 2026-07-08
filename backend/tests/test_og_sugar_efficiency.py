"""Sugar/extract OG efficiency + percent boundary fixes (tilt_ui-ju0z).

Kettle sugars and extracts contribute ~100% of their potential — brewhouse
efficiency only models mash losses. Applying it to sugar understates OG
(Pliny the Elder: computed 1.070 vs Brewfather 1.077, ABV 7.4 vs 8.3).

Related boundary bug: BeerJSON percents are decimals (0-1); the serializer's
`value < 1.0` heuristic misreads exactly 1.0 (i.e. 100%) as "already a
percentage", so a 100%-yield sugar was stored as yield_percent=1.0.
"""

import pytest

from backend.models import RecipeFermentable
from backend.services.brewing import calculate_og_from_fermentables
from backend.services.serializers.recipe_serializer import RecipeSerializer


def _ferm(name: str, kg: float, ferm_type: str, yield_percent: float) -> RecipeFermentable:
    return RecipeFermentable(
        name=name,
        amount_kg=kg,
        type=ferm_type,
        yield_percent=yield_percent,
        color_srm=3,
    )


class TestSugarSkipsEfficiency:
    def test_sugar_contributes_full_potential_regardless_of_efficiency(self):
        sugar = [_ferm("Cane Sugar", 1.0, "sugar", 100.0)]
        og_low_eff, _ = calculate_og_from_fermentables(sugar, 20.0, 0.5)
        og_high_eff, _ = calculate_og_from_fermentables(sugar, 20.0, 0.9)
        assert og_low_eff == pytest.approx(og_high_eff)
        # 1kg @ 46 PPG in 20L: 2.205lb * 46 / 5.283gal = 19.2 points
        assert og_low_eff == pytest.approx(1.0192, abs=0.0005)

    def test_extract_types_also_skip_efficiency(self):
        for t in ("extract", "dry extract", "honey", "fruit", "juice"):
            ferms = [_ferm("Extract", 1.0, t, 80.0)]
            a, _ = calculate_og_from_fermentables(ferms, 20.0, 0.5)
            b, _ = calculate_og_from_fermentables(ferms, 20.0, 0.9)
            assert a == pytest.approx(b), t

    def test_grain_still_scaled_by_efficiency(self):
        grain = [_ferm("Pale Ale", 5.0, "grain", 80.0)]
        og_low, _ = calculate_og_from_fermentables(grain, 20.0, 0.5)
        og_high, _ = calculate_og_from_fermentables(grain, 20.0, 0.9)
        assert og_high > og_low

    def test_pliny_grain_bill_matches_brewfather_og(self):
        """4 fermentables, 25L, 58% brewhouse -> Brewfather says 1.077."""
        ferms = [
            _ferm("Pale Ale", 8.816, "grain", 82.8),
            _ferm("Cane (Beet) Sugar", 0.434, "sugar", 100.0),
            _ferm("Caramel/Crystal 40 - US", 0.408, "grain", 75.734625870948),
            _ferm("Carapils - Dextrine Malt - US", 0.408, "grain", 71.406932964037),
        ]
        og, _ = calculate_og_from_fermentables(ferms, 25.0, 0.58)
        assert og == pytest.approx(1.077, abs=0.001)


class TestLLMToolsStatsMirror:
    """services/llm/tools/recipe.py has a dict-based duplicate of the OG calc
    used when the assistant saves/updates recipes — must apply the same rule."""

    def test_llm_calculate_recipe_stats_sugar_skips_efficiency(self):
        from backend.services.llm.tools.recipe import calculate_recipe_stats

        def doc(eff):
            return {
                "batch_size": {"value": 20.0, "unit": "l"},
                "efficiency": {"brewhouse": {"value": eff, "unit": "%"}},
                "ingredients": {
                    "fermentable_additions": [
                        {"name": "Cane Sugar", "type": "sugar",
                         "amount": {"value": 1.0, "unit": "kg"}},
                    ]
                },
            }

        og_low = calculate_recipe_stats(doc(50))["og"]
        og_high = calculate_recipe_stats(doc(90))["og"]
        assert og_low == pytest.approx(og_high)


class TestPercentBoundary:
    def test_extract_percent_leaves_exactly_one_unchanged(self):
        """1.0 is ambiguous globally (1% ABV/alpha exist) — resolved per-site."""
        s = RecipeSerializer()
        assert s._extract_percent({"value": 1.0, "unit": "%"}) == pytest.approx(1.0)

    def test_extract_percent_decimal_and_percent_forms_unchanged(self):
        s = RecipeSerializer()
        assert s._extract_percent({"value": 0.828, "unit": "%"}) == pytest.approx(82.8)
        assert s._extract_percent({"value": 82.8, "unit": "%"}) == pytest.approx(82.8)

    def test_serializer_stores_100_percent_sugar_yield(self):
        """Brewfather 100% potential -> BeerJSON {'value': 1.0} -> DB 100, not 1."""
        s = RecipeSerializer()
        ferm = s._create_fermentable(
            {
                "name": "Cane (Beet) Sugar",
                "type": "sugar",
                "amount": {"value": 0.434, "unit": "kg"},
                "yield": {"fine_grind": {"value": 1.0, "unit": "%"}},
            }
        )
        assert ferm.yield_percent == pytest.approx(100.0)
