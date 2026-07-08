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


# Pydantic v2's model_json_schema targets JSON Schema 2020-12 (the
# handwritten originals claimed draft-07; that would now be a lie).
_DIALECT = "https://json-schema.org/draft/2020-12/schema"
_MODELS = {
    "brewsignal-recipe-v1.0.schema.json":
        (BrewSignalRecipe, "https://brewsignal.io/schemas/recipe-v1.0.json"),
    "brewsignal-recipe-v2.0.schema.json":
        (BrewSignalRecipeV2, "https://brewsignal.io/schemas/recipe-v2.0.json"),
}


def generate() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for filename, (model, schema_id) in _MODELS.items():
        schema = model.model_json_schema()
        # json_schema_extra examples leak as a non-keyword top-level
        # 'example'; the valid 2020-12 keyword would be 'examples'
        # (tilt_ui-4bwa item 6)
        schema.pop("example", None)
        out[filename] = {"$schema": _DIALECT, "$id": schema_id, **schema}
    return out


def main() -> None:
    for filename, schema in generate().items():
        path = SCHEMA_DIR / filename
        path.write_text(json.dumps(schema, indent=2) + "\n")
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
