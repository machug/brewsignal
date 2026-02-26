"""Unit tests for inventory deduction service - check_inventory_availability.

Tests the pure function that checks whether inventory has sufficient
ingredients for a recipe. Uses MagicMock objects since the function
has no DB access.
"""

import pytest
from unittest.mock import MagicMock

from backend.services.inventory import check_inventory_availability


def _make_recipe_hop(name: str, form: str, amount_grams: float) -> MagicMock:
    """Create a mock RecipeHop."""
    hop = MagicMock()
    hop.name = name
    hop.form = form
    hop.amount_grams = amount_grams
    return hop


def _make_recipe_culture(
    name: str,
    producer: str = "Fermentis",
    product_id: str = "US-05",
    amount: float = 1.0,
    amount_unit: str = "pkg",
) -> MagicMock:
    """Create a mock RecipeCulture."""
    culture = MagicMock()
    culture.name = name
    culture.producer = producer
    culture.product_id = product_id
    culture.amount = amount
    culture.amount_unit = amount_unit
    return culture


def _make_hop_inventory(
    variety: str,
    form: str = "pellet",
    amount_grams: float = 100.0,
) -> MagicMock:
    """Create a mock HopInventory."""
    inv = MagicMock()
    inv.variety = variety
    inv.form = form
    inv.amount_grams = amount_grams
    return inv


def _make_yeast_inventory(
    custom_name: str | None = None,
    strain_name: str | None = None,
    quantity: int = 1,
) -> MagicMock:
    """Create a mock YeastInventory.

    Args:
        custom_name: Custom name for unlisted strains
        strain_name: Name on the related YeastStrain object
        quantity: Number of packages/vials
    """
    inv = MagicMock()
    inv.custom_name = custom_name
    inv.quantity = quantity

    if strain_name:
        inv.yeast_strain = MagicMock()
        inv.yeast_strain.name = strain_name
    else:
        inv.yeast_strain = None

    return inv


class TestCheckHopAvailability:
    """Tests for hop availability checking."""

    def test_all_hops_available(self):
        """When inventory has enough hops, all entries are sufficient."""
        recipe_hops = [
            _make_recipe_hop("Citra", "pellet", 50.0),
            _make_recipe_hop("Cascade", "pellet", 30.0),
        ]
        hop_inventory = [
            _make_hop_inventory("Citra", "pellet", 100.0),
            _make_hop_inventory("Cascade", "pellet", 50.0),
        ]

        result = check_inventory_availability(recipe_hops, [], hop_inventory, [])

        assert result["all_sufficient"] is True
        assert len(result["hops"]) == 2
        assert result["hops"][0]["name"] == "Citra"
        assert result["hops"][0]["sufficient"] is True
        assert result["hops"][0]["available"] == 100.0
        assert result["hops"][0]["needed"] == 50.0
        assert result["hops"][0]["needed_unit"] == "g"
        assert "shortage" not in result["hops"][0]

    def test_insufficient_hops(self):
        """When inventory is short, sufficient=False and shortage is calculated."""
        recipe_hops = [_make_recipe_hop("Citra", "pellet", 150.0)]
        hop_inventory = [_make_hop_inventory("Citra", "pellet", 100.0)]

        result = check_inventory_availability(recipe_hops, [], hop_inventory, [])

        assert result["all_sufficient"] is False
        assert result["hops"][0]["sufficient"] is False
        assert result["hops"][0]["shortage"] == 50.0
        assert result["hops"][0]["available"] == 100.0
        assert result["hops"][0]["needed"] == 150.0

    def test_missing_hop_variety(self):
        """When a hop variety is not in inventory, available=0 and sufficient=False."""
        recipe_hops = [_make_recipe_hop("Mosaic", "pellet", 25.0)]
        hop_inventory = [_make_hop_inventory("Citra", "pellet", 100.0)]

        result = check_inventory_availability(recipe_hops, [], hop_inventory, [])

        assert result["all_sufficient"] is False
        assert result["hops"][0]["name"] == "Mosaic"
        assert result["hops"][0]["available"] == 0.0
        assert result["hops"][0]["sufficient"] is False
        assert result["hops"][0]["shortage"] == 25.0

    def test_multiple_inventory_items_aggregate(self):
        """Multiple inventory items for same variety are summed."""
        recipe_hops = [_make_recipe_hop("Citra", "pellet", 120.0)]
        hop_inventory = [
            _make_hop_inventory("Citra", "pellet", 80.0),
            _make_hop_inventory("Citra", "leaf", 50.0),
        ]

        result = check_inventory_availability(recipe_hops, [], hop_inventory, [])

        assert result["all_sufficient"] is True
        assert result["hops"][0]["available"] == 130.0
        assert result["hops"][0]["sufficient"] is True

    def test_case_insensitive_hop_matching(self):
        """Hop names match case-insensitively."""
        recipe_hops = [_make_recipe_hop("citra", "pellet", 50.0)]
        hop_inventory = [_make_hop_inventory("CITRA", "pellet", 100.0)]

        result = check_inventory_availability(recipe_hops, [], hop_inventory, [])

        assert result["all_sufficient"] is True
        assert result["hops"][0]["available"] == 100.0
        assert result["hops"][0]["sufficient"] is True

    def test_exact_amount_is_sufficient(self):
        """Having exactly the needed amount is sufficient."""
        recipe_hops = [_make_recipe_hop("Citra", "pellet", 100.0)]
        hop_inventory = [_make_hop_inventory("Citra", "pellet", 100.0)]

        result = check_inventory_availability(recipe_hops, [], hop_inventory, [])

        assert result["all_sufficient"] is True
        assert result["hops"][0]["sufficient"] is True

    def test_empty_recipe_hops(self):
        """No recipe hops means all_sufficient with empty hops list."""
        result = check_inventory_availability([], [], [], [])

        assert result["all_sufficient"] is True
        assert result["hops"] == []
        assert result["yeast"] == []


class TestCheckYeastAvailability:
    """Tests for yeast availability checking."""

    def test_yeast_available_by_custom_name(self):
        """Yeast matches by custom_name."""
        recipe_cultures = [_make_recipe_culture("US-05", "Fermentis")]
        yeast_inventory = [_make_yeast_inventory(custom_name="US-05", quantity=2)]

        result = check_inventory_availability([], recipe_cultures, [], yeast_inventory)

        assert result["all_sufficient"] is True
        assert result["yeast"][0]["name"] == "US-05"
        assert result["yeast"][0]["available"] == 2.0
        assert result["yeast"][0]["sufficient"] is True

    def test_yeast_available_by_strain_name(self):
        """Yeast matches by yeast_strain.name when custom_name is None."""
        recipe_cultures = [_make_recipe_culture("Safale US-05", "Fermentis")]
        yeast_inventory = [
            _make_yeast_inventory(strain_name="Safale US-05", quantity=3),
        ]

        result = check_inventory_availability([], recipe_cultures, [], yeast_inventory)

        assert result["all_sufficient"] is True
        assert result["yeast"][0]["available"] == 3.0

    def test_insufficient_yeast(self):
        """When yeast inventory is short, shortage is calculated."""
        recipe_cultures = [_make_recipe_culture("US-05", amount=3.0, amount_unit="pkg")]
        yeast_inventory = [_make_yeast_inventory(custom_name="US-05", quantity=1)]

        result = check_inventory_availability([], recipe_cultures, [], yeast_inventory)

        assert result["all_sufficient"] is False
        assert result["yeast"][0]["sufficient"] is False
        assert result["yeast"][0]["shortage"] == 2.0
        assert result["yeast"][0]["available"] == 1.0

    def test_missing_yeast_variety(self):
        """When yeast is not in inventory, available=0 and sufficient=False."""
        recipe_cultures = [_make_recipe_culture("WLP001", "White Labs")]
        yeast_inventory = [_make_yeast_inventory(custom_name="US-05", quantity=2)]

        result = check_inventory_availability([], recipe_cultures, [], yeast_inventory)

        assert result["all_sufficient"] is False
        assert result["yeast"][0]["available"] == 0.0
        assert result["yeast"][0]["sufficient"] is False
        assert result["yeast"][0]["shortage"] == 1.0

    def test_case_insensitive_yeast_matching(self):
        """Yeast names match case-insensitively."""
        recipe_cultures = [_make_recipe_culture("us-05")]
        yeast_inventory = [_make_yeast_inventory(custom_name="US-05", quantity=2)]

        result = check_inventory_availability([], recipe_cultures, [], yeast_inventory)

        assert result["all_sufficient"] is True
        assert result["yeast"][0]["sufficient"] is True

    def test_yeast_default_amount(self):
        """When recipe culture has no amount, defaults to 1.0 pkg."""
        recipe_cultures = [_make_recipe_culture("US-05", amount=None, amount_unit=None)]
        yeast_inventory = [_make_yeast_inventory(custom_name="US-05", quantity=1)]

        result = check_inventory_availability([], recipe_cultures, [], yeast_inventory)

        assert result["all_sufficient"] is True
        assert result["yeast"][0]["needed"] == 1.0
        assert result["yeast"][0]["needed_unit"] == "pkg"

    def test_multiple_yeast_inventory_aggregate(self):
        """Multiple yeast inventory items for same name are summed."""
        recipe_cultures = [_make_recipe_culture("US-05", amount=3.0)]
        yeast_inventory = [
            _make_yeast_inventory(custom_name="US-05", quantity=2),
            _make_yeast_inventory(custom_name="US-05", quantity=2),
        ]

        result = check_inventory_availability([], recipe_cultures, [], yeast_inventory)

        assert result["all_sufficient"] is True
        assert result["yeast"][0]["available"] == 4.0


class TestAllSufficientFlag:
    """Tests for the all_sufficient summary flag."""

    def test_all_sufficient_when_everything_available(self):
        """all_sufficient is True when all hops and yeast are sufficient."""
        recipe_hops = [_make_recipe_hop("Citra", "pellet", 50.0)]
        recipe_cultures = [_make_recipe_culture("US-05")]
        hop_inventory = [_make_hop_inventory("Citra", "pellet", 100.0)]
        yeast_inventory = [_make_yeast_inventory(custom_name="US-05", quantity=2)]

        result = check_inventory_availability(
            recipe_hops, recipe_cultures, hop_inventory, yeast_inventory
        )

        assert result["all_sufficient"] is True

    def test_not_sufficient_when_hop_shortage(self):
        """all_sufficient is False when any hop has a shortage."""
        recipe_hops = [
            _make_recipe_hop("Citra", "pellet", 50.0),
            _make_recipe_hop("Mosaic", "pellet", 30.0),  # Not in inventory
        ]
        recipe_cultures = [_make_recipe_culture("US-05")]
        hop_inventory = [_make_hop_inventory("Citra", "pellet", 100.0)]
        yeast_inventory = [_make_yeast_inventory(custom_name="US-05", quantity=2)]

        result = check_inventory_availability(
            recipe_hops, recipe_cultures, hop_inventory, yeast_inventory
        )

        assert result["all_sufficient"] is False
        # Citra is sufficient, Mosaic is not
        assert result["hops"][0]["sufficient"] is True
        assert result["hops"][1]["sufficient"] is False

    def test_not_sufficient_when_yeast_shortage(self):
        """all_sufficient is False when any yeast has a shortage."""
        recipe_hops = [_make_recipe_hop("Citra", "pellet", 50.0)]
        recipe_cultures = [_make_recipe_culture("WLP001", "White Labs")]
        hop_inventory = [_make_hop_inventory("Citra", "pellet", 100.0)]
        yeast_inventory = [_make_yeast_inventory(custom_name="US-05", quantity=2)]

        result = check_inventory_availability(
            recipe_hops, recipe_cultures, hop_inventory, yeast_inventory
        )

        assert result["all_sufficient"] is False
        assert result["hops"][0]["sufficient"] is True
        assert result["yeast"][0]["sufficient"] is False

    def test_not_sufficient_when_both_shortage(self):
        """all_sufficient is False when both hops and yeast have shortages."""
        recipe_hops = [_make_recipe_hop("Mosaic", "pellet", 50.0)]
        recipe_cultures = [_make_recipe_culture("WLP001", "White Labs")]
        hop_inventory = []
        yeast_inventory = []

        result = check_inventory_availability(
            recipe_hops, recipe_cultures, hop_inventory, yeast_inventory
        )

        assert result["all_sufficient"] is False
        assert result["hops"][0]["sufficient"] is False
        assert result["yeast"][0]["sufficient"] is False
