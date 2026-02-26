"""Inventory deduction service for batch brewing.

Handles checking ingredient availability, deducting inventory when a batch
starts brewing, and reversing deductions if a batch is rolled back.

Three main functions:
- check_inventory_availability: Pure function for pre-brew checks
- deduct_inventory_for_batch: Async DB function that FIFO-deducts inventory
- reverse_inventory_deductions: Async DB function that restores deducted amounts
"""

import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.config import get_settings
from backend.models import (
    HopInventory,
    InventoryDeduction,
    Recipe,
    YeastInventory,
)

logger = logging.getLogger(__name__)


def check_inventory_availability(
    recipe_hops: list,
    recipe_cultures: list,
    hop_inventory: list,
    yeast_inventory: list,
) -> dict:
    """Check if inventory has sufficient ingredients for a recipe.

    Pure function - no DB access. Takes pre-fetched lists and returns
    an availability report.

    Args:
        recipe_hops: List of RecipeHop objects (need .name, .form, .amount_grams)
        recipe_cultures: List of RecipeCulture objects (need .name, .producer,
            .product_id, .amount, .amount_unit)
        hop_inventory: List of HopInventory objects (need .variety, .form, .amount_grams)
        yeast_inventory: List of YeastInventory objects (need .custom_name,
            .yeast_strain (with .name), .quantity)

    Returns:
        dict with keys:
            hops: list of availability entries per recipe hop
            yeast: list of availability entries per recipe culture
            all_sufficient: bool, True only if every ingredient has enough
    """
    all_sufficient = True

    # --- Hops ---
    # Build a lookup of total available grams by lowercase variety name
    hop_available: dict[str, float] = {}
    for inv_item in hop_inventory:
        key = inv_item.variety.lower()
        hop_available[key] = hop_available.get(key, 0.0) + inv_item.amount_grams

    hop_results = []
    for hop in recipe_hops:
        name_lower = hop.name.lower()
        needed = hop.amount_grams
        available = hop_available.get(name_lower, 0.0)
        sufficient = available >= needed

        entry = {
            "name": hop.name,
            "form": hop.form,
            "needed": needed,
            "needed_unit": "g",
            "available": available,
            "sufficient": sufficient,
        }

        if not sufficient:
            entry["shortage"] = round(needed - available, 2)
            all_sufficient = False

        hop_results.append(entry)

    # --- Yeast ---
    # Build a lookup of total available quantity by lowercase name
    # Match against custom_name or yeast_strain.name
    yeast_available: dict[str, float] = {}
    for inv_item in yeast_inventory:
        # Determine the name to use for matching
        name = None
        if inv_item.custom_name:
            name = inv_item.custom_name.lower()
        elif inv_item.yeast_strain and inv_item.yeast_strain.name:
            name = inv_item.yeast_strain.name.lower()

        if name:
            yeast_available[name] = yeast_available.get(name, 0.0) + inv_item.quantity

    yeast_results = []
    for culture in recipe_cultures:
        name_lower = culture.name.lower()
        needed = culture.amount if culture.amount is not None else 1.0
        needed_unit = culture.amount_unit if culture.amount_unit else "pkg"
        available = yeast_available.get(name_lower, 0.0)
        sufficient = available >= needed

        entry = {
            "name": culture.name,
            "producer": culture.producer,
            "needed": needed,
            "needed_unit": needed_unit,
            "available": available,
            "sufficient": sufficient,
        }

        if not sufficient:
            entry["shortage"] = round(needed - available, 2)
            all_sufficient = False

        yeast_results.append(entry)

    return {
        "hops": hop_results,
        "yeast": yeast_results,
        "all_sufficient": all_sufficient,
    }


async def deduct_inventory_for_batch(
    db: AsyncSession,
    batch_id: int,
    recipe: Recipe,
    user_id: Optional[str] = None,
) -> list[dict]:
    """Deduct inventory items for a batch's recipe ingredients.

    Uses FIFO ordering: oldest crop_year first for hops, oldest expiry_date
    first for yeast. Does NOT block if insufficient - deducts what's available
    and logs a warning.

    Args:
        db: Async database session
        batch_id: The batch being brewed
        recipe: Recipe with eagerly-loaded hops and cultures
        user_id: Owner UUID for multi-tenant filtering (cloud mode)

    Returns:
        List of dicts describing each deduction made
    """
    settings = get_settings()
    deductions = []

    # --- Deduct hops ---
    for recipe_hop in recipe.hops:
        remaining_needed = recipe_hop.amount_grams

        # Query matching hop inventory, FIFO by crop_year then created_at
        query = select(HopInventory).where(
            HopInventory.variety.ilike(recipe_hop.name),
            HopInventory.amount_grams > 0,
        )

        # Multi-tenant filtering
        if not settings.is_local and user_id is not None:
            query = query.where(HopInventory.user_id == user_id)

        query = query.order_by(
            HopInventory.crop_year.asc().nulls_last(),
            HopInventory.created_at.asc(),
        )

        result = await db.execute(query)
        inventory_items = result.scalars().all()

        if not inventory_items:
            logger.warning(
                "No inventory found for hop '%s' (batch %d) - skipping deduction",
                recipe_hop.name,
                batch_id,
            )
            continue

        total_available = sum(item.amount_grams for item in inventory_items)
        if total_available < remaining_needed:
            logger.warning(
                "Insufficient hop inventory for '%s' (batch %d): "
                "need %.1fg, have %.1fg - deducting what's available",
                recipe_hop.name,
                batch_id,
                remaining_needed,
                total_available,
            )

        for inv_item in inventory_items:
            if remaining_needed <= 0:
                break

            deduct_amount = min(inv_item.amount_grams, remaining_needed)
            inv_item.amount_grams = round(inv_item.amount_grams - deduct_amount, 1)
            remaining_needed = round(remaining_needed - deduct_amount, 1)

            deduction = InventoryDeduction(
                batch_id=batch_id,
                ingredient_type="hop",
                inventory_item_id=inv_item.id,
                ingredient_name=recipe_hop.name,
                amount_deducted=deduct_amount,
                amount_unit="g",
            )
            db.add(deduction)

            deductions.append({
                "ingredient_type": "hop",
                "ingredient_name": recipe_hop.name,
                "inventory_item_id": inv_item.id,
                "amount_deducted": deduct_amount,
                "amount_unit": "g",
            })

    # --- Deduct yeast ---
    for culture in recipe.cultures:
        needed_qty = culture.amount if culture.amount is not None else 1.0
        needed_unit = culture.amount_unit if culture.amount_unit else "pkg"
        remaining_needed = needed_qty

        # Query matching yeast inventory, FIFO by expiry_date then created_at
        # Match by case-insensitive name against custom_name or yeast_strain.name
        # We need to check both fields, so use a subquery approach
        query = select(YeastInventory).options(
            selectinload(YeastInventory.yeast_strain)
        ).where(
            YeastInventory.quantity > 0,
        )

        # Multi-tenant filtering
        if not settings.is_local and user_id is not None:
            query = query.where(YeastInventory.user_id == user_id)

        query = query.order_by(
            YeastInventory.expiry_date.asc().nulls_last(),
            YeastInventory.created_at.asc(),
        )

        result = await db.execute(query)
        all_yeast_items = result.scalars().all()

        # Filter in Python for case-insensitive name matching
        # (since we need to check custom_name OR yeast_strain.name)
        culture_name_lower = culture.name.lower()
        matching_items = []
        for inv_item in all_yeast_items:
            item_name = None
            if inv_item.custom_name:
                item_name = inv_item.custom_name.lower()
            elif inv_item.yeast_strain and inv_item.yeast_strain.name:
                item_name = inv_item.yeast_strain.name.lower()

            if item_name == culture_name_lower:
                matching_items.append(inv_item)

        if not matching_items:
            logger.warning(
                "No inventory found for yeast '%s' (batch %d) - skipping deduction",
                culture.name,
                batch_id,
            )
            continue

        total_available = sum(item.quantity for item in matching_items)
        if total_available < remaining_needed:
            logger.warning(
                "Insufficient yeast inventory for '%s' (batch %d): "
                "need %.1f %s, have %d - deducting what's available",
                culture.name,
                batch_id,
                remaining_needed,
                needed_unit,
                total_available,
            )

        for inv_item in matching_items:
            if remaining_needed <= 0:
                break

            deduct_amount = min(inv_item.quantity, remaining_needed)
            inv_item.quantity -= int(deduct_amount)
            remaining_needed -= deduct_amount

            deduction = InventoryDeduction(
                batch_id=batch_id,
                ingredient_type="yeast",
                inventory_item_id=inv_item.id,
                ingredient_name=culture.name,
                amount_deducted=deduct_amount,
                amount_unit=needed_unit,
            )
            db.add(deduction)

            deductions.append({
                "ingredient_type": "yeast",
                "ingredient_name": culture.name,
                "inventory_item_id": inv_item.id,
                "amount_deducted": deduct_amount,
                "amount_unit": needed_unit,
            })

    await db.flush()

    logger.info(
        "Deducted %d inventory items for batch %d",
        len(deductions),
        batch_id,
    )

    return deductions


async def reverse_inventory_deductions(
    db: AsyncSession,
    batch_id: int,
) -> list[dict]:
    """Reverse all inventory deductions for a batch.

    Finds all non-reversed InventoryDeduction records for the batch,
    restores amounts to the original inventory items, and marks them
    as reversed. Double-reversal is a no-op (already reversed records
    are skipped).

    Args:
        db: Async database session
        batch_id: The batch whose deductions to reverse

    Returns:
        List of dicts describing each restoration made
    """
    # Find all non-reversed deductions for this batch
    query = select(InventoryDeduction).where(
        InventoryDeduction.batch_id == batch_id,
        InventoryDeduction.reversed == False,  # noqa: E712
    )
    result = await db.execute(query)
    deduction_records = result.scalars().all()

    if not deduction_records:
        logger.info("No unreversed deductions found for batch %d", batch_id)
        return []

    restorations = []

    for deduction in deduction_records:
        if deduction.ingredient_type == "hop":
            # Restore hop inventory
            inv_query = select(HopInventory).where(
                HopInventory.id == deduction.inventory_item_id
            )
            inv_result = await db.execute(inv_query)
            inv_item = inv_result.scalar_one_or_none()

            if inv_item:
                inv_item.amount_grams += deduction.amount_deducted
                logger.debug(
                    "Restored %.1fg of '%s' to hop inventory item %d",
                    deduction.amount_deducted,
                    deduction.ingredient_name,
                    inv_item.id,
                )
            else:
                logger.warning(
                    "Hop inventory item %d not found for reversal "
                    "(deduction %d, batch %d) - marking as reversed anyway",
                    deduction.inventory_item_id,
                    deduction.id,
                    batch_id,
                )

        elif deduction.ingredient_type == "yeast":
            # Restore yeast inventory
            inv_query = select(YeastInventory).where(
                YeastInventory.id == deduction.inventory_item_id
            )
            inv_result = await db.execute(inv_query)
            inv_item = inv_result.scalar_one_or_none()

            if inv_item:
                inv_item.quantity += int(deduction.amount_deducted)
                logger.debug(
                    "Restored %d of '%s' to yeast inventory item %d",
                    int(deduction.amount_deducted),
                    deduction.ingredient_name,
                    inv_item.id,
                )
            else:
                logger.warning(
                    "Yeast inventory item %d not found for reversal "
                    "(deduction %d, batch %d) - marking as reversed anyway",
                    deduction.inventory_item_id,
                    deduction.id,
                    batch_id,
                )

        # Mark deduction as reversed
        deduction.reversed = True

        restorations.append({
            "ingredient_type": deduction.ingredient_type,
            "ingredient_name": deduction.ingredient_name,
            "inventory_item_id": deduction.inventory_item_id,
            "amount_restored": deduction.amount_deducted,
            "amount_unit": deduction.amount_unit,
        })

    await db.flush()

    logger.info(
        "Reversed %d inventory deductions for batch %d",
        len(restorations),
        batch_id,
    )

    return restorations
