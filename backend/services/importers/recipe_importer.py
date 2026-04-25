"""Recipe import orchestrator - coordinates the full import pipeline."""
import json
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.parsers.beerxml_parser import BeerXMLParser
from backend.services.converters.beerxml_to_beerjson import BeerXMLToBeerJSONConverter
from backend.services.converters.brewfather_to_beerjson import BrewfatherToBeerJSONConverter
from backend.services.converters.brewsignal_to_beerjson import BrewSignalToBeerJSONConverter
from backend.services.validators.beerjson_validator import BeerJSONValidator
from backend.services.serializers.recipe_serializer import RecipeSerializer
from backend.services.brewsignal_format import BrewSignalRecipe
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
        self.brewsignal_converter = BrewSignalToBeerJSONConverter()
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
        bs_payload: Optional[Dict[str, Any]] = None

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
                elif detected_format in ("brewfather", "beerjson", "brewsignal"):
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
                    # Converter attaches Brewfather water under
                    # _brewfather_water itself; no extra step needed.
                    beerjson_dict = self.brewfather_converter.convert(parsed_dict)
                elif detected_format == "brewsignal":
                    # Strip envelope/markers before strict validation
                    # (BrewSignalRecipe sets extra=forbid). Recipe payloads
                    # may carry _format / brewsignal_version metadata or
                    # be wrapped under a "recipe" key.
                    cleaned = parsed_dict
                    if isinstance(cleaned, dict) and 'recipe' in cleaned \
                            and isinstance(cleaned['recipe'], dict):
                        cleaned = cleaned['recipe']
                    bs_payload = {
                        k: v for k, v in cleaned.items()
                        if k not in ('_format', 'brewsignal_version')
                    }
                    BrewSignalRecipe.model_validate(bs_payload)
                    beerjson_dict = self.brewsignal_converter.convert(bs_payload)
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
                # The serializer doesn't carry style_id through the BeerJSON
                # `style` object. For native BrewSignal imports, apply the
                # original style_id directly so the FK column is populated.
                if detected_format == "brewsignal" and bs_payload \
                        and bs_payload.get('style_id'):
                    recipe.style_id = bs_payload['style_id']
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
            if not isinstance(data, dict):
                return None

            # Check for BeerJSON structure (wrapped envelope)
            if 'beerjson' in data:
                return "beerjson"

            # Native BrewSignal: flat JSON, no wrapper, but uses snake_case
            # keys like batch_size_liters/color_srm/boil_time_minutes that
            # Brewfather (camelCase) does not. _format/brewsignal_version
            # are explicit markers when present.
            if data.get('_format') == 'brewsignal' or 'brewsignal_version' in data:
                return "brewsignal"
            brewsignal_keys = {'batch_size_liters', 'color_srm', 'boil_time_minutes',
                               'fermentation_steps', 'mash_steps'}
            if any(k in data for k in brewsignal_keys):
                return "brewsignal"

            # Nested fingerprints — a sparse BrewSignal recipe may not
            # have any of the top-level snake_case keys but still uses
            # BrewSignal-only ingredient field names like amount_kg /
            # amount_grams / alpha_acid_percent (Brewfather uses amount
            # in kg with a unit string, and alpha at the hop root).
            ferms = data.get('fermentables') or []
            if isinstance(ferms, list) and ferms and isinstance(ferms[0], dict) \
                    and 'amount_kg' in ferms[0]:
                return "brewsignal"
            hops = data.get('hops') or []
            if isinstance(hops, list) and hops and isinstance(hops[0], dict) \
                    and ('amount_grams' in hops[0] or 'alpha_acid_percent' in hops[0]):
                return "brewsignal"
            # Singular `yeast` object (any shape) is BrewSignal-specific.
            # Brewfather uses a `yeasts` array, so a top-level `yeast` dict
            # would silently disappear through the Brewfather converter.
            if isinstance(data.get('yeast'), dict):
                return "brewsignal"
            miscs = data.get('miscs') or []
            if isinstance(miscs, list) and miscs and isinstance(miscs[0], dict) \
                    and 'amount_grams' in miscs[0]:
                return "brewsignal"

            # `{"recipe": {...}}` envelope is BrewSignal (Brewfather has
            # no such wrapper).
            if isinstance(data.get('recipe'), dict):
                return "brewsignal"

            # Brewfather positive markers. Distinct camelCase top-level
            # keys, the _type sentinel exports always carry, and a few
            # scalar field names that Brewfather uses but BrewSignal
            # does not (BrewSignal uses color_srm, not color; style as
            # an object vs. style_id string).
            brewfather_markers = {
                '_type', 'batchSize', 'boilTime', 'boilSize',
                'mashAdjustments', 'spargeAdjustments', 'yeasts',
            }
            if any(k in data for k in brewfather_markers):
                return "brewfather"
            # `color` at root without BrewSignal's `color_srm` is a
            # Brewfather-shaped trimmed export.
            if 'color' in data and 'color_srm' not in data:
                return "brewfather"
            # Brewfather embeds style as an object; BrewSignal uses a
            # `style_id` string instead.
            if isinstance(data.get('style'), dict):
                return "brewfather"
            # Brewfather uses scalar `efficiency` and `carbonation`
            # (BrewSignal uses efficiency_percent / carbonation_vols).
            for bf_scalar, bs_scalar in (
                ('efficiency', 'efficiency_percent'),
                ('carbonation', 'carbonation_vols'),
            ):
                if bf_scalar in data and bs_scalar not in data:
                    return "brewfather"
            # Brewfather ingredient items use raw `amount` numbers and
            # `alpha` at hop root; BrewSignal uses amount_kg /
            # amount_grams / alpha_acid_percent. We already routed the
            # BrewSignal cases above, so any leftover ingredient that
            # has `amount` / `alpha` without the BrewSignal-specific
            # field is a Brewfather signature.
            if isinstance(ferms, list) and ferms and isinstance(ferms[0], dict) \
                    and 'amount' in ferms[0]:
                return "brewfather"
            if isinstance(hops, list) and hops and isinstance(hops[0], dict) \
                    and ('alpha' in hops[0] or 'amount' in hops[0]):
                return "brewfather"
            return "brewsignal"

        except json.JSONDecodeError:
            # Not JSON, not XML - unknown format
            return None
