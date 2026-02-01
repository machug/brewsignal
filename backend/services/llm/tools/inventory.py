"""Inventory management tools for the AI brewing assistant."""

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import select, or_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.config import get_settings
from backend.models import (
    HopInventory, YeastInventory, YeastStrain, Equipment, Batch, Recipe
)


def _user_owns_hop_condition(user_id: Optional[str]):
    """Create a SQLAlchemy condition for hop ownership.

    In LOCAL mode: includes user's hops + "local" user + unclaimed (NULL)
    In CLOUD mode: strict user_id filtering
    """
    settings = get_settings()
    if settings.is_local:
        return or_(
            HopInventory.user_id == user_id,
            HopInventory.user_id == "local",
            HopInventory.user_id.is_(None),
        )
    return HopInventory.user_id == user_id


def _user_owns_yeast_condition(user_id: Optional[str]):
    """Create a SQLAlchemy condition for yeast ownership."""
    settings = get_settings()
    if settings.is_local:
        return or_(
            YeastInventory.user_id == user_id,
            YeastInventory.user_id == "local",
            YeastInventory.user_id.is_(None),
        )
    return YeastInventory.user_id == user_id


def _user_owns_equipment_condition(user_id: Optional[str]):
    """Create a SQLAlchemy condition for equipment ownership."""
    settings = get_settings()
    if settings.is_local:
        return or_(
            Equipment.user_id == user_id,
            Equipment.user_id == "local",
            Equipment.user_id.is_(None),
        )
    return Equipment.user_id == user_id


async def search_inventory_hops(
    db: AsyncSession,
    query: Optional[str] = None,
    min_amount_grams: Optional[float] = None,
    form: Optional[str] = None,
    limit: int = 20,
    user_id: Optional[str] = None,
) -> dict[str, Any]:
    """Search the user's hop inventory."""
    stmt = select(HopInventory).order_by(HopInventory.variety)

    # Filter by user ownership
    if user_id:
        stmt = stmt.where(_user_owns_hop_condition(user_id))

    if query:
        stmt = stmt.where(HopInventory.variety.ilike(f"%{query}%"))
    if min_amount_grams is not None:
        stmt = stmt.where(HopInventory.amount_grams >= min_amount_grams)
    if form:
        stmt = stmt.where(HopInventory.form == form)

    stmt = stmt.limit(limit)

    result = await db.execute(stmt)
    hops = result.scalars().all()

    if not hops:
        return {
            "count": 0,
            "message": "No hops found in inventory",
            "hops": []
        }

    return {
        "count": len(hops),
        "hops": [
            {
                "id": h.id,
                "variety": h.variety,
                "amount_grams": round(h.amount_grams, 1),
                "alpha_acid_percent": h.alpha_acid_percent,
                "form": h.form,
                "crop_year": h.crop_year,
                "storage_location": h.storage_location,
            }
            for h in hops
        ]
    }


async def search_inventory_yeast(
    db: AsyncSession,
    query: Optional[str] = None,
    type: Optional[str] = None,
    form: Optional[str] = None,
    include_expired: bool = False,
    limit: int = 20,
    user_id: Optional[str] = None,
) -> dict[str, Any]:
    """Search the user's yeast inventory."""
    stmt = (
        select(YeastInventory)
        .options(selectinload(YeastInventory.yeast_strain))
        .order_by(YeastInventory.expiry_date.asc().nullsfirst())
    )

    # Filter by user ownership
    if user_id:
        stmt = stmt.where(_user_owns_yeast_condition(user_id))

    if query:
        # Search in both yeast strain name and custom name
        stmt = stmt.outerjoin(YeastStrain).where(
            or_(
                YeastInventory.custom_name.ilike(f"%{query}%"),
                YeastStrain.name.ilike(f"%{query}%"),
                YeastStrain.product_id.ilike(f"%{query}%"),
            )
        )

    if type:
        stmt = stmt.outerjoin(YeastStrain).where(YeastStrain.type == type.lower())

    if form:
        stmt = stmt.where(YeastInventory.form == form)

    if not include_expired:
        now = datetime.now(timezone.utc)
        stmt = stmt.where(
            or_(
                YeastInventory.expiry_date.is_(None),
                YeastInventory.expiry_date > now,
            )
        )

    stmt = stmt.limit(limit)

    result = await db.execute(stmt)
    yeasts = result.scalars().all()

    if not yeasts:
        return {
            "count": 0,
            "message": "No yeast found in inventory",
            "yeasts": []
        }

    now = datetime.now(timezone.utc)

    return {
        "count": len(yeasts),
        "yeasts": [
            {
                "id": y.id,
                "name": y.yeast_strain.name if y.yeast_strain else y.custom_name,
                "producer": y.yeast_strain.producer if y.yeast_strain else None,
                "product_id": y.yeast_strain.product_id if y.yeast_strain else None,
                "type": y.yeast_strain.type if y.yeast_strain else None,
                "quantity": y.quantity,
                "form": y.form,
                "expiry_date": y.expiry_date.isoformat() if y.expiry_date else None,
                "days_until_expiry": (y.expiry_date.replace(tzinfo=timezone.utc) - now).days if y.expiry_date else None,
                "generation": y.generation,
                "storage_location": y.storage_location,
            }
            for y in yeasts
        ]
    }


async def check_recipe_ingredients(
    db: AsyncSession,
    hop_varieties: Optional[list[str]] = None,
    yeast_query: Optional[str] = None,
    user_id: Optional[str] = None,
) -> dict[str, Any]:
    """Check if user has specific hops and yeast in inventory."""
    result = {
        "hops": {"requested": [], "available": [], "missing": []},
        "yeast": {"requested": None, "available": [], "found": False}
    }

    # Check hops
    if hop_varieties:
        result["hops"]["requested"] = hop_varieties
        for variety in hop_varieties:
            stmt = select(HopInventory).where(
                HopInventory.variety.ilike(f"%{variety}%"),
                HopInventory.amount_grams > 0
            )
            if user_id:
                stmt = stmt.where(_user_owns_hop_condition(user_id))
            hop_result = await db.execute(stmt)
            hops = hop_result.scalars().all()

            if hops:
                for h in hops:
                    result["hops"]["available"].append({
                        "variety": h.variety,
                        "amount_grams": round(h.amount_grams, 1),
                        "alpha_acid_percent": h.alpha_acid_percent,
                    })
            else:
                result["hops"]["missing"].append(variety)

    # Check yeast
    if yeast_query:
        result["yeast"]["requested"] = yeast_query
        now = datetime.now(timezone.utc)

        stmt = (
            select(YeastInventory)
            .options(selectinload(YeastInventory.yeast_strain))
            .outerjoin(YeastStrain)
            .where(
                YeastInventory.quantity > 0,
                or_(
                    YeastInventory.expiry_date.is_(None),
                    YeastInventory.expiry_date > now,
                ),
                or_(
                    YeastInventory.custom_name.ilike(f"%{yeast_query}%"),
                    YeastStrain.name.ilike(f"%{yeast_query}%"),
                    YeastStrain.product_id.ilike(f"%{yeast_query}%"),
                    YeastStrain.type.ilike(f"%{yeast_query}%"),
                )
            )
        )
        if user_id:
            stmt = stmt.where(_user_owns_yeast_condition(user_id))

        yeast_result = await db.execute(stmt)
        yeasts = yeast_result.scalars().all()

        if yeasts:
            result["yeast"]["found"] = True
            for y in yeasts:
                result["yeast"]["available"].append({
                    "name": y.yeast_strain.name if y.yeast_strain else y.custom_name,
                    "product_id": y.yeast_strain.product_id if y.yeast_strain else None,
                    "quantity": y.quantity,
                    "form": y.form,
                    "days_until_expiry": (y.expiry_date.replace(tzinfo=timezone.utc) - now).days if y.expiry_date else None,
                })

    return result


async def get_inventory_summary(
    db: AsyncSession,
    user_id: Optional[str] = None,
) -> dict[str, Any]:
    """Get a summary of the user's brewing inventory."""
    now = datetime.now(timezone.utc)
    expiry_cutoff = now + timedelta(days=30)

    # Hop summary - filter by user
    hop_stmt = select(
        func.count(HopInventory.id).label("total_items"),
        func.sum(HopInventory.amount_grams).label("total_grams"),
        func.count(func.distinct(HopInventory.variety)).label("unique_varieties"),
    )
    if user_id:
        hop_stmt = hop_stmt.where(_user_owns_hop_condition(user_id))
    hop_result = await db.execute(hop_stmt)
    hop_row = hop_result.one()

    # Yeast summary - filter by user
    yeast_stmt = select(
        func.count(YeastInventory.id).label("total_items"),
        func.sum(YeastInventory.quantity).label("total_quantity"),
    ).where(YeastInventory.quantity > 0)
    if user_id:
        yeast_stmt = yeast_stmt.where(_user_owns_yeast_condition(user_id))
    yeast_result = await db.execute(yeast_stmt)
    yeast_row = yeast_result.one()

    # Expiring soon - filter by user
    expiring_stmt = select(func.count(YeastInventory.id)).where(
        YeastInventory.expiry_date.is_not(None),
        YeastInventory.expiry_date <= expiry_cutoff,
        YeastInventory.expiry_date > now,
        YeastInventory.quantity > 0,
    )
    if user_id:
        expiring_stmt = expiring_stmt.where(_user_owns_yeast_condition(user_id))
    expiring_result = await db.execute(expiring_stmt)
    expiring_count = expiring_result.scalar() or 0

    return {
        "hops": {
            "total_items": hop_row.total_items or 0,
            "total_grams": round(hop_row.total_grams or 0, 1),
            "unique_varieties": hop_row.unique_varieties or 0,
        },
        "yeast": {
            "total_items": yeast_row.total_items or 0,
            "total_quantity": yeast_row.total_quantity or 0,
            "expiring_within_30_days": expiring_count,
        }
    }


async def get_equipment(
    db: AsyncSession,
    type: Optional[str] = None,
    active_only: bool = True,
    user_id: Optional[str] = None,
) -> dict[str, Any]:
    """Get user's brewing equipment."""
    stmt = select(Equipment).order_by(Equipment.type, Equipment.name)

    # Filter by user ownership
    if user_id:
        stmt = stmt.where(_user_owns_equipment_condition(user_id))

    if type:
        stmt = stmt.where(Equipment.type == type)

    if active_only:
        stmt = stmt.where(Equipment.is_active == True)

    result = await db.execute(stmt)
    equipment_list = result.scalars().all()

    if not equipment_list:
        return {
            "count": 0,
            "message": "No equipment found. Add your brewing equipment in the Inventory page.",
            "equipment": [],
            "brewing_defaults": None
        }

    # Find primary fermenter or all-in-one for default batch size
    primary_fermenter = None
    for eq in equipment_list:
        if eq.type in ("fermenter", "all_in_one") and eq.capacity_liters:
            if primary_fermenter is None or eq.type == "all_in_one":
                primary_fermenter = eq

    brewing_defaults = None
    if primary_fermenter:
        # Default batch size is typically 80-90% of fermenter capacity for headspace
        default_batch_size = round(primary_fermenter.capacity_liters * 0.85, 1)
        brewing_defaults = {
            "batch_size_liters": default_batch_size,
            "fermenter_capacity_liters": primary_fermenter.capacity_liters,
            "primary_fermenter": primary_fermenter.name,
            "efficiency_percent": 72  # Default efficiency - could be made configurable
        }

    return {
        "count": len(equipment_list),
        "equipment": [
            {
                "id": eq.id,
                "name": eq.name,
                "type": eq.type,
                "brand": eq.brand,
                "model": eq.model,
                "capacity_liters": eq.capacity_liters,
                "capacity_kg": eq.capacity_kg,
                "is_active": eq.is_active,
                "notes": eq.notes,
            }
            for eq in equipment_list
        ],
        "brewing_defaults": brewing_defaults
    }
