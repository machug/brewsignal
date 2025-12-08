"""Recipe import orchestrator - coordinates the full import pipeline."""
import json
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.parsers.beerxml_parser import BeerXMLParser
from backend.services.converters.beerxml_to_beerjson import BeerXMLToBeerJSONConverter
from backend.services.converters.brewfather_to_beerjson import BrewfatherToBeerJSONConverter
from backend.services.validators.beerjson_validator import BeerJSONValidator
from backend.services.serializers.recipe_serializer import RecipeSerializer
from backend.models import Recipe


@dataclass
class ImportResult:
    """Result of recipe import operation."""
    success: bool
    format: Optional[str]  # Detected format: beerxml, brewfather, beerjson
    recipe: Optional[Recipe]
    errors: List[str]


class RecipeImporter:
    """Orchestrate recipe import: Parse → Convert → Validate → Serialize → Persist."""

    def __init__(self):
        """Initialize import pipeline components."""
        self.beerxml_parser = BeerXMLParser()
        self.beerxml_converter = BeerXMLToBeerJSONConverter()
        self.brewfather_converter = BrewfatherToBeerJSONConverter()
        self.validator = BeerJSONValidator()
        self.serializer = RecipeSerializer()

    async def import_recipe(
        self,
        content: str,
        format_hint: Optional[str],
        session: AsyncSession
    ) -> ImportResult:
        """Import recipe from any supported format.

        Pipeline stages:
        1. Auto-detect format (if not provided)
        2. Parse source format to dict
        3. Convert to BeerJSON (if needed)
        4. Validate against BeerJSON schema
        5. Serialize to SQLAlchemy models
        6. Persist to database

        Args:
            content: Recipe file content as string
            format_hint: Optional format hint ('beerxml', 'brewfather', 'beerjson')
            session: Async SQLAlchemy session

        Returns:
            ImportResult with success status, recipe, and any errors
        """
        errors = []
        detected_format = None
        beerjson_dict = None

        try:
            # Stage 1: Auto-detect format
            if format_hint:
                detected_format = format_hint.lower()
            else:
                detected_format = self._detect_format(content)
                if not detected_format:
                    return ImportResult(
                        success=False,
                        format=None,
                        recipe=None,
                        errors=["Unable to detect recipe format. File must be BeerXML, Brewfather JSON, or BeerJSON."]
                    )

            # Stage 2: Parse source format
            try:
                if detected_format == "beerxml":
                    parsed_dict = self.beerxml_parser.parse(content)
                elif detected_format == "brewfather":
                    parsed_dict = json.loads(content)
                elif detected_format == "beerjson":
                    parsed_dict = json.loads(content)
                else:
                    await session.rollback()
                    return ImportResult(
                        success=False,
                        format=detected_format,
                        recipe=None,
                        errors=[f"Unsupported format: {detected_format}"]
                    )
            except ValueError as e:
                await session.rollback()
                return ImportResult(
                    success=False,
                    format=detected_format,
                    recipe=None,
                    errors=[f"Parse error: {str(e)}"]
                )
            except json.JSONDecodeError as e:
                await session.rollback()
                return ImportResult(
                    success=False,
                    format=detected_format,
                    recipe=None,
                    errors=[f"Invalid JSON: {str(e)}"]
                )

            # Stage 3: Convert to BeerJSON (if needed)
            try:
                if detected_format == "beerxml":
                    beerjson_dict = self.beerxml_converter.convert(parsed_dict)
                elif detected_format == "brewfather":
                    beerjson_dict = self.brewfather_converter.convert(parsed_dict)
                elif detected_format == "beerjson":
                    beerjson_dict = parsed_dict
            except Exception as e:
                await session.rollback()
                return ImportResult(
                    success=False,
                    format=detected_format,
                    recipe=None,
                    errors=[f"Conversion error: {str(e)}"]
                )

            # Stage 4: Validate against BeerJSON schema (only for native BeerJSON files)
            # Skip validation for converted formats (BeerXML, Brewfather) since they
            # have different required fields and converting to BeerJSON may create
            # incomplete documents that fail strict validation
            if detected_format == "beerjson":
                is_valid, validation_errors = self.validator.validate(beerjson_dict)
                if not is_valid:
                    await session.rollback()
                    return ImportResult(
                        success=False,
                        format=detected_format,
                        recipe=None,
                        errors=[f"Validation error: {err}" for err in validation_errors]
                    )

            # Stage 5: Serialize to SQLAlchemy models
            try:
                # Extract first recipe from BeerJSON document
                beerjson_recipe = beerjson_dict['beerjson']['recipes'][0]
                recipe = await self.serializer.serialize(beerjson_recipe, session)
            except Exception as e:
                await session.rollback()
                return ImportResult(
                    success=False,
                    format=detected_format,
                    recipe=None,
                    errors=[f"Serialization error: {str(e)}"]
                )

            # Stage 6: Persist to database
            try:
                session.add(recipe)
                await session.flush()  # Flush to get ID, but don't commit yet
            except Exception as e:
                await session.rollback()
                return ImportResult(
                    success=False,
                    format=detected_format,
                    recipe=None,
                    errors=[f"Database error: {str(e)}"]
                )

            # Success!
            return ImportResult(
                success=True,
                format=detected_format,
                recipe=recipe,
                errors=[]
            )

        except Exception as e:
            # Catch-all for unexpected errors
            await session.rollback()
            return ImportResult(
                success=False,
                format=detected_format,
                recipe=None,
                errors=[f"Unexpected error: {str(e)}"]
            )

    def _detect_format(self, content: str) -> Optional[str]:
        """Auto-detect recipe format from content.

        Detection strategy:
        1. Check if starts with '<' -> BeerXML
        2. Try parsing as JSON:
           - Has 'beerjson' key -> BeerJSON
           - Otherwise -> Brewfather JSON

        Args:
            content: Recipe file content

        Returns:
            Format string ('beerxml', 'brewfather', 'beerjson') or None
        """
        content = content.strip()

        # Check for XML (BeerXML)
        if content.startswith('<'):
            return "beerxml"

        # Try parsing as JSON
        try:
            data = json.loads(content)

            # Check for BeerJSON structure
            if isinstance(data, dict) and 'beerjson' in data:
                return "beerjson"

            # Otherwise assume Brewfather JSON
            return "brewfather"

        except json.JSONDecodeError:
            # Not JSON, not XML - unknown format
            return None
