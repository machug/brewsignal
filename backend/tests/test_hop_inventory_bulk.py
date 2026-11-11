"""Bulk hop inventory update from a pasted list (tilt_ui-86wt)."""
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import HopInventory, HopVariety
from backend.services.hop_inventory_bulk import BulkHopItem, bulk_update_hops
from backend.services.llm.tools import execute_tool


async def _library(db: AsyncSession, name: str, lo: float, hi: float):
    """Get-or-create a library row (the test DB may already seed the library)."""
    v = (await db.execute(select(HopVariety).where(HopVariety.name == name))).scalar_one_or_none()
    if v is None:
        v = HopVariety(name=name)
        db.add(v)
    v.alpha_acid_low, v.alpha_acid_high = lo, hi
    await db.flush()


async def _seed(db: AsyncSession):
    for name, lo, hi in (("Citra", 11.0, 13.0), ("Cascade", 5.0, 7.0), ("Amarillo", 8.0, 11.0)):
        await _library(db, name, lo, hi)
    db.add_all([
        # Stock: Cascade kept (amount changes), Amarillo not in list, Citra twice
        HopInventory(variety="Cascade", amount_grams=40, storage_location="Freezer", user_id=None),
        HopInventory(variety="Amarillo", amount_grams=95, user_id=None),
        HopInventory(variety="Citra", amount_grams=10, user_id=None),
        HopInventory(variety="Citra", amount_grams=20, user_id=None),
        # Another tenant's stock must never be touched
        HopInventory(variety="Mosaic", amount_grams=500, user_id="other-user"),
    ])
    await db.commit()


async def _apply(db, items, replace):
    """Apply with the stock_version of a fresh preview (a version is now required)."""
    version = (await bulk_update_hops(db, "local", items, replace=replace, dry_run=True))["stock_version"]
    return await bulk_update_hops(db, "local", items, replace=replace, dry_run=False, expected_stock_version=version)


ITEMS = [
    BulkHopItem(name="citra", amount_grams=100),
    BulkHopItem(name="Cascade", amount_grams=30),
    BulkHopItem(name="Cascade", amount_grams=20),   # duplicates are summed
    BulkHopItem(name="Zorbatron", amount_grams=40),   # not in library (typos like "Galaxxy" fuzzy-match to Galaxy)
]


async def _stock(db):
    rows = (await db.execute(select(HopInventory).order_by(HopInventory.id))).scalars().all()
    return {(r.variety, r.user_id): r for r in rows}, rows


@pytest.mark.asyncio
async def test_dry_run_plans_replace_without_writing(test_db: AsyncSession):
    await _seed(test_db)
    plan = await bulk_update_hops(test_db, "local", ITEMS, replace=True, dry_run=True)

    assert plan["applied"] is False
    assert [a["variety"] for a in plan["add"]] == ["Zorbatron"]
    assert plan["not_in_library"] == ["Zorbatron"]
    assert {(u["variety"], u["from_grams"], u["to_grams"]) for u in plan["update"]} == {
        ("Citra", 30, 100),  # from = total of both Citra rows
        ("Cascade", 40, 50),
    }
    removed = sorted((r["variety"], r["amount_grams"]) for r in plan["remove"])
    assert removed == [("Amarillo", 95), ("Citra", 20)]  # not listed + Citra row merged into first
    reasons = {r["variety"]: r["reason"] for r in plan["remove"]}
    assert reasons == {"Amarillo": "not_listed", "Citra": "merged"}
    assert len((await _stock(test_db))[1]) == 5  # nothing written


@pytest.mark.asyncio
async def test_apply_replace(test_db: AsyncSession):
    await _seed(test_db)
    await _apply(test_db, ITEMS, replace=True)
    by_key, rows = await _stock(test_db)

    assert sorted(r.variety for r in rows if r.user_id != "other-user") == ["Cascade", "Citra", "Zorbatron"]
    assert by_key[("Cascade", None)].amount_grams == 50
    assert by_key[("Cascade", None)].storage_location == "Freezer"  # kept on update
    assert by_key[("Citra", None)].amount_grams == 100
    assert by_key[("Mosaic", "other-user")].amount_grams == 500  # other tenant untouched


@pytest.mark.asyncio
async def test_apply_merge_keeps_unlisted_stock(test_db: AsyncSession):
    await _seed(test_db)
    plan = await bulk_update_hops(
        test_db, "local", [BulkHopItem(name="Citra", amount_grams=5)], replace=False, dry_run=False,
        expected_stock_version=(await bulk_update_hops(
            test_db, "local", [BulkHopItem(name="Citra", amount_grams=5)], replace=False, dry_run=True
        ))["stock_version"],
    )
    # Listed Citra is the new total: its two rows merge; unlisted hops stay.
    assert [(r["variety"], r["reason"]) for r in plan["remove"]] == [("Citra", "merged")]
    by_key, rows = await _stock(test_db)
    assert sorted(r.variety for r in rows) == ["Amarillo", "Cascade", "Citra", "Mosaic"]
    assert by_key[("Citra", None)].amount_grams == 5


@pytest.mark.asyncio
async def test_new_hop_gets_library_alpha(test_db: AsyncSession):
    await _library(test_db, "Citra", 11.0, 13.0)
    await test_db.commit()
    plan = await bulk_update_hops(
        test_db, "local", [BulkHopItem(name="CITRA ", amount_grams=28)], replace=False, dry_run=True
    )
    assert plan["add"] == [{
        "variety": "Citra", "amount_grams": 28, "alpha_acid_percent": 12.0,
        "in_library": True, "fuzzy_from": [],
    }]


@pytest.mark.asyncio
async def test_tool_never_writes_and_returns_confirmation(test_db: AsyncSession):
    await _seed(test_db)
    result = await execute_tool(
        test_db, "update_hop_inventory",
        {"items": [{"name": "Citra", "amount_grams": 100}]}, user_id="local",
    )
    assert result["applied"] is False and result["replace"] is True
    assert result["confirmation"]["kind"] == "hop_inventory"
    assert len((await _stock(test_db))[1]) == 5


@pytest.mark.asyncio
async def test_bulk_endpoint_defaults_to_dry_run_then_applies(client: AsyncClient, test_db: AsyncSession):
    await _seed(test_db)
    body = {"items": [{"name": "Citra", "amount_grams": 100}], "replace": True}

    preview = await client.post("/api/inventory/hops/bulk", json=body)
    assert preview.status_code == 200 and preview.json()["applied"] is False
    assert len((await _stock(test_db))[1]) == 5

    no_version = await client.post("/api/inventory/hops/bulk", json={**body, "dry_run": False})
    assert no_version.status_code == 422  # apply needs the preview's stock_version

    applied = await client.post("/api/inventory/hops/bulk", json={
        **body, "dry_run": False, "expected_stock_version": preview.json()["stock_version"],
    })
    assert applied.status_code == 200 and applied.json()["applied"] is True
    _, rows = await _stock(test_db)
    assert sorted(r.variety for r in rows) == ["Citra", "Mosaic"]


@pytest.mark.asyncio
async def test_bulk_endpoint_rejects_negative_amounts(client: AsyncClient):
    r = await client.post("/api/inventory/hops/bulk", json={"items": [{"name": "Citra", "amount_grams": -1}]})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_zero_grams_removes_in_merge_mode_too(test_db: AsyncSession):
    await _seed(test_db)
    items = [BulkHopItem(name="Amarillo", amount_grams=0)]
    preview = await bulk_update_hops(test_db, "local", items, replace=True, dry_run=True)
    zero = [r for r in preview["remove"] if r["variety"] == "Amarillo"]
    assert zero and zero[0]["replace_only"] is False

    plan = await _apply(test_db, items, replace=False)
    assert [r["variety"] for r in plan["remove"]] == ["Amarillo"]
    _, rows = await _stock(test_db)
    assert "Amarillo" not in [r.variety for r in rows]
    assert [r.variety for r in rows].count("Citra") == 2  # merge keeps duplicates


@pytest.mark.asyncio
async def test_apply_refused_when_stock_changed_since_preview(client: AsyncClient, test_db: AsyncSession):
    await _seed(test_db)
    body = {"items": [{"name": "Citra", "amount_grams": 100}], "replace": True}
    version = (await client.post("/api/inventory/hops/bulk", json=body)).json()["stock_version"]

    test_db.add(HopInventory(variety="Nelson Sauvin", amount_grams=50, user_id=None))
    await test_db.commit()

    r = await client.post("/api/inventory/hops/bulk",
                          json={**body, "dry_run": False, "expected_stock_version": version})
    assert r.status_code == 409
    _, rows = await _stock(test_db)
    assert "Nelson Sauvin" in [x.variety for x in rows]  # nothing deleted

    fresh = (await client.post("/api/inventory/hops/bulk", json=body)).json()["stock_version"]
    ok = await client.post("/api/inventory/hops/bulk",
                           json={**body, "dry_run": False, "expected_stock_version": fresh})
    assert ok.status_code == 200 and ok.json()["applied"] is True


@pytest.mark.asyncio
async def test_stock_spelling_matches_library_name(test_db: AsyncSession):
    """Stock 'Tettnanger' and pasted 'Tettnang' are the same hop (no duplicate add)."""
    await _library(test_db, "Tettnang", 3.5, 5.5)
    test_db.add(HopInventory(variety="Tettnanger", amount_grams=50, crop_year=2023, user_id=None))
    await test_db.commit()
    plan = await bulk_update_hops(
        test_db, "local", [BulkHopItem(name="Tettnang", amount_grams=80)], replace=False, dry_run=True
    )
    assert plan["add"] == []
    assert [(u["variety"], u["from_grams"], u["to_grams"]) for u in plan["update"]] == [("Tettnanger", 50, 80)]


@pytest.mark.asyncio
async def test_fuzzy_match_is_reported(test_db: AsyncSession):
    await _library(test_db, "Citra", 11.0, 13.0)
    await test_db.commit()
    plan = await bulk_update_hops(
        test_db, "local", [BulkHopItem(name="Citraa", amount_grams=10)], replace=False, dry_run=True
    )
    assert plan["add"][0]["variety"] == "Citra"
    assert plan["add"][0]["fuzzy_from"] == ["Citraa"]


@pytest.mark.asyncio
async def test_tool_rejects_oversized_list(test_db: AsyncSession):
    items = [{"name": f"Hop {i}", "amount_grams": 1} for i in range(201)]
    result = await execute_tool(test_db, "update_hop_inventory", {"items": items}, user_id="local")
    assert "error" in result


@pytest.mark.asyncio
async def test_distinct_stock_names_never_merged_by_fuzzy_match(test_db: AsyncSession):
    """Stock Solaris + Polaris (library has only Polaris): updating Polaris leaves Solaris alone."""
    await _library(test_db, "Polaris", 18.0, 23.0)
    test_db.add_all([
        HopInventory(variety="Solaris", amount_grams=40, user_id=None),
        HopInventory(variety="Polaris", amount_grams=30, user_id=None),
    ])
    await test_db.commit()
    for grams in (60, 0):
        plan = await bulk_update_hops(
            test_db, "local", [BulkHopItem(name="Polaris", amount_grams=grams)], replace=False, dry_run=True
        )
        touched = {u["variety"] for u in plan["update"]} | {r["variety"] for r in plan["remove"]}
        assert touched == {"Polaris"}


@pytest.mark.asyncio
async def test_sole_fuzzy_stock_match_is_flagged(test_db: AsyncSession):
    await _library(test_db, "Polaris", 18.0, 23.0)
    test_db.add(HopInventory(variety="Solaris", amount_grams=40, user_id=None))
    await test_db.commit()
    plan = await bulk_update_hops(
        test_db, "local", [BulkHopItem(name="Polaris", amount_grams=0)], replace=False, dry_run=True
    )
    assert [(r["variety"], r["guessed_as"]) for r in plan["remove"]] == [("Solaris", "Polaris")]
    plan = await bulk_update_hops(
        test_db, "local", [BulkHopItem(name="Polaris", amount_grams=60)], replace=False, dry_run=True
    )
    assert [(u["variety"], u["guessed_as"]) for u in plan["update"]] == [("Solaris", "Polaris")]


@pytest.mark.asyncio
async def test_guessed_match_with_same_amount_still_flagged(test_db: AsyncSession):
    await _library(test_db, "Polaris", 18.0, 23.0)
    test_db.add(HopInventory(variety="Solaris", amount_grams=40, user_id=None))
    await test_db.commit()
    plan = await bulk_update_hops(
        test_db, "local", [BulkHopItem(name="Polaris", amount_grams=40)], replace=False, dry_run=True
    )
    assert plan["unchanged"] == []
    assert [(u["variety"], u["guessed_as"]) for u in plan["update"]] == [("Solaris", "Polaris")]


@pytest.mark.asyncio
async def test_accents_match_exactly(test_db: AsyncSession):
    """'Mittelfruh' (no umlaut) is an exact match, not a guess, in list and stock."""
    await _library(test_db, "Hallertau Mittelfrüh", 3.0, 5.5)
    test_db.add(HopInventory(variety="Hallertau Mittelfruh", amount_grams=20, user_id=None))
    await test_db.commit()
    plan = await bulk_update_hops(
        test_db, "local", [BulkHopItem(name="hallertau Mittelfruh", amount_grams=50)], replace=True, dry_run=True
    )
    assert plan["add"] == [] and plan["remove"] == []
    [u] = plan["update"]
    assert (u["from_grams"], u["to_grams"], u["fuzzy_from"], u["guessed_as"]) == (20, 50, [], None)
