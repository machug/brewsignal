"""Unit and integration tests for inventory deduction service.

Unit tests for the pure function check_inventory_availability (using MagicMock).
Integration tests for deduct_inventory_for_batch and reverse_inventory_deductions
using a real async SQLite database.
"""

import pytest
from unittest.mock import MagicMock, patch

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload
from sqlalchemy import select

from backend.models import (
    Base,
    Batch,
    Recipe,
    RecipeHop,
    RecipeCulture,
    HopInventory,
    YeastInventory,
    InventoryDeduction,
)
from backend.services.inventory import (
    check_inventory_availability,
    deduct_inventory_for_batch,
    reverse_inventory_deductions,
)


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


# ============================================================================
# Integration tests - deduct_inventory_for_batch & reverse_inventory_deductions
# ============================================================================


@pytest.fixture
async def async_db():
    """Create an in-memory async SQLite database for testing."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session

    await engine.dispose()


@pytest.fixture
async def seeded_db(async_db):
    """Seed the database with a recipe, inventory, and batch for testing.

    Creates:
    - Recipe with 2 hops (Citra 60g, Mosaic 30g) and 1 yeast (US-05, 1 pkg)
    - Hop inventory: Citra 100g (crop_year=2024), Citra 50g (crop_year=2025),
      Mosaic 40g (crop_year=2025)
    - Yeast inventory: US-05 with quantity=3
    - Batch in 'planning' status linked to the recipe
    """
    db = async_db

    # Create recipe
    recipe = Recipe(name="Test IPA", type="All Grain")
    db.add(recipe)
    await db.flush()

    # Add recipe hops
    hop_citra = RecipeHop(
        recipe_id=recipe.id,
        name="Citra",
        form="pellet",
        alpha_acid_percent=12.0,
        amount_grams=60.0,
    )
    hop_mosaic = RecipeHop(
        recipe_id=recipe.id,
        name="Mosaic",
        form="pellet",
        alpha_acid_percent=11.5,
        amount_grams=30.0,
    )
    db.add_all([hop_citra, hop_mosaic])

    # Add recipe culture
    culture = RecipeCulture(
        recipe_id=recipe.id,
        name="US-05",
        producer="Fermentis",
        product_id="US-05",
        form="dry",
        amount=1.0,
        amount_unit="pkg",
    )
    db.add(culture)

    # Add hop inventory (Citra 2024 lot, Citra 2025 lot, Mosaic 2025 lot)
    inv_citra_2024 = HopInventory(
        variety="Citra",
        amount_grams=100.0,
        alpha_acid_percent=12.0,
        crop_year=2024,
        form="pellet",
    )
    inv_citra_2025 = HopInventory(
        variety="Citra",
        amount_grams=50.0,
        alpha_acid_percent=13.0,
        crop_year=2025,
        form="pellet",
    )
    inv_mosaic_2025 = HopInventory(
        variety="Mosaic",
        amount_grams=40.0,
        alpha_acid_percent=11.5,
        crop_year=2025,
        form="pellet",
    )
    db.add_all([inv_citra_2024, inv_citra_2025, inv_mosaic_2025])

    # Add yeast inventory
    inv_yeast = YeastInventory(
        custom_name="US-05",
        quantity=3,
        form="dry",
    )
    db.add(inv_yeast)

    # Create batch linked to recipe
    batch = Batch(
        name="Test IPA Batch #1",
        status="planning",
        recipe_id=recipe.id,
    )
    db.add(batch)

    await db.flush()
    await db.commit()

    return {
        "db": db,
        "recipe_id": recipe.id,
        "batch_id": batch.id,
        "citra_2024_id": inv_citra_2024.id,
        "citra_2025_id": inv_citra_2025.id,
        "mosaic_2025_id": inv_mosaic_2025.id,
        "yeast_id": inv_yeast.id,
    }


async def _load_recipe(db: AsyncSession, recipe_id: int) -> Recipe:
    """Load a recipe with eagerly-loaded hops and cultures."""
    result = await db.execute(
        select(Recipe)
        .where(Recipe.id == recipe_id)
        .options(selectinload(Recipe.hops), selectinload(Recipe.cultures))
    )
    return result.scalar_one()


@patch("backend.services.inventory.get_settings")
class TestInventoryDeductionIntegration:
    """Integration tests for inventory deduction with real async SQLite."""

    @pytest.mark.asyncio
    async def test_deduction_fifo_oldest_first(self, mock_settings, seeded_db):
        """Deduction uses FIFO: Citra deducts from 2024 lot first."""
        mock_settings.return_value.is_local = True
        db = seeded_db["db"]

        recipe = await _load_recipe(db, seeded_db["recipe_id"])
        await deduct_inventory_for_batch(db, seeded_db["batch_id"], recipe, "test-user")
        await db.commit()

        # Reload inventory items to check amounts
        citra_2024 = await db.get(HopInventory, seeded_db["citra_2024_id"])
        await db.refresh(citra_2024)
        citra_2025 = await db.get(HopInventory, seeded_db["citra_2025_id"])
        await db.refresh(citra_2025)
        mosaic_2025 = await db.get(HopInventory, seeded_db["mosaic_2025_id"])
        await db.refresh(mosaic_2025)
        yeast = await db.get(YeastInventory, seeded_db["yeast_id"])
        await db.refresh(yeast)

        # Citra needed 60g: 2024 lot (100g) deducted first -> 40g remaining
        assert citra_2024.amount_grams == 40.0
        # 2025 lot untouched since 2024 had enough
        assert citra_2025.amount_grams == 50.0
        # Mosaic needed 30g: 40g -> 10g
        assert mosaic_2025.amount_grams == 10.0
        # Yeast needed 1 pkg: 3 -> 2
        assert yeast.quantity == 2

    @pytest.mark.asyncio
    async def test_deduction_records_created(self, mock_settings, seeded_db):
        """After deduction, InventoryDeduction records are created."""
        mock_settings.return_value.is_local = True
        db = seeded_db["db"]

        recipe = await _load_recipe(db, seeded_db["recipe_id"])
        await deduct_inventory_for_batch(db, seeded_db["batch_id"], recipe, "test-user")
        await db.commit()

        # Query all deduction records for this batch
        result = await db.execute(
            select(InventoryDeduction).where(
                InventoryDeduction.batch_id == seeded_db["batch_id"]
            )
        )
        deductions = result.scalars().all()

        # Should have 3 records: 1 Citra hop + 1 Mosaic hop + 1 US-05 yeast
        assert len(deductions) == 3

        # Verify deduction details
        hop_deductions = [d for d in deductions if d.ingredient_type == "hop"]
        yeast_deductions = [d for d in deductions if d.ingredient_type == "yeast"]
        assert len(hop_deductions) == 2
        assert len(yeast_deductions) == 1

        # Check hop names
        hop_names = {d.ingredient_name for d in hop_deductions}
        assert hop_names == {"Citra", "Mosaic"}

        # Check yeast deduction
        assert yeast_deductions[0].ingredient_name == "US-05"
        assert yeast_deductions[0].amount_deducted == 1.0
        assert yeast_deductions[0].amount_unit == "pkg"

    @pytest.mark.asyncio
    async def test_reversal_restores_inventory(self, mock_settings, seeded_db):
        """Deduct then reverse: all inventory quantities restored to original values."""
        mock_settings.return_value.is_local = True
        db = seeded_db["db"]

        recipe = await _load_recipe(db, seeded_db["recipe_id"])
        await deduct_inventory_for_batch(db, seeded_db["batch_id"], recipe, "test-user")
        await db.commit()

        # Now reverse
        restorations = await reverse_inventory_deductions(db, seeded_db["batch_id"])
        await db.commit()

        assert len(restorations) == 3

        # Reload and verify original values are restored
        citra_2024 = await db.get(HopInventory, seeded_db["citra_2024_id"])
        await db.refresh(citra_2024)
        citra_2025 = await db.get(HopInventory, seeded_db["citra_2025_id"])
        await db.refresh(citra_2025)
        mosaic_2025 = await db.get(HopInventory, seeded_db["mosaic_2025_id"])
        await db.refresh(mosaic_2025)
        yeast = await db.get(YeastInventory, seeded_db["yeast_id"])
        await db.refresh(yeast)

        assert citra_2024.amount_grams == 100.0
        assert citra_2025.amount_grams == 50.0
        assert mosaic_2025.amount_grams == 40.0
        assert yeast.quantity == 3

    @pytest.mark.asyncio
    async def test_double_reversal_is_noop(self, mock_settings, seeded_db):
        """Deduct, reverse, reverse again: second reversal is a no-op."""
        mock_settings.return_value.is_local = True
        db = seeded_db["db"]

        recipe = await _load_recipe(db, seeded_db["recipe_id"])
        await deduct_inventory_for_batch(db, seeded_db["batch_id"], recipe, "test-user")
        await db.commit()

        # First reversal
        first_restorations = await reverse_inventory_deductions(db, seeded_db["batch_id"])
        await db.commit()
        assert len(first_restorations) == 3

        # Second reversal - should be no-op
        second_restorations = await reverse_inventory_deductions(db, seeded_db["batch_id"])
        await db.commit()
        assert second_restorations == []

        # Inventory should still be at original values (unchanged from first reversal)
        citra_2024 = await db.get(HopInventory, seeded_db["citra_2024_id"])
        await db.refresh(citra_2024)
        citra_2025 = await db.get(HopInventory, seeded_db["citra_2025_id"])
        await db.refresh(citra_2025)
        mosaic_2025 = await db.get(HopInventory, seeded_db["mosaic_2025_id"])
        await db.refresh(mosaic_2025)
        yeast = await db.get(YeastInventory, seeded_db["yeast_id"])
        await db.refresh(yeast)

        assert citra_2024.amount_grams == 100.0
        assert citra_2025.amount_grams == 50.0
        assert mosaic_2025.amount_grams == 40.0
        assert yeast.quantity == 3

    @pytest.mark.asyncio
    async def test_cross_lot_fifo_split(self, mock_settings, async_db):
        """When one lot is insufficient, deduction spans to the next lot."""
        mock_settings.return_value.is_local = True
        db = async_db

        # Recipe needs 120g Citra — more than any single lot
        recipe = Recipe(name="Big IPA", type="All Grain")
        db.add(recipe)
        await db.flush()

        hop = RecipeHop(
            recipe_id=recipe.id, name="Citra", form="pellet",
            alpha_acid_percent=12.0, amount_grams=120.0,
        )
        db.add(hop)

        # Two lots: 2024 has 100g, 2025 has 50g
        inv1 = HopInventory(variety="Citra", amount_grams=100.0, crop_year=2024, form="pellet")
        inv2 = HopInventory(variety="Citra", amount_grams=50.0, crop_year=2025, form="pellet")
        db.add_all([inv1, inv2])

        batch = Batch(name="Big IPA #1", status="planning", recipe_id=recipe.id)
        db.add(batch)
        await db.flush()
        await db.commit()

        recipe = await _load_recipe(db, recipe.id)
        report = await deduct_inventory_for_batch(db, batch.id, recipe, "test-user")
        await db.commit()

        # Should have 2 deduction records (split across lots)
        assert len(report) == 2

        await db.refresh(inv1)
        await db.refresh(inv2)
        # 2024 lot fully consumed: 100 - 100 = 0
        assert inv1.amount_grams == 0.0
        # 2025 lot partially consumed: 50 - 20 = 30
        assert inv2.amount_grams == 30.0

    @pytest.mark.asyncio
    async def test_insufficient_inventory_partial_deduction(self, mock_settings, async_db):
        """When total inventory is less than needed, deducts what's available."""
        mock_settings.return_value.is_local = True
        db = async_db

        # Recipe needs 80g Citra but only 50g available
        recipe = Recipe(name="Short IPA", type="All Grain")
        db.add(recipe)
        await db.flush()

        hop = RecipeHop(
            recipe_id=recipe.id, name="Citra", form="pellet",
            alpha_acid_percent=12.0, amount_grams=80.0,
        )
        db.add(hop)

        inv = HopInventory(variety="Citra", amount_grams=50.0, crop_year=2024, form="pellet")
        db.add(inv)

        batch = Batch(name="Short IPA #1", status="planning", recipe_id=recipe.id)
        db.add(batch)
        await db.flush()
        await db.commit()

        recipe = await _load_recipe(db, recipe.id)
        report = await deduct_inventory_for_batch(db, batch.id, recipe, "test-user")
        await db.commit()

        # Should deduct what's available (50g), not fail
        assert len(report) == 1
        assert report[0]["amount_deducted"] == 50.0

        await db.refresh(inv)
        assert inv.amount_grams == 0.0
