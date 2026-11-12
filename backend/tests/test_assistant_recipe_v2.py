"""Assistant recipe tools on v2: save whole, edit by patch (tilt_ui-eevz.1)."""

import json
from pathlib import Path

import pytest

from backend.services.llm.tools.recipe_v2 import (
    get_recipe_document,
    save_recipe_document,
    update_recipe_document,
)

JASPER = json.loads((Path(__file__).resolve().parents[2] / "docs" / "examples" / "jasper-clone.v2.brewsignal").read_text())


def _strip(doc):
    """Export minus fields that legitimately change on any save."""
    d = json.loads(json.dumps(doc))
    d.pop("created_at", None)
    d.pop("exported_at", None)
    return d


async def _save(db, doc=JASPER):
    out = await save_recipe_document(db, doc)
    assert out.get("applied"), out
    return out


@pytest.mark.asyncio
async def test_save_keeps_everything_the_importer_keeps(test_db):
    out = await _save(test_db)
    assert out["counts"] == {
        "fermentables": 3, "hops": 3, "cultures": 1, "miscs": 0,
        "mash_steps": 1, "fermentation_steps": 4, "water_profiles": 1, "water_adjustments": 1,
    }
    assert out["yeast"] == ["London Ale III"]
    assert out["calculated"]["og"] and out["calculated"]["ibu"]  # calculated from ingredients
    assert not [w for w in out["warnings"] if w.startswith("No ")]


@pytest.mark.asyncio
async def test_get_returns_a_v2_document_with_the_yeast(test_db):
    out = await _save(test_db)
    got = await get_recipe_document(test_db, out["recipe_id"])
    cultures = got["document"]["recipe"]["ingredients"]["culture_additions"]
    assert cultures[0]["name"] == "London Ale III"


@pytest.mark.asyncio
async def test_patch_changes_only_what_it_names(test_db):
    rid = (await _save(test_db))["recipe_id"]
    before = _strip((await get_recipe_document(test_db, rid))["document"])

    out = await update_recipe_document(test_db, rid, [
        {"op": "replace", "path": "/recipe/name", "value": "Jasper v2"},
    ])
    assert out.get("applied"), out
    after = _strip((await get_recipe_document(test_db, rid))["document"])

    assert after["recipe"]["name"] == "Jasper v2"
    after["recipe"]["name"] = before["recipe"]["name"]
    assert after == before  # nothing else moved: water, fermentation steps, yeast, hop extras


@pytest.mark.asyncio
async def test_patch_adds_a_misc_and_keeps_it_on_the_next_edit(test_db):
    rid = (await _save(test_db))["recipe_id"]
    misc = {"name": "Whirlfloc", "type": "fining", "amount": {"value": 1, "unit": "each"},
            "timing": {"use": "add_to_boil", "time": {"value": 10, "unit": "min"}}}
    # Jasper has no miscs; the list is always present so "-" appends (Gemini review)
    out = await update_recipe_document(test_db, rid, [
        {"op": "add", "path": "/recipe/ingredients/miscellaneous_additions/-", "value": misc},
    ])
    assert out["counts"]["miscs"] == 1, out
    out = await update_recipe_document(test_db, rid, [
        {"op": "replace", "path": "/recipe/name", "value": "Jasper again"},
    ])
    assert out["counts"]["miscs"] == 1 and out["counts"]["water_profiles"] == 1


@pytest.mark.asyncio
async def test_bad_patch_changes_nothing(test_db):
    rid = (await _save(test_db))["recipe_id"]
    before = _strip((await get_recipe_document(test_db, rid))["document"])
    out = await update_recipe_document(test_db, rid, [
        {"op": "replace", "path": "/recipe/ingredients/hop_additions/9/amount", "value": 1},
    ])
    assert "error" in out
    assert _strip((await get_recipe_document(test_db, rid))["document"]) == before


@pytest.mark.asyncio
async def test_missing_yeast_is_warned_not_silently_accepted(test_db):
    doc = json.loads(json.dumps(JASPER))
    del doc["recipe"]["ingredients"]["culture_additions"]
    out = await _save(test_db, doc)
    assert out["counts"]["cultures"] == 0
    assert any("No yeast" in w for w in out["warnings"])


@pytest.mark.asyncio
async def test_not_a_v2_envelope(test_db):
    out = await save_recipe_document(test_db, {"name": "flat shape"})
    assert "error" in out


EDITOR_RECIPE = {
    # Shape the app's own recipe editor posts (frontend/src/routes/recipes/new)
    "name": "Editor APA", "type": "all-grain", "batch_size_liters": 20, "efficiency_percent": 72,
    "yeast_name": "US-05", "yeast_lab": "Fermentis", "yeast_product_id": "US-05",
    "yeast_temp_min": 15.0, "yeast_temp_max": 22.0, "yeast_attenuation": 81.0,
    "format_extensions": {
        "fermentables": [{"name": "Pale Ale Malt", "amount_kg": 4.5, "color_lovibond": 3, "potential_sg": 1.037, "type": "grain"}],
        "hops": [
            {"name": "Cascade", "amount_grams": 25, "alpha_acid_percent": 6.0, "boil_time_minutes": 60, "use": "boil", "form": "pellet"},
            {"name": "Citra", "amount_grams": 50, "alpha_acid_percent": 12.0, "boil_time_minutes": 4, "use": "dry_hop", "form": "pellet"},
        ],
    },
}


def _page_view(r):
    """What the recipe page shows: name/amount/use of hops and grains, and the yeast."""
    hops = sorted((h["name"], round(h.get("amount_grams") or 0, 1)) for h in (r.get("hops") or []))
    ferms = sorted((f["name"], round(f.get("amount_kg") or 0, 3)) for f in (r.get("fermentables") or []))
    yeast = (r.get("yeast_name"), r.get("yeast_temp_min"), r.get("yeast_temp_max"))
    return hops, ferms, yeast


@pytest.mark.asyncio
async def test_patching_an_editor_made_recipe_keeps_hops_grains_and_yeast(client, test_db):
    created = await client.post("/api/recipes", json=EDITOR_RECIPE)
    assert created.status_code == 201, created.text
    rid = created.json()["id"]
    before = _page_view((await client.get(f"/api/recipes/{rid}")).json())
    assert before == ([("Cascade", 25.0), ("Citra", 50.0)], [("Pale Ale Malt", 4.5)], ("US-05", 15.0, 22.0))

    out = await update_recipe_document(test_db, rid, [{"op": "replace", "path": "/recipe/name", "value": "Editor APA 2"}])
    assert out.get("applied"), out
    test_db.expire_all()
    after_json = (await client.get(f"/api/recipes/{rid}")).json()
    assert after_json["name"] == "Editor APA 2"
    assert _page_view(after_json) == before


def _minimal(style=None, hops=None):
    recipe = {
        "name": "Minimal v2", "type": "all grain",
        "batch_size": {"value": 20, "unit": "l"},
        "efficiency": {"brewhouse": {"value": 72, "unit": "%"}},
        "ingredients": {
            "fermentable_additions": [{"name": "Pale Ale Malt", "type": "grain",
                                       "color": {"value": 3, "unit": "Lovi"},
                                       "yield": {"potential": {"value": 1.037, "unit": "sg"}},
                                       "amount": {"value": 4.5, "unit": "kg"}}],
            "hop_additions": hops or [{"name": "Centennial", "alpha_acid": {"value": 10, "unit": "%"},
                                       "amount": {"value": 30, "unit": "g"},
                                       "timing": {"use": "add_to_boil", "duration": {"value": 60, "unit": "min"}}}],
            "culture_additions": [{"name": "US-05", "producer": "Fermentis", "type": "ale", "form": "dry"}],
        },
    }
    if style:
        recipe["style"] = {"name": style, "category": "", "style_guide": "", "type": "beer"}
    return {"brewsignal_version": "2.0", "recipe": recipe}


@pytest.mark.asyncio
async def test_style_name_resolves_to_style_row(test_db):
    """Ported from the old save_recipe path (tilt_ui-3vc)."""
    from backend.models import Recipe, Style

    test_db.add(Style(id="test-style-apa-v2", guide="BJCP 2021", category_number="18", style_letter="B",
                      name="Test American Pale Ale", category="Pale American Ale", type="Ale"))
    await test_db.commit()
    out = await _save(test_db, _minimal(style="Test American Pale Ale"))
    assert (await test_db.get(Recipe, out["recipe_id"])).style_id == "test-style-apa-v2"


@pytest.mark.asyncio
async def test_extract_hop_round_trips(test_db):
    """Ported from the old LLM save path (tilt_ui-0l5): extract markers survive save and patch."""
    hops = [
        {"name": "Mosaic", "alpha_acid": {"value": 12, "unit": "%"}, "amount": {"value": 20, "unit": "g"},
         "timing": {"use": "add_to_boil", "duration": {"value": 60, "unit": "min"}}},
        {"name": "Quantum MOS", "is_extract": True, "amount_ml": 2.5, "amount": {"value": 2.5, "unit": "ml"},
         "timing": {"use": "add_to_fermentation"}},
    ]
    rid = (await _save(test_db, _minimal(hops=hops)))["recipe_id"]
    out = await update_recipe_document(test_db, rid, [{"op": "replace", "path": "/recipe/name", "value": "Renamed"}])
    assert out.get("applied"), out
    doc_hops = (await get_recipe_document(test_db, rid))["document"]["recipe"]["ingredients"]["hop_additions"]
    quantum = next(h for h in doc_hops if h["name"] == "Quantum MOS")
    assert quantum.get("is_extract") is True and quantum.get("amount_ml") == 2.5



@pytest.mark.asyncio
async def test_edit_keeps_targets_beerxml_fields_and_column_only_yeast(test_db):
    """Gemini review: columns v2 cannot carry must survive an edit; yeast kept only in yeast_* is exported."""
    from backend.models import Recipe

    vals = dict(name="Legacy", type="all-grain", batch_size_liters=20.0, target_og=1.052, target_fg=1.012,
                target_abv=5.3, target_ibu=34.0, target_srm=7.5, yeast_name="US-05", yeast_lab="Fermentis",
                yeast_temp_min=15.0, yeast_temp_max=22.0, brewer="B", primary_age_days=10, primary_temp_c=19.0,
                priming_sugar_name="dextrose", taste_notes="TN", taste_rating=4.0, beerxml_content="<x/>")
    r = Recipe(**vals)
    test_db.add(r)
    await test_db.commit()
    doc = (await get_recipe_document(test_db, r.id))["document"]
    assert doc["recipe"]["ingredients"]["culture_additions"][0]["name"] == "US-05"  # assistant can see it

    out = await update_recipe_document(test_db, r.id, [{"op": "replace", "path": "/recipe/name", "value": "Legacy 2"}])
    assert out.get("applied"), out
    test_db.expire_all()
    after = await test_db.get(Recipe, r.id)
    for k, v in vals.items():
        if k != "name":
            assert getattr(after, k) == v, (k, getattr(after, k), v)
    assert out["yeast"] == ["US-05"]


@pytest.mark.asyncio
async def test_patching_a_declared_stat_updates_the_target(test_db):
    rid = (await _save(test_db))["recipe_id"]
    out = await update_recipe_document(test_db, rid, [
        {"op": "replace", "path": "/recipe/original_gravity", "value": {"value": 1.060, "unit": "sg"}},
    ])
    assert out["targets"]["og"] == pytest.approx(1.060), out


@pytest.mark.asyncio
async def test_no_leftover_rows_after_edits(test_db):
    from sqlalchemy import func, select

    from backend.models import Recipe, RecipeHop

    rid = (await _save(test_db))["recipe_id"]
    for name in ("a", "b"):
        await update_recipe_document(test_db, rid, [{"op": "replace", "path": "/recipe/name", "value": name}])
    assert await test_db.scalar(select(func.count(Recipe.id))) == 1
    assert await test_db.scalar(select(func.count(RecipeHop.id))) == 3


@pytest.mark.asyncio
async def test_index_mistakes_are_refused(test_db):
    rid = (await _save(test_db))["recipe_id"]
    for ops in (
        [{"op": "replace", "path": "/recipe/ingredients/hop_additions/-1/amount/value", "value": 1}],
        [{"op": "replace", "path": "/recipe/ingredients/hop_additions/01/amount/value", "value": 1}],
        [{"op": "remove", "path": "/recipe/ingredients/hop_additions/0"},
         {"op": "remove", "path": "/recipe/ingredients/hop_additions/2"}],  # index drift
    ):
        out = await update_recipe_document(test_db, rid, ops)
        assert "error" in out, ops


@pytest.mark.asyncio
async def test_preview_stores_nothing_and_describes_the_change(test_db):
    from sqlalchemy import func, select

    from backend.models import Recipe
    from backend.services.llm.tools.recipe_v2 import preview_recipe_change

    rid = (await _save(test_db))["recipe_id"]
    doc = (await get_recipe_document(test_db, rid))["document"]
    old_name = doc["recipe"]["ingredients"]["hop_additions"][0]["name"]
    out = await preview_recipe_change(test_db, recipe_id=rid, operations=[
        {"op": "replace", "path": "/recipe/ingredients/hop_additions/0/amount/value", "value": 99},
    ])
    assert out.get("valid"), out
    assert any(old_name in c and "added" in c and "99" in c for c in out["changes"]), out["changes"]
    assert out["before"]["calculated"]["ibu"] != out["calculated"]["ibu"]
    assert await test_db.scalar(select(func.count(Recipe.id))) == 1
    unchanged = (await get_recipe_document(test_db, rid))["document"]
    assert unchanged["recipe"]["ingredients"]["hop_additions"][0]["amount"]["value"] != 99

    new = await preview_recipe_change(test_db, document=JASPER)
    assert new.get("valid") and await test_db.scalar(select(func.count(Recipe.id))) == 1



@pytest.mark.asyncio
async def test_removing_a_hop_keeps_whirlpool_details_on_the_right_hop(test_db):
    """v2 links hop extras by position; Jasper has three Citra additions (bittering, whirlpool, dry hop)."""
    rid = (await _save(test_db))["recipe_id"]
    hops = (await get_recipe_document(test_db, rid))["document"]["recipe"]["ingredients"]["hop_additions"]
    assert hops[1]["brewsignal"]["hop_use"] == "whirlpool"  # inline in the assistant's view
    out = await update_recipe_document(test_db, rid, [{"op": "remove", "path": "/recipe/ingredients/hop_additions/0"}])
    assert out.get("applied"), out
    hops = (await get_recipe_document(test_db, rid))["document"]["recipe"]["ingredients"]["hop_additions"]
    assert [h["brewsignal"]["hop_use"] for h in hops] == ["whirlpool", "dry_hop"]
    assert hops[0]["brewsignal"]["temperature"]["value"] == 79.0
