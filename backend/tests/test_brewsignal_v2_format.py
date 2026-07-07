"""Envelope validation for BrewSignal Recipe Format v2 (tilt_ui-0jkg)."""
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.services.brewsignal_format import BrewSignalRecipeV2

JASPER = Path(__file__).resolve().parents[2] / "docs" / "examples" / "jasper-clone.v2.brewsignal"


def test_jasper_example_validates():
    doc = BrewSignalRecipeV2.model_validate(json.loads(JASPER.read_text()))
    assert doc.brewsignal_version == "2.0"
    assert doc.recipe["name"] == "Jasper Clone (Fidens DIPA)"
    assert doc.brewsignal["process"]["lodo"] is True


def test_wrong_version_rejected():
    with pytest.raises(ValidationError):
        BrewSignalRecipeV2.model_validate(
            {"brewsignal_version": "1.0", "recipe": {"name": "X"}}
        )


def test_recipe_requires_name():
    with pytest.raises(ValidationError):
        BrewSignalRecipeV2.model_validate(
            {"brewsignal_version": "2.0", "recipe": {}}
        )


def test_extra_envelope_keys_tolerated():
    doc = BrewSignalRecipeV2.model_validate(
        {"brewsignal_version": "2.0", "recipe": {"name": "X"}, "_comment": "hi"}
    )
    assert doc.recipe["name"] == "X"
