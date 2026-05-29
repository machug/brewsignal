"""Backfill: resolve NULL recipe.style_id from the free-text type field.

Recipes imported before the import-path fix (tilt_ui-ru9) landed with
style_id=NULL even when their style was knowable. The companion code fixes
stop new NULLs at the source (importer resolves the BeerJSON style name;
resolve_style_id gained an alias map). This migration is the one-time
historical cleanup for rows already in the database.

Signal: recipe.type. Some legacy/UI recipes recorded the style there
("Irish Stout", "Hazy IPA") rather than a recipe type. resolve_style_id maps
those — including colloquial aliases (NEIPA, XPA) — to a styles.id FK. Genuine
type values ("all-grain", "extract") match no style and are left NULL: the
backfill never guesses from name/notes, so it cannot assign a wrong style.

Runs after style seeding (it resolves against the seeded BJCP table) and is
gated on a config flag so it only sweeps once. Idempotent regardless: it only
touches rows where style_id IS NULL.
"""
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from backend.models import Config, Recipe
from backend.services.style_resolver import resolve_style_id

logger = logging.getLogger(__name__)

_FLAG_KEY = "backfill_recipe_style_id_complete"


async def backfill_null_style_ids(session: AsyncSession) -> int:
    """Resolve style_id for every recipe where it's NULL, from recipe.type.

    Returns the number of recipes updated. Commits only when something changed.
    """
    recipes = (
        await session.execute(select(Recipe).where(Recipe.style_id.is_(None)))
    ).scalars().all()

    updated = 0
    for recipe in recipes:
        # allow_substring=False: recipe.type is a noisy field. A bare "IPA"
        # must not substring-match to "English IPA"; only exact names and
        # curated aliases ("NEIPA", "Irish Stout") are trustworthy enough to
        # write as an FK during an unattended backfill.
        resolved = await resolve_style_id(
            session, recipe.type, allow_substring=False
        )
        if resolved:
            recipe.style_id = resolved
            updated += 1

    if updated:
        await session.commit()
    return updated


async def migrate_backfill_recipe_style_id(engine: AsyncEngine) -> None:
    """One-time historical backfill, gated on a config flag.

    Opens its own session (the styles table must be seeded first, so this runs
    at the end of init_db, not inside the schema-migration connection blocks).
    """
    from backend.database import async_session_factory

    logger.info("Running migration: backfill_recipe_style_id")
    async with async_session_factory() as session:
        flag = await session.get(Config, _FLAG_KEY)
        if flag is not None:
            logger.info("backfill_recipe_style_id already completed, skipping")
            return

        updated = await backfill_null_style_ids(session)

        session.add(Config(key=_FLAG_KEY, value="true"))
        await session.commit()
        logger.info(
            "backfill_recipe_style_id completed: %d recipe(s) backfilled", updated
        )
