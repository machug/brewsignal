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


def _resolve(name: str, library: dict[str, HopVariety]) -> tuple[Optional[HopVariety], bool]:
    """Library variety for a name, and whether it was a fuzzy (non-exact) match."""
    key = name.strip().lower()
    if key in library:
        return library[key], False
    close = difflib.get_close_matches(key, library.keys(), n=1, cutoff=0.85)
    return (library[close[0]], True) if close else (None, False)


def _key(name: str, library: dict[str, HopVariety]) -> str:
    """Grouping key shared by pasted names and stock rows, so 'Tettnanger'
    stock and a pasted 'Tettnang' land on the same library variety."""
    var, _ = _resolve(name, library)
    return (var.name if var else name.strip()).lower()


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
    and notes and gets the new total; other rows of that hop are merged into
    it. With replace=True, rows not in the list are removed. A listed hop
    with 0 g is removed in either mode.

    Raises StaleStockError when applying with an expected_stock_version that
    no longer matches the current stock.
    """
    library = {
        v.name.lower(): v for v in (await db.execute(select(HopVariety))).scalars()
    }

    wanted: dict[str, dict[str, Any]] = {}
    for item in items:
        var, fuzzy = _resolve(item.name, library)
        variety = var.name if var else item.name.strip()
        entry = wanted.setdefault(variety.lower(), {
            "variety": variety,
            "amount_grams": 0.0,
            "alpha_acid_percent": _alpha(var) if var else None,
            "in_library": var is not None,
            "input_names": [],
            "fuzzy_from": [],  # typed names that were guessed to mean this hop
        })
        entry["amount_grams"] += item.amount_grams
        entry["input_names"].append(item.name)
        if fuzzy and item.name.strip() not in entry["fuzzy_from"]:
            entry["fuzzy_from"].append(item.name.strip())

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
        existing.setdefault(_key(row.variety, library), []).append(row)
    # A fuzzy stock match is trusted only when it is the sole spelling in its
    # group (stock 'Tettnanger' -> Tettnang). If distinct stock names land on
    # one variety (Solaris + Polaris -> Polaris), keep only the exact name
    # there and give the others their own key, so they are never merged.
    for key in list(existing):
        group = existing[key]
        if len({r.variety.strip().lower() for r in group}) > 1:
            existing[key] = [r for r in group if r.variety.strip().lower() == key]
            for r in group:
                if r.variety.strip().lower() != key:
                    existing.setdefault(r.variety.strip().lower(), []).append(r)
            if not existing[key]:
                del existing[key]

    # The listed amount is the new TOTAL for that hop. Several stock rows of
    # one hop (crop years, forms) are merged into the first row, which keeps
    # its crop year, storage and notes.
    # remove holds (row, reason): "not_listed" rows are removed only on replace.
    add, update, unchanged, remove = [], [], [], []
    for key, want in wanted.items():
        have = existing.get(key, [])
        if not have:
            if want["amount_grams"] > 0:
                add.append(want)
            continue
        if want["amount_grams"] <= 0:
            remove.extend((r, "zero", want["variety"]) for r in have)
            continue
        first, extras = have[0], have[1:]
        total = sum(r.amount_grams for r in have)
        same_name = all(r.variety.strip().lower() == want["variety"].lower() for r in have)
        if not extras and same_name and abs(total - want["amount_grams"]) <= 1e-9:
            unchanged.append(first)  # a guessed name match is listed as an update so the card warns
        else:
            update.append((first, want, total))
        remove.extend((r, "merged", want["variety"]) for r in extras)
    remove.extend((r, "not_listed", None) for key, rs in existing.items() if key not in wanted for r in rs)
    if not replace:
        remove = [x for x in remove if x[1] != "not_listed"]

    def guessed_as(row: HopInventory, variety: Optional[str]) -> Optional[str]:
        """Listed hop a stock row was fuzzy-matched to, shown on the card."""
        return variety if variety and row.variety.strip().lower() != variety.lower() else None

    plan = {
        "replace": replace,
        "applied": False,
        "stock_version": stock_version,
        "add": [
            {k: w[k] for k in ("variety", "amount_grams", "alpha_acid_percent", "in_library", "fuzzy_from")}
            for w in add
        ],
        "update": [
            {"id": r.id, "variety": r.variety, "from_grams": total, "to_grams": w["amount_grams"],
             "fuzzy_from": w["fuzzy_from"], "guessed_as": guessed_as(r, w["variety"])}
            for r, w, total in update
        ],
        "remove": [
            {"id": r.id, "variety": r.variety, "amount_grams": r.amount_grams,
             "crop_year": r.crop_year, "form": r.form,
             "reason": why, "replace_only": why == "not_listed", "guessed_as": guessed_as(r, v)}
            for r, why, v in remove
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
    for r, w, _ in update:
        r.amount_grams = w["amount_grams"]
    for r, _, _ in remove:
        await db.delete(r)
    await db.commit()
    plan["applied"] = True
    return plan
