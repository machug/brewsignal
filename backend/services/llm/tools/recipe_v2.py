"""Assistant recipe tools on BrewSignal Recipe Format v2 (tilt_ui-eevz.1).

The assistant reads a recipe as the same v2 document the app exports. New
recipes are sent whole; edits are sent as a short JSON Patch (add / remove /
replace) applied to the server's own current copy, so anything the model does
not mention is kept exactly as it was. Saves go through the v2 importer, so
an assistant save lands in the database exactly like importing that document:
child rows, the flat yeast_* columns and format_extensions stay consistent.

Every save/edit can be previewed first (preview_recipe_change): the import
runs inside a savepoint that is rolled back, returning calculated stats,
target deltas, warnings and a plain-language diff. The chat agent previews
before asking the user to approve, so a broken edit never reaches the card.
"""

import json
import logging
from collections import Counter
from typing import Any, Optional

from sqlalchemy import inspect as sa_inspect, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.models import Recipe
from backend.services.brewing import calculate_recipe_stats
from backend.services.converters.brewsignal_v2 import RecipeToBrewSignalV2Converter
from backend.services.fermentable_colors import resolve_fermentable_color_srm
from backend.services.importers.recipe_importer import RecipeImporter

from .recipe import _user_owns_recipe_condition

logger = logging.getLogger(__name__)

CHILDREN = (
    "fermentables", "hops", "cultures", "miscs",
    "mash_steps", "fermentation_steps", "water_profiles", "water_adjustments",
)
INGREDIENT_LISTS = ("fermentable_additions", "hop_additions", "culture_additions", "miscellaneous_additions")
# Never taken from the replacement on an edit
_IDENTITY = {"id", "user_id", "created_at"}
# BeerXML-era columns v2 cannot carry: an edit keeps them as they were
_LEGACY = {
    "brewer", "asst_brewer", "primary_age_days", "primary_temp_c", "secondary_age_days",
    "secondary_temp_c", "tertiary_age_days", "tertiary_temp_c", "age_days", "age_temp_c",
    "forced_carbonation", "priming_sugar_name", "priming_sugar_amount_kg",
    "taste_notes", "taste_rating", "date", "beerxml_content",
}
# The source beer's declared numbers: kept on an edit unless the patch sets them
_TARGETS = {"target_og", "target_fg", "target_abv", "target_ibu", "target_srm"}
_STAT_PATHS = (
    "/recipe/original_gravity", "/recipe/final_gravity", "/recipe/alcohol_by_volume",
    "/recipe/ibu_estimate", "/recipe/color_estimate",
)


# =============================================================================
# JSON Patch (RFC 6902 subset)
# =============================================================================


class PatchError(ValueError):
    pass


def _parse_pointer(path: str) -> list[str]:
    if not isinstance(path, str) or not path.startswith("/"):
        raise PatchError(f"path must start with '/': {path!r}")
    return [p.replace("~1", "/").replace("~0", "~") for p in path[1:].split("/")]


def _index(token: str, length: int, path: str, allow_end: bool) -> int:
    """Strict RFC 6901 array index: digits only, no sign, no leading zero, in range."""
    if not (token == "0" or (token.isdigit() and not token.startswith("0"))):
        raise PatchError(f"bad list index {token!r} in {path}")
    i = int(token)
    if i > length or (i == length and not allow_end):
        raise PatchError(f"index {i} out of range (list has {length} items) in {path}")
    return i


def _walk(doc: Any, parts: list[str], path: str) -> Any:
    node = doc
    for part in parts:
        if isinstance(node, list):
            node = node[_index(part, len(node), path, allow_end=False)]
        elif isinstance(node, dict) and part in node:
            node = node[part]
        else:
            raise PatchError(f"path not found: {path}")
    return node


def apply_patch(doc: dict, operations: list[dict]) -> dict:
    """Apply add/remove/replace operations to a copy of doc.

    ponytail: add/remove/replace only; move/copy/test not needed for recipe edits.
    Two position-shifting operations (insert or remove by index) on the same list are
    refused: models compute every index against the original list, so the second one
    would hit the wrong item. Replace the whole list instead.
    """
    doc = json.loads(json.dumps(doc))
    if not isinstance(operations, list) or not operations:
        raise PatchError("operations must be a non-empty list")
    shifting: Counter = Counter()
    for op in operations:
        parts = _parse_pointer((op or {}).get("path", ""))
        if (op or {}).get("op") == "remove" or ((op or {}).get("op") == "add" and parts[-1] != "-"):
            if parts[-1].isdigit():
                shifting["/" + "/".join(parts[:-1])] += 1
    crowded = [p for p, n in shifting.items() if n > 1]
    if crowded:
        raise PatchError(
            f"several inserts/removes by index in {crowded[0]}; replace that whole list in one operation instead"
        )
    for n, op in enumerate(operations):
        kind, path = (op or {}).get("op"), (op or {}).get("path")
        if kind not in ("add", "remove", "replace"):
            raise PatchError(f"operation {n}: op must be add, remove or replace")
        parts = _parse_pointer(path)
        if parts == [""]:
            raise PatchError(f"operation {n}: cannot change the whole document")
        if kind != "remove" and "value" not in op:
            raise PatchError(f"operation {n}: {kind} needs a value")
        parent, key = _walk(doc, parts[:-1], path), parts[-1]
        if isinstance(parent, list):
            if kind == "add" and key == "-":
                parent.append(op["value"])
                continue
            i = _index(key, len(parent), path, allow_end=(kind == "add"))
            if kind == "add":
                parent.insert(i, op["value"])
            elif kind == "remove":
                parent.pop(i)
            else:
                parent[i] = op["value"]
        elif isinstance(parent, dict):
            if kind in ("remove", "replace") and key not in parent:
                raise PatchError(f"operation {n}: path not found: {path}")
            if kind == "remove":
                del parent[key]
            else:
                parent[key] = op["value"]
        else:
            raise PatchError(f"operation {n}: cannot index into a value at {path}")
    return doc


# =============================================================================
# Load / import
# =============================================================================


async def _load(db: AsyncSession, recipe_id: int, user_id: Optional[str]) -> Optional[Recipe]:
    stmt = (
        select(Recipe)
        .options(selectinload(Recipe.style), *(selectinload(getattr(Recipe, c)) for c in CHILDREN))
        .where(Recipe.id == recipe_id)
    )
    if user_id:
        stmt = stmt.where(_user_owns_recipe_condition(user_id))
    return (await db.execute(stmt)).scalar_one_or_none()


def _hops(doc: dict) -> list:
    return doc.get("recipe", {}).get("ingredients", {}).get("hop_additions") or []


def _inline_hop_extras(doc: dict) -> None:
    """Move brewsignal.hop_additions[i] (whirlpool temp, dry-hop stage...) onto hop i as "brewsignal".

    v2 links those extras to hops by list position. Inline, a patch that removes or
    reorders hops carries each hop's extras with it instead of shifting them onto
    the wrong hop.
    """
    entries = (doc.get("brewsignal") or {}).pop("hop_additions", None) or []
    hops = _hops(doc)
    for entry in entries:
        i = entry.get("index")
        if isinstance(i, int) and 0 <= i < len(hops):
            extras = {k: v for k, v in entry.items() if k not in ("index", "name", "ref_use")}
            hops[i]["brewsignal"] = {**hops[i].get("brewsignal", {}), **extras}


def _outline_hop_extras(doc: dict) -> dict:
    """Inverse of _inline_hop_extras on a copy: positions taken from the hops' current order."""
    doc = json.loads(json.dumps(doc))
    entries = []
    for i, hop in enumerate(_hops(doc)):
        extras = hop.pop("brewsignal", None)
        if extras:
            entries.append({"index": i, "name": hop.get("name"),
                            "ref_use": (hop.get("timing") or {}).get("use"), **extras})
    if entries:
        brewsignal = doc.get("brewsignal") or {}
        brewsignal["hop_additions"] = entries
        doc["brewsignal"] = brewsignal
    return doc


def _export(recipe: Recipe) -> dict:
    """The assistant's view: v2 with hop extras inline and every ingredient list present."""
    doc = RecipeToBrewSignalV2Converter().convert(recipe)
    ingredients = doc.setdefault("recipe", {}).setdefault("ingredients", {})
    for key in INGREDIENT_LISTS:
        ingredients.setdefault(key, [])
    _inline_hop_extras(doc)
    return doc


async def get_recipe_document(db: AsyncSession, recipe_id: int, user_id: Optional[str] = None) -> dict[str, Any]:
    recipe = await _load(db, recipe_id, user_id)
    if recipe is None:
        return {"error": f"Recipe {recipe_id} not found"}
    return {"recipe_id": recipe.id, "document": _export(recipe)}


async def _import(db: AsyncSession, document: dict[str, Any]) -> tuple[Optional[Recipe], list[str]]:
    """Import a v2 document as a new (flushed, uncommitted) recipe with calculated stats."""
    if not isinstance(document, dict) or not isinstance(document.get("recipe"), dict):
        return None, ['document must be a v2 envelope: {"brewsignal_version": "2.0", "recipe": {...}, "brewsignal": {...}}']
    doc = {**_outline_hop_extras(document), "brewsignal_version": "2.0"}
    result = await RecipeImporter().import_recipe(json.dumps(doc), "brewsignal", db)
    if not result.success:
        return None, result.errors
    recipe = result.recipe
    # Same as the app: fill missing grain colors from the reference table, then
    # calculate OG/FG/ABV/IBU/SRM from the ingredients. Declared numbers from
    # the document stay in target_* (what the source beer claims).
    for ferm in recipe.fermentables:
        if ferm.color_srm is None:
            ferm.color_srm = await resolve_fermentable_color_srm(db, ferm.name)
    stats = calculate_recipe_stats(recipe) if (recipe.fermentables or recipe.hops) else {}
    for key in ("og", "fg", "abv", "ibu", "color_srm"):
        setattr(recipe, key, stats.get(key))
    return recipe, []


# =============================================================================
# Summaries and diffs (what the model and the approval card see)
# =============================================================================

_TARGET_TOLERANCE = {"og": 0.003, "fg": 0.003, "abv": 0.4, "ibu": 8, "srm": 3}


def _stats(recipe: Recipe) -> dict:
    return {
        "calculated": {"og": recipe.og, "fg": recipe.fg, "abv": recipe.abv, "ibu": recipe.ibu, "srm": recipe.color_srm},
        "targets": {"og": recipe.target_og, "fg": recipe.target_fg, "abv": recipe.target_abv,
                    "ibu": recipe.target_ibu, "srm": recipe.target_srm},
    }


def _warnings(recipe: Recipe) -> list[str]:
    out = []
    if not recipe.cultures:
        out.append("No yeast: add recipe.ingredients.culture_additions.")
    if not recipe.fermentables:
        out.append("No fermentables: add recipe.ingredients.fermentable_additions.")
    s = _stats(recipe)
    for key, tol in _TARGET_TOLERANCE.items():
        calc, target = s["calculated"][key], s["targets"][key]
        if calc is not None and target is not None and abs(calc - target) > tol:
            out.append(f"Calculated {key.upper()} {calc:g} is off the target {target:g}; adjust the recipe if this is a clone.")
    return out


def _amount(a: Any) -> str:
    return f"{a.get('value'):g} {a.get('unit', '')}".strip() if isinstance(a, dict) and isinstance(a.get("value"), (int, float)) else ""


def _label(item: dict) -> str:
    """Short human label for one ingredient or step, e.g. 'Citra 50 g, add_to_boil 20 min'."""
    bits = [str(item.get("name", "?"))]
    for key in ("amount", "step_temperature", "start_temperature"):
        if _amount(item.get(key)):
            bits.append(_amount(item[key]))
    timing = item.get("timing") or {}
    when = " ".join(x for x in (timing.get("use", ""), _amount(timing.get("duration")) or _amount(timing.get("time"))) if x)
    if when:
        bits.append(when)
    if _amount(item.get("step_time")):
        bits.append(_amount(item["step_time"]))
    return ", ".join(bits)


def _sections(doc: dict) -> dict[str, list[str]]:
    r = doc.get("recipe", {})
    ing = r.get("ingredients", {})
    return {
        "Grains & sugars": [_label(x) for x in ing.get("fermentable_additions") or []],
        "Hops": [_label(x) for x in ing.get("hop_additions") or []],
        "Yeast": [_label(x) for x in ing.get("culture_additions") or []],
        "Other ingredients": [_label(x) for x in ing.get("miscellaneous_additions") or []],
        "Mash": [_label(x) for x in (r.get("mash") or {}).get("mash_steps") or []],
        "Fermentation": [_label(x) for x in (r.get("fermentation") or {}).get("fermentation_steps") or []],
    }


def _diff(old: dict, new: dict) -> list[str]:
    lines = []
    for field in ("name", "type"):
        a, b = old.get("recipe", {}).get(field), new.get("recipe", {}).get(field)
        if a != b:
            lines.append(f"{field}: {a} -> {b}")
    for field in ("batch_size",):
        a, b = _amount(old.get("recipe", {}).get(field)), _amount(new.get("recipe", {}).get(field))
        if a != b:
            lines.append(f"batch size: {a} -> {b}")
    a, b = (old.get("recipe", {}).get("style") or {}).get("name"), (new.get("recipe", {}).get("style") or {}).get("name")
    if a != b:
        lines.append(f"style: {a} -> {b}")
    old_s, new_s = _sections(old), _sections(new)
    for section in old_s:
        before, after = Counter(old_s[section]), Counter(new_s[section])
        lines += [f"{section}: removed {x}" for x in (before - after).elements()]
        lines += [f"{section}: added {x}" for x in (after - before).elements()]
    if (old.get("brewsignal") or {}) != (new.get("brewsignal") or {}):
        lines.append("BrewSignal extras (water, process, yeast management) changed")
    return lines


def _result(recipe: Recipe, verb: str) -> dict[str, Any]:
    return {
        "applied": True,
        "recipe_id": recipe.id,
        "name": recipe.name,
        **_stats(recipe),
        "counts": {c: len(getattr(recipe, c)) for c in CHILDREN},
        "yeast": [c.name for c in recipe.cultures],
        "warnings": _warnings(recipe),
        "message": f"Recipe '{recipe.name}' {verb} with ID {recipe.id}",
    }


# =============================================================================
# Preview, save, update
# =============================================================================


async def _patched_document(db, recipe_id, operations, user_id):
    existing = await _load(db, recipe_id, user_id)
    if existing is None:
        return None, None, {"error": f"Recipe {recipe_id} not found"}
    current = _export(existing)
    try:
        return existing, (current, apply_patch(current, operations)), None
    except PatchError as e:
        return existing, None, {"error": f"Patch not applied: {e}", "hint": "Call get_recipe for the current paths."}


async def preview_recipe_change(
    db: AsyncSession,
    *,
    document: Optional[dict] = None,
    recipe_id: Optional[int] = None,
    operations: Optional[list[dict]] = None,
    user_id: Optional[str] = None,
) -> dict[str, Any]:
    """Dry run of a save (document) or an edit (recipe_id + operations). Nothing is stored."""
    if recipe_id is None and document is None:
        return {"error": "Give a document (new recipe) or recipe_id + operations (edit)."}
    before = None
    if recipe_id is not None:
        existing, docs, err = await _patched_document(db, recipe_id, operations, user_id)
        if err:
            return err
        before_stats = _stats(existing)
        old_doc, document = docs
    savepoint = await db.begin_nested()
    try:
        new, errors = await _import(db, document)
        if new is None:
            return {"error": "Recipe would not import", "details": errors}
        out = {
            "valid": True,
            "name": new.name,
            **_stats(new),
            "warnings": _warnings(new),
            "sections": _sections(document),
        }
        if recipe_id is not None:
            out["before"] = before_stats
            out["changes"] = _diff(old_doc, document) or ["No visible change"]
        return out
    finally:
        await savepoint.rollback()


async def save_recipe_document(db: AsyncSession, document: dict[str, Any], user_id: Optional[str] = None) -> dict[str, Any]:
    try:
        recipe, errors = await _import(db, document)
        if recipe is None:
            return {"error": "Recipe not saved", "details": errors}
        recipe.user_id = user_id
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return _result(await _load(db, recipe.id, None), "saved")


async def update_recipe_document(
    db: AsyncSession, recipe_id: int, operations: list[dict], user_id: Optional[str] = None
) -> dict[str, Any]:
    """Patch a recipe's v2 document and store the result, keeping its id (batches point at it)."""
    existing, docs, err = await _patched_document(db, recipe_id, operations, user_id)
    if err:
        return err
    stats_patched = any(str(o.get("path", "")).startswith(_STAT_PATHS) for o in operations)
    try:
        new, errors = await _import(db, docs[1])
        if new is None:
            return {"error": "Recipe not updated", "details": errors}
        keep = _IDENTITY | _LEGACY | (set() if stats_patched else _TARGETS)
        # Move children off the temp copy first, so deleting it cascades to nothing
        moved = {name: list(getattr(new, name)) for name in CHILDREN}
        for name in CHILDREN:
            getattr(existing, name).clear()  # old rows: orphan-deleted
        await db.flush()
        for attr in sa_inspect(Recipe).column_attrs:
            if attr.key not in keep:
                setattr(existing, attr.key, getattr(new, attr.key))
        for name, rows in moved.items():
            setattr(existing, name, rows)  # re-parented onto the kept recipe id
        await db.flush()
        await db.delete(new)
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    db.expunge(existing)
    return _result(await _load(db, recipe_id, None), "updated")
