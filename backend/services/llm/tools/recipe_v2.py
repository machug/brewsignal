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

The assistant's view differs from the plain export in three ways:
- the stat fields (original_gravity...) carry the recipe's declared targets
  when it has them, so the model reasons about the source beer's numbers;
- each hop carries its own "brewsignal" extras (whirlpool temperature...),
  which v2 otherwise links by list position;
- every ingredient list is present, so "/…/miscellaneous_additions/-" works.
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
# v2 stat field -> (target column, unit) : the source beer's declared numbers
_TARGET_FIELDS = {
    "original_gravity": ("target_og", "sg"),
    "final_gravity": ("target_fg", "sg"),
    "alcohol_by_volume": ("target_abv", "%"),
    "ibu_estimate": ("target_ibu", "IBUs"),
    "color_estimate": ("target_srm", "SRM"),
}


def _is_num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _touches(operations: list[dict], prefix: str) -> bool:
    """True when an operation's path is prefix or below it (not just a string prefix)."""
    for op in operations:
        path = str((op or {}).get("path", ""))
        if path == prefix or path.startswith(prefix + "/"):
            return True
    return False


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
    would hit the wrong item. Replace the whole list instead. A null value on add or
    replace is refused too: some providers fill a forgotten value with null, which
    would silently blank a field. To delete something, use remove.
    """
    doc = json.loads(json.dumps(doc))
    if not isinstance(operations, list) or not operations:
        raise PatchError("operations must be a non-empty list")
    shifting: Counter = Counter()
    for op in operations:
        if not isinstance(op, dict):
            raise PatchError("each operation must be an object with op, path and value")
        parts = _parse_pointer(op.get("path", ""))
        if op.get("op") == "remove" or (op.get("op") == "add" and parts[-1] != "-"):
            if parts[-1].isdigit():
                shifting["/" + "/".join(parts[:-1])] += 1
    crowded = [p for p, n in shifting.items() if n > 1]
    if crowded:
        raise PatchError(
            f"several inserts/removes by index in {crowded[0]}; replace that whole list in one operation instead"
        )
    for n, op in enumerate(operations):
        kind, path = op.get("op"), op.get("path")
        if kind not in ("add", "remove", "replace"):
            raise PatchError(f"operation {n}: op must be add, remove or replace")
        parts = _parse_pointer(path)
        if parts == [""]:
            raise PatchError(f"operation {n}: cannot change the whole document")
        if kind != "remove" and op.get("value") is None:
            raise PatchError(f"operation {n}: {kind} needs a non-null value (use remove to delete)")
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
# Load / export / import
# =============================================================================


async def _load(db: AsyncSession, recipe_id: int, user_id: Optional[str], check_owner: bool = True) -> Optional[Recipe]:
    stmt = (
        select(Recipe)
        .options(selectinload(Recipe.style), *(selectinload(getattr(Recipe, c)) for c in CHILDREN))
        .where(Recipe.id == recipe_id)
    )
    if check_owner:  # local mode allows all; cloud requires the owner (None owns nothing of others)
        stmt = stmt.where(_user_owns_recipe_condition(user_id))
    return (await db.execute(stmt)).scalar_one_or_none()


def _hops(doc: dict) -> list:
    hops = ((doc.get("recipe") or {}).get("ingredients") or {}).get("hop_additions")
    return hops if isinstance(hops, list) else []


def _inline_hop_extras(doc: dict) -> None:
    """Move brewsignal.hop_additions[i] (whirlpool temp, dry-hop stage...) onto hop i as "brewsignal".

    v2 links those extras to hops by list position. Inline, a patch that removes or
    reorders hops carries each hop's extras with it instead of shifting them onto
    the wrong hop.
    """
    brewsignal = doc.get("brewsignal")
    entries = brewsignal.pop("hop_additions", None) if isinstance(brewsignal, dict) else None
    hops = _hops(doc)
    for entry in entries or []:
        i = entry.get("index") if isinstance(entry, dict) else None
        if _is_num(i) and isinstance(i, int) and 0 <= i < len(hops) and isinstance(hops[i], dict):
            extras = {k: v for k, v in entry.items() if k not in ("index", "name", "ref_use")}
            hops[i]["brewsignal"] = {**(hops[i].get("brewsignal") or {}), **extras}


def _outline_hop_extras(doc: dict) -> dict:
    """Inverse of _inline_hop_extras on a copy: positions taken from the hops' current order."""
    doc = json.loads(json.dumps(doc))
    entries = []
    for i, hop in enumerate(_hops(doc)):
        if not isinstance(hop, dict):
            continue
        extras = hop.pop("brewsignal", None)
        if isinstance(extras, dict) and extras:
            entries.append({"index": i, "name": hop.get("name"),
                            "ref_use": (hop.get("timing") or {}).get("use") if isinstance(hop.get("timing"), dict) else None,
                            **extras})
    if entries:
        brewsignal = doc.get("brewsignal") if isinstance(doc.get("brewsignal"), dict) else {}
        brewsignal["hop_additions"] = entries
        doc["brewsignal"] = brewsignal
    return doc


def _export(recipe: Recipe) -> dict:
    """The assistant's view of a recipe (see module docstring)."""
    doc = RecipeToBrewSignalV2Converter().convert(recipe)
    r = doc.setdefault("recipe", {})
    for field, (column, unit) in _TARGET_FIELDS.items():
        target = getattr(recipe, column)
        if target is not None:
            r[field] = {"value": target, "unit": unit}
    ingredients = r.setdefault("ingredients", {})
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
    """Import a v2 document as a new (flushed, uncommitted) recipe with calculated stats.

    Call inside a savepoint: on failure the importer leaves rollback to it.
    """
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
        if _is_num(calc) and _is_num(target) and abs(calc - target) > tol:
            out.append(f"Calculated {key.upper()} {calc:g} is off the target {target:g}; adjust the recipe if this is a clone.")
    return out


def _amount(a: Any) -> str:
    if isinstance(a, dict) and _is_num(a.get("value")):
        return f"{a['value']:g} {a.get('unit', '')}".strip()
    return ""


def _label(item: Any) -> str:
    """Short human label for one ingredient or step, e.g. 'Citra 162 g, whirlpool 79 C 20 min'."""
    if not isinstance(item, dict):
        return str(item)
    bits = [str(item.get("name", "?"))]
    if item.get("is_extract") and _is_num(item.get("amount_ml")):
        bits.append(f"{item['amount_ml']:g} ml extract")
    for key in ("amount", "step_temperature", "start_temperature"):
        if _amount(item.get(key)):
            bits.append(_amount(item[key]))
    timing = item.get("timing") if isinstance(item.get("timing"), dict) else {}
    extra = item.get("brewsignal") if isinstance(item.get("brewsignal"), dict) else {}
    use = extra.get("hop_use") or timing.get("use", "")
    when = [use, _amount(extra.get("temperature")), _amount(extra.get("stand_time"))
            or _amount(timing.get("duration")) or _amount(timing.get("time"))]
    if extra.get("dry_hop_stage") is not None:
        when.append(f"stage {extra['dry_hop_stage']}")
    when_text = " ".join(str(x) for x in when if x)
    if when_text:
        bits.append(when_text)
    if _amount(item.get("step_time")):
        bits.append(_amount(item["step_time"]))
    return ", ".join(bits)


_SECTION_PATHS = {
    "Grains & sugars": ("ingredients", "fermentable_additions"),
    "Hops": ("ingredients", "hop_additions"),
    "Yeast": ("ingredients", "culture_additions"),
    "Other ingredients": ("ingredients", "miscellaneous_additions"),
    "Mash": ("mash", "mash_steps"),
    "Fermentation": ("fermentation", "fermentation_steps"),
}


def _section_items(doc: dict, path: tuple) -> list:
    node = (doc.get("recipe") or {}).get(path[0])
    items = node.get(path[1]) if isinstance(node, dict) else None
    return items if isinstance(items, list) else []


def _sections(doc: dict) -> dict[str, list[str]]:
    return {name: [_label(x) for x in _section_items(doc, path)] for name, path in _SECTION_PATHS.items()}


def _leaves(node: Any, prefix: str = "") -> dict[str, Any]:
    """Flatten to {dotted.path: value}; a {"value", "unit"} object stays one leaf."""
    if isinstance(node, dict) and not node:
        return {}  # empty container: nothing to show
    if isinstance(node, dict) and not (set(node) <= {"value", "unit"} and "value" in node):
        out: dict[str, Any] = {}
        for k, v in node.items():
            out.update(_leaves(v, f"{prefix}.{k}" if prefix else str(k)))
        return out
    return {prefix: node}


def _show(v: Any) -> str:
    if v is None:
        return "(none)"
    if _amount(v):
        return _amount(v)
    text = v if isinstance(v, str) else json.dumps(v)
    return text if len(text) <= 60 else text[:57] + "..."


def _diff(old: dict, new: dict) -> list[str]:
    """Every change, in words: list items by label, everything else field by field."""
    lines = []
    for name, path in _SECTION_PATHS.items():
        canon = lambda x: json.dumps(x, sort_keys=True)  # noqa: E731
        before = Counter(canon(x) for x in _section_items(old, path))
        after = Counter(canon(x) for x in _section_items(new, path))
        lines += [f"{name}: removed {_label(json.loads(x))}" for x in (before - after).elements()]
        lines += [f"{name}: added {_label(json.loads(x))}" for x in (after - before).elements()]

    def rest(doc):
        d = json.loads(json.dumps(doc))
        r = d.get("recipe") if isinstance(d.get("recipe"), dict) else {}
        for section, key in _SECTION_PATHS.values():
            if isinstance(r.get(section), dict):
                r[section].pop(key, None)
        for k in ("created_at", "exported_at"):
            d.pop(k, None)
        return _leaves(d)

    a, b = rest(old), rest(new)
    for path in sorted(set(a) | set(b)):
        if a.get(path) != b.get(path):
            lines.append(f"{path.removeprefix('recipe.')}: {_show(a.get(path))} -> {_show(b.get(path))}")
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


async def _undo(savepoint) -> None:
    """Roll a savepoint back even when a failed flush already marked it inactive.

    An inactive savepoint still needs its rollback before the session works again
    (PendingRollbackError otherwise). Only an already-closed one is skipped.
    """
    try:
        await savepoint.rollback()
    except Exception:  # already closed: nothing left to undo
        pass


def _prepare_edit_document(current: dict, operations: list[dict]) -> dict:
    """Apply the patch and drop links the patch made stale."""
    document = apply_patch(current, operations)
    if _touches(operations, "/recipe/style") and isinstance(document.get("brewsignal"), dict):
        # brewsignal.style_id wins over the style name on import; a renamed style must re-resolve
        document["brewsignal"].pop("style_id", None)
    return document


async def _patched(db, recipe_id, operations, user_id):
    """(existing recipe, current doc, patched doc) or an error dict."""
    existing = await _load(db, recipe_id, user_id)
    if existing is None:
        return None, {"error": f"Recipe {recipe_id} not found"}
    current = _export(existing)
    try:
        return (existing, current, _prepare_edit_document(current, operations)), None
    except PatchError as e:
        return None, {"error": f"Patch not applied: {e}", "hint": "Call get_recipe for the current paths."}


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
    old_doc = before = None
    if recipe_id is not None:
        found, err = await _patched(db, recipe_id, operations, user_id)
        if err:
            return err
        existing, old_doc, document = found
        before = _stats(existing)
    savepoint = await db.begin_nested()
    try:
        new, errors = await _import(db, document)
        if new is None:
            return {"error": "Recipe would not import", "details": errors}
        if recipe_id is not None:
            # Targets the edit does not touch stay as they were on the real save
            for field, (column, _unit) in _TARGET_FIELDS.items():
                if not _touches(operations, f"/recipe/{field}"):
                    setattr(new, column, before["targets"][column.removeprefix("target_")])
        out = {"valid": True, "name": new.name, **_stats(new), "warnings": _warnings(new), "sections": _sections(document)}
        if recipe_id is not None:
            out["before"] = before
            out["changes"] = _diff(old_doc, document) or ["No change"]
        return out
    except Exception as e:  # malformed model output must come back as an error, not a crash
        logger.info("Recipe preview failed: %s", e)
        return {"error": f"Recipe would not import: {e}"}
    finally:
        await _undo(savepoint)


async def save_recipe_document(db: AsyncSession, document: dict[str, Any], user_id: Optional[str] = None) -> dict[str, Any]:
    savepoint = await db.begin_nested()
    try:
        recipe, errors = await _import(db, document)
        if recipe is None:
            await _undo(savepoint)
            return {"error": "Recipe not saved", "details": errors}
        recipe.user_id = user_id
        await db.commit()
    except Exception as e:
        logger.exception("Assistant recipe save failed")
        await _undo(savepoint)
        return {"error": f"Recipe not saved: {e}"}
    return _result(await _load(db, recipe.id, None, check_owner=False), "saved")


async def update_recipe_document(
    db: AsyncSession, recipe_id: int, operations: list[dict], user_id: Optional[str] = None
) -> dict[str, Any]:
    """Patch a recipe's v2 document and store the result, keeping its id (batches point at it)."""
    found, err = await _patched(db, recipe_id, operations, user_id)
    if err:
        return err
    existing, _old, document = found
    keep = _IDENTITY | _LEGACY | {
        column for field, (column, _u) in _TARGET_FIELDS.items() if not _touches(operations, f"/recipe/{field}")
    }
    savepoint = await db.begin_nested()
    try:
        new, errors = await _import(db, document)
        if new is None:
            await _undo(savepoint)
            return {"error": "Recipe not updated", "details": errors}
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
    except Exception as e:
        logger.exception("Assistant recipe update failed")
        await _undo(savepoint)
        return {"error": f"Recipe not updated: {e}"}
    db.expunge(existing)
    return _result(await _load(db, recipe_id, None, check_owner=False), "updated")
