"""BeerJSON 1.0 validator using jsonschema."""
import json
import os
from typing import Dict, Any, List, Tuple
from pathlib import Path
import jsonschema
from jsonschema.validators import Draft7Validator


class BeerJSONValidator:
    """Validate BeerJSON documents against BeerJSON 1.0 schema."""

    def __init__(self):
        """Initialize validator with BeerJSON 1.0 schema."""
        self.schema_dir = Path(__file__).parent / "schemas"
        self.schema = self._load_schema()
        self.validator = self._create_validator()

    def _load_schema(self) -> Dict[str, Any]:
        """Load the main BeerJSON schema file.

        Returns:
            Parsed JSON schema as dict
        """
        schema_path = self.schema_dir / "beer.json"

        if not schema_path.exists():
            raise FileNotFoundError(
                f"BeerJSON schema not found at {schema_path}. "
                "Ensure schema files are downloaded from "
                "https://github.com/beerjson/beerjson"
            )

        with open(schema_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _create_validator(self) -> Draft7Validator:
        """Create JSON schema validator with proper reference resolution.

        The BeerJSON schema uses $ref to reference other schema files.
        This creates a validator that can resolve those references.

        Returns:
            Draft7Validator configured for BeerJSON schema
        """
        # Load all schema files into a store for reference resolution
        store = {}
        for schema_file in self.schema_dir.glob("*.json"):
            with open(schema_file, "r", encoding="utf-8") as f:
                schema_data = json.load(f)
                # Store with both filename and $id URL
                store[schema_file.name] = schema_data
                if "$id" in schema_data:
                    store[schema_data["$id"]] = schema_data

        # Create custom resolver
        from jsonschema import RefResolver
        base_uri = self.schema.get("$id", f"file://{self.schema_dir}/")
        resolver = RefResolver(
            base_uri=base_uri,
            referrer=self.schema,
            store=store
        )

        # Create validator with resolver
        validator_cls = Draft7Validator
        validator = validator_cls(self.schema, resolver=resolver)

        return validator

    def validate(self, beerjson_data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Validate a BeerJSON document against the schema.

        Args:
            beerjson_data: Parsed BeerJSON document as dict

        Returns:
            Tuple of (is_valid, error_messages)
            - is_valid: True if valid, False if validation errors
            - error_messages: List of validation error descriptions
        """
        errors = []

        try:
            # Validate using the validator instance
            validation_errors = list(self.validator.iter_errors(beerjson_data))

            if not validation_errors:
                return (True, [])

            # Collect all validation errors
            for error in validation_errors:
                error_msg = self._format_validation_error(error)
                errors.append(error_msg)

            return (False, errors)

        except jsonschema.SchemaError as e:
            # Schema itself is invalid (shouldn't happen with official schema)
            errors.append(f"Schema error: {str(e)}")
            return (False, errors)

    def _format_validation_error(self, error: jsonschema.ValidationError) -> str:
        """Format a validation error into a readable message.

        Args:
            error: ValidationError from jsonschema

        Returns:
            Formatted error message string
        """
        # Build path to the problematic field
        path = " -> ".join(str(p) for p in error.absolute_path) if error.absolute_path else "root"

        # Get the validation rule that failed
        validator = error.validator

        # Format the message
        if validator == "required":
            missing_prop = error.message.split("'")[1] if "'" in error.message else "unknown"
            return f"Missing required property '{missing_prop}' at {path}"
        elif validator == "type":
            expected_type = error.validator_value
            return f"Invalid type at {path}: {error.message}"
        elif validator == "enum":
            allowed_values = error.validator_value
            return f"Invalid value at {path}: must be one of {allowed_values}"
        elif validator == "pattern":
            return f"Value at {path} does not match required pattern: {error.message}"
        else:
            return f"Validation error at {path}: {error.message}"

    def validate_recipe(self, recipe: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Validate a single recipe (convenience method).

        Wraps the recipe in BeerJSON structure before validation.

        Args:
            recipe: Recipe dict (without beerjson wrapper)

        Returns:
            Tuple of (is_valid, error_messages)
        """
        beerjson_doc = {
            "beerjson": {
                "version": 1.0,  # BeerJSON schema expects number, not string
                "recipes": [recipe]
            }
        }

        return self.validate(beerjson_doc)
