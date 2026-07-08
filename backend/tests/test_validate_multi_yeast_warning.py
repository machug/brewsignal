"""Multi-yeast silent data loss warning (tilt_ui-mrn).

BrewSignal v1 format supports a single yeast. When a BeerJSON document with
multiple culture_additions is converted to v1, extra cultures are dropped.
The converter must record a warning and /api/recipes/validate must surface it.
"""

import pytest

from backend.services.brewsignal_format import BeerJSONToBrewSignalConverter


def _beerjson_doc(cultures: list[dict]) -> dict:
    return {
        "beerjson": {
            "version": 1.0,
            "recipes": [
                {
                    "name": "Multi Yeast Saison",
                    "original_gravity": {"unit": "sg", "value": 1.055},
                    "final_gravity": {"unit": "sg", "value": 1.005},
                    "ingredients": {"culture_additions": cultures},
                }
            ],
        }
    }


TWO_CULTURES = [
    {"name": "French Saison", "type": "ale", "form": "liquid"},
    {"name": "Brett Brux", "type": "brett", "form": "liquid"},
]


class TestConverterWarnings:
    def test_multi_culture_conversion_records_dropped_culture_warning(self):
        converter = BeerJSONToBrewSignalConverter()
        result = converter.convert(_beerjson_doc(TWO_CULTURES))

        # First culture kept, as before
        assert result["recipe"]["yeast"]["name"] == "French Saison"
        # Drop is reported, not silent
        assert len(converter.warnings) == 1
        warning = converter.warnings[0]
        assert "Brett Brux" in warning
        assert "dropped" in warning.lower()

    def test_single_culture_conversion_has_no_warnings(self):
        converter = BeerJSONToBrewSignalConverter()
        converter.convert(_beerjson_doc(TWO_CULTURES[:1]))
        assert converter.warnings == []

    def test_no_cultures_has_no_warnings(self):
        converter = BeerJSONToBrewSignalConverter()
        converter.convert(_beerjson_doc([]))
        assert converter.warnings == []

    def test_malformed_extra_culture_entry_does_not_crash(self):
        # codex P2: null/non-object extra entries must not raise AttributeError
        converter = BeerJSONToBrewSignalConverter()
        result = converter.convert(_beerjson_doc([TWO_CULTURES[0], None, "junk"]))
        assert result["recipe"]["yeast"]["name"] == "French Saison"
        assert len(converter.warnings) == 1
        assert "dropped" in converter.warnings[0].lower()


class TestValidateEndpointSurfacesDrop:
    @pytest.mark.asyncio
    async def test_validate_beerjson_multi_yeast_returns_warning(self, client):
        response = await client.post(
            "/api/recipes/validate",
            json={"format": "beerjson", "data": _beerjson_doc(TWO_CULTURES)},
        )
        assert response.status_code == 200
        body = response.json()
        culture_warnings = [
            w for w in body["warnings"] if "culture" in w["field"]
        ]
        assert len(culture_warnings) == 1
        assert "Brett Brux" in culture_warnings[0]["warning"]

    @pytest.mark.asyncio
    async def test_validate_beerjson_single_yeast_no_culture_warning(self, client):
        response = await client.post(
            "/api/recipes/validate",
            json={"format": "beerjson", "data": _beerjson_doc(TWO_CULTURES[:1])},
        )
        assert response.status_code == 200
        body = response.json()
        assert [w for w in body["warnings"] if "culture" in w["field"]] == []
