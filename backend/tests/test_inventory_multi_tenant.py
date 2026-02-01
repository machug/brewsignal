"""Tests for multi-tenant isolation of inventory tables.

These tests verify that:
1. Inventory tables have user_id columns after migration
2. Inventory routers filter data by user_id
3. AG-UI inventory tools accept and use user_id parameter
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Equipment, HopInventory, YeastInventory


@pytest.mark.asyncio
class TestInventoryMigration:
    """Test that inventory tables have user_id columns."""

    async def test_equipment_has_user_id_column(self, test_db: AsyncSession):
        """Equipment table should have a user_id column."""
        # Get connection and inspect table
        conn = await test_db.connection()
        raw_conn = await conn.get_raw_connection()

        # For SQLite, use PRAGMA to get column info
        result = await test_db.execute(text("PRAGMA table_info(equipment)"))
        columns = {row[1]: row for row in result.fetchall()}

        assert "user_id" in columns, "equipment table missing user_id column"
        # Column should be VARCHAR(36)
        assert "VARCHAR" in columns["user_id"][2].upper() or "TEXT" in columns["user_id"][2].upper()

    async def test_hop_inventory_has_user_id_column(self, test_db: AsyncSession):
        """HopInventory table should have a user_id column."""
        result = await test_db.execute(text("PRAGMA table_info(hop_inventory)"))
        columns = {row[1]: row for row in result.fetchall()}

        assert "user_id" in columns, "hop_inventory table missing user_id column"

    async def test_yeast_inventory_has_user_id_column(self, test_db: AsyncSession):
        """YeastInventory table should have a user_id column."""
        result = await test_db.execute(text("PRAGMA table_info(yeast_inventory)"))
        columns = {row[1]: row for row in result.fetchall()}

        assert "user_id" in columns, "yeast_inventory table missing user_id column"

    async def test_equipment_user_id_has_index(self, test_db: AsyncSession):
        """Equipment table should have an index on user_id."""
        result = await test_db.execute(text("PRAGMA index_list(equipment)"))
        indexes = [row[1] for row in result.fetchall()]

        assert any("user_id" in idx for idx in indexes), "equipment table missing user_id index"

    async def test_hop_inventory_user_id_has_index(self, test_db: AsyncSession):
        """HopInventory table should have an index on user_id."""
        result = await test_db.execute(text("PRAGMA index_list(hop_inventory)"))
        indexes = [row[1] for row in result.fetchall()]

        assert any("user_id" in idx for idx in indexes), "hop_inventory table missing user_id index"

    async def test_yeast_inventory_user_id_has_index(self, test_db: AsyncSession):
        """YeastInventory table should have an index on user_id."""
        result = await test_db.execute(text("PRAGMA index_list(yeast_inventory)"))
        indexes = [row[1] for row in result.fetchall()]

        assert any("user_id" in idx for idx in indexes), "yeast_inventory table missing user_id index"


@pytest.mark.asyncio
class TestInventoryModelUserIdField:
    """Test that inventory models have user_id field and it can be set."""

    async def test_equipment_model_has_user_id(self, test_db: AsyncSession):
        """Equipment model should accept user_id on creation."""
        equipment = Equipment(
            name="Test Kettle",
            type="kettle",
            user_id="test-user-123",
        )
        test_db.add(equipment)
        await test_db.commit()
        await test_db.refresh(equipment)

        assert equipment.user_id == "test-user-123"

    async def test_hop_inventory_model_has_user_id(self, test_db: AsyncSession):
        """HopInventory model should accept user_id on creation."""
        hop = HopInventory(
            variety="Citra",
            amount_grams=100.0,
            user_id="test-user-456",
        )
        test_db.add(hop)
        await test_db.commit()
        await test_db.refresh(hop)

        assert hop.user_id == "test-user-456"

    async def test_yeast_inventory_model_has_user_id(self, test_db: AsyncSession):
        """YeastInventory model should accept user_id on creation."""
        yeast = YeastInventory(
            custom_name="US-05",
            quantity=2,
            form="dry",
            user_id="test-user-789",
        )
        test_db.add(yeast)
        await test_db.commit()
        await test_db.refresh(yeast)

        assert yeast.user_id == "test-user-789"

    async def test_equipment_user_id_nullable(self, test_db: AsyncSession):
        """Equipment user_id should be nullable for backward compatibility."""
        equipment = Equipment(
            name="Old Kettle",
            type="kettle",
            # No user_id - should work
        )
        test_db.add(equipment)
        await test_db.commit()
        await test_db.refresh(equipment)

        assert equipment.user_id is None


@pytest.mark.asyncio
class TestEquipmentRouterUserFiltering:
    """Test that equipment router filters by user_id."""

    async def test_list_equipment_filters_by_user(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        """List equipment should only return items owned by current user."""
        # Create equipment for two different users
        user1_equipment = Equipment(name="User1 Kettle", type="kettle", user_id="user-1")
        user2_equipment = Equipment(name="User2 Kettle", type="kettle", user_id="user-2")
        # Also create equipment for "local" user and null user_id (should be visible)
        local_equipment = Equipment(name="Local Kettle", type="kettle", user_id="local")
        null_equipment = Equipment(name="Legacy Kettle", type="kettle", user_id=None)
        test_db.add_all([user1_equipment, user2_equipment, local_equipment, null_equipment])
        await test_db.commit()

        # In LOCAL mode without auth, should see equipment owned by "local" user
        # or with null user_id (backward compatibility)
        response = await client.get("/api/inventory/equipment")
        assert response.status_code == 200

        data = response.json()
        equipment_names = [e["name"] for e in data]

        # User-1 and user-2 equipment should NOT be visible
        assert "User1 Kettle" not in equipment_names, \
            "Equipment from user-1 should not be visible to local user"
        assert "User2 Kettle" not in equipment_names, \
            "Equipment from user-2 should not be visible to local user"

        # Local and legacy equipment SHOULD be visible
        assert "Local Kettle" in equipment_names, \
            "Equipment from 'local' user should be visible"
        assert "Legacy Kettle" in equipment_names, \
            "Equipment with null user_id should be visible (backward compatibility)"

    async def test_create_equipment_sets_user_id(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        """Creating equipment should set user_id to current user."""
        response = await client.post(
            "/api/inventory/equipment",
            json={"name": "New Kettle", "type": "kettle"},
        )
        assert response.status_code == 201

        # In LOCAL mode, user_id should be set to "local"
        data = response.json()
        # The response might not include user_id in schema, so check database
        result = await test_db.execute(
            text("SELECT user_id FROM equipment WHERE id = :id"),
            {"id": data["id"]},
        )
        row = result.fetchone()
        assert row[0] == "local", "Created equipment should have user_id set to 'local'"

    async def test_get_equipment_enforces_ownership(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        """Get equipment should return 404 for equipment owned by another user."""
        # Create equipment owned by another user
        other_equipment = Equipment(name="Other Kettle", type="kettle", user_id="other-user")
        test_db.add(other_equipment)
        await test_db.commit()
        await test_db.refresh(other_equipment)

        # Try to access it as "local" user
        response = await client.get(f"/api/inventory/equipment/{other_equipment.id}")
        assert response.status_code == 404, \
            "Should return 404 for equipment owned by another user"

    async def test_update_equipment_enforces_ownership(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        """Update equipment should return 404 for equipment owned by another user."""
        other_equipment = Equipment(name="Other Kettle", type="kettle", user_id="other-user")
        test_db.add(other_equipment)
        await test_db.commit()
        await test_db.refresh(other_equipment)

        response = await client.put(
            f"/api/inventory/equipment/{other_equipment.id}",
            json={"name": "Hacked Kettle"},
        )
        assert response.status_code == 404, \
            "Should return 404 when trying to update equipment owned by another user"

    async def test_delete_equipment_enforces_ownership(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        """Delete equipment should return 404 for equipment owned by another user."""
        other_equipment = Equipment(name="Other Kettle", type="kettle", user_id="other-user")
        test_db.add(other_equipment)
        await test_db.commit()
        await test_db.refresh(other_equipment)

        response = await client.delete(f"/api/inventory/equipment/{other_equipment.id}")
        assert response.status_code == 404, \
            "Should return 404 when trying to delete equipment owned by another user"


@pytest.mark.asyncio
class TestHopInventoryRouterUserFiltering:
    """Test that hop inventory router filters by user_id."""

    async def test_list_hops_filters_by_user(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        """List hops should only return items owned by current user."""
        # Create hops for two different users
        user1_hop = HopInventory(variety="Citra", amount_grams=100, user_id="user-1")
        user2_hop = HopInventory(variety="Cascade", amount_grams=200, user_id="user-2")
        # Also create hops for "local" user and null user_id (should be visible)
        local_hop = HopInventory(variety="Simcoe", amount_grams=150, user_id="local")
        null_hop = HopInventory(variety="Mosaic", amount_grams=50, user_id=None)
        test_db.add_all([user1_hop, user2_hop, local_hop, null_hop])
        await test_db.commit()

        response = await client.get("/api/inventory/hops")
        assert response.status_code == 200

        data = response.json()
        hop_varieties = [h["variety"] for h in data]

        # User-1 and user-2 hops should NOT be visible
        assert "Citra" not in hop_varieties, \
            "Hops from user-1 should not be visible to local user"
        assert "Cascade" not in hop_varieties, \
            "Hops from user-2 should not be visible to local user"

        # Local and legacy hops SHOULD be visible
        assert "Simcoe" in hop_varieties, \
            "Hops from 'local' user should be visible"
        assert "Mosaic" in hop_varieties, \
            "Hops with null user_id should be visible (backward compatibility)"

    async def test_create_hop_sets_user_id(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        """Creating hop inventory should set user_id to current user."""
        response = await client.post(
            "/api/inventory/hops",
            json={"variety": "Simcoe", "amount_grams": 150},
        )
        assert response.status_code == 201

        data = response.json()
        result = await test_db.execute(
            text("SELECT user_id FROM hop_inventory WHERE id = :id"),
            {"id": data["id"]},
        )
        row = result.fetchone()
        assert row[0] == "local", "Created hop should have user_id set to 'local'"


@pytest.mark.asyncio
class TestYeastInventoryRouterUserFiltering:
    """Test that yeast inventory router filters by user_id."""

    async def test_list_yeast_filters_by_user(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        """List yeast should only return items owned by current user."""
        # Create yeast for two different users
        user1_yeast = YeastInventory(custom_name="US-05", quantity=1, form="dry", user_id="user-1")
        user2_yeast = YeastInventory(custom_name="S-04", quantity=2, form="dry", user_id="user-2")
        # Also create yeast for "local" user and null user_id (should be visible)
        local_yeast = YeastInventory(custom_name="WLP001", quantity=1, form="liquid", user_id="local")
        null_yeast = YeastInventory(custom_name="WY1056", quantity=1, form="liquid", user_id=None)
        test_db.add_all([user1_yeast, user2_yeast, local_yeast, null_yeast])
        await test_db.commit()

        response = await client.get("/api/inventory/yeast")
        assert response.status_code == 200

        data = response.json()
        yeast_names = [y["custom_name"] for y in data]

        # User-1 and user-2 yeast should NOT be visible
        assert "US-05" not in yeast_names, \
            "Yeast from user-1 should not be visible to local user"
        assert "S-04" not in yeast_names, \
            "Yeast from user-2 should not be visible to local user"

        # Local and legacy yeast SHOULD be visible
        assert "WLP001" in yeast_names, \
            "Yeast from 'local' user should be visible"
        assert "WY1056" in yeast_names, \
            "Yeast with null user_id should be visible (backward compatibility)"

    async def test_create_yeast_sets_user_id(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        """Creating yeast inventory should set user_id to current user."""
        response = await client.post(
            "/api/inventory/yeast",
            json={"custom_name": "WLP001", "quantity": 1, "form": "liquid"},
        )
        assert response.status_code == 201

        data = response.json()
        result = await test_db.execute(
            text("SELECT user_id FROM yeast_inventory WHERE id = :id"),
            {"id": data["id"]},
        )
        row = result.fetchone()
        assert row[0] == "local", "Created yeast should have user_id set to 'local'"


@pytest.mark.asyncio
class TestInventoryToolsUserFiltering:
    """Test that AG-UI inventory tools filter by user_id."""

    async def test_search_inventory_hops_filters_by_user(self, test_db: AsyncSession):
        """search_inventory_hops should only return hops owned by user."""
        from backend.services.llm.tools.inventory import search_inventory_hops

        # Create hops for different users
        user1_hop = HopInventory(variety="Citra", amount_grams=100, user_id="user-1")
        user2_hop = HopInventory(variety="Cascade", amount_grams=200, user_id="user-2")
        local_hop = HopInventory(variety="Simcoe", amount_grams=150, user_id="local")
        null_hop = HopInventory(variety="Mosaic", amount_grams=50, user_id=None)
        test_db.add_all([user1_hop, user2_hop, local_hop, null_hop])
        await test_db.commit()

        # Call with user_id="local" - should see local user + null
        result = await search_inventory_hops(db=test_db, user_id="local")

        hop_varieties = [h["variety"] for h in result["hops"]]

        # Should NOT see user-1 or user-2 hops
        assert "Citra" not in hop_varieties, "user-1 hops should not be visible"
        assert "Cascade" not in hop_varieties, "user-2 hops should not be visible"

        # Should see local and null hops
        assert "Simcoe" in hop_varieties, "local user hops should be visible"
        assert "Mosaic" in hop_varieties, "null user_id hops should be visible"

    async def test_search_inventory_yeast_filters_by_user(self, test_db: AsyncSession):
        """search_inventory_yeast should only return yeast owned by user."""
        from backend.services.llm.tools.inventory import search_inventory_yeast

        # Create yeast for different users
        user1_yeast = YeastInventory(custom_name="US-05", quantity=1, form="dry", user_id="user-1")
        user2_yeast = YeastInventory(custom_name="S-04", quantity=2, form="dry", user_id="user-2")
        local_yeast = YeastInventory(custom_name="WLP001", quantity=1, form="liquid", user_id="local")
        null_yeast = YeastInventory(custom_name="WY1056", quantity=1, form="liquid", user_id=None)
        test_db.add_all([user1_yeast, user2_yeast, local_yeast, null_yeast])
        await test_db.commit()

        # Call with user_id="local"
        result = await search_inventory_yeast(db=test_db, user_id="local")

        yeast_names = [y["name"] for y in result["yeasts"]]

        # Should NOT see user-1 or user-2 yeast
        assert "US-05" not in yeast_names, "user-1 yeast should not be visible"
        assert "S-04" not in yeast_names, "user-2 yeast should not be visible"

        # Should see local and null yeast
        assert "WLP001" in yeast_names, "local user yeast should be visible"
        assert "WY1056" in yeast_names, "null user_id yeast should be visible"

    async def test_get_equipment_filters_by_user(self, test_db: AsyncSession):
        """get_equipment should only return equipment owned by user."""
        from backend.services.llm.tools.inventory import get_equipment

        # Create equipment for different users
        user1_eq = Equipment(name="User1 Kettle", type="kettle", user_id="user-1")
        user2_eq = Equipment(name="User2 Kettle", type="kettle", user_id="user-2")
        local_eq = Equipment(name="Local Kettle", type="kettle", user_id="local")
        null_eq = Equipment(name="Legacy Kettle", type="kettle", user_id=None)
        test_db.add_all([user1_eq, user2_eq, local_eq, null_eq])
        await test_db.commit()

        # Call with user_id="local"
        result = await get_equipment(db=test_db, user_id="local")

        eq_names = [e["name"] for e in result["equipment"]]

        # Should NOT see user-1 or user-2 equipment
        assert "User1 Kettle" not in eq_names, "user-1 equipment should not be visible"
        assert "User2 Kettle" not in eq_names, "user-2 equipment should not be visible"

        # Should see local and null equipment
        assert "Local Kettle" in eq_names, "local user equipment should be visible"
        assert "Legacy Kettle" in eq_names, "null user_id equipment should be visible"

    async def test_get_inventory_summary_filters_by_user(self, test_db: AsyncSession):
        """get_inventory_summary should only count inventory owned by user."""
        from backend.services.llm.tools.inventory import get_inventory_summary

        # Create inventory for different users
        user1_hop = HopInventory(variety="Citra", amount_grams=100, user_id="user-1")
        local_hop = HopInventory(variety="Simcoe", amount_grams=150, user_id="local")
        null_hop = HopInventory(variety="Mosaic", amount_grams=50, user_id=None)
        test_db.add_all([user1_hop, local_hop, null_hop])
        await test_db.commit()

        # Call with user_id="local"
        result = await get_inventory_summary(db=test_db, user_id="local")

        # Should count 2 hop items (local + null), not 3
        assert result["hops"]["total_items"] == 2, \
            "Summary should only count user-owned hops"

        # Total grams should be 200 (150 + 50), not 300
        assert result["hops"]["total_grams"] == 200.0, \
            "Summary should only sum user-owned hop amounts"
