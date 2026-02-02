"""Tests for Recipe Water Profiles sub-resource API endpoints."""

import pytest
from httpx import AsyncClient, ASGITransport
from backend.main import app
from backend.database import init_db, async_session_factory
from backend.models import Recipe


@pytest.fixture(scope="module", autouse=True)
async def setup_db():
    """Initialize database before tests."""
    await init_db()


@pytest.fixture
async def async_client():
    """Create async test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
async def sample_recipe_id():
    """Create a sample recipe and return its ID."""
    async with async_session_factory() as session:
        recipe = Recipe(
            user_id="local",  # Matches the fallback user in local mode
            name="Test Water Profiles Recipe",
            og=1.050,
            fg=1.010,
            batch_size_liters=20.0,
        )
        session.add(recipe)
        await session.commit()
        await session.refresh(recipe)
        yield recipe.id
        # Cleanup
        await session.delete(recipe)
        await session.commit()


@pytest.mark.asyncio
async def test_get_water_profiles(async_client: AsyncClient, sample_recipe_id: int):
    """GET /recipes/{id}/water-profiles returns water profiles."""
    response = await async_client.get(
        f"/api/recipes/{sample_recipe_id}/water-profiles",
    )
    assert response.status_code == 200
    assert isinstance(response.json(), list)


@pytest.mark.asyncio
async def test_put_water_profiles(async_client: AsyncClient, sample_recipe_id: int):
    """PUT /recipes/{id}/water-profiles replaces all water profiles."""
    new_profiles = [
        {"profile_type": "source", "name": "Melbourne", "calcium_ppm": 10, "sulfate_ppm": 5},
        {"profile_type": "target", "name": "Dublin", "calcium_ppm": 120, "sulfate_ppm": 54}
    ]

    response = await async_client.put(
        f"/api/recipes/{sample_recipe_id}/water-profiles",
        json=new_profiles,
    )
    assert response.status_code == 200

    data = response.json()
    assert len(data) == 2
    source = next(p for p in data if p["profile_type"] == "source")
    assert source["name"] == "Melbourne"
    assert source["calcium_ppm"] == 10


@pytest.mark.asyncio
async def test_delete_water_profiles(async_client: AsyncClient, sample_recipe_id: int):
    """DELETE /recipes/{id}/water-profiles removes all water profiles."""
    # First add some profiles
    profiles = [
        {"profile_type": "source", "name": "Test Source", "calcium_ppm": 50}
    ]
    await async_client.put(
        f"/api/recipes/{sample_recipe_id}/water-profiles",
        json=profiles,
    )

    # Now delete
    response = await async_client.delete(
        f"/api/recipes/{sample_recipe_id}/water-profiles",
    )
    assert response.status_code == 200

    # Verify empty
    get_response = await async_client.get(
        f"/api/recipes/{sample_recipe_id}/water-profiles",
    )
    assert get_response.json() == []


@pytest.mark.asyncio
async def test_get_water_profiles_not_found(async_client: AsyncClient):
    """GET /recipes/{id}/water-profiles returns 404 for non-existent recipe."""
    response = await async_client.get("/api/recipes/99999/water-profiles")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_put_water_profiles_not_found(async_client: AsyncClient):
    """PUT /recipes/{id}/water-profiles returns 404 for non-existent recipe."""
    profiles = [{"profile_type": "source", "name": "Test"}]
    response = await async_client.put("/api/recipes/99999/water-profiles", json=profiles)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_water_profiles_not_found(async_client: AsyncClient):
    """DELETE /recipes/{id}/water-profiles returns 404 for non-existent recipe."""
    response = await async_client.delete("/api/recipes/99999/water-profiles")
    assert response.status_code == 404
