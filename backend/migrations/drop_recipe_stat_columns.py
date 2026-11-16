"""Drop recipes.og/fg/abv/ibu/color_srm (tilt_ui-4x2f.5).

Stats are now calculated on read. Before the drop, nothing is lost:
  1. Running batches (at or past fermenting) with no snapshot get expected_*
     per field: the stored legacy value, else the effective stats.
  2. Per field, a stored legacy value the calculator cannot reproduce (recipe
     without fermentables, or a stored IBU > 0 where the calculator gives
     none or 0) is copied to target_* when target_* is empty.
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

    stored = {row[0]: dict(zip(legacy, row[1:])) for row in (await conn.execute(text(
        "SELECT id, " + ", ".join(legacy) + " FROM recipes"
    ))).fetchall()}
    batch_columns = {row[1] for row in (await conn.execute(text("PRAGMA table_info(batches)"))).fetchall()}
    seed_batches = all(n in batch_columns for n, _ in _EXPECTED)
    async with AsyncSession(bind=conn, expire_on_commit=False) as session:
        recipes = (await session.execute(recipe_with_ingredients_stmt())).scalars().all()
        for recipe in recipes:
            calc = calculate_recipe_stats(recipe)
            values = stored[recipe.id]
            for col, target, attr in _FIELDS:
                legacy_value = values.get(col)
                if legacy_value is None or getattr(recipe, target) is not None:
                    continue
                calculated = getattr(calc, attr) if calc else None
                # IBU is 0.0 (not None) with no boil/whirlpool hops: a stored IBU is not reproducible
                if calculated is None or (attr == "ibu" and not calculated and legacy_value > 0):
                    setattr(recipe, target, legacy_value)
        await session.flush()

        if seed_batches:
            # D6 per field: the legacy stored value (what the batch has been running
            # against) if set, else the effective stats. Soft-deleted batches included.
            nulls = " AND ".join(f"{n} IS NULL" for n, _ in _EXPECTED)
            rows = (await conn.execute(text(
                "SELECT id, recipe_id FROM batches WHERE recipe_id IS NOT NULL "
                f"AND status NOT IN ('planning', 'brewing') AND {nulls}"
            ))).fetchall()
            by_id = {r.id: r for r in recipes}
            for batch_id, recipe_id in rows:
                recipe = by_id.get(recipe_id)
                if recipe is None:
                    continue
                calc = calculate_recipe_stats(recipe)
                snap = {}
                for name, col in _EXPECTED:
                    attr = "srm" if col == "color_srm" else col
                    value = stored[recipe_id].get(col)
                    if value is None and calc is not None:
                        value = getattr(calc, attr)
                    if value is None:
                        value = getattr(recipe, "target_" + attr)
                    snap[name] = value
                sets = ", ".join(f"{n} = :{n}" for n in snap)
                await conn.execute(text(f"UPDATE batches SET {sets} WHERE id = :id"), {**snap, "id": batch_id})

    for col in legacy:
        await conn.execute(text(f"ALTER TABLE recipes DROP COLUMN {col}"))
    logger.info("Migration drop_recipe_stat_columns completed")
