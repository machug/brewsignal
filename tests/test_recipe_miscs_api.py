"""Tests for Recipe Miscs sub-resource API endpoints."""

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
            name="Test Miscs Recipe",
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
async def test_get_miscs(async_client: AsyncClient, sample_recipe_id: int):
    """GET /recipes/{id}/miscs returns misc ingredients."""
    response = await async_client.get(
        f"/api/recipes/{sample_recipe_id}/miscs",
    )
    assert response.status_code == 200
    assert isinstance(response.json(), list)


@pytest.mark.asyncio
async def test_put_miscs_replaces_all(async_client: AsyncClient, sample_recipe_id: int):
    """PUT /recipes/{id}/miscs replaces all misc ingredients."""
    new_miscs = [
        {"name": "Irish Moss", "type": "fining", "use": "boil", "time_min": 15, "amount_kg": 0.001},
        {"name": "Coriander", "type": "spice", "use": "boil", "time_min": 5, "amount_kg": 0.015}
    ]

    response = await async_client.put(
        f"/api/recipes/{sample_recipe_id}/miscs",
        json=new_miscs,
    )
    assert response.status_code == 200

    data = response.json()
    assert len(data) == 2
    assert data[0]["name"] == "Irish Moss"


@pytest.mark.asyncio
async def test_delete_miscs(async_client: AsyncClient, sample_recipe_id: int):
    """DELETE /recipes/{id}/miscs removes all misc ingredients."""
    # First add some miscs
    miscs = [
        {"name": "Test Misc", "type": "spice", "use": "boil", "time_min": 10, "amount_kg": 0.005}
    ]
    await async_client.put(
        f"/api/recipes/{sample_recipe_id}/miscs",
        json=miscs,
    )

    # Now delete
    response = await async_client.delete(
        f"/api/recipes/{sample_recipe_id}/miscs",
    )
    assert response.status_code == 200

    # Verify empty
    get_response = await async_client.get(
        f"/api/recipes/{sample_recipe_id}/miscs",
    )
    assert get_response.json() == []


@pytest.mark.asyncio
async def test_get_miscs_not_found(async_client: AsyncClient):
    """GET /recipes/{id}/miscs returns 404 for non-existent recipe."""
    response = await async_client.get("/api/recipes/99999/miscs")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_put_miscs_not_found(async_client: AsyncClient):
    """PUT /recipes/{id}/miscs returns 404 for non-existent recipe."""
    miscs = [{"name": "Test", "type": "spice", "use": "boil", "time_min": 10, "amount_kg": 0.005}]
    response = await async_client.put("/api/recipes/99999/miscs", json=miscs)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_miscs_not_found(async_client: AsyncClient):
    """DELETE /recipes/{id}/miscs returns 404 for non-existent recipe."""
    response = await async_client.delete("/api/recipes/99999/miscs")
    assert response.status_code == 404
