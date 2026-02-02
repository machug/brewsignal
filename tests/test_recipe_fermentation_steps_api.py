"""Tests for Recipe Fermentation Steps sub-resource API endpoints."""
import pytest
from httpx import AsyncClient, ASGITransport
from backend.main import app
from backend.database import init_db, async_session_factory
from backend.models import Recipe, RecipeFermentationStep


@pytest.fixture(scope="module", autouse=True)
async def setup_db():
    """Initialize database before tests."""
    await init_db()


@pytest.fixture
async def sample_recipe_id():
    """Create a sample recipe and return its ID."""
    async with async_session_factory() as session:
        recipe = Recipe(
            user_id="local",  # Matches LOCAL mode auth user
            name="Test Fermentation Recipe",
            og=1.055,
            fg=1.012,
            abv=5.6,
            batch_size_liters=20.0,
        )
        session.add(recipe)
        await session.commit()
        await session.refresh(recipe)
        recipe_id = recipe.id
    return recipe_id


@pytest.fixture
async def async_client():
    """Create an async HTTP client for testing."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
def auth_headers():
    """Return empty headers for local mode (no auth required)."""
    # In LOCAL deployment mode, no auth headers are needed
    return {}


@pytest.mark.asyncio
async def test_get_fermentation_steps_empty(async_client: AsyncClient, auth_headers: dict, sample_recipe_id: int):
    """GET /recipes/{id}/fermentation-steps returns empty list when no steps exist."""
    response = await async_client.get(
        f"/api/recipes/{sample_recipe_id}/fermentation-steps",
        headers=auth_headers
    )
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_put_fermentation_steps(async_client: AsyncClient, auth_headers: dict, sample_recipe_id: int):
    """PUT /recipes/{id}/fermentation-steps replaces all fermentation steps."""
    new_steps = [
        {"step_number": 1, "type": "primary", "temp_c": 18, "time_days": 14},
        {"step_number": 2, "type": "conditioning", "temp_c": 4, "time_days": 7}
    ]

    response = await async_client.put(
        f"/api/recipes/{sample_recipe_id}/fermentation-steps",
        json=new_steps,
        headers=auth_headers
    )
    assert response.status_code == 200

    data = response.json()
    assert len(data) == 2
    assert data[0]["type"] == "primary"
    assert data[0]["temp_c"] == 18
    assert data[0]["step_number"] == 1
    assert data[1]["type"] == "conditioning"
    assert data[1]["temp_c"] == 4


@pytest.mark.asyncio
async def test_get_fermentation_steps(async_client: AsyncClient, auth_headers: dict, sample_recipe_id: int):
    """GET /recipes/{id}/fermentation-steps returns fermentation steps."""
    # First add some steps
    new_steps = [
        {"step_number": 1, "type": "primary", "temp_c": 19, "time_days": 10},
    ]
    await async_client.put(
        f"/api/recipes/{sample_recipe_id}/fermentation-steps",
        json=new_steps,
        headers=auth_headers
    )

    # Now get them
    response = await async_client.get(
        f"/api/recipes/{sample_recipe_id}/fermentation-steps",
        headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    # Check that our step is there
    primary_step = next((s for s in data if s["type"] == "primary"), None)
    assert primary_step is not None
    assert primary_step["temp_c"] == 19


@pytest.mark.asyncio
async def test_delete_fermentation_steps(async_client: AsyncClient, auth_headers: dict, sample_recipe_id: int):
    """DELETE /recipes/{id}/fermentation-steps removes all fermentation steps."""
    # First add some steps
    new_steps = [
        {"step_number": 1, "type": "primary", "temp_c": 20, "time_days": 7},
    ]
    await async_client.put(
        f"/api/recipes/{sample_recipe_id}/fermentation-steps",
        json=new_steps,
        headers=auth_headers
    )

    # Now delete them
    response = await async_client.delete(
        f"/api/recipes/{sample_recipe_id}/fermentation-steps",
        headers=auth_headers
    )
    assert response.status_code == 200

    # Verify deletion
    get_response = await async_client.get(
        f"/api/recipes/{sample_recipe_id}/fermentation-steps",
        headers=auth_headers
    )
    assert get_response.json() == []


@pytest.mark.asyncio
async def test_get_fermentation_steps_recipe_not_found(async_client: AsyncClient, auth_headers: dict):
    """GET /recipes/{id}/fermentation-steps returns 404 for non-existent recipe."""
    response = await async_client.get(
        "/api/recipes/99999/fermentation-steps",
        headers=auth_headers
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_put_fermentation_steps_recipe_not_found(async_client: AsyncClient, auth_headers: dict):
    """PUT /recipes/{id}/fermentation-steps returns 404 for non-existent recipe."""
    new_steps = [{"step_number": 1, "type": "primary", "temp_c": 18, "time_days": 14}]
    response = await async_client.put(
        "/api/recipes/99999/fermentation-steps",
        json=new_steps,
        headers=auth_headers
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_fermentation_steps_recipe_not_found(async_client: AsyncClient, auth_headers: dict):
    """DELETE /recipes/{id}/fermentation-steps returns 404 for non-existent recipe."""
    response = await async_client.delete(
        "/api/recipes/99999/fermentation-steps",
        headers=auth_headers
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_put_fermentation_steps_replaces_existing(async_client: AsyncClient, auth_headers: dict, sample_recipe_id: int):
    """PUT /recipes/{id}/fermentation-steps replaces all existing steps."""
    # Add initial steps
    initial_steps = [
        {"step_number": 1, "type": "primary", "temp_c": 18, "time_days": 14},
        {"step_number": 2, "type": "secondary", "temp_c": 16, "time_days": 7},
    ]
    await async_client.put(
        f"/api/recipes/{sample_recipe_id}/fermentation-steps",
        json=initial_steps,
        headers=auth_headers
    )

    # Replace with different steps
    new_steps = [
        {"step_number": 1, "type": "conditioning", "temp_c": 2, "time_days": 30},
    ]
    response = await async_client.put(
        f"/api/recipes/{sample_recipe_id}/fermentation-steps",
        json=new_steps,
        headers=auth_headers
    )
    assert response.status_code == 200

    # Verify only new steps exist
    data = response.json()
    assert len(data) == 1
    assert data[0]["type"] == "conditioning"
    assert data[0]["temp_c"] == 2
