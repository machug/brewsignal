"""End-to-end round-trip for Abstrax extract hops (tilt_ui-0l5 phase 1).

Saves a recipe containing one extract and one pellet via the LLM save_recipe
path, then reloads it and asserts the extract markers survived persistence.
The LLM path is the canonical ingress for structured hop data today — a
dedicated REST PUT /recipes/{id}/hops endpoint is deferred until Phase 2.
"""
import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.database import async_session_factory, init_db
from backend.models import Recipe
from backend.services.llm.tools.recipe import (
    calculate_recipe_stats,
    get_recipe,
    normalize_recipe_to_beerjson,
    save_recipe,
)


@pytest.fixture(scope="module", autouse=True)
async def setup_db():
    """Initialize the shared SQLite schema once for this module.

    Mirrors test_extract_hops_schema.py — init_db is idempotent and the
    other extract tests in this suite already rely on the shared DB.
    """
    await init_db()


def _extract_recipe_id(save_result: dict) -> int:
    """save_recipe returns {"recipe_id": N, ...} on success."""
    assert save_result.get("success") is True, (
        f"save_recipe failed: {save_result}"
    )
    rid = save_result.get("recipe_id")
    assert rid, f"save_recipe did not return recipe_id; result={save_result}"
    return rid


@pytest.mark.asyncio
async def test_extract_round_trip_persists_field_values():
    """Save -> reload via ORM: extract identity columns survive the trip."""
    async with async_session_factory() as db:
        save_result = await save_recipe(
            db,
            {
                "name": "Extract Round Trip Persist Test",
                "batch_size_liters": 20,
                "boil_time_minutes": 60,
                "hops": [
                    {
                        "name": "Mosaic",
                        "amount": 20,
                        "alpha_acid": 12,
                        "use": "boil",
                        "time": 60,
                    },
                    {
                        "name": "Quantum MOS",
                        "is_extract": True,
                        "amount_ml": 2.5,
                        "use": "dry_hop",
                    },
                ],
            },
            user_id="local",
            user_confirmed=True,
        )

    recipe_id = _extract_recipe_id(save_result)

    # Reload directly via the ORM so we know we're reading from the DB
    # (not from any in-memory normalization cache).
    async with async_session_factory() as db:
        row = (await db.execute(
            select(Recipe)
            .options(selectinload(Recipe.hops))
            .where(Recipe.id == recipe_id)
        )).scalar_one()
        hops = list(row.hops)

    assert len(hops) == 2, (
        f"expected 2 hops, got {[(h.name, h.is_extract) for h in hops]}"
    )
    mosaic = next(h for h in hops if h.name == "Mosaic")
    quantum = next(h for h in hops if h.name == "Quantum MOS")

    # Extract row -- iso-alpha / lupulin dosing.
    assert quantum.is_extract is True
    assert quantum.amount_ml == 2.5
    # amount_grams sentinel: extracts dose in mL, the column is NOT NULL so
    # the serializer writes 0.0 (see recipe_serializer._create_hop).
    assert quantum.amount_grams in (0, 0.0)
    # Alpha is meaningless for an extract; either None or 0 is acceptable.
    assert quantum.alpha_acid_percent in (None, 0, 0.0)

    # Pellet row -- traditional bittering hop must keep its alpha + grams.
    assert mosaic.is_extract is False
    assert mosaic.alpha_acid_percent and mosaic.alpha_acid_percent > 0
    assert mosaic.amount_grams and mosaic.amount_grams > 0


@pytest.mark.asyncio
async def test_extract_does_not_perturb_ibu_after_round_trip():
    """Baseline pellet-only IBU == mixed pellet+extract IBU after save+reload.

    save_recipe computes IBU via calculate_recipe_stats and persists it to
    Recipe.ibu. get_recipe surfaces that stored value, so comparing the two
    reloaded recipes proves the extract contributed zero IBU end-to-end.
    Also verifies the recipe shape from get_recipe carries is_extract +
    amount_ml so the frontend / future agent can see them.
    """
    async with async_session_factory() as db:
        baseline_save = await save_recipe(
            db,
            {
                "name": "Pellet Only Round Trip Baseline",
                "batch_size_liters": 20,
                "boil_time_minutes": 60,
                "hops": [
                    {"name": "Mosaic", "amount": 20, "alpha_acid": 12,
                     "use": "boil", "time": 60},
                ],
            },
            user_id="local",
            user_confirmed=True,
        )
        baseline_id = _extract_recipe_id(baseline_save)

        mixed_save = await save_recipe(
            db,
            {
                "name": "Mixed Pellet Plus Extract Round Trip",
                "batch_size_liters": 20,
                "boil_time_minutes": 60,
                "hops": [
                    {"name": "Mosaic", "amount": 20, "alpha_acid": 12,
                     "use": "boil", "time": 60},
                    {"name": "Quantum MOS", "is_extract": True,
                     "amount_ml": 2.5, "use": "dry_hop"},
                ],
            },
            user_id="local",
            user_confirmed=True,
        )
        mixed_id = _extract_recipe_id(mixed_save)

    # Reload through get_recipe -- this is the dict shape the frontend
    # / chat agent actually consumes.
    async with async_session_factory() as db:
        baseline_recipe = await get_recipe(db, baseline_id)
        mixed_recipe = await get_recipe(db, mixed_id)

    # Sanity: get_recipe should not return an error dict.
    assert "error" not in baseline_recipe, baseline_recipe
    assert "error" not in mixed_recipe, mixed_recipe

    # Stored IBU comes from calculate_recipe_stats at save time.
    baseline_ibu = baseline_recipe["ibu"]
    mixed_ibu = mixed_recipe["ibu"]
    assert baseline_ibu > 0, f"pellet-only baseline must have IBU; got {baseline_ibu}"
    assert mixed_ibu == pytest.approx(baseline_ibu), (
        f"extract perturbed stored IBU: baseline={baseline_ibu} mixed={mixed_ibu}"
    )

    # Re-running calculate_recipe_stats on the same payload that was saved
    # must also skip the extract (defends against future regressions where
    # the cached recipe.ibu drifts from what the calc would produce now).
    recomputed_mixed = calculate_recipe_stats(normalize_recipe_to_beerjson({
        "name": "Mixed Recompute",
        "batch_size_liters": 20,
        "boil_time_minutes": 60,
        "hops": [
            {"name": "Mosaic", "amount": 20, "alpha_acid": 12,
             "use": "boil", "time": 60},
            {"name": "Quantum MOS", "is_extract": True,
             "amount_ml": 2.5, "use": "dry_hop"},
        ],
    }))["ibu"]
    assert recomputed_mixed == pytest.approx(baseline_ibu), (
        f"recomputed mixed IBU drifted from baseline: "
        f"recomputed={recomputed_mixed} baseline={baseline_ibu}"
    )

    # Confirm get_recipe surfaces the extract markers on the hops list.
    # This is what the future inventory / detail UI binds against.
    mixed_hops = mixed_recipe.get("hops") or []
    extract = next(
        (h for h in mixed_hops if h.get("name") == "Quantum MOS"), None
    )
    assert extract is not None, (
        f"Quantum MOS missing from get_recipe hops: {mixed_hops}"
    )
    assert extract.get("is_extract") is True, (
        f"is_extract not surfaced by get_recipe: {extract}"
    )
    assert extract.get("amount_ml") == 2.5, (
        f"amount_ml not surfaced by get_recipe: {extract}"
    )

    # And the pellet must be marked False (not True or missing).
    pellet = next(
        (h for h in mixed_hops if h.get("name") == "Mosaic"), None
    )
    assert pellet is not None
    assert pellet.get("is_extract") is False
    assert pellet.get("amount_ml") is None
