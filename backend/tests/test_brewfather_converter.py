"""Tests for Brewfather to BeerJSON converter."""
import pytest
from backend.models import Recipe
from backend.services.converters.brewfather_to_beerjson import BrewfatherToBeerJSONConverter
from backend.services.serializers.recipe_serializer import RecipeSerializer


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


class TestWaterAdjustmentImport:
    """Brewfather water.{mash,sparge}Adjustments must persist as
    RecipeWaterAdjustment rows with volume + salts + acids (tilt_ui-2br).

    Production Recipe 21 has zero adjustment rows even though the path
    works for fresh imports — these tests pin that path so a future
    refactor cannot silently regress it."""

    def _bf_water(self) -> dict:
        return {
            'source': {
                'name': 'RO Water', 'calcium': 1, 'magnesium': 0,
                'sodium': 0, 'chloride': 1, 'sulfate': 1, 'bicarbonate': 0,
            },
            'target': {
                'name': 'Sulfate-Forward IPA', 'calcium': 130, 'magnesium': 10,
                'sodium': 20, 'chloride': 70, 'sulfate': 225, 'bicarbonate': 0,
            },
            'mashAdjustments': {
                'volume': 13.29,
                'calciumSulfate': 1.5,
                'calciumChloride': 1.7,
                'sodiumChloride': 0.4,
                'acids': [{'type': 'lactic', 'amount': 1.0, 'concentration': 88}],
            },
            'spargeAdjustments': {
                'volume': 14.75,
                'calciumSulfate': 1.66,
                'calciumChloride': 1.89,
                'acids': [{'type': 'lactic', 'amount': 0.22, 'concentration': 80}],
            },
        }

    def test_mash_adjustment_creates_row_with_volume_salts_and_acid(self):
        recipe = Recipe(name='Test')
        RecipeSerializer()._serialize_brewfather_water(recipe, self._bf_water())
        mash = next(a for a in recipe.water_adjustments if a.stage == 'mash')
        assert mash.volume_liters == 13.29
        assert mash.calcium_sulfate_g == 1.5
        assert mash.calcium_chloride_g == 1.7
        assert mash.sodium_chloride_g == 0.4
        assert mash.acid_type == 'lactic'
        assert mash.acid_ml == 1.0
        assert mash.acid_concentration_percent == 88

    def test_sparge_adjustment_creates_row_with_volume_salts_and_acid(self):
        recipe = Recipe(name='Test')
        RecipeSerializer()._serialize_brewfather_water(recipe, self._bf_water())
        sparge = next(a for a in recipe.water_adjustments if a.stage == 'sparge')
        assert sparge.volume_liters == 14.75
        assert sparge.calcium_sulfate_g == 1.66
        assert sparge.calcium_chloride_g == 1.89
        assert sparge.acid_type == 'lactic'

    def test_converter_emits_brewfather_water_extension(self):
        """The converter is the single source of truth for attaching the
        Brewfather water object. Importers and any other caller can rely on
        _brewfather_water being present in the BeerJSON dict whenever the
        source had a water section — no extra augmentation step required."""
        bf_recipe = {'name': 'Test', 'water': self._bf_water()}
        beerjson_recipe = BrewfatherToBeerJSONConverter().convert(bf_recipe)[
            'beerjson'
        ]['recipes'][0]
        assert beerjson_recipe['_brewfather_water'] == bf_recipe['water']

    def test_converter_omits_brewfather_water_when_absent(self):
        bf_recipe = {'name': 'Test'}
        beerjson_recipe = BrewfatherToBeerJSONConverter().convert(bf_recipe)[
            'beerjson'
        ]['recipes'][0]
        assert '_brewfather_water' not in beerjson_recipe


class TestImportPopulatesTargetStats:
    """Imported brewer-declared OG/FG/ABV/IBU/SRM must populate target_*
    columns in addition to the canonical og/fg/... columns. The canonical
    fields are subject to recalculation; target_* preserves the imported
    source-of-truth (tilt_ui-ak6)."""

    def test_brewfather_import_sets_both_canonical_and_target_stats(self):
        from backend.models import Recipe
        from backend.services.serializers.recipe_serializer import RecipeSerializer
        bf = {
            'name': 'Project Alpha 81 Clone',
            'og': 1.067,
            'fg': 1.013,
            'abv': 6.9,
            'ibu': 60,
            'color': 4.0,
        }
        beerjson = BrewfatherToBeerJSONConverter().convert(bf)['beerjson']
        recipe = Recipe(name='temp')
        RecipeSerializer()._extract_recipe_vitals(recipe, beerjson['recipes'][0])

        assert recipe.og == 1.067
        assert recipe.target_og == 1.067
        assert recipe.fg == 1.013
        assert recipe.target_fg == 1.013
        assert abs((recipe.abv or 0) - 6.9) < 0.01
        assert abs((recipe.target_abv or 0) - 6.9) < 0.01
        assert recipe.ibu == 60
        assert recipe.target_ibu == 60
        assert recipe.color_srm == 4.0
        assert recipe.target_srm == 4.0

    def test_target_stats_unset_when_source_omits_them(self):
        from backend.models import Recipe
        from backend.services.serializers.recipe_serializer import RecipeSerializer
        beerjson = BrewfatherToBeerJSONConverter().convert(
            {'name': 'Bare Recipe'}
        )['beerjson']
        recipe = Recipe(name='temp')
        RecipeSerializer()._extract_recipe_vitals(recipe, beerjson['recipes'][0])
        # Brewfather converter still emits zero-valued unit objects for og/fg/...
        # (they default to None upstream). What matters is target_* tracks
        # whatever the canonical column gets, never out of sync.
        assert recipe.target_og == recipe.og
        assert recipe.target_fg == recipe.fg
        assert recipe.target_ibu == recipe.ibu


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
