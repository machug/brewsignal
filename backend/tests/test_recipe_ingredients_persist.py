"""UI POST/PUT /recipes must persist ingredients to the relationship tables
(recipe_hops / recipe_fermentables), not just format_extensions
(tilt_ui-9y7 + tilt_ui-hfi).
"""

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.models import Recipe, RecipeFermentable, RecipeHop


def _stout_payload(name="UI Stout"):
    # Mirrors the editor's format_extensions shape. Roasted Barley carries NO
    # color (the editor omits it), so the backend must enrich from the
    # reference table and recompute color_srm.
    return {
        "name": name,
        "author": "Tester",
        "batch_size_liters": 23,
        "efficiency_percent": 72,
        "og": 1.045,
        "fg": 1.010,
        "abv": 4.6,
        "ibu": 42,
        "color_srm": 4,  # wrong pale value the editor computed
        "format_extensions": {
            "fermentables": [
                {"name": "Maris Otter", "amount_kg": 3.8},
                {"name": "Roasted Barley", "amount_kg": 0.4},
            ],
            "hops": [
                {
                    "name": "East Kent Goldings",
                    "amount_grams": 65,
                    "alpha_acid_percent": 5.0,
                    "boil_time_minutes": 60,
                    "use": "boil",
                    "form": "pellet",
                }
            ],
        },
    }


async def _hops(db, recipe_id):
    return (
        await db.execute(select(RecipeHop).where(RecipeHop.recipe_id == recipe_id))
    ).scalars().all()


async def _ferms(db, recipe_id):
    return (
        await db.execute(
            select(RecipeFermentable).where(
                RecipeFermentable.recipe_id == recipe_id
            )
        )
    ).scalars().all()


class TestCreatePersistsIngredients:
    @pytest.mark.asyncio
    async def test_hops_written_to_recipe_hops(self, client, test_db):
        r = await client.post("/api/recipes", json=_stout_payload())
        assert r.status_code == 201, r.text
        rid = r.json()["id"]
        hops = await _hops(test_db, rid)
        assert len(hops) == 1
        assert hops[0].name == "East Kent Goldings"
        assert hops[0].timing["use"] == "boil"
        assert hops[0].timing["duration"]["value"] == 60

    @pytest.mark.asyncio
    async def test_fermentables_written_and_colored(self, client, test_db):
        r = await client.post("/api/recipes", json=_stout_payload())
        rid = r.json()["id"]
        ferms = await _ferms(test_db, rid)
        names = {f.name: f.color_srm for f in ferms}
        assert names["Maris Otter"] is not None
        # Roasted Barley had no color in the payload -> enriched from reference.
        assert names["Roasted Barley"] == 500

    @pytest.mark.asyncio
    async def test_color_srm_recomputed_from_grain_bill(self, client):
        r = await client.post("/api/recipes", json=_stout_payload())
        # Editor sent color_srm=4 (pale); server recomputes from the colored
        # bill to a real dry-stout color.
        assert r.json()["color_srm"] > 25


class TestMetadataPreserved:
    @pytest.mark.asyncio
    async def test_potential_and_hop_metadata_carried(self, client, test_db):
        payload = _stout_payload("Meta Stout")
        payload["format_extensions"]["fermentables"][0]["potential_sg"] = 1.038
        payload["format_extensions"]["hops"][0]["beta_acid_percent"] = 3.2
        payload["format_extensions"]["hops"][0]["purpose"] = "bittering"
        rid = (await client.post("/api/recipes", json=payload)).json()["id"]

        ferm = next(
            f for f in await _ferms(test_db, rid) if f.name == "Maris Otter"
        )
        # potential_sg -> yield_percent (OG-relevant) preserved
        assert ferm.yield_percent is not None and ferm.yield_percent > 0
        hop = (await _hops(test_db, rid))[0]
        assert hop.beta_acid_percent == 3.2
        # Full editor row stashed for round-trip
        assert hop.format_extensions.get("purpose") == "bittering"


class TestUpdateRebuildsIngredients:
    @pytest.mark.asyncio
    async def test_put_rebuilds_relationship_tables(self, client, test_db):
        rid = (await client.post("/api/recipes", json=_stout_payload())).json()["id"]
        # Edit: drop to a single pale grain and a different hop.
        patch = {
            "format_extensions": {
                "fermentables": [{"name": "Pilsner Malt", "amount_kg": 4.0}],
                "hops": [
                    {
                        "name": "Saaz",
                        "amount_grams": 30,
                        "alpha_acid_percent": 3.5,
                        "boil_time_minutes": 15,
                        "use": "boil",
                    }
                ],
            }
        }
        r = await client.put(f"/api/recipes/{rid}", json=patch)
        assert r.status_code == 200, r.text
        ferms = await _ferms(test_db, rid)
        hops = await _hops(test_db, rid)
        assert [f.name for f in ferms] == ["Pilsner Malt"]
        assert [h.name for h in hops] == ["Saaz"]
