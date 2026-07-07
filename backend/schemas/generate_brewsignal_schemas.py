"""Regenerate BrewSignal recipe JSON Schemas from the Pydantic models.

The .schema.json files in this directory are generated artifacts — edit
backend/services/brewsignal_format.py and re-run this, never the JSON:

    uv run python -m backend.schemas.generate_brewsignal_schemas

test_brewsignal_schema_drift.py fails CI when they fall out of sync.
"""
import json
from pathlib import Path

from backend.services.brewsignal_format import BrewSignalRecipe, BrewSignalRecipeV2

SCHEMA_DIR = Path(__file__).parent


def generate() -> dict[str, dict]:
    return {
        "brewsignal-recipe-v1.0.schema.json": BrewSignalRecipe.model_json_schema(),
        "brewsignal-recipe-v2.0.schema.json": BrewSignalRecipeV2.model_json_schema(),
    }


def main() -> None:
    for filename, schema in generate().items():
        path = SCHEMA_DIR / filename
        path.write_text(json.dumps(schema, indent=2) + "\n")
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
