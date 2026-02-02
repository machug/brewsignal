"""Tests for Recipe Water Adjustments sub-resource API endpoints."""

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
            name="Test Water Adjustments Recipe",
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
async def test_get_water_adjustments(async_client: AsyncClient, sample_recipe_id: int):
    """GET /recipes/{id}/water-adjustments returns water adjustments."""
    response = await async_client.get(
        f"/api/recipes/{sample_recipe_id}/water-adjustments",
    )
    assert response.status_code == 200
    assert isinstance(response.json(), list)


@pytest.mark.asyncio
async def test_put_water_adjustments(async_client: AsyncClient, sample_recipe_id: int):
    """PUT /recipes/{id}/water-adjustments replaces all water adjustments."""
    new_adjustments = [
        {"stage": "mash", "volume_liters": 15, "calcium_sulfate_g": 2.5, "calcium_chloride_g": 1.5},
        {"stage": "sparge", "volume_liters": 18, "calcium_sulfate_g": 2.0, "acid_type": "lactic", "acid_ml": 1.5}
    ]

    response = await async_client.put(
        f"/api/recipes/{sample_recipe_id}/water-adjustments",
        json=new_adjustments,
    )
    assert response.status_code == 200

    data = response.json()
    assert len(data) == 2
    mash = next(a for a in data if a["stage"] == "mash")
    assert mash["calcium_sulfate_g"] == 2.5


@pytest.mark.asyncio
async def test_delete_water_adjustments(async_client: AsyncClient, sample_recipe_id: int):
    """DELETE /recipes/{id}/water-adjustments removes all water adjustments."""
    # First add some adjustments
    adjustments = [
        {"stage": "mash", "volume_liters": 15, "calcium_sulfate_g": 2.0}
    ]
    await async_client.put(
        f"/api/recipes/{sample_recipe_id}/water-adjustments",
        json=adjustments,
    )

    # Now delete
    response = await async_client.delete(
        f"/api/recipes/{sample_recipe_id}/water-adjustments",
    )
    assert response.status_code == 200

    # Verify empty
    get_response = await async_client.get(
        f"/api/recipes/{sample_recipe_id}/water-adjustments",
    )
    assert get_response.json() == []


@pytest.mark.asyncio
async def test_get_water_adjustments_not_found(async_client: AsyncClient):
    """GET /recipes/{id}/water-adjustments returns 404 for non-existent recipe."""
    response = await async_client.get("/api/recipes/99999/water-adjustments")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_put_water_adjustments_not_found(async_client: AsyncClient):
    """PUT /recipes/{id}/water-adjustments returns 404 for non-existent recipe."""
    adjustments = [{"stage": "mash", "volume_liters": 15}]
    response = await async_client.put("/api/recipes/99999/water-adjustments", json=adjustments)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_water_adjustments_not_found(async_client: AsyncClient):
    """DELETE /recipes/{id}/water-adjustments returns 404 for non-existent recipe."""
    response = await async_client.delete("/api/recipes/99999/water-adjustments")
    assert response.status_code == 404
