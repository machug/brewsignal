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
