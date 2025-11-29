"""Tests for tilt API endpoints."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Tilt


@pytest.mark.asyncio
class TestTiltOriginalGravityAPI:
    """Test tilt original gravity update functionality."""

    async def test_update_og_sets_value(self, client: AsyncClient, test_db: AsyncSession):
        """Test setting original gravity on a tilt."""
        # Create a tilt
        tilt = Tilt(id="test-og-tilt", color="RED", beer_name="Test Beer")
        test_db.add(tilt)
        await test_db.commit()

        # Update OG
        response = await client.put(
            "/api/tilts/test-og-tilt",
            json={"original_gravity": 1.055}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["original_gravity"] == 1.055

        # Verify via GET
        response = await client.get("/api/tilts/test-og-tilt")
        assert response.status_code == 200
        assert response.json()["original_gravity"] == 1.055

    async def test_update_og_can_clear_to_null(self, client: AsyncClient, test_db: AsyncSession):
        """Test clearing original gravity to null."""
        # Create a tilt with OG set
        tilt = Tilt(id="test-og-clear", color="GREEN", beer_name="Test Beer", original_gravity=1.060)
        test_db.add(tilt)
        await test_db.commit()

        # Verify OG is set
        response = await client.get("/api/tilts/test-og-clear")
        assert response.json()["original_gravity"] == 1.060

        # Clear OG by setting to null
        response = await client.put(
            "/api/tilts/test-og-clear",
            json={"original_gravity": None}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["original_gravity"] is None

        # Verify via GET
        response = await client.get("/api/tilts/test-og-clear")
        assert response.json()["original_gravity"] is None

    async def test_update_og_without_field_preserves_value(self, client: AsyncClient, test_db: AsyncSession):
        """Test that not providing OG field preserves existing value."""
        # Create a tilt with OG set
        tilt = Tilt(id="test-og-preserve", color="BLUE", beer_name="Test Beer", original_gravity=1.050)
        test_db.add(tilt)
        await test_db.commit()

        # Update only beer_name, not OG
        response = await client.put(
            "/api/tilts/test-og-preserve",
            json={"beer_name": "New Beer Name"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["beer_name"] == "New Beer Name"
        assert data["original_gravity"] == 1.050  # Preserved

    async def test_update_og_validates_range(self, client: AsyncClient, test_db: AsyncSession):
        """Test that OG values are validated to be in valid range."""
        # Create a tilt
        tilt = Tilt(id="test-og-validate", color="YELLOW", beer_name="Test Beer")
        test_db.add(tilt)
        await test_db.commit()

        # Try to set OG too low
        response = await client.put(
            "/api/tilts/test-og-validate",
            json={"original_gravity": 0.9}
        )
        assert response.status_code == 422  # Validation error

        # Try to set OG too high
        response = await client.put(
            "/api/tilts/test-og-validate",
            json={"original_gravity": 1.3}
        )
        assert response.status_code == 422  # Validation error

        # Set valid OG
        response = await client.put(
            "/api/tilts/test-og-validate",
            json={"original_gravity": 1.100}
        )
        assert response.status_code == 200
        assert response.json()["original_gravity"] == 1.100

    async def test_update_tilt_not_found(self, client: AsyncClient):
        """Test updating non-existent tilt."""
        response = await client.put(
            "/api/tilts/nonexistent",
            json={"original_gravity": 1.050}
        )
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
class TestTiltUpdateModel:
    """Test TiltUpdate Pydantic model behavior."""

    def test_is_field_set_when_provided(self):
        """Test is_field_set returns True when field is explicitly provided."""
        from backend.models import TiltUpdate
        
        # Field provided with value
        update = TiltUpdate(original_gravity=1.050)
        assert update.is_field_set("original_gravity") is True
        
        # Field provided with null
        update = TiltUpdate(original_gravity=None)
        assert update.is_field_set("original_gravity") is True

    def test_is_field_set_when_not_provided(self):
        """Test is_field_set returns False when field is not provided."""
        from backend.models import TiltUpdate
        
        # Empty update
        update = TiltUpdate()
        assert update.is_field_set("original_gravity") is False
        
        # Only other field provided
        update = TiltUpdate(beer_name="Test")
        assert update.is_field_set("original_gravity") is False
        assert update.is_field_set("beer_name") is True
