"""Backfill: repair recipe.color_srm computed from color-less grain bills.

Recipes saved before the color-enrichment fix (tilt_ui-81n) have color_srm
computed when a dark grain's color was missing — defaulted to pale — so dark
beers read as ~3 SRM. This one-time sweep enriches any missing fermentable
colors from the reference table and recomputes color_srm from the (now colored)
grain bill via the canonical brewing calc.

Only color_srm is rewritten, and only when the recompute is substantially
HIGHER than the stored value — the failure mode always understates SRM (dark
grains treated as pale). A recomputed value that is equal or lower is left
alone, so brewer-declared/imported color_srm (which can legitimately differ
from the simplified grain-bill calc) is never clobbered downward. IBU and
gravity are left untouched. Gated on a config flag; idempotent.
"""
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import selectinload

from backend.models import Config, Recipe
from backend.services.brewing import calculate_recipe_stats
from backend.services.fermentable_colors import resolve_fermentable_color_srm

logger = logging.getLogger(__name__)

_FLAG_KEY = "backfill_recipe_color_srm_complete"
# Only repair when the recompute exceeds the stored value by this much. The
# bug always understates SRM, so we never lower an existing (possibly brewer-
# declared) color_srm — that would clobber good imported data.
_MIN_UNDERSTATEMENT_SRM = 2.0


async def backfill_recipe_color_srm(session: AsyncSession) -> int:
    """Enrich missing fermentable colors, recompute color_srm from the grain
    bill, and update recipes whose stored color_srm is wrong.

    Returns the number of recipes whose color_srm was changed.
    """
    recipes = (
        await session.execute(
            select(Recipe).options(
                selectinload(Recipe.fermentables),
                selectinload(Recipe.hops),
                selectinload(Recipe.cultures),
            )
        )
    ).scalars().all()

    changed = 0
    dirty = False
    for recipe in recipes:
        if not recipe.fermentables:
            continue

        # Enrich any fermentable missing a color from the reference table so
        # the recompute sees real grain colors.
        for ferm in recipe.fermentables:
            if ferm.color_srm is None:
                srm = await resolve_fermentable_color_srm(session, ferm.name)
                if srm is not None:
                    ferm.color_srm = srm
                    dirty = True

        new_srm = calculate_recipe_stats(recipe).get("color_srm")
        if new_srm is None:
            continue

        if recipe.color_srm is None or (
            float(new_srm) - float(recipe.color_srm) > _MIN_UNDERSTATEMENT_SRM
        ):
            recipe.color_srm = new_srm
            changed += 1
            dirty = True

    if dirty:
        await session.commit()
    return changed


async def migrate_backfill_recipe_color_srm(engine: AsyncEngine) -> None:
    """One-time historical repair, gated on a config flag. Runs after seeding
    (needs the seeded fermentable reference table)."""
    from backend.database import async_session_factory

    logger.info("Running migration: backfill_recipe_color_srm")
    async with async_session_factory() as session:
        flag = await session.get(Config, _FLAG_KEY)
        if flag is not None:
            logger.info("backfill_recipe_color_srm already completed, skipping")
            return

        changed = await backfill_recipe_color_srm(session)

        session.add(Config(key=_FLAG_KEY, value="true"))
        await session.commit()
        logger.info(
            "backfill_recipe_color_srm completed: %d recipe(s) repaired", changed
        )
