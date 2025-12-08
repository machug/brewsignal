"""Tests for RecipeImporter orchestrator."""
import pytest
from pathlib import Path

from backend.services.importers.recipe_importer import RecipeImporter, ImportResult
from backend.database import init_db, get_db
from backend.models import Recipe
from sqlalchemy import select


@pytest.fixture
async def db_session():
    """Create test database session."""
    await init_db()
    async for session in get_db():
        yield session
        break


@pytest.mark.asyncio
async def test_import_beerxml_success(db_session):
    """Test importing BeerXML file successfully."""
    # Load test file
    test_file = Path("docs/Brewfather_BeerXML_PhilterXPAClone_20251207.xml")
    with open(test_file, "r") as f:
        content = f.read()

    # Import recipe
    importer = RecipeImporter()
    result = await importer.import_recipe(content, "beerxml", db_session)

    # Verify success
    assert result.success is True
    assert len(result.errors) == 0
    assert result.recipe is not None
    assert result.recipe.name == "Philter XPA - Clone"
    assert result.recipe.author == "Pig Den Brewing"
    assert result.recipe.og == pytest.approx(1.040)

    # Verify ingredients loaded
    assert len(result.recipe.fermentables) == 4
    assert len(result.recipe.hops) == 6
    assert len(result.recipe.cultures) == 1

    # Verify mash steps loaded
    assert len(result.recipe.mash_steps) == 3

    # Verify database persistence
    await db_session.commit()
    recipe_id = result.recipe.id

    # Query back from DB
    stmt = select(Recipe).where(Recipe.id == recipe_id)
    db_result = await db_session.execute(stmt)
    db_recipe = db_result.scalar_one()

    assert db_recipe.name == "Philter XPA - Clone"


@pytest.mark.asyncio
async def test_import_brewfather_json_success(db_session):
    """Test importing Brewfather JSON file successfully."""
    # Load test file
    test_file = Path("docs/Brewfather_RECIPE_PhilterXPAClone_20251207.json")
    with open(test_file, "r") as f:
        content = f.read()

    # Import recipe
    importer = RecipeImporter()
    result = await importer.import_recipe(content, "brewfather", db_session)

    # Verify success
    assert result.success is True
    assert len(result.errors) == 0
    assert result.recipe is not None
    assert result.recipe.name == "Philter XPA - Clone"


@pytest.mark.asyncio
async def test_import_beerjson_success(db_session):
    """Test importing BeerJSON file successfully."""
    # Create minimal BeerJSON document
    beerjson_content = """{
        "beerjson": {
            "version": 1.0,
            "recipes": [{
                "name": "Test Recipe",
                "type": "all grain",
                "author": "Test Author",
                "batch_size": {"value": 20.0, "unit": "l"},
                "boil": {
                    "boil_time": {"value": 60, "unit": "min"}
                },
                "efficiency": {
                    "brewhouse": {"value": 0.75, "unit": "%"}
                },
                "original_gravity": {"value": 1.050, "unit": "sg"},
                "final_gravity": {"value": 1.010, "unit": "sg"},
                "ingredients": {
                    "fermentable_additions": [{
                        "name": "Pale Malt",
                        "type": "grain",
                        "amount": {"value": 5.0, "unit": "kg"},
                        "color": {"value": 3, "unit": "SRM"},
                        "yield": {
                            "fine_grind": {"value": 0.80, "unit": "%"}
                        }
                    }],
                    "hop_additions": [{
                        "name": "Cascade",
                        "form": "pellet",
                        "alpha_acid": {"value": 0.055, "unit": "%"},
                        "amount": {"value": 50, "unit": "g"},
                        "timing": {
                            "use": "add_to_boil",
                            "duration": {"value": 60, "unit": "min"}
                        }
                    }],
                    "culture_additions": [{
                        "name": "US-05",
                        "type": "ale",
                        "form": "dry",
                        "amount": {"value": 1, "unit": "pkg"}
                    }]
                },
                "mash": {
                    "name": "Single Infusion",
                    "grain_temperature": {"value": 20, "unit": "C"},
                    "mash_steps": [{
                        "name": "Saccharification",
                        "type": "temperature",
                        "step_temperature": {"value": 66, "unit": "C"},
                        "step_time": {"value": 60, "unit": "min"}
                    }]
                }
            }]
        }
    }"""

    # Import recipe
    importer = RecipeImporter()
    result = await importer.import_recipe(beerjson_content, "beerjson", db_session)

    # Verify success
    assert result.success is True
    assert len(result.errors) == 0
    assert result.recipe is not None
    assert result.recipe.name == "Test Recipe"
    assert result.recipe.og == pytest.approx(1.050)


@pytest.mark.asyncio
async def test_import_auto_detect_beerxml(db_session):
    """Test auto-detecting BeerXML format."""
    # Load test file
    test_file = Path("docs/Brewfather_BeerXML_PhilterXPAClone_20251207.xml")
    with open(test_file, "r") as f:
        content = f.read()

    # Import without specifying format
    importer = RecipeImporter()
    result = await importer.import_recipe(content, None, db_session)

    # Verify success
    assert result.success is True
    assert result.format == "beerxml"
    assert result.recipe.name == "Philter XPA - Clone"


@pytest.mark.asyncio
async def test_import_auto_detect_brewfather_json(db_session):
    """Test auto-detecting Brewfather JSON format."""
    # Load test file
    test_file = Path("docs/Brewfather_RECIPE_PhilterXPAClone_20251207.json")
    with open(test_file, "r") as f:
        content = f.read()

    # Import without specifying format
    importer = RecipeImporter()
    result = await importer.import_recipe(content, None, db_session)

    # Verify success
    assert result.success is True
    assert result.format == "brewfather"


@pytest.mark.asyncio
async def test_import_auto_detect_beerjson(db_session):
    """Test auto-detecting BeerJSON format."""
    beerjson_content = """{
        "beerjson": {
            "version": 1.0,
            "recipes": [{
                "name": "Test BeerJSON",
                "type": "all grain",
                "author": "Test",
                "batch_size": {"value": 20.0, "unit": "l"},
                "boil": {
                    "boil_time": {"value": 60, "unit": "min"}
                },
                "efficiency": {
                    "brewhouse": {"value": 0.75, "unit": "%"}
                },
                "ingredients": {
                    "fermentable_additions": []
                }
            }]
        }
    }"""

    # Import without specifying format
    importer = RecipeImporter()
    result = await importer.import_recipe(beerjson_content, None, db_session)

    # Verify success
    assert result.success is True
    assert result.format == "beerjson"


@pytest.mark.asyncio
async def test_import_invalid_xml(db_session):
    """Test handling invalid XML."""
    content = "<RECIPES><RECIPE>Invalid XML without closing tags"

    importer = RecipeImporter()
    result = await importer.import_recipe(content, "beerxml", db_session)

    # Verify failure
    assert result.success is False
    assert len(result.errors) > 0
    assert "Invalid XML" in result.errors[0]
    assert result.recipe is None


@pytest.mark.asyncio
async def test_import_invalid_json(db_session):
    """Test handling invalid JSON."""
    content = '{"beerjson": {"version": "1.0", "recipes": ['

    importer = RecipeImporter()
    result = await importer.import_recipe(content, "beerjson", db_session)

    # Verify failure
    assert result.success is False
    assert len(result.errors) > 0
    assert result.recipe is None


@pytest.mark.asyncio
async def test_import_validation_errors(db_session):
    """Test handling BeerJSON validation errors."""
    # Missing required fields
    invalid_beerjson = """{
        "beerjson": {
            "version": "1.0",
            "recipes": [{
                "name": "Invalid Recipe"
            }]
        }
    }"""

    importer = RecipeImporter()
    result = await importer.import_recipe(invalid_beerjson, "beerjson", db_session)

    # Verify failure with validation errors
    assert result.success is False
    assert len(result.errors) > 0
    assert result.recipe is None


@pytest.mark.asyncio
async def test_import_database_rollback_on_error(db_session):
    """Test that database transaction rolls back on error."""
    # Get initial recipe count
    stmt = select(Recipe)
    initial_count = len((await db_session.execute(stmt)).scalars().all())

    # Try to import invalid data
    invalid_content = "<INVALID>XML</INVALID>"

    importer = RecipeImporter()
    result = await importer.import_recipe(invalid_content, "beerxml", db_session)

    # Verify no recipe was created
    assert result.success is False
    final_count = len((await db_session.execute(stmt)).scalars().all())
    assert final_count == initial_count


def test_import_result_structure():
    """Test ImportResult data structure."""
    # Success result
    success_result = ImportResult(
        success=True,
        format="beerxml",
        recipe=None,
        errors=[]
    )
    assert success_result.success is True
    assert success_result.format == "beerxml"
    assert len(success_result.errors) == 0

    # Failure result
    failure_result = ImportResult(
        success=False,
        format=None,
        recipe=None,
        errors=["Error 1", "Error 2"]
    )
    assert failure_result.success is False
    assert len(failure_result.errors) == 2
