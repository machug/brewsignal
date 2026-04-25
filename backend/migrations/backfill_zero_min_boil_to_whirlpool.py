"""Backfill: retag 0-minute boil hops as whirlpool/flameout additions.

Pre-2.13.0 imports of Brewfather Whirlpool hops landed as
`use=add_to_boil` with `duration.value=0` (the converter mismapped
Whirlpool, fixed in tilt_ui-53n). Some legacy BeerXML imports went
through hop_timing_converter.convert_hop_timing_safe, which omits the
duration field when time_min == 0, leaving rows with no explicit zero.

Heuristic (aggressive — single-tenant deployment, owner-acknowledged
trade-off): retag any `use=add_to_boil` / short-form `boil` hop whose
duration is either explicitly 0 OR missing. The downside: legacy First
Wort additions converted by the same helper also become
`{"use":"add_to_boil"}` with no duration and will be retagged as
whirlpool. For BrewSignal's actual data set that's the right call —
the Brewfather Whirlpool case dominates and First Wort additions are
rare here. Documented so a future contributor with multi-user data can
narrow the rule.

Touches:
- recipe_hops.timing (BeerJSON-shaped JSON column)
- recipes.format_extensions.hops[*].use + .boil_time_minutes (legacy
  editor shape carried alongside)

Idempotent: skips hops already tagged whirlpool/add_to_whirlpool.
"""
import json
import logging
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

logger = logging.getLogger(__name__)


def _is_zero_min_boil_timing(timing: dict) -> bool:
    """Match `use=add_to_boil`/`boil` rows whose duration is either
    explicitly 0 or absent. See module docstring for the trade-off."""
    if not isinstance(timing, dict):
        return False
    use = (timing.get('use') or '').lower()
    if use not in ('add_to_boil', 'boil'):
        return False
    duration = timing.get('duration')
    if duration is None:
        return True  # missing duration: treat as zero (aggressive)
    if isinstance(duration, dict):
        if 'value' not in duration:
            return True  # no value: treat as zero
        value = duration['value']
    else:
        value = duration
    try:
        return float(value) == 0.0
    except (TypeError, ValueError):
        return False


def _is_zero_min_boil_ext_hop(hop: dict) -> bool:
    """Match `use=add_to_boil`/`boil` editor-shape hops whose
    boil_time_minutes is explicitly 0, missing, or null."""
    if not isinstance(hop, dict):
        return False
    use = (hop.get('use') or '').lower()
    if use not in ('add_to_boil', 'boil'):
        return False
    value = hop.get('boil_time_minutes')
    if value is None:
        return True  # missing or null: treat as zero
    try:
        return float(value) == 0.0
    except (TypeError, ValueError):
        return False


async def migrate_backfill_zero_min_boil_to_whirlpool(conn: AsyncConnection) -> None:
    logger.info("Running migration: backfill_zero_min_boil_to_whirlpool")

    # Skip if recipe_hops doesn't exist yet (fresh install with no recipes)
    result = await conn.execute(text(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='recipe_hops'"
    ))
    if not result.fetchone():
        logger.info("recipe_hops table doesn't exist yet, skipping migration")
        return

    # 1. recipe_hops.timing
    result = await conn.execute(text("SELECT id, timing FROM recipe_hops WHERE timing IS NOT NULL"))
    rows = result.fetchall()
    retagged_hops = 0
    for hop_id, timing_raw in rows:
        try:
            timing = timing_raw if isinstance(timing_raw, dict) else json.loads(timing_raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if not _is_zero_min_boil_timing(timing):
            continue
        timing['use'] = 'add_to_whirlpool'
        await conn.execute(
            text("UPDATE recipe_hops SET timing = :timing WHERE id = :id"),
            {"timing": json.dumps(timing), "id": hop_id},
        )
        retagged_hops += 1
    if retagged_hops:
        logger.info("Retagged %d zero-min boil rows in recipe_hops", retagged_hops)

    # 2. recipes.format_extensions.hops[]
    result = await conn.execute(text(
        "SELECT id, format_extensions FROM recipes WHERE format_extensions IS NOT NULL"
    ))
    rows = result.fetchall()
    retagged_recipes = 0
    for recipe_id, ext_raw in rows:
        try:
            ext = ext_raw if isinstance(ext_raw, dict) else json.loads(ext_raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        hops = ext.get('hops') if isinstance(ext, dict) else None
        if not isinstance(hops, list):
            continue
        changed = False
        for hop in hops:
            if _is_zero_min_boil_ext_hop(hop):
                hop['use'] = 'add_to_whirlpool'
                changed = True
        if changed:
            await conn.execute(
                text("UPDATE recipes SET format_extensions = :ext WHERE id = :id"),
                {"ext": json.dumps(ext), "id": recipe_id},
            )
            retagged_recipes += 1
    if retagged_recipes:
        logger.info(
            "Retagged zero-min boil hops in format_extensions for %d recipes",
            retagged_recipes,
        )

    if not retagged_hops and not retagged_recipes:
        logger.info("No zero-min boil hops to retag — nothing to do")
    logger.info("Migration backfill_zero_min_boil_to_whirlpool completed")
