"""Tests for reflections API endpoints."""

import pytest
from httpx import AsyncClient


class TestReflectionsAPI:
    """Test reflection CRUD endpoints."""

    @pytest.mark.asyncio
    async def test_create_reflection(self, client: AsyncClient):
        """POST /api/batches/{id}/reflections creates a reflection."""
        # Create a batch first
        batch_resp = await client.post("/api/batches", json={"name": "Test Batch", "status": "fermenting"})
        assert batch_resp.status_code == 201
        batch_id = batch_resp.json()["id"]

        response = await client.post(
            f"/api/batches/{batch_id}/reflections",
            json={
                "phase": "brew_day",
                "what_went_well": "Hit mash temp on first try",
                "metrics": {"efficiency_actual": 72.5, "efficiency_expected": 75.0}
            }
        )
        assert response.status_code == 201
        data = response.json()
        assert data["phase"] == "brew_day"
        assert data["what_went_well"] == "Hit mash temp on first try"
        assert data["metrics"]["efficiency_actual"] == 72.5

    @pytest.mark.asyncio
    async def test_create_reflection_invalid_phase(self, client: AsyncClient):
        """POST /api/batches/{id}/reflections rejects invalid phase."""
        batch_resp = await client.post("/api/batches", json={"name": "Test Batch", "status": "fermenting"})
        batch_id = batch_resp.json()["id"]

        response = await client.post(
            f"/api/batches/{batch_id}/reflections",
            json={"phase": "invalid_phase"}
        )
        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_create_reflection_duplicate_phase(self, client: AsyncClient):
        """POST /api/batches/{id}/reflections rejects duplicate phase."""
        batch_resp = await client.post("/api/batches", json={"name": "Test Batch", "status": "fermenting"})
        batch_id = batch_resp.json()["id"]

        # Create first reflection
        await client.post(
            f"/api/batches/{batch_id}/reflections",
            json={"phase": "brew_day"}
        )

        # Try to create duplicate
        response = await client.post(
            f"/api/batches/{batch_id}/reflections",
            json={"phase": "brew_day"}
        )
        assert response.status_code == 409
        assert "already exists" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_list_reflections(self, client: AsyncClient):
        """GET /api/batches/{id}/reflections returns all reflections."""
        batch_resp = await client.post("/api/batches", json={"name": "Test Batch", "status": "fermenting"})
        batch_id = batch_resp.json()["id"]

        await client.post(
            f"/api/batches/{batch_id}/reflections",
            json={"phase": "brew_day", "what_went_well": "Good efficiency"}
        )

        response = await client.get(f"/api/batches/{batch_id}/reflections")
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        assert data[0]["phase"] == "brew_day"

    @pytest.mark.asyncio
    async def test_list_reflections_empty(self, client: AsyncClient):
        """GET /api/batches/{id}/reflections returns empty list for new batch."""
        batch_resp = await client.post("/api/batches", json={"name": "Test Batch", "status": "fermenting"})
        batch_id = batch_resp.json()["id"]

        response = await client.get(f"/api/batches/{batch_id}/reflections")
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_get_reflection_by_phase(self, client: AsyncClient):
        """GET /api/batches/{id}/reflections/{phase} returns specific phase."""
        batch_resp = await client.post("/api/batches", json={"name": "Test Batch", "status": "fermenting"})
        batch_id = batch_resp.json()["id"]

        await client.post(
            f"/api/batches/{batch_id}/reflections",
            json={"phase": "fermentation", "what_went_well": "Clean fermentation"}
        )

        response = await client.get(f"/api/batches/{batch_id}/reflections/fermentation")
        assert response.status_code == 200
        data = response.json()
        assert data["phase"] == "fermentation"

    @pytest.mark.asyncio
    async def test_get_reflection_by_phase_not_found(self, client: AsyncClient):
        """GET /api/batches/{id}/reflections/{phase} returns 404 for missing phase."""
        batch_resp = await client.post("/api/batches", json={"name": "Test Batch", "status": "fermenting"})
        batch_id = batch_resp.json()["id"]

        response = await client.get(f"/api/batches/{batch_id}/reflections/brew_day")
        assert response.status_code == 404
        assert "No reflection found" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_update_reflection(self, client: AsyncClient):
        """PUT /api/batches/{id}/reflections/{id} updates a reflection."""
        batch_resp = await client.post("/api/batches", json={"name": "Test Batch", "status": "fermenting"})
        batch_id = batch_resp.json()["id"]

        create_resp = await client.post(
            f"/api/batches/{batch_id}/reflections",
            json={"phase": "brew_day"}
        )
        reflection_id = create_resp.json()["id"]

        response = await client.put(
            f"/api/batches/{batch_id}/reflections/{reflection_id}",
            json={"lessons_learned": "Start heating strike water earlier"}
        )
        assert response.status_code == 200
        assert response.json()["lessons_learned"] == "Start heating strike water earlier"

    @pytest.mark.asyncio
    async def test_update_reflection_not_found(self, client: AsyncClient):
        """PUT /api/batches/{id}/reflections/{id} returns 404 for missing reflection."""
        batch_resp = await client.post("/api/batches", json={"name": "Test Batch", "status": "fermenting"})
        batch_id = batch_resp.json()["id"]

        response = await client.put(
            f"/api/batches/{batch_id}/reflections/99999",
            json={"lessons_learned": "Something"}
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_reflection_batch_not_found(self, client: AsyncClient):
        """Reflection endpoints return 404 for non-existent batch."""
        response = await client.get("/api/batches/99999/reflections")
        assert response.status_code == 404

        response = await client.post(
            "/api/batches/99999/reflections",
            json={"phase": "brew_day"}
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_reflection_partial(self, client: AsyncClient):
        """PUT /api/batches/{id}/reflections/{id} allows partial updates."""
        batch_resp = await client.post("/api/batches", json={"name": "Test Batch", "status": "fermenting"})
        batch_id = batch_resp.json()["id"]

        create_resp = await client.post(
            f"/api/batches/{batch_id}/reflections",
            json={
                "phase": "brew_day",
                "what_went_well": "Good efficiency",
                "what_went_wrong": "Boil over"
            }
        )
        reflection_id = create_resp.json()["id"]

        # Update only one field
        response = await client.put(
            f"/api/batches/{batch_id}/reflections/{reflection_id}",
            json={"lessons_learned": "Watch the boil more carefully"}
        )
        assert response.status_code == 200
        data = response.json()
        # Original fields should be preserved
        assert data["what_went_well"] == "Good efficiency"
        assert data["what_went_wrong"] == "Boil over"
        # New field should be set
        assert data["lessons_learned"] == "Watch the boil more carefully"
