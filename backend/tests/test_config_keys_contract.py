"""Guard: every key the frontend sends via updateConfig({...}) must be a ConfigUpdate
field, or Pydantic silently drops it (tilt_ui-fbk8: ai_lite_enabled never persisted)."""

import re
from pathlib import Path

from backend.models import ConfigUpdate

FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "src"


def test_frontend_config_keys_are_accepted():
    fields = set(ConfigUpdate.model_fields)
    missing = {}
    for f in list(FRONTEND.rglob("*.svelte")) + list(FRONTEND.rglob("*.ts")):
        for m in re.finditer(r"updateConfig\(\s*\{(.*?)\}\s*\)", f.read_text(), re.S):
            body = m.group(1)
            keys = set(re.findall(r"([a-z_][a-z0-9_]*)\s*:", body))
            keys |= set(re.findall(r"^\s*([a-z_][a-z0-9_]*),?\s*$", body, re.M))
            bad = sorted(k for k in keys if k not in fields)
            if bad:
                missing[str(f.relative_to(FRONTEND))] = bad
    assert not missing, f"frontend sends config keys ConfigUpdate drops: {missing}"
