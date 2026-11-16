"""Drop of recipes.og/fg/abv/ibu/color_srm (tilt_ui-4x2f.5)."""
import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import InvalidRequestError

from backend.migrations.add_recipe_target_stats import migrate_add_recipe_target_stats
from backend.migrations.drop_recipe_stat_columns import migrate_drop_recipe_stat_columns
from backend.models import Batch, Recipe, RecipeFermentable, RecipeHop

LEGACY = ("og", "fg", "abv", "ibu", "color_srm")
BOIL60 = {"use": "add_to_boil", "duration": {"value": 60, "unit": "min"}}


async def _cols(db, table="recipes"):
    return {r[1] for r in (await db.execute(text(f"PRAGMA table_info({table})"))).all()}


async def _old_schema(db):
    """The pre-4x2f.5 schema: legacy stat columns present."""
    async with db.bind.begin() as conn:
        for c in LEGACY:
            await conn.execute(text(f"ALTER TABLE recipes ADD COLUMN {c} FLOAT"))


async def _recipe(db, name, grain=True, hops=True, **legacy):
    r = Recipe(name=name, batch_size_liters=20.0, efficiency_percent=75.0)
    db.add(r)
    await db.commit()
    if grain:
        db.add(RecipeFermentable(recipe_id=r.id, name="Pale", type="grain", amount_kg=5.0,
                                 yield_percent=80.0, color_srm=3.0))
    if hops:
        db.add(RecipeHop(recipe_id=r.id, name="H", alpha_acid_percent=10.0, amount_grams=30.0, timing=BOIL60))
    await db.commit()
    sets = ", ".join(f"{k}=:{k}" for k in legacy)
    if sets:
        await db.execute(text(f"UPDATE recipes SET {sets} WHERE id=:id"), {**legacy, "id": r.id})
        await db.commit()
    return r.id


async def _run_drop(db):
    async with db.bind.begin() as conn:
        await migrate_drop_recipe_stat_columns(conn)


async def _targets(db, rid):
    return tuple((await db.execute(text(
        "SELECT target_og, target_fg, target_abv, target_ibu, target_srm FROM recipes WHERE id=:i"),
        {"i": rid})).one())


@pytest.mark.asyncio
async def test_drop_preserves_uncalculable_stats_per_field(test_db):
    await _old_schema(test_db)
    full = dict(og=1.099, fg=1.033, abv=9.9, ibu=40.0, color_srm=12.0)
    no_hops = await _recipe(test_db, "nohops", hops=False, **full)
    no_grain = await _recipe(test_db, "nograin", grain=False, hops=False, **full)
    has_target = await _recipe(test_db, "t", grain=False, hops=False, **full)
    await test_db.execute(text("UPDATE recipes SET target_og=1.050 WHERE id=:i"), {"i": has_target})
    await test_db.commit()

    await _run_drop(test_db)

    assert not (await _cols(test_db) & set(LEGACY))
    # grains but no hops: the calculator has no real IBU, so only the stored ibu is kept
    assert await _targets(test_db, no_hops) == (None, None, None, 40.0, None)
    assert await _targets(test_db, no_grain) == (1.099, 1.033, 9.9, 40.0, 12.0)
    # an existing target is never overwritten; other fields are copied
    assert await _targets(test_db, has_target) == (1.050, 1.033, 9.9, 40.0, 12.0)


@pytest.mark.asyncio
async def test_drop_is_idempotent(test_db):
    await _old_schema(test_db)
    rid = await _recipe(test_db, "x", grain=False, hops=False, og=1.05)
    await _run_drop(test_db)
    await _run_drop(test_db)
    assert (await _targets(test_db, rid))[0] == 1.05
    assert not (await _cols(test_db) & set(LEGACY))


@pytest.mark.asyncio
async def test_drop_runs_after_target_migration_on_old_db(test_db):
    await _old_schema(test_db)
    rid = await _recipe(test_db, "old", grain=False, hops=False, og=1.061, ibu=33.0)
    async with test_db.bind.begin() as conn:
        for c in ("target_og", "target_fg", "target_abv", "target_ibu", "target_srm"):
            await conn.execute(text(f"ALTER TABLE recipes DROP COLUMN {c}"))
    async with test_db.bind.begin() as conn:
        await migrate_add_recipe_target_stats(conn)
        await migrate_drop_recipe_stat_columns(conn)
    cols = await _cols(test_db)
    assert not (cols & set(LEGACY)) and "target_og" in cols
    t = await _targets(test_db, rid)
    assert (t[0], t[3]) == (1.061, 33.0)


@pytest.mark.asyncio
async def test_drop_snapshots_legacy_into_running_batches(test_db):
    """The deploy must not move a running batch: legacy values seed expected_* first."""
    await _old_schema(test_db)
    rid = await _recipe(test_db, "r", og=1.099, fg=1.033, abv=9.9, ibu=77.0, color_srm=12.0)
    test_db.add_all([Batch(name="f", status="fermenting", recipe_id=rid),
                     Batch(name="p", status="planning", recipe_id=rid)])
    await test_db.commit()
    await _run_drop(test_db)
    rows = (await test_db.execute(text("SELECT name, expected_og, expected_srm FROM batches ORDER BY name"))).all()
    assert [tuple(r) for r in rows] == [("f", 1.099, 12.0), ("p", None, None)]


@pytest.mark.asyncio
async def test_lazy_raise_catches_unloaded_ingredients(test_db):
    rid = await _recipe(test_db, "lazy")
    test_db.expire_all()
    recipe = (await test_db.execute(select(Recipe).where(Recipe.id == rid))).scalar_one()
    for rel in ("fermentables", "hops", "cultures"):
        with pytest.raises(InvalidRequestError):
            getattr(recipe, rel)


@pytest.mark.asyncio
async def test_drop_seeds_batch_per_field(test_db):
    """Legacy og set, fg NULL but calculable: expected_og = legacy, expected_fg = calculated."""
    from backend.services.recipe_stats import effective_stats, recipe_with_ingredients_stmt
    await _old_schema(test_db)
    rid = await _recipe(test_db, "partial", og=1.099)
    test_db.add(Batch(name="f", status="fermenting", recipe_id=rid))
    await test_db.commit()
    recipe = (await test_db.execute(recipe_with_ingredients_stmt().where(Recipe.id == rid))).scalar_one()
    calc = effective_stats(recipe)
    await _run_drop(test_db)
    og, fg, ibu = (await test_db.execute(text(
        "SELECT expected_og, expected_fg, expected_ibu FROM batches"))).one()
    assert (og, fg, ibu) == (1.099, calc.fg, calc.ibu)


@pytest.mark.asyncio
async def test_drop_keeps_stored_ibu_when_calculated_ibu_is_zero(test_db):
    """Only dry hops: the calculator gives 0.0 IBU, the stored 35 is kept as a target."""
    await _old_schema(test_db)
    rid = await _recipe(test_db, "dry", hops=False, ibu=35.0)
    test_db.add(RecipeHop(recipe_id=rid, name="D", alpha_acid_percent=10.0, amount_grams=50.0,
                          timing={"use": "add_to_fermentation", "duration": {"value": 3, "unit": "day"}}))
    await test_db.commit()
    await _run_drop(test_db)
    assert (await _targets(test_db, rid))[3] == 35.0
