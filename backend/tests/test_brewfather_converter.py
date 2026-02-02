"""Tests for Brewfather to BeerJSON converter."""
import pytest
from backend.services.converters.brewfather_to_beerjson import BrewfatherToBeerJSONConverter


class TestMiscTimingConversion:
    """Tests for misc ingredient timing conversion."""

    def test_misc_sparge_timing_preserved(self):
        """Verify sparge water agents get timing.use = 'add_to_sparge'."""
        converter = BrewfatherToBeerJSONConverter()
        bf_recipe = {
            'name': 'Test Recipe',
            'miscs': [
                {'name': 'Gypsum', 'type': 'Water Agent', 'use': 'Sparge', 'amount': 1.5, 'unit': 'g'}
            ]
        }
        result = converter.convert(bf_recipe)
        misc = result['beerjson']['recipes'][0]['ingredients']['miscellaneous_additions'][0]
        assert misc['timing']['use'] == 'add_to_sparge'

    def test_misc_mash_timing_unchanged(self):
        """Verify mash water agents still get timing.use = 'add_to_mash'."""
        converter = BrewfatherToBeerJSONConverter()
        bf_recipe = {
            'name': 'Test Recipe',
            'miscs': [
                {'name': 'Gypsum', 'type': 'Water Agent', 'use': 'Mash', 'amount': 2.0, 'unit': 'g'}
            ]
        }
        result = converter.convert(bf_recipe)
        misc = result['beerjson']['recipes'][0]['ingredients']['miscellaneous_additions'][0]
        assert misc['timing']['use'] == 'add_to_mash'
