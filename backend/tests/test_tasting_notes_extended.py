"""Tests for extended tasting note API endpoints."""

import pytest
from httpx import AsyncClient


class TestTastingNotesExtendedAPI:
    """Test extended tasting note fields in API."""

    @pytest.mark.asyncio
    async def test_create_tasting_note_with_context(self, client: AsyncClient):
        """POST tasting note accepts context fields."""
        # Create a batch first
        batch_resp = await client.post("/api/batches", json={"name": "Test Batch", "status": "fermenting"})
        assert batch_resp.status_code == 201
        batch_id = batch_resp.json()["id"]

        response = await client.post(
            f"/api/batches/{batch_id}/tasting-notes",
            json={
                "batch_id": batch_id,
                "days_since_packaging": 14,
                "serving_temp_c": 4.0,
                "glassware": "tulip",
                "appearance_score": 4,
                "appearance_notes": "Clear golden color",
                "aroma_score": 4,
                "flavor_score": 5,
                "mouthfeel_score": 4,
                "overall_score": 4,
            }
        )
        assert response.status_code == 201
        data = response.json()
        assert data["days_since_packaging"] == 14
        assert data["serving_temp_c"] == 4.0
        assert data["glassware"] == "tulip"

    @pytest.mark.asyncio
    async def test_create_tasting_note_calculates_total(self, client: AsyncClient):
        """POST tasting note calculates total_score."""
        # Create a batch first
        batch_resp = await client.post("/api/batches", json={"name": "Test Batch", "status": "fermenting"})
        assert batch_resp.status_code == 201
        batch_id = batch_resp.json()["id"]

        response = await client.post(
            f"/api/batches/{batch_id}/tasting-notes",
            json={
                "batch_id": batch_id,
                "appearance_score": 4,
                "aroma_score": 4,
                "flavor_score": 5,
                "mouthfeel_score": 4,
                "overall_score": 4,
            }
        )
        assert response.status_code == 201
        data = response.json()
        assert data["total_score"] == 21  # 4+4+5+4+4

    @pytest.mark.asyncio
    async def test_tasting_note_style_assessment(self, client: AsyncClient):
        """POST tasting note accepts style assessment fields."""
        # Create a batch first
        batch_resp = await client.post("/api/batches", json={"name": "Test Batch", "status": "fermenting"})
        assert batch_resp.status_code == 201
        batch_id = batch_resp.json()["id"]

        response = await client.post(
            f"/api/batches/{batch_id}/tasting-notes",
            json={
                "batch_id": batch_id,
                "appearance_score": 3,
                "to_style": False,
                "style_deviation_notes": "Too dark for style, more like a brown ale"
            }
        )
        assert response.status_code == 201
        data = response.json()
        assert data["to_style"] is False
        assert "Too dark" in data["style_deviation_notes"]

    @pytest.mark.asyncio
    async def test_create_tasting_note_partial_scores(self, client: AsyncClient):
        """POST tasting note calculates total_score with partial scores."""
        # Create a batch first
        batch_resp = await client.post("/api/batches", json={"name": "Test Batch", "status": "fermenting"})
        assert batch_resp.status_code == 201
        batch_id = batch_resp.json()["id"]

        response = await client.post(
            f"/api/batches/{batch_id}/tasting-notes",
            json={
                "batch_id": batch_id,
                "appearance_score": 4,
                "flavor_score": 5,
                # Other scores omitted
            }
        )
        assert response.status_code == 201
        data = response.json()
        assert data["total_score"] == 9  # 4+5

    @pytest.mark.asyncio
    async def test_create_tasting_note_no_scores(self, client: AsyncClient):
        """POST tasting note with no scores has None total_score."""
        # Create a batch first
        batch_resp = await client.post("/api/batches", json={"name": "Test Batch", "status": "fermenting"})
        assert batch_resp.status_code == 201
        batch_id = batch_resp.json()["id"]

        response = await client.post(
            f"/api/batches/{batch_id}/tasting-notes",
            json={
                "batch_id": batch_id,
                "appearance_notes": "Just some notes without scores",
            }
        )
        assert response.status_code == 201
        data = response.json()
        assert data["total_score"] is None

    @pytest.mark.asyncio
    async def test_create_tasting_note_sets_user_id(self, client: AsyncClient):
        """POST tasting note sets user_id from authenticated user."""
        # Create a batch first
        batch_resp = await client.post("/api/batches", json={"name": "Test Batch", "status": "fermenting"})
        assert batch_resp.status_code == 201
        batch_id = batch_resp.json()["id"]

        response = await client.post(
            f"/api/batches/{batch_id}/tasting-notes",
            json={
                "batch_id": batch_id,
                "appearance_score": 4,
            }
        )
        assert response.status_code == 201
        data = response.json()
        # In local mode, user_id is "local"
        assert data["user_id"] == "local"

    @pytest.mark.asyncio
    async def test_update_tasting_note_recalculates_total(self, client: AsyncClient):
        """PUT tasting note recalculates total_score when scores change."""
        # Create a batch first
        batch_resp = await client.post("/api/batches", json={"name": "Test Batch", "status": "fermenting"})
        assert batch_resp.status_code == 201
        batch_id = batch_resp.json()["id"]

        # Create a note with scores
        create_resp = await client.post(
            f"/api/batches/{batch_id}/tasting-notes",
            json={
                "batch_id": batch_id,
                "appearance_score": 4,
                "aroma_score": 4,
            }
        )
        assert create_resp.status_code == 201
        note_id = create_resp.json()["id"]
        assert create_resp.json()["total_score"] == 8

        # Update scores
        response = await client.put(
            f"/api/batches/{batch_id}/tasting-notes/{note_id}",
            json={
                "flavor_score": 5,
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total_score"] == 13  # 4+4+5

    @pytest.mark.asyncio
    async def test_update_tasting_note_context_fields(self, client: AsyncClient):
        """PUT tasting note updates context fields."""
        # Create a batch first
        batch_resp = await client.post("/api/batches", json={"name": "Test Batch", "status": "fermenting"})
        assert batch_resp.status_code == 201
        batch_id = batch_resp.json()["id"]

        # Create a note
        create_resp = await client.post(
            f"/api/batches/{batch_id}/tasting-notes",
            json={
                "batch_id": batch_id,
                "appearance_score": 4,
            }
        )
        assert create_resp.status_code == 201
        note_id = create_resp.json()["id"]

        # Update context fields
        response = await client.put(
            f"/api/batches/{batch_id}/tasting-notes/{note_id}",
            json={
                "days_since_packaging": 21,
                "serving_temp_c": 6.0,
                "glassware": "pint",
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["days_since_packaging"] == 21
        assert data["serving_temp_c"] == 6.0
        assert data["glassware"] == "pint"
