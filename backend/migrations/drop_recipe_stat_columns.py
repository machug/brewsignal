"""Drop recipes.og/fg/abv/ibu/color_srm (tilt_ui-4x2f.5).

Stats are now calculated on read. Before the drop, nothing is lost:
  1. Running batches (at or past fermenting) with no snapshot get expected_*
     from the stored legacy values (what they have been running against).
  2. Per field, a stored legacy value the calculator cannot reproduce (recipe
     without fermentables, or IBU with no hops) is copied to target_* when
     target_* is empty.
"""
import logging

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

logger = logging.getLogger(__name__)

# legacy column -> (target column, CalculatedStats attribute)
_FIELDS = (("og", "target_og", "og"), ("fg", "target_fg", "fg"), ("abv", "target_abv", "abv"),
           ("ibu", "target_ibu", "ibu"), ("color_srm", "target_srm", "srm"))
_EXPECTED = (("expected_og", "og"), ("expected_fg", "fg"), ("expected_abv", "abv"),
             ("expected_ibu", "ibu"), ("expected_srm", "color_srm"))


async def migrate_drop_recipe_stat_columns(conn: AsyncConnection) -> None:
    from backend.models import Recipe
    from backend.services.brewing import calculate_recipe_stats
    from backend.services.recipe_stats import recipe_with_ingredients_stmt

    columns = {row[1] for row in (await conn.execute(text("PRAGMA table_info(recipes)"))).fetchall()}
    legacy = [c for c, _, _ in _FIELDS if c in columns]
    if not legacy:
        return

    batch_columns = {row[1] for row in (await conn.execute(text("PRAGMA table_info(batches)"))).fetchall()}
    if all(n in batch_columns for n, _ in _EXPECTED):
        sets = ", ".join(
            f"{n} = (SELECT r.{c} FROM recipes r WHERE r.id = batches.recipe_id)" for n, c in _EXPECTED
            if c in columns
        )
        nulls = " AND ".join(f"{n} IS NULL" for n, _ in _EXPECTED)
        await conn.execute(text(
            f"UPDATE batches SET {sets} WHERE recipe_id IS NOT NULL "
            f"AND status NOT IN ('planning', 'brewing') AND {nulls}"
        ))

    stored = {row[0]: row[1:] for row in (await conn.execute(text(
        "SELECT id, " + ", ".join(c for c, _, _ in _FIELDS) + " FROM recipes"
    ))).fetchall()}
    async with AsyncSession(bind=conn, expire_on_commit=False) as session:
        recipes = (await session.execute(recipe_with_ingredients_stmt())).scalars().all()
        for recipe in recipes:
            calc = calculate_recipe_stats(recipe)
            has_hops = any((h.amount_grams or 0) > 0 for h in recipe.hops)
            values = dict(zip((c for c, _, _ in _FIELDS), stored[recipe.id]))
            for col, target, attr in _FIELDS:
                uncalculable = calc is None or (attr == "ibu" and not has_hops)
                if uncalculable and getattr(recipe, target) is None and values[col] is not None:
                    setattr(recipe, target, values[col])
        await session.flush()

    for col in legacy:
        await conn.execute(text(f"ALTER TABLE recipes DROP COLUMN {col}"))
    logger.info("Migration drop_recipe_stat_columns completed")
