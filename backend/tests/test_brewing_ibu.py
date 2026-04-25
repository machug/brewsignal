"""IBU calculation tests, focused on whirlpool/hop-stand modeling (tilt_ui-23u)."""

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
    """Dry hops must continue to contribute zero IBU."""

    def test_dry_hop_contributes_zero(self):
        hop = RecipeHop(
            name="Mosaic Cryo",
            amount_grams=50.0,
            alpha_acid_percent=22.0,
            timing={"use": "add_to_fermentation", "duration": {"value": 4, "unit": "day"}},
        )
        ibu = calculate_ibu_from_hops([hop], batch_liters=20, og=1.060)
        assert ibu == 0
