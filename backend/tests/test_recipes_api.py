"""Tests for recipes API endpoints."""

import pytest
import pytest_asyncio

from backend.models import Recipe


@pytest_asyncio.fixture
async def test_recipe(test_db):
    """Create a test recipe for update tests."""
    recipe = Recipe(
        name="Test Recipe",
        og=1.050,
        fg=1.010,
        abv=5.0,
        batch_size_liters=20
    )
    test_db.add(recipe)
    await test_db.commit()
    await test_db.refresh(recipe)
    return recipe


@pytest.mark.asyncio
async def test_list_recipes_empty(client):
    """GET /api/recipes should return empty list when no recipes exist."""
    response = await client.get("/api/recipes")

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_create_recipe(client):
    """POST /api/recipes should create a new recipe."""
    recipe_data = {
        "name": "Test Recipe",
        "author": "Tester",
        "og": 1.050,
        "fg": 1.010,
        "yeast_name": "US-05",
        "yeast_temp_min": 15.0,
        "yeast_temp_max": 22.0,
    }

    response = await client.post("/api/recipes", json=recipe_data)

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test Recipe"
    assert data["og"] == 1.050
    assert data["yeast_temp_min"] == 15.0
    assert "id" in data


@pytest.mark.asyncio
async def test_get_recipe(client):
    """GET /api/recipes/{id} should return specific recipe."""
    # Create recipe first
    recipe_data = {"name": "Get Test Recipe"}
    create_response = await client.post("/api/recipes", json=recipe_data)
    recipe_id = create_response.json()["id"]

    # Get it
    response = await client.get(f"/api/recipes/{recipe_id}")

    assert response.status_code == 200
    assert response.json()["name"] == "Get Test Recipe"


@pytest.mark.asyncio
async def test_get_recipe_not_found(client):
    """GET /api/recipes/{id} should return 404 for non-existent recipe."""
    response = await client.get("/api/recipes/99999")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_import_beerxml(client):
    """POST /api/recipes/import should import BeerXML file."""
    beerxml = """<?xml version="1.0"?>
    <RECIPES>
      <RECIPE>
        <NAME>Imported IPA</NAME>
        <OG>1.065</OG>
        <FG>1.012</FG>
        <YEASTS>
          <YEAST>
            <NAME>US-05</NAME>
            <MIN_TEMPERATURE>15.0</MIN_TEMPERATURE>
            <MAX_TEMPERATURE>22.0</MAX_TEMPERATURE>
          </YEAST>
        </YEASTS>
      </RECIPE>
    </RECIPES>
    """

    response = await client.post(
        "/api/recipes/import",
        files={"file": ("recipe.xml", beerxml, "text/xml")},
    )

    assert response.status_code in (200, 201)  # Accept both 200 OK and 201 Created
    data = response.json()
    assert data["name"] == "Imported IPA"
    assert data["og"] == 1.065
    assert data["yeast_name"] == "US-05"


@pytest.mark.asyncio
async def test_update_recipe(client):
    """PUT /api/recipes/{id} should update recipe fields."""
    # Create recipe first
    recipe_data = {
        "name": "Original Name",
        "og": 1.050,
        "fg": 1.010,
        "ibu": 40,
        "color_srm": 10,
    }
    create_response = await client.post("/api/recipes", json=recipe_data)
    recipe_id = create_response.json()["id"]

    # Update it
    update_data = {
        "name": "Updated Name",
        "og": 1.055,
        "ibu": 45,
        "batch_size_liters": 19.0,
        "yeast_name": "US-05",
    }
    response = await client.put(f"/api/recipes/{recipe_id}", json=update_data)

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated Name"
    assert data["og"] == 1.055
    assert data["fg"] == 1.010  # Unchanged
    assert data["ibu"] == 45
    assert data["color_srm"] == 10  # Unchanged
    assert data["batch_size_liters"] == 19.0
    assert data["yeast_name"] == "US-05"


@pytest.mark.asyncio
async def test_update_recipe_not_found(client):
    """PUT /api/recipes/{id} should return 404 for non-existent recipe."""
    response = await client.put("/api/recipes/99999", json={"name": "New Name"})
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_recipe_partial(client):
    """PUT /api/recipes/{id} should allow partial updates."""
    # Create recipe
    create_response = await client.post("/api/recipes", json={"name": "Test", "og": 1.050})
    recipe_id = create_response.json()["id"]

    # Update only name
    response = await client.put(f"/api/recipes/{recipe_id}", json={"name": "Updated"})

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated"
    assert data["og"] == 1.050  # Should be unchanged


@pytest.mark.asyncio
async def test_update_recipe_protected_fields(client):
    """PUT /api/recipes/{id} should only update whitelisted fields."""
    # Create recipe
    create_response = await client.post("/api/recipes", json={"name": "Test Recipe", "og": 1.050})
    recipe_id = create_response.json()["id"]
    original_created_at = create_response.json()["created_at"]

    # Attempt to update with a protected field (created_at is not in allowed_fields)
    # The endpoint should ignore the protected field
    response = await client.put(
        f"/api/recipes/{recipe_id}",
        json={"name": "Updated Name", "created_at": "2099-01-01T00:00:00Z"}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated Name"  # Allowed field should update
    assert data["created_at"] == original_created_at  # Protected field should NOT change


@pytest.mark.asyncio
async def test_delete_recipe(client):
    """DELETE /api/recipes/{id} should remove recipe."""
    # Create recipe first
    create_response = await client.post("/api/recipes", json={"name": "Delete Me"})
    recipe_id = create_response.json()["id"]

    # Delete it
    response = await client.delete(f"/api/recipes/{recipe_id}")
    assert response.status_code == 200

    # Verify deleted
    get_response = await client.get(f"/api/recipes/{recipe_id}")
    assert get_response.status_code == 404


@pytest.mark.asyncio
async def test_import_beerxml_invalid_extension(client):
    """POST /api/recipes/import should reject non-XML file extensions."""
    response = await client.post(
        "/api/recipes/import",
        files={"file": ("recipe.txt", "not xml content", "text/plain")},
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "file type" in detail.lower() or "xml" in detail.lower() or "json" in detail.lower()


@pytest.mark.asyncio
async def test_import_beerxml_invalid_mime_type(client):
    """POST /api/recipes/import should reject invalid MIME types."""
    response = await client.post(
        "/api/recipes/import",
        files={"file": ("recipe.xml", "content", "text/plain")},
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    detail_str = detail if isinstance(detail, str) else " ".join(detail)
    assert "xml" in detail_str.lower() or "format" in detail_str.lower() or "parse" in detail_str.lower()


@pytest.mark.asyncio
async def test_import_beerxml_file_too_large(client):
    """POST /api/recipes/import should reject files larger than 1MB."""
    # Create content larger than 1MB
    large_content = "x" * (1_000_001)

    response = await client.post(
        "/api/recipes/import",
        files={"file": ("recipe.xml", large_content, "text/xml")},
    )

    assert response.status_code == 400
    assert "large" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_import_beerxml_invalid_xml(client):
    """POST /api/recipes/import should reject malformed XML."""
    invalid_xml = "<RECIPES><RECIPE>unclosed tag"

    response = await client.post(
        "/api/recipes/import",
        files={"file": ("recipe.xml", invalid_xml, "text/xml")},
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    detail_str = detail if isinstance(detail, str) else " ".join(detail)
    assert "xml" in detail_str.lower() or "parse" in detail_str.lower() or "format" in detail_str.lower()


@pytest.mark.asyncio
async def test_import_beerxml_non_utf8(client):
    """POST /api/recipes/import should reject non-UTF-8 encoded files."""
    # Use Latin-1 encoding
    non_utf8_content = b"<?xml version='1.0'?><RECIPES><RECIPE><NAME>\xe9</NAME></RECIPE></RECIPES>"

    response = await client.post(
        "/api/recipes/import",
        files={"file": ("recipe.xml", non_utf8_content, "text/xml")},
    )

    assert response.status_code == 400
    assert "utf-8" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_import_beerxml_empty_file(client):
    """POST /api/recipes/import should reject empty XML files."""
    response = await client.post(
        "/api/recipes/import",
        files={"file": ("recipe.xml", "", "text/xml")},
    )

    assert response.status_code == 400


# ========================================
# Validation Tests
# ========================================


@pytest.mark.asyncio
async def test_create_recipe_og_less_than_fg(client):
    """Creating recipe with OG <= FG should fail."""
    response = await client.post("/api/recipes", json={
        "name": "Invalid Gravity Test",
        "og": 1.010,
        "fg": 1.050,
        "abv": 5.0,
        "batch_size_liters": 20
    })
    assert response.status_code == 400
    assert "greater than final gravity" in response.json()["detail"]


@pytest.mark.asyncio
async def test_create_recipe_zero_batch_size(client):
    """Creating recipe with batch_size <= 0 should fail."""
    response = await client.post("/api/recipes", json={
        "name": "Zero Batch Size Test",
        "og": 1.050,
        "fg": 1.010,
        "abv": 5.0,
        "batch_size_liters": 0
    })
    assert response.status_code == 400
    assert "greater than zero" in response.json()["detail"]


@pytest.mark.asyncio
async def test_create_recipe_negative_batch_size(client):
    """Creating recipe with negative batch_size should fail."""
    response = await client.post("/api/recipes", json={
        "name": "Negative Batch Size Test",
        "og": 1.050,
        "fg": 1.010,
        "abv": 5.0,
        "batch_size_liters": -10
    })
    assert response.status_code == 400
    assert "greater than zero" in response.json()["detail"]


@pytest.mark.asyncio
async def test_create_recipe_abv_too_high(client):
    """Creating recipe with ABV > 20 should fail."""
    response = await client.post("/api/recipes", json={
        "name": "High ABV Test",
        "og": 1.050,
        "fg": 1.010,
        "abv": 25.0,
        "batch_size_liters": 20
    })
    assert response.status_code == 400
    assert "between 0% and 20%" in response.json()["detail"]


@pytest.mark.asyncio
async def test_create_recipe_negative_abv(client):
    """Creating recipe with negative ABV should fail."""
    response = await client.post("/api/recipes", json={
        "name": "Negative ABV Test",
        "og": 1.050,
        "fg": 1.010,
        "abv": -5.0,
        "batch_size_liters": 20
    })
    assert response.status_code == 400
    assert "between 0% and 20%" in response.json()["detail"]


@pytest.mark.asyncio
async def test_update_recipe_partial_og_creates_invalid_state(
    client,
    test_recipe: Recipe
):
    """Updating only OG to value < existing FG should fail."""
    # test_recipe has og=1.050, fg=1.010
    response = await client.put(f"/api/recipes/{test_recipe.id}", json={
        "og": 1.005  # Less than existing fg=1.010
    })
    assert response.status_code == 400
    assert "greater than final gravity" in response.json()["detail"]


@pytest.mark.asyncio
async def test_update_recipe_partial_fg_creates_invalid_state(
    client,
    test_recipe: Recipe
):
    """Updating only FG to value > existing OG should fail."""
    # test_recipe has og=1.050, fg=1.010
    response = await client.put(f"/api/recipes/{test_recipe.id}", json={
        "fg": 1.060  # Greater than existing og=1.050
    })
    assert response.status_code == 400
    assert "greater than final gravity" in response.json()["detail"]


@pytest.mark.asyncio
async def test_update_recipe_valid_partial_update(
    client,
    test_recipe: Recipe
):
    """Updating OG to valid value should succeed."""
    # test_recipe has og=1.050, fg=1.010
    response = await client.put(f"/api/recipes/{test_recipe.id}", json={
        "og": 1.055  # Valid: still > fg
    })
    assert response.status_code == 200
    assert response.json()["og"] == 1.055
