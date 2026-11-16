"""calculated in the recipe API, POST /api/recipes/calculate, server-filled legacy columns (tilt_ui-4x2f.2)."""
import json

import pytest

from backend.models import Recipe, RecipeFermentable, RecipeHop
from backend.services.recipe_stats import effective_stats


BOIL60 = {"use": "add_to_boil", "duration": {"value": 60, "unit": "min"}}


async def _recipe(db, hops=True, grain=True, **kw):
    r = Recipe(name=kw.pop("name", "R"), batch_size_liters=20.0, efficiency_percent=75.0, **kw)
    db.add(r)
    await db.commit()
    rows = []
    if grain:
        rows.append(RecipeFermentable(recipe_id=r.id, name="Pale", type="grain", amount_kg=5.0,
                                      yield_percent=80.0, color_srm=3.0))
    if hops:
        rows.append(RecipeHop(recipe_id=r.id, name="Hop", alpha_acid_percent=10.0, amount_grams=30.0,
                              timing=BOIL60))
    db.add_all(rows)
    await db.commit()
    return r


@pytest.mark.asyncio
async def test_list_and_detail_include_calculated(client, test_db):
    r = await _recipe(test_db)
    listed = (await client.get("/api/recipes")).json()
    detail = (await client.get(f"/api/recipes/{r.id}")).json()
    assert detail["calculated"]["og"] > 1.0
    assert detail["calculated"]["ibu"] > 0
    assert [x for x in listed if x["id"] == r.id][0]["calculated"] == detail["calculated"]


@pytest.mark.asyncio
async def test_declared_only_recipe_has_null_calculated(client, test_db):
    r = await _recipe(test_db, hops=False, grain=False, target_og=1.050)
    assert (await client.get(f"/api/recipes/{r.id}")).json()["calculated"] is None


@pytest.mark.asyncio
async def test_effective_stats_per_field(client, test_db):
    from backend.services.recipe_stats import recipe_with_ingredients_stmt
    from sqlalchemy import select

    # calculated og/fg; no hops plus target_ibu=40 -> ibu is the calculated 0, not 40
    r = await _recipe(test_db, hops=False, target_ibu=40.0)
    loaded = (await test_db.execute(recipe_with_ingredients_stmt().where(Recipe.id == r.id))).scalar_one()
    e = effective_stats(loaded)
    assert e.source == "calculated" and e.ibu == 0 and e.og > 1.0

    # no grains, only target_og -> og declared, rest None
    r2 = await _recipe(test_db, hops=False, grain=False, target_og=1.050)
    loaded = (await test_db.execute(recipe_with_ingredients_stmt().where(Recipe.id == r2.id))).scalar_one()
    e = effective_stats(loaded)
    assert (e.source, e.og, e.fg, e.abv, e.ibu, e.srm) == ("declared", 1.050, None, None, None, None)

    r3 = await _recipe(test_db, hops=False, grain=False)
    loaded = (await test_db.execute(recipe_with_ingredients_stmt().where(Recipe.id == r3.id))).scalar_one()
    assert effective_stats(loaded).source == "empty"


@pytest.mark.asyncio
async def test_calculate_endpoint_matches_saved_recipe(client, test_db):
    r = await _recipe(test_db)
    saved = (await client.get(f"/api/recipes/{r.id}")).json()["calculated"]
    body = {
        "batch_size_liters": 20.0, "efficiency_percent": 75.0,
        "fermentables": [{"name": "Pale", "type": "grain", "amount_kg": 5.0,
                          "yield_percent": 80.0, "color_srm": 3.0}],
        "hops": [{"name": "Hop", "amount_grams": 30.0, "alpha_acid_percent": 10.0, "timing": BOIL60}],
        "cultures": [],
    }
    resp = await client.post("/api/recipes/calculate", json=body)
    assert resp.status_code == 200
    assert resp.json() == saved


@pytest.mark.asyncio
async def test_calculate_endpoint_empty_returns_null(client):
    resp = await client.post("/api/recipes/calculate", json={"fermentables": [], "hops": []})
    assert resp.status_code == 200
    assert resp.json() is None


@pytest.mark.asyncio
async def test_update_ignores_client_stats(client, test_db):
    r = await _recipe(test_db)
    calculated = (await client.get(f"/api/recipes/{r.id}")).json()["calculated"]
    resp = await client.put(f"/api/recipes/{r.id}", json={"og": 1.200, "ibu": 99.0, "name": "X"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["og"] == calculated["og"] != 1.200
    assert data["ibu"] == calculated["ibu"]


@pytest.mark.asyncio
async def test_create_ignores_client_stats(client):
    resp = await client.post("/api/recipes", json={
        "name": "C", "og": 1.200, "batch_size_liters": 20.0,
        "format_extensions": {"fermentables": [{"name": "Pale", "type": "grain", "amount_kg": 5.0,
                                                "yield_percent": 80.0, "color_srm": 3.0}]},
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["og"] == data["calculated"]["og"] != 1.200


@pytest.mark.asyncio
async def test_importer_writes_targets(client):
    doc = {
        "beerjson": {"version": 1.0, "recipes": [{
            "name": "Imp", "type": "all grain", "author": "t",
            "batch_size": {"value": 20, "unit": "l"},
            "efficiency": {"brewhouse": {"value": 75, "unit": "%"}},
            "original_gravity": {"value": 1.099, "unit": "sg"},
            "ibu_estimate": {"value": 77, "unit": "IBUs"},
            "ingredients": {
                "fermentable_additions": [{
                    "name": "Pale", "type": "grain", "yield": {"fine_grind": {"value": 80, "unit": "%"}},
                    "color": {"value": 3, "unit": "SRM"}, "amount": {"value": 5, "unit": "kg"}}],
            },
        }]}
    }
    resp = await client.post("/api/recipes/import", files={"file": ("r.json", json.dumps(doc), "application/json")})
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["target_og"] == 1.099 and data["target_ibu"] == 77
    assert data["calculated"] is not None
    assert data["og"] == data["calculated"]["og"] != 1.099


@pytest.mark.asyncio
async def test_batch_recipe_includes_calculated(client, test_db):
    r = await _recipe(test_db)
    b = (await client.post("/api/batches", json={"recipe_id": r.id, "status": "planning"})).json()
    got = (await client.get(f"/api/batches/{b['id']}")).json()
    assert got["recipe"]["calculated"]["og"] > 1.0


_GRAIN = {"name": "Pale", "type": "grain", "amount_kg": 5.0, "yield_percent": 80.0, "color_srm": 3.0}


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_hop", [
    {"name": "H", "amount_grams": 30, "timing": {"use": 123}},
    {"name": "H", "amount_grams": 30, "timing": {"use": "whirlpool", "temperature": {"value": -273.15, "unit": "C"}}},
    {"name": "H", "amount_grams": 30, "timing": {"use": "boil", "duration": {"value": "x", "unit": "min"}}},
    {"name": "H", "amount_grams": -5},
    {"name": "H", "amount_grams": 1e308, "alpha_acid_percent": 10},
])
async def test_calculate_rejects_bad_hops(client, bad_hop):
    resp = await client.post("/api/recipes/calculate", json={"fermentables": [_GRAIN], "hops": [bad_hop]})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_calculate_rejects_negative_and_oversized(client):
    neg = await client.post("/api/recipes/calculate", json={"fermentables": [{**_GRAIN, "amount_kg": -1}]})
    assert neg.status_code == 422
    many = await client.post("/api/recipes/calculate", json={"fermentables": [_GRAIN] * 101})
    assert many.status_code == 422


@pytest.mark.asyncio
async def test_put_yeast_change_updates_calculated_fg(client):
    created = await client.post("/api/recipes", json={
        "name": "Y", "batch_size_liters": 20.0, "yeast_name": "US-05", "yeast_attenuation": 75.0,
        "format_extensions": {"fermentables": [_GRAIN]},
    })
    rid = created.json()["id"]
    before = created.json()["calculated"]
    resp = await client.put(f"/api/recipes/{rid}", json={"yeast_name": "WLP001", "yeast_attenuation": 85.0})
    assert resp.status_code == 200
    after = resp.json()["calculated"]
    assert after["og"] == before["og"]
    assert after["fg"] < before["fg"]
    assert resp.json()["fg"] == after["fg"]
    # a second PUT that does not mention yeast keeps the new attenuation
    again = await client.put(f"/api/recipes/{rid}", json={"notes": "n"})
    assert again.json()["calculated"]["fg"] == after["fg"]


@pytest.mark.asyncio
async def test_put_resending_same_yeast_keeps_culture_range(client, test_db):
    from backend.models import RecipeCulture
    from sqlalchemy import select
    r = await _recipe(test_db, hops=False, yeast_name="Y", yeast_attenuation=70.0)
    test_db.add(RecipeCulture(recipe_id=r.id, name="Y", attenuation_min_percent=70.0,
                              attenuation_max_percent=80.0))
    await test_db.commit()
    before = (await client.get(f"/api/recipes/{r.id}")).json()["calculated"]
    resp = await client.put(f"/api/recipes/{r.id}", json={"yeast_name": "Y", "yeast_attenuation": 70.0})
    assert resp.status_code == 200
    assert resp.json()["calculated"]["fg"] == before["fg"]
    c = (await test_db.execute(select(RecipeCulture).where(RecipeCulture.recipe_id == r.id))).scalar_one()
    await test_db.refresh(c)
    assert (c.attenuation_min_percent, c.attenuation_max_percent) == (70.0, 80.0)


@pytest.mark.asyncio
async def test_attenuation_only_put_keeps_all_cultures(client, test_db):
    from backend.models import RecipeCulture
    from sqlalchemy import select
    r = await _recipe(test_db, hops=False)
    test_db.add_all([RecipeCulture(recipe_id=r.id, name="A", attenuation_min_percent=70.0, attenuation_max_percent=70.0),
                     RecipeCulture(recipe_id=r.id, name="B")])
    await test_db.commit()
    resp = await client.put(f"/api/recipes/{r.id}", json={"yeast_attenuation": 85.0})
    assert resp.status_code == 200
    names = [c.name for c in (await test_db.execute(
        select(RecipeCulture).where(RecipeCulture.recipe_id == r.id).order_by(RecipeCulture.id))).scalars()]
    assert names == ["A", "B"]
