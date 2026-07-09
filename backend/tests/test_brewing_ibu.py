"""IBU calculation tests, focused on whirlpool/hop-stand modeling (tilt_ui-23u)."""

import pytest

from backend.models import RecipeHop
from backend.services.brewing import calculate_ibu_from_hops


def _hop(use: str, duration_min: float, amount_g: float = 30.0, alpha: float = 12.0) -> RecipeHop:
    return RecipeHop(
        name="Test",
        amount_grams=amount_g,
        alpha_acid_percent=alpha,
        timing={"use": use, "duration": {"value": duration_min, "unit": "min"}},
    )


class TestBoilHopRegression:
    """Boil hop IBU calculation must remain Tinseth-compatible."""

    def test_60min_boil_hop_produces_expected_tinseth_ibu(self):
        # 30g of 12% AA hop at 60min in 20L at OG 1.060.
        # Tinseth: bigness ~0.96, btFactor ~0.219, util ~0.21 -> ~38 IBU.
        ibu = calculate_ibu_from_hops([_hop("add_to_boil", 60)], batch_liters=20, og=1.060)
        assert 30 <= ibu <= 45

    def test_zero_minute_boil_hop_produces_zero_ibu(self):
        """Boil-tagged 0-min hop intentionally contributes nothing.

        True flameout/whirlpool additions should be tagged add_to_whirlpool;
        we don't want to silently credit a mis-tagged boil hop.
        """
        ibu = calculate_ibu_from_hops([_hop("add_to_boil", 0)], batch_liters=20, og=1.060)
        assert ibu == 0


class TestWhirlpoolStandModel:
    """Whirlpool/hop-stand additions contribute IBU proportional to stand time."""

    def test_zero_minute_flameout_whirlpool_contributes_nonzero_ibu(self):
        """A 0-min whirlpool addition (true flameout) gets baseline utilization."""
        ibu = calculate_ibu_from_hops([_hop("add_to_whirlpool", 0)], batch_liters=20, og=1.060)
        assert ibu > 0

    def test_longer_stand_produces_more_ibu_than_flameout(self):
        ibu_flameout = calculate_ibu_from_hops(
            [_hop("add_to_whirlpool", 0)], batch_liters=20, og=1.060
        )
        ibu_20min = calculate_ibu_from_hops(
            [_hop("add_to_whirlpool", 20)], batch_liters=20, og=1.060
        )
        assert ibu_20min > ibu_flameout

    def test_whirlpool_utilization_is_capped_for_long_stands(self):
        """Stands longer than ~30min should not produce runaway IBU."""
        ibu_30min = calculate_ibu_from_hops(
            [_hop("add_to_whirlpool", 30)], batch_liters=20, og=1.060
        )
        ibu_120min = calculate_ibu_from_hops(
            [_hop("add_to_whirlpool", 120)], batch_liters=20, og=1.060
        )
        assert ibu_120min <= ibu_30min * 1.05  # Within 5% of the cap.

    def test_recipe21_whirlpool_addition_produces_realistic_ibu(self):
        """Recipe 21 'Project Alpha 81 Clone': 5g of 5% Riwaka in 23L whirlpool.
        Should land in the low single digits, not zero, not 50."""
        riwaka = RecipeHop(
            name="Riwaka",
            amount_grams=5.0,
            alpha_acid_percent=5.0,
            timing={"use": "add_to_whirlpool", "duration": {"value": 0, "unit": "min"}},
        )
        ibu = calculate_ibu_from_hops([riwaka], batch_liters=23.0, og=1.067)
        # 5g * 5% AA * 5% util * 1000 / 23 ~ 0.5 IBU. Range generous for tweaks.
        assert 0.3 <= ibu <= 3.0


class TestDryHopUnchanged:
    """Dry hops must contribute zero IBU and not get credited by any other
    branch (no double-counting). Pins the audit conclusion for tilt_ui-4te.
    """

    def test_dry_hop_contributes_zero(self):
        hop = RecipeHop(
            name="Mosaic Cryo",
            amount_grams=50.0,
            alpha_acid_percent=22.0,
            timing={"use": "add_to_fermentation", "duration": {"value": 4, "unit": "day"}},
        )
        ibu = calculate_ibu_from_hops([hop], batch_liters=20, og=1.060)
        assert ibu == 0

    def test_short_form_dry_hop_use_also_contributes_zero(self):
        """Frontend / legacy data uses 'dry_hop' short form — still 0."""
        hop = RecipeHop(
            name="Citra",
            amount_grams=50.0,
            alpha_acid_percent=12.0,
            timing={"use": "dry_hop", "duration": {"value": 4, "unit": "day"}},
        )
        ibu = calculate_ibu_from_hops([hop], batch_liters=20, og=1.060)
        assert ibu == 0

    def test_recipe21_full_dry_hop_charge_contributes_zero(self):
        """Recipe 21 has 4 dry hop additions totaling ~140g of high-alpha
        cryo hops. Total dry-hop IBU contribution must be exactly 0."""
        dry_hops = [
            RecipeHop(name="Mosaic Cryo", amount_grams=40, alpha_acid_percent=22.0,
                      timing={"use": "add_to_fermentation", "duration": {"value": 4, "unit": "day"}}),
            RecipeHop(name="Krush Cryo", amount_grams=40, alpha_acid_percent=18.0,
                      timing={"use": "add_to_fermentation", "duration": {"value": 4, "unit": "day"}}),
            RecipeHop(name="Columbus Cryo", amount_grams=30, alpha_acid_percent=20.0,
                      timing={"use": "add_to_fermentation", "duration": {"value": 4, "unit": "day"}}),
            RecipeHop(name="Riwaka", amount_grams=30, alpha_acid_percent=5.0,
                      timing={"use": "add_to_fermentation", "duration": {"value": 4, "unit": "day"}}),
        ]
        ibu = calculate_ibu_from_hops(dry_hops, batch_liters=23.0, og=1.067)
        assert ibu == 0

    def test_dry_hop_alongside_whirlpool_and_boil_does_not_inflate_total(self):
        """Total IBU must equal sum of boil + whirlpool only, with the dry
        hops adding 0. Defends against any future regression where the
        dry-hop branch starts crediting through whirlpool or boil paths."""
        boil_hop = RecipeHop(
            name="Columbus", amount_grams=30, alpha_acid_percent=20.0,
            timing={"use": "add_to_boil", "duration": {"value": 60, "unit": "min"}},
        )
        whirlpool_hop = RecipeHop(
            name="Mosaic", amount_grams=40, alpha_acid_percent=12.5,
            timing={"use": "add_to_whirlpool", "duration": {"value": 20, "unit": "min"}},
        )
        dry_hop = RecipeHop(
            name="Mosaic Cryo", amount_grams=50, alpha_acid_percent=22.0,
            timing={"use": "add_to_fermentation", "duration": {"value": 4, "unit": "day"}},
        )

        without_dry = calculate_ibu_from_hops([boil_hop, whirlpool_hop], batch_liters=23, og=1.060)
        with_dry = calculate_ibu_from_hops([boil_hop, whirlpool_hop, dry_hop], batch_liters=23, og=1.060)
        assert with_dry == without_dry


class TestLLMToolsCalculatorAgreesOnZero:
    """The LLM-tools recipe calculator is a separate code path used when
    the assistant saves recipes. It must agree that dry hops produce 0 IBU."""

    def test_llm_calculator_credits_zero_ibu_to_dry_hops(self):
        """The LLM calculator reads amount.value as grams. Use a charge
        that would visibly inflate IBU if the dry-hop branch were ever
        miswired into boil or whirlpool — 50g of 22% AA cryo hops would
        yield ~10+ IBU through the whirlpool branch and ~50+ through the
        boil branch."""
        from backend.services.llm.tools.recipe import calculate_recipe_stats

        normalized = {
            "batch_size": {"value": 23, "unit": "l"},
            "ingredients": {
                "fermentable_additions": [
                    {"name": "Pilsner", "amount": {"value": 5, "unit": "kg"},
                     "yield": {"fine_grind": {"value": 80, "unit": "%"}}}
                ],
                "hop_additions": [
                    {"name": "Mosaic Cryo", "amount": {"value": 50, "unit": "g"},
                     "alpha_acid": {"value": 22, "unit": "%"},
                     "timing": {"use": "add_to_fermentation",
                                "duration": {"value": 4, "unit": "day"}}}
                ],
            },
        }
        stats = calculate_recipe_stats(normalized)
        assert stats["ibu"] == 0


class TestPelletAndFirstWortAdjustments:
    """Backend must mirror the frontend Tinseth adjustments (tilt_ui-nbh0):
    pellet form +10% utilization, first-wort +10%. Without them the
    displayed (frontend) IBU and the recalculate-endpoint IBU disagree."""

    def _hop_with_form(self, form, use="add_to_boil", duration=60.0):
        return RecipeHop(
            name="Test",
            amount_grams=30.0,
            alpha_acid_percent=12.0,
            form=form,
            timing={"use": use, "duration": {"value": duration, "unit": "min"}},
        )

    def test_pellet_boil_hop_gets_10_percent_more_than_leaf(self):
        pellet = calculate_ibu_from_hops(
            [self._hop_with_form("pellet")], batch_liters=20, og=1.060)
        leaf = calculate_ibu_from_hops(
            [self._hop_with_form("leaf")], batch_liters=20, og=1.060)
        assert pellet == pytest.approx(leaf * 1.10)

    def test_missing_form_defaults_to_pellet(self):
        """Frontend maps missing forms to pellet before calculating —
        the backend must default the same way or the mismatch persists."""
        none_form = calculate_ibu_from_hops(
            [self._hop_with_form(None)], batch_liters=20, og=1.060)
        pellet = calculate_ibu_from_hops(
            [self._hop_with_form("pellet")], batch_liters=20, og=1.060)
        assert none_form == pytest.approx(pellet)

    def test_first_wort_gets_10_percent_more_than_boil(self):
        fw = calculate_ibu_from_hops(
            [self._hop_with_form("leaf", use="first_wort")], batch_liters=20, og=1.060)
        boil = calculate_ibu_from_hops(
            [self._hop_with_form("leaf", use="add_to_boil")], batch_liters=20, og=1.060)
        assert fw == pytest.approx(boil * 1.10)

    def test_pellet_first_wort_stacks_both_adjustments(self):
        both = calculate_ibu_from_hops(
            [self._hop_with_form("pellet", use="first_wort")], batch_liters=20, og=1.060)
        base = calculate_ibu_from_hops(
            [self._hop_with_form("leaf", use="add_to_boil")], batch_liters=20, og=1.060)
        assert both == pytest.approx(base * 1.21)


class TestLLMToolsIBUMirrorAdjustments:
    """LLM-tools duplicate calculator must apply the same pellet/first-wort
    adjustments (tilt_ui-nbh0)."""

    def _doc(self, form, use):
        return {
            "batch_size": {"value": 20.0, "unit": "l"},
            "original_gravity": {"value": 1.060},
            "efficiency": {"brewhouse": {"value": 72, "unit": "%"}},
            "ingredients": {
                "hop_additions": [{
                    "name": "Test", "form": form,
                    "amount": {"value": 30.0, "unit": "g"},
                    "alpha_acid": {"value": 12.0, "unit": "%"},
                    "timing": {"use": use,
                               "duration": {"value": 60.0, "unit": "min"}},
                }]
            },
        }

    def test_llm_mirror_applies_pellet_adjustment(self):
        from backend.services.llm.tools.recipe import calculate_recipe_stats
        pellet = calculate_recipe_stats(self._doc("pellet", "add_to_boil"))["ibu"]
        leaf = calculate_recipe_stats(self._doc("leaf", "add_to_boil"))["ibu"]
        assert pellet == pytest.approx(leaf * 1.10, rel=0.01)

    def test_llm_mirror_applies_first_wort_adjustment(self):
        from backend.services.llm.tools.recipe import calculate_recipe_stats
        fw = calculate_recipe_stats(self._doc("leaf", "first_wort"))["ibu"]
        boil = calculate_recipe_stats(self._doc("leaf", "add_to_boil"))["ibu"]
        assert fw == pytest.approx(boil * 1.10, rel=0.01)
