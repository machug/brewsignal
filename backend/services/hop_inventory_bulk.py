"""Bulk hop inventory update from a pasted list (name + grams).

Shared by the assistant tool (preview only) and POST /api/inventory/hops/bulk
(preview or apply, called by the chat confirm card). Names are resolved
against the hop library so variety spelling and alpha acid come from there.
"""

import difflib
import hashlib
from typing import Any, Optional

from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import get_settings
from backend.models import HopInventory, HopVariety


class BulkHopItem(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    amount_grams: float = Field(ge=0)


class BulkHopRequest(BaseModel):
    items: list[BulkHopItem] = Field(min_length=1, max_length=200)
    replace: bool = False  # True: remove stock not in the list
    dry_run: bool = True   # Safe default: preview only
    # stock_version from the preview the user confirmed; apply is refused if
    # the inventory changed since, so the user never applies an unseen plan.
    expected_stock_version: Optional[str] = None


class StaleStockError(Exception):
    pass


def hop_owner_condition(user_id: Optional[str]):
    """Same ownership rule as the hop inventory routes."""
    if get_settings().is_local:
        return or_(HopInventory.user_id == user_id, HopInventory.user_id.is_(None))
    return HopInventory.user_id == user_id


def _resolve(name: str, library: dict[str, HopVariety]) -> Optional[HopVariety]:
    key = name.strip().lower()
    if key in library:
        return library[key]
    close = difflib.get_close_matches(key, library.keys(), n=1, cutoff=0.85)
    return library[close[0]] if close else None


def _alpha(v: HopVariety) -> Optional[float]:
    vals = [x for x in (v.alpha_acid_low, v.alpha_acid_high) if x is not None]
    return round(sum(vals) / len(vals), 1) if vals else None


async def bulk_update_hops(
    db: AsyncSession,
    user_id: Optional[str],
    items: list[BulkHopItem],
    replace: bool,
    dry_run: bool,
    expected_stock_version: Optional[str] = None,
) -> dict[str, Any]:
    """Plan (and unless dry_run, apply) a bulk hop inventory update.

    Duplicate names in the list are summed. Existing stock is matched by
    variety (case-insensitive); the first row keeps its crop year, storage
    and notes and gets the new amount. With replace=True, rows not in the
    list (and duplicate rows of a listed variety) are removed. A listed hop
    with 0 g is removed in either mode.

    Raises StaleStockError when applying with an expected_stock_version that
    no longer matches the current stock.
    """
    library = {
        v.name.lower(): v for v in (await db.execute(select(HopVariety))).scalars()
    }

    wanted: dict[str, dict[str, Any]] = {}
    for item in items:
        var = _resolve(item.name, library)
        variety = var.name if var else item.name.strip()
        entry = wanted.setdefault(variety.lower(), {
            "variety": variety,
            "amount_grams": 0.0,
            "alpha_acid_percent": _alpha(var) if var else None,
            "in_library": var is not None,
            "input_names": [],
        })
        entry["amount_grams"] += item.amount_grams
        entry["input_names"].append(item.name)

    rows = (await db.execute(
        select(HopInventory).where(hop_owner_condition(user_id)).order_by(HopInventory.id)
    )).scalars().all()
    stock_version = hashlib.sha256(
        repr([(r.id, r.variety, r.amount_grams) for r in rows]).encode()
    ).hexdigest()[:16]
    if not dry_run and expected_stock_version and expected_stock_version != stock_version:
        raise StaleStockError("Hop inventory changed since this preview")

    existing: dict[str, list[HopInventory]] = {}
    for row in rows:
        existing.setdefault(row.variety.strip().lower(), []).append(row)

    # remove holds (row, replace_only): replace_only rows are kept by add & update
    add, update, unchanged, remove = [], [], [], []
    for key, want in wanted.items():
        have = existing.get(key, [])
        if not have:
            if want["amount_grams"] > 0:
                add.append(want)
            continue
        if want["amount_grams"] <= 0:
            remove.extend((r, False) for r in have)
            continue
        first, extras = have[0], have[1:]
        if abs(first.amount_grams - want["amount_grams"]) > 1e-9:
            update.append((first, want))
        else:
            unchanged.append(first)
        remove.extend((r, True) for r in extras)
    remove.extend((r, True) for key, rs in existing.items() if key not in wanted for r in rs)
    if not replace:
        remove = [(r, ro) for r, ro in remove if not ro]

    plan = {
        "replace": replace,
        "applied": False,
        "stock_version": stock_version,
        "add": [{k: w[k] for k in ("variety", "amount_grams", "alpha_acid_percent", "in_library")} for w in add],
        "update": [
            {"id": r.id, "variety": r.variety, "from_grams": r.amount_grams, "to_grams": w["amount_grams"]}
            for r, w in update
        ],
        "remove": [
            {"id": r.id, "variety": r.variety, "amount_grams": r.amount_grams, "replace_only": ro}
            for r, ro in remove
        ],
        "unchanged": [{"id": r.id, "variety": r.variety, "amount_grams": r.amount_grams} for r in unchanged],
        "not_in_library": sorted({n for w in wanted.values() if not w["in_library"] for n in w["input_names"]}),
    }
    if dry_run:
        return plan

    for w in add:
        db.add(HopInventory(
            user_id=user_id,
            variety=w["variety"],
            amount_grams=w["amount_grams"],
            alpha_acid_percent=w["alpha_acid_percent"],
            form="pellet",
        ))
    for r, w in update:
        r.amount_grams = w["amount_grams"]
    for r, _ in remove:
        await db.delete(r)
    await db.commit()
    plan["applied"] = True
    return plan
