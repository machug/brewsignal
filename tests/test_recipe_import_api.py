"""Tests for recipe import API endpoint."""
import pytest
from pathlib import Path
from httpx import AsyncClient, ASGITransport
from backend.main import app
from backend.database import init_db


@pytest.fixture(scope="module", autouse=True)
async def setup_db():
    """Initialize database before tests."""
    await init_db()


@pytest.mark.asyncio
async def test_import_beerxml_via_api():
    """Test importing BeerXML via API endpoint."""
    # Load test file
    test_file = Path("docs/Brewfather_BeerXML_PhilterXPAClone_20251207.xml")
    with open(test_file, "rb") as f:
        content = f.read()

    # Send POST request
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/recipes/import",
            files={"file": ("recipe.xml", content, "application/xml")}
        )

    # Verify response
    assert response.status_code == 201
    data = response.json()

    assert "id" in data
    assert data["name"] == "Philter XPA - Clone"
    assert data["author"] == "Pig Den Brewing"
    assert data["og"] == pytest.approx(1.040)
    assert data["batch_size_liters"] == pytest.approx(21.0)


@pytest.mark.asyncio
async def test_import_brewfather_json_via_api():
    """Test importing Brewfather JSON via API endpoint."""
    # Load test file
    test_file = Path("docs/Brewfather_RECIPE_PhilterXPAClone_20251207.json")
    with open(test_file, "rb") as f:
        content = f.read()

    # Send POST request
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/recipes/import",
            files={"file": ("recipe.json", content, "application/json")}
        )

    # Verify response
    assert response.status_code == 201
    data = response.json()

    assert "id" in data
    assert data["name"] == "Philter XPA - Clone"


@pytest.mark.asyncio
async def test_import_beerjson_via_api():
    """Test importing BeerJSON via API endpoint."""
    # Create minimal BeerJSON document
    beerjson_content = """{
        "beerjson": {
            "version": 1.0,
            "recipes": [{
                "name": "API Test Recipe",
                "type": "all grain",
                "author": "Test",
                "batch_size": {"value": 20.0, "unit": "l"},
                "boil": {
                    "boil_time": {"value": 60, "unit": "min"}
                },
                "efficiency": {
                    "brewhouse": {"value": 0.75, "unit": "%"}
                },
                "original_gravity": {"value": 1.050, "unit": "sg"},
                "ingredients": {
                    "fermentable_additions": [{
                        "name": "Pale Malt",
                        "type": "grain",
                        "amount": {"value": 5.0, "unit": "kg"},
                        "color": {"value": 3, "unit": "SRM"},
                        "yield": {
                            "fine_grind": {"value": 0.80, "unit": "%"}
                        }
                    }]
                }
            }]
        }
    }"""

    # Send POST request
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/recipes/import",
            files={"file": ("recipe.json", beerjson_content.encode(), "application/json")}
        )

    # Verify response
    assert response.status_code == 201
    data = response.json()

    assert "id" in data
    assert data["name"] == "API Test Recipe"
    assert data["og"] == pytest.approx(1.050)


@pytest.mark.asyncio
async def test_import_invalid_file():
    """Test handling invalid file content."""
    invalid_content = b"<INVALID>XML</INVALID>"

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/recipes/import",
            files={"file": ("recipe.xml", invalid_content, "application/xml")}
        )

    # Verify error response
    assert response.status_code == 400
    data = response.json()

    assert "detail" in data
    assert len(data["detail"]) > 0


@pytest.mark.asyncio
async def test_import_validation_error():
    """Test handling BeerJSON validation errors."""
    # Missing required fields
    invalid_beerjson = b"""{
        "beerjson": {
            "version": 1.0,
            "recipes": [{
                "name": "Invalid Recipe"
            }]
        }
    }"""

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/recipes/import",
            files={"file": ("recipe.json", invalid_beerjson, "application/json")}
        )

    # Verify error response
    assert response.status_code == 400
    data = response.json()

    assert "detail" in data
    assert isinstance(data["detail"], list)


@pytest.mark.asyncio
async def test_import_auto_detect_format():
    """Test that format is auto-detected from file content."""
    # Load BeerXML file
    test_file = Path("docs/Brewfather_BeerXML_PhilterXPAClone_20251207.xml")
    with open(test_file, "rb") as f:
        content = f.read()

    # Don't specify format in request
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/recipes/import",
            files={"file": ("recipe.xml", content, "application/xml")}
        )

    # Verify it still works
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Philter XPA - Clone"
