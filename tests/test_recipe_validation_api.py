"""Tests for recipe validation API endpoint."""
import pytest
from httpx import AsyncClient, ASGITransport

from backend.main import app
from backend.database import init_db


@pytest.fixture(scope="module", autouse=True)
async def setup_db():
    """Initialize database before tests."""
    await init_db()


@pytest.mark.asyncio
async def test_validate_brewsignal_minimal():
    """Minimal BrewSignal payload should validate."""
    payload = {
        "format": "brewsignal",
        "data": {
            "name": "Test IPA",
            "og": 1.050,
            "fg": 1.010,
        },
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/recipes/validate", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is True
    assert body["errors"] == []


@pytest.mark.asyncio
async def test_validate_brewsignal_invalid():
    """Invalid BrewSignal payload should return errors."""
    payload = {
        "format": "brewsignal",
        "data": {
            "name": "Bad Recipe",
            "og": "1.050",  # Invalid type
            "fg": 1.010,
        },
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/recipes/validate", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is False
    assert len(body["errors"]) > 0


@pytest.mark.asyncio
async def test_validate_beerjson_minimal():
    """Minimal BeerJSON payload should validate."""
    payload = {
        "format": "beerjson",
        "data": {
            "beerjson": {
                "version": 1.0,
                "recipes": [{
                    "name": "BeerJSON Test",
                    "original_gravity": {"value": 1.050, "unit": "sg"},
                    "final_gravity": {"value": 1.010, "unit": "sg"},
                }],
            }
        },
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/recipes/validate", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is True
    assert body["errors"] == []


@pytest.mark.asyncio
async def test_validate_unsupported_format():
    """Unsupported formats should return 400."""
    payload = {
        "format": "beerxml",
        "data": {"recipe": {"name": "Test"}},
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/recipes/validate", json=payload)

    assert response.status_code == 400
