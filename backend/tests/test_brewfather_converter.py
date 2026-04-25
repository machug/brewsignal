"""Tests for Brewfather to BeerJSON converter."""
import pytest
from backend.services.converters.brewfather_to_beerjson import BrewfatherToBeerJSONConverter


def _convert_single_hop(bf_hop: dict) -> dict:
    """Convert a Brewfather recipe with one hop and return that hop's BeerJSON form."""
    converter = BrewfatherToBeerJSONConverter()
    bf_recipe = {'name': 'Test Recipe', 'hops': [bf_hop]}
    result = converter.convert(bf_recipe)
    return result['beerjson']['recipes'][0]['ingredients']['hop_additions'][0]


class TestHopTimingConversion:
    """Tests for hop use/timing conversion (tilt_ui-53n)."""

    def test_whirlpool_hop_maps_to_add_to_whirlpool_with_stand_duration(self):
        """Brewfather Whirlpool addition must map to add_to_whirlpool, not add_to_boil.

        Mapping Whirlpool to add_to_boil is the bug: combined with the IBU
        calculator's zero-utilization rule for boil_min == 0, whirlpool/flameout
        hops contribute 0 IBU. The brewing calculator already understands
        add_to_whirlpool — only the converter mapping needs to change.
        """
        hop = _convert_single_hop({
            'name': 'Mosaic',
            'use': 'Whirlpool',
            'time': 20,
            'amount': 0.04,
            'alpha': 12.5,
        })
        assert hop['timing']['use'] == 'add_to_whirlpool'
        assert hop['timing']['duration'] == {'value': 20.0, 'unit': 'min'}

    def test_flameout_whirlpool_with_zero_time_still_distinguished_from_boil(self):
        """Zero-time Whirlpool (flameout-style) must remain add_to_whirlpool."""
        hop = _convert_single_hop({
            'name': 'Riwaka',
            'use': 'Whirlpool',
            'time': 0,
            'amount': 0.03,
            'alpha': 5.0,
        })
        assert hop['timing']['use'] == 'add_to_whirlpool'

    def test_boil_hop_still_maps_to_add_to_boil(self):
        """Regular boil additions must continue to map to add_to_boil."""
        hop = _convert_single_hop({
            'name': 'Columbus',
            'use': 'Boil',
            'time': 60,
            'amount': 0.005,
            'alpha': 20.0,
        })
        assert hop['timing']['use'] == 'add_to_boil'
        assert hop['timing']['duration'] == {'value': 60.0, 'unit': 'min'}

    def test_dry_hop_still_maps_to_add_to_fermentation(self):
        """Dry hop additions must continue to map to add_to_fermentation."""
        hop = _convert_single_hop({
            'name': 'Mosaic Cryo',
            'use': 'Dry Hop',
            'time': 4,
            'amount': 0.05,
            'alpha': 22.0,
        })
        assert hop['timing']['use'] == 'add_to_fermentation'
        assert hop['timing']['duration'] == {'value': 4, 'unit': 'day'}


class TestBoilFields:
    """Brewfather boilTime + boilSize must both reach BeerJSON `boil` (tilt_ui-u19)."""

    def test_boil_size_is_mapped_to_beerjson(self):
        converter = BrewfatherToBeerJSONConverter()
        result = converter.convert({
            'name': 'Test',
            'batchSize': 23.0,
            'boilTime': 60,
            'boilSize': 28.5,
        })
        recipe = result['beerjson']['recipes'][0]
        assert 'boil' in recipe
        assert recipe['boil']['boil_size'] == {'value': 28.5, 'unit': 'l'}
        assert recipe['boil']['boil_time'] == {'value': 60, 'unit': 'min'}

    def test_boil_size_present_even_when_boil_time_absent(self):
        converter = BrewfatherToBeerJSONConverter()
        result = converter.convert({'name': 'Test', 'boilSize': 28.5})
        recipe = result['beerjson']['recipes'][0]
        assert recipe['boil']['boil_size'] == {'value': 28.5, 'unit': 'l'}

    def test_boil_block_omitted_when_neither_field_present(self):
        converter = BrewfatherToBeerJSONConverter()
        result = converter.convert({'name': 'Test'})
        recipe = result['beerjson']['recipes'][0]
        assert 'boil' not in recipe


class TestHopTimingRoundTrip:
    """Reverse converter must understand add_to_whirlpool emitted by the
    forward Brewfather converter, otherwise round-trip export loses the
    Whirlpool tag (tilt_ui-53n)."""

    def test_whirlpool_use_round_trips_to_brewfather(self):
        from backend.models import RecipeHop
        from backend.services.converters.recipe_to_brewfather import (
            RecipeToBrewfatherConverter,
        )

        hop = RecipeHop(
            name='Mosaic',
            amount_grams=40.0,
            alpha_acid_percent=12.5,
            timing={
                'use': 'add_to_whirlpool',
                'duration': {'value': 20.0, 'unit': 'min'},
            },
        )
        converter = RecipeToBrewfatherConverter()
        bf_use, bf_time = converter._extract_hop_timing(hop.timing)
        assert bf_use == 'Whirlpool'
        assert bf_time == 20.0


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
