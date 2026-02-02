"""Tests for Recipe Mash Steps sub-resource API endpoints."""

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
            name="Test Mash Steps Recipe",
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
async def test_get_mash_steps(async_client: AsyncClient, sample_recipe_id: int):
    """GET /recipes/{id}/mash-steps returns mash steps."""
    response = await async_client.get(
        f"/api/recipes/{sample_recipe_id}/mash-steps",
    )
    assert response.status_code == 200
    assert isinstance(response.json(), list)


@pytest.mark.asyncio
async def test_put_mash_steps_replaces_all(async_client: AsyncClient, sample_recipe_id: int):
    """PUT /recipes/{id}/mash-steps replaces all mash steps."""
    new_steps = [
        {"step_number": 1, "name": "Mash In", "type": "infusion", "temp_c": 67, "time_minutes": 60},
        {"step_number": 2, "name": "Mash Out", "type": "temperature", "temp_c": 76, "time_minutes": 10}
    ]

    response = await async_client.put(
        f"/api/recipes/{sample_recipe_id}/mash-steps",
        json=new_steps,
    )
    assert response.status_code == 200

    data = response.json()
    assert len(data) == 2
    assert data[0]["name"] == "Mash In"
    assert data[0]["temp_c"] == 67
    assert data[1]["name"] == "Mash Out"


@pytest.mark.asyncio
async def test_delete_mash_steps(async_client: AsyncClient, sample_recipe_id: int):
    """DELETE /recipes/{id}/mash-steps removes all mash steps."""
    # First add some steps
    steps = [
        {"step_number": 1, "name": "Test Step", "type": "infusion", "temp_c": 65, "time_minutes": 60}
    ]
    await async_client.put(
        f"/api/recipes/{sample_recipe_id}/mash-steps",
        json=steps,
    )

    # Now delete
    response = await async_client.delete(
        f"/api/recipes/{sample_recipe_id}/mash-steps",
    )
    assert response.status_code == 200

    # Verify empty
    get_response = await async_client.get(
        f"/api/recipes/{sample_recipe_id}/mash-steps",
    )
    assert get_response.json() == []


@pytest.mark.asyncio
async def test_get_mash_steps_not_found(async_client: AsyncClient):
    """GET /recipes/{id}/mash-steps returns 404 for non-existent recipe."""
    response = await async_client.get("/api/recipes/99999/mash-steps")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_put_mash_steps_not_found(async_client: AsyncClient):
    """PUT /recipes/{id}/mash-steps returns 404 for non-existent recipe."""
    steps = [{"step_number": 1, "name": "Test", "type": "infusion", "temp_c": 65, "time_minutes": 60}]
    response = await async_client.put("/api/recipes/99999/mash-steps", json=steps)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_mash_steps_not_found(async_client: AsyncClient):
    """DELETE /recipes/{id}/mash-steps returns 404 for non-existent recipe."""
    response = await async_client.delete("/api/recipes/99999/mash-steps")
    assert response.status_code == 404
