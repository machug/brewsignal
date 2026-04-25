"""Backfill: retag 0-minute boil hops as whirlpool/flameout additions.

Pre-2.13.0 imports of Brewfather Whirlpool hops landed as
`use=add_to_boil` with `duration.value=0` (the converter mismapped
Whirlpool, fixed in tilt_ui-53n). The IBU calculator correctly returns
zero utilization for a 0-minute boil, so those hops contribute nothing
even though they were the source recipe's flameout/whirlpool additions.

Heuristic: a `use=add_to_boil` (or short-form `boil`) hop with a
duration of 0 minutes is unambiguously a flameout/whirlpool addition —
no real recipe boils for 0 minutes. Retag to `add_to_whirlpool` so the
new stand-time IBU model credits them.

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
    if not isinstance(timing, dict):
        return False
    use = (timing.get('use') or '').lower()
    if use not in ('add_to_boil', 'boil'):
        return False
    duration = timing.get('duration') or {}
    if isinstance(duration, dict):
        value = duration.get('value')
    else:
        value = duration
    try:
        return float(value or 0) == 0.0
    except (TypeError, ValueError):
        return False


def _is_zero_min_boil_ext_hop(hop: dict) -> bool:
    if not isinstance(hop, dict):
        return False
    use = (hop.get('use') or '').lower()
    if use not in ('add_to_boil', 'boil'):
        return False
    try:
        return float(hop.get('boil_time_minutes') or 0) == 0.0
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
