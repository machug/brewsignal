"""Format schema docs must match the Pydantic models (tilt_ui-0jkg)."""
import json

from backend.schemas.generate_brewsignal_schemas import SCHEMA_DIR, generate


def test_schema_files_match_models():
    for filename, schema in generate().items():
        path = SCHEMA_DIR / filename
        assert path.exists(), (
            f"{filename} missing — run: "
            "uv run python -m backend.schemas.generate_brewsignal_schemas"
        )
        on_disk = json.loads(path.read_text())
        assert on_disk == schema, (
            f"{filename} drifted from the Pydantic model — run: "
            "uv run python -m backend.schemas.generate_brewsignal_schemas"
        )


def test_schemas_carry_identity_keywords_and_no_stray_example():
    """tilt_ui-4bwa item 6: the regenerated schemas dropped the $schema/$id
    keywords the handwritten originals had, and the v1 model's
    json_schema_extra leaked a non-keyword top-level 'example'."""
    for filename, schema in generate().items():
        assert schema["$schema"] == \
            "https://json-schema.org/draft/2020-12/schema", filename
        assert schema["$id"].startswith("https://brewsignal.io/schemas/"), filename
        assert "example" not in schema, filename
