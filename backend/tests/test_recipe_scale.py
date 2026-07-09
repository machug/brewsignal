"""POST /api/recipes/{id}/scale must proportionally scale every per-batch
amount — relationship tables AND the format_extensions editor cache — then
recompute stats (tilt_ui-2kzp).
"""

import pytest
from sqlalchemy import select

from backend.models import (
    Recipe,
    RecipeFermentable,
    RecipeHop,
    RecipeMashStep,
    RecipeMisc,
    RecipeWaterAdjustment,
)


def _ipa_payload(name="Scalable IPA"):
    return {
        "name": name,
        "author": "Tester",
        "batch_size_liters": 20,
        "boil_size_l": 24.0,
        "efficiency_percent": 72,
        "yeast_name": "US-05",
        "yeast_attenuation": 78,
        "format_extensions": {
            "fermentables": [
                {"name": "Pale Malt 2-Row (US)", "amount_kg": 5.0},
                {"name": "Munich Malt", "amount_kg": 0.5},
            ],
            "hops": [
                {
                    "name": "Magnum",
                    "amount_grams": 20,
                    "alpha_acid_percent": 12.0,
                    "boil_time_minutes": 60,
                    "use": "boil",
                    "form": "pellet",
                },
                {
                    "name": "Citra Incognito",
                    "amount_grams": 0,
                    "amount_ml": 50,
                    "is_extract": True,
                    "alpha_acid_percent": 20.0,
                    "boil_time_minutes": 5,
                    "use": "boil",
                    "form": "extract",
                },
            ],
        },
    }


async def _create_recipe(client, payload=None):
    payload = payload or _ipa_payload()
    boil_size = payload.pop("boil_size_l", None)
    r = await client.post("/api/recipes", json=payload)
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    if boil_size is not None:
        # RecipeCreate has no boil_size_l; set it through the update path.
        r = await client.put(f"/api/recipes/{rid}", json={"boil_size_l": boil_size})
        assert r.status_code == 200, r.text
        assert r.json()["boil_size_l"] == boil_size, r.json().get("boil_size_l")
    return rid


async def _rows(db, model, rid):
    return (
        (await db.execute(select(model).where(model.recipe_id == rid)))
        .scalars()
        .all()
    )


class TestScaleEndpoint:
    @pytest.mark.asyncio
    async def test_scales_fermentables_and_hops(self, client, test_db):
        rid = await _create_recipe(client)
        r = await client.post(
            f"/api/recipes/{rid}/scale", json={"target_batch_size_liters": 40}
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["batch_size_liters"] == 40
        assert body["boil_size_l"] == pytest.approx(48.0, abs=0.05)

        ferms = await _rows(test_db, RecipeFermentable, rid)
        by_name = {f.name: f.amount_kg for f in ferms}
        assert by_name["Pale Malt 2-Row (US)"] == pytest.approx(10.0, abs=0.01)
        assert by_name["Munich Malt"] == pytest.approx(1.0, abs=0.01)

        hops = await _rows(test_db, RecipeHop, rid)
        by_name = {h.name: h for h in hops}
        assert by_name["Magnum"].amount_grams == pytest.approx(40, abs=0.1)
        assert by_name["Citra Incognito"].amount_ml == pytest.approx(100, abs=0.1)

    @pytest.mark.asyncio
    async def test_scales_format_extensions_mirror(self, client, test_db):
        rid = await _create_recipe(client)
        r = await client.post(
            f"/api/recipes/{rid}/scale", json={"target_batch_size_liters": 10}
        )
        assert r.status_code == 200, r.text
        # format_extensions is only exposed on the detail response
        ext = (await client.get(f"/api/recipes/{rid}")).json()["format_extensions"]
        ferm_amounts = {f["name"]: f["amount_kg"] for f in ext["fermentables"]}
        assert ferm_amounts["Pale Malt 2-Row (US)"] == pytest.approx(2.5, abs=0.01)
        hop_rows = {h["name"]: h for h in ext["hops"]}
        assert hop_rows["Magnum"]["amount_grams"] == pytest.approx(10, abs=0.1)
        assert hop_rows["Citra Incognito"]["amount_ml"] == pytest.approx(25, abs=0.1)

    @pytest.mark.asyncio
    async def test_scales_miscs_mash_steps_and_water_adjustments(
        self, client, test_db
    ):
        rid = await _create_recipe(client)
        r = await client.put(
            f"/api/recipes/{rid}/miscs",
            json=[
                {
                    "name": "Irish Moss",
                    "type": "fining",
                    "use": "boil",
                    "time_min": 15,
                    "amount_kg": 5.0,
                    "amount_unit": "g",
                }
            ],
        )
        assert r.status_code == 200, r.text
        r = await client.put(
            f"/api/recipes/{rid}/mash-steps",
            json=[
                {
                    "step_number": 1,
                    "name": "Saccharification",
                    "type": "infusion",
                    "temp_c": 66,
                    "time_minutes": 60,
                    "infusion_amount_liters": 15.0,
                }
            ],
        )
        assert r.status_code == 200, r.text
        r = await client.put(
            f"/api/recipes/{rid}/water-adjustments",
            json=[
                {
                    "stage": "mash",
                    "volume_liters": 16.0,
                    "calcium_sulfate_g": 4.0,
                    "sodium_chloride_g": 1.0,
                    "acid_ml": 2.0,
                }
            ],
        )
        assert r.status_code == 200, r.text

        r = await client.post(
            f"/api/recipes/{rid}/scale", json={"target_batch_size_liters": 40}
        )
        assert r.status_code == 200, r.text

        miscs = await _rows(test_db, RecipeMisc, rid)
        assert miscs[0].amount_kg == pytest.approx(10.0, abs=0.01)

        steps = await _rows(test_db, RecipeMashStep, rid)
        assert steps[0].infusion_amount_liters == pytest.approx(30.0, abs=0.01)
        assert steps[0].temp_c == pytest.approx(66)  # temps never scale

        adjustments = await _rows(test_db, RecipeWaterAdjustment, rid)
        adj = adjustments[0]
        assert adj.volume_liters == pytest.approx(32.0, abs=0.01)
        assert adj.calcium_sulfate_g == pytest.approx(8.0, abs=0.01)
        assert adj.sodium_chloride_g == pytest.approx(2.0, abs=0.01)
        assert adj.acid_ml == pytest.approx(4.0, abs=0.01)

    @pytest.mark.asyncio
    async def test_stats_recomputed_and_roughly_invariant(self, client, test_db):
        rid = await _create_recipe(client)
        # Establish a computed baseline first — creation doesn't run the calculators.
        before = (await client.post(f"/api/recipes/{rid}/recalculate")).json()
        r = await client.post(
            f"/api/recipes/{rid}/scale", json={"target_batch_size_liters": 40}
        )
        assert r.status_code == 200, r.text
        after = r.json()
        # Proportional scaling keeps concentrations constant; recomputed
        # stats should match the originals closely.
        assert after["og"] == pytest.approx(before["og"], abs=0.002)
        assert after["ibu"] == pytest.approx(before["ibu"], rel=0.05)
        assert after["color_srm"] == pytest.approx(before["color_srm"], rel=0.05)

    @pytest.mark.asyncio
    async def test_dry_run_previews_without_persisting(self, client, test_db):
        rid = await _create_recipe(client)
        r = await client.post(
            f"/api/recipes/{rid}/scale",
            json={"target_batch_size_liters": 40, "dry_run": True},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        # Response shows the scaled preview...
        assert body["batch_size_liters"] == 40
        preview = {f["name"]: f["amount_kg"] for f in body["fermentables"]}
        assert preview["Pale Malt 2-Row (US)"] == pytest.approx(10.0, abs=0.01)
        # Hops must be in the preview too (RecipeResponse has no hops list —
        # the endpoint returns RecipeDetailResponse for exactly this reason).
        hop_preview = {h["name"]: h["amount_grams"] for h in body["hops"]}
        assert hop_preview["Magnum"] == pytest.approx(40, abs=0.1)

        # ...but nothing was persisted.
        after = (await client.get(f"/api/recipes/{rid}")).json()
        assert after["batch_size_liters"] == 20
        stored = {f["name"]: f["amount_kg"] for f in after["fermentables"]}
        assert stored["Pale Malt 2-Row (US)"] == pytest.approx(5.0, abs=0.01)
        ext = {f["name"]: f["amount_kg"] for f in after["format_extensions"]["fermentables"]}
        assert ext["Pale Malt 2-Row (US)"] == pytest.approx(5.0, abs=0.01)

    @pytest.mark.asyncio
    async def test_rejects_non_positive_target(self, client, test_db):
        rid = await _create_recipe(client)
        r = await client.post(
            f"/api/recipes/{rid}/scale", json={"target_batch_size_liters": 0}
        )
        assert r.status_code == 422, r.text

    @pytest.mark.asyncio
    async def test_rejects_recipe_without_batch_size(self, client, test_db):
        payload = _ipa_payload("No Batch Size")
        payload.pop("batch_size_liters")
        rid = await _create_recipe(client, payload)
        r = await client.post(
            f"/api/recipes/{rid}/scale", json={"target_batch_size_liters": 40}
        )
        assert r.status_code == 400, r.text

    @pytest.mark.asyncio
    async def test_unknown_recipe_404s(self, client, test_db):
        r = await client.post(
            "/api/recipes/999999/scale", json={"target_batch_size_liters": 40}
        )
        assert r.status_code == 404, r.text
