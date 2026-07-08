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


class TestBrewfatherWaterExport:
    """Export must include water chemistry the DB already holds (tilt_ui-0jkg)."""

    def _recipe_with_water(self):
        from backend.models import (
            Recipe, RecipeWaterAdjustment, RecipeWaterProfile,
        )
        recipe = Recipe(name="Watery", og=1.050, fg=1.010)
        recipe.water_profiles.append(RecipeWaterProfile(
            profile_type="target", name="Hazy build",
            chloride_ppm=125.0, sulfate_ppm=75.0, ph=5.4,
        ))
        recipe.water_profiles.append(RecipeWaterProfile(
            profile_type="source", calcium_ppm=20.0,
        ))
        recipe.water_adjustments.append(RecipeWaterAdjustment(
            stage="mash", volume_liters=18.0,
            calcium_chloride_g=3.2, calcium_sulfate_g=1.1,
            acid_type="lactic", acid_ml=2.0, acid_concentration_percent=88.0,
        ))
        recipe.water_adjustments.append(RecipeWaterAdjustment(
            stage="total", calcium_chloride_g=5.0,  # derived by Brewfather; skipped
        ))
        return recipe

    def test_water_profiles_exported(self):
        from backend.services.converters.recipe_to_brewfather import (
            RecipeToBrewfatherConverter,
        )
        bf = RecipeToBrewfatherConverter().convert(self._recipe_with_water())
        assert bf["water"]["target"]["chloride"] == 125.0
        assert bf["water"]["target"]["sulfate"] == 75.0
        assert bf["water"]["target"]["ph"] == 5.4
        assert bf["water"]["source"]["calcium"] == 20.0

    def test_adjustments_exported_camel_case(self):
        from backend.services.converters.recipe_to_brewfather import (
            RecipeToBrewfatherConverter,
        )
        bf = RecipeToBrewfatherConverter().convert(self._recipe_with_water())
        mash = bf["water"]["mashAdjustments"]
        assert mash["calciumChloride"] == 3.2
        assert mash["calciumSulfate"] == 1.1
        assert mash["volume"] == 18.0
        assert mash["acids"] == [
            {"type": "lactic", "amount": 2.0, "concentration": 88.0}
        ]
        # 'total' stage has no Brewfather key — must not crash or leak
        assert "totalAdjustments" not in bf["water"]

    def test_no_water_key_when_recipe_has_none(self):
        from backend.models import Recipe
        from backend.services.converters.recipe_to_brewfather import (
            RecipeToBrewfatherConverter,
        )
        bf = RecipeToBrewfatherConverter().convert(Recipe(name="Dry", og=1.05, fg=1.01))
        assert "water" not in bf

    def test_acid_concentration_only_adjustment_keeps_acids(self):
        """tilt_ui-4bwa item 5: the acid gate checked only type/ml, so an
        adjustment carrying nothing but acid_concentration_percent dropped
        its acids array on export."""
        from backend.models import Recipe, RecipeWaterAdjustment
        from backend.services.converters.recipe_to_brewfather import (
            RecipeToBrewfatherConverter,
        )
        recipe = Recipe(name="Acidic", og=1.05, fg=1.01)
        recipe.water_adjustments.append(RecipeWaterAdjustment(
            stage="mash", acid_concentration_percent=88.0,
        ))
        bf = RecipeToBrewfatherConverter().convert(recipe)
        assert bf["water"]["mashAdjustments"]["acids"] == [
            {"type": None, "amount": None, "concentration": 88.0}
        ]

    def test_all_none_profile_emits_no_empty_dict(self):
        """tilt_ui-4bwa item 5: a profile row with every chemistry field
        NULL exported as `"source": {}` cruft."""
        from backend.models import Recipe, RecipeWaterProfile
        from backend.services.converters.recipe_to_brewfather import (
            RecipeToBrewfatherConverter,
        )
        recipe = Recipe(name="Blank water", og=1.05, fg=1.01)
        recipe.water_profiles.append(RecipeWaterProfile(profile_type="source"))
        bf = RecipeToBrewfatherConverter().convert(recipe)
        assert "source" not in bf.get("water", {})


class TestWaterAdjustmentMiscDedup:
    """Brewfather mirrors water salts as miscs flagged waterAdjustment: true.
    When the water block is present it is the single authority — flagged miscs
    are duplicates and must be skipped (tilt_ui-zlzz)."""

    WATER = {'mashAdjustments': {'calciumSulfate': 9, 'calciumChloride': 5,
                                 'acids': [{'type': 'lactic', 'amount': '5', 'concentration': 80}]}}
    SALT = {'name': 'Gypsum (Calcium Sulfate)', 'type': 'Water Agent', 'use': 'Mash',
            'amount': 11.842, 'unit': 'g', 'waterAdjustment': True}
    FINING = {'name': 'Whirlfloc', 'type': 'Fining', 'use': 'Boil',
              'amount': 0.658, 'unit': 'items'}

    def _miscs(self, result):
        ing = result['beerjson']['recipes'][0].get('ingredients', {})
        return ing.get('miscellaneous_additions', [])

    def test_flagged_misc_skipped_when_water_block_present(self):
        converter = BrewfatherToBeerJSONConverter()
        result = converter.convert({
            'name': 'Pliny', 'water': self.WATER,
            'miscs': [self.SALT, self.FINING],
        })
        names = [m['name'] for m in self._miscs(result)]
        assert names == ['Whirlfloc']

    def test_flagged_misc_kept_when_no_water_block(self):
        converter = BrewfatherToBeerJSONConverter()
        result = converter.convert({
            'name': 'No Water', 'miscs': [self.SALT, self.FINING],
        })
        names = [m['name'] for m in self._miscs(result)]
        assert names == ['Gypsum (Calcium Sulfate)', 'Whirlfloc']

    def test_flagged_misc_kept_when_water_block_empty(self):
        converter = BrewfatherToBeerJSONConverter()
        result = converter.convert({
            'name': 'Empty Water', 'water': {},
            'miscs': [self.SALT, self.FINING],
        })
        names = [m['name'] for m in self._miscs(result)]
        assert names == ['Gypsum (Calcium Sulfate)', 'Whirlfloc']

    def test_unflagged_miscs_never_skipped(self):
        converter = BrewfatherToBeerJSONConverter()
        result = converter.convert({
            'name': 'Pliny', 'water': self.WATER, 'miscs': [self.FINING],
        })
        assert [m['name'] for m in self._miscs(result)] == ['Whirlfloc']

    def test_flagged_misc_kept_when_water_importer_cannot_represent_it(self):
        """Campden etc. have no column in the water adjustment model — the
        flagged misc is the only import path, so it must survive."""
        converter = BrewfatherToBeerJSONConverter()
        campden = {'name': 'Campden Tablets (Sodium Metabisulfite)',
                   'type': 'Water Agent', 'use': 'Mash',
                   'amount': 1.0, 'unit': 'items', 'waterAdjustment': True}
        result = converter.convert({
            'name': 'Pliny', 'water': self.WATER,
            'miscs': [campden, self.SALT, self.FINING],
        })
        names = [m['name'] for m in self._miscs(result)]
        assert names == ['Campden Tablets (Sodium Metabisulfite)', 'Whirlfloc']

    def test_flagged_acid_misc_skipped_when_water_block_present(self):
        converter = BrewfatherToBeerJSONConverter()
        lactic = {'name': 'Lactic Acid', 'type': 'Water Agent', 'use': 'Mash',
                  'amount': 6.579, 'unit': 'ml', 'waterAdjustment': True}
        result = converter.convert({
            'name': 'Pliny', 'water': self.WATER, 'miscs': [lactic, self.FINING],
        })
        assert [m['name'] for m in self._miscs(result)] == ['Whirlfloc']

    def test_flagged_salt_kept_when_water_block_has_profiles_only(self):
        """Profile-only water blocks import no adjustment rows — flagged
        salt mirrors are then the only copy and must survive."""
        converter = BrewfatherToBeerJSONConverter()
        profiles_only = {'source': {'name': 'X', 'calcium': 50}}
        result = converter.convert({
            'name': 'Profiles Only', 'water': profiles_only,
            'miscs': [self.SALT, self.FINING],
        })
        names = [m['name'] for m in self._miscs(result)]
        assert names == ['Gypsum (Calcium Sulfate)', 'Whirlfloc']

    def test_flagged_salt_kept_when_adjustments_lack_that_substance(self):
        """Water block has gypsum but not sodium chloride — a flagged table
        salt mirror has no other import path and must survive."""
        converter = BrewfatherToBeerJSONConverter()
        salt_misc = {'name': 'Canning Salt (Sodium Chloride)', 'type': 'Water Agent',
                     'use': 'Mash', 'amount': 2.0, 'unit': 'g', 'waterAdjustment': True}
        result = converter.convert({
            'name': 'Partial', 'water': {'mashAdjustments': {'calciumSulfate': 9}},
            'miscs': [salt_misc, self.SALT, self.FINING],
        })
        names = [m['name'] for m in self._miscs(result)]
        assert names == ['Canning Salt (Sodium Chloride)', 'Whirlfloc']

    def test_flagged_acid_kept_when_no_acids_in_adjustments(self):
        converter = BrewfatherToBeerJSONConverter()
        lactic = {'name': 'Lactic Acid', 'type': 'Water Agent', 'use': 'Mash',
                  'amount': 5.0, 'unit': 'ml', 'waterAdjustment': True}
        result = converter.convert({
            'name': 'No Acids', 'water': {'mashAdjustments': {'calciumSulfate': 9}},
            'miscs': [lactic, self.FINING],
        })
        names = [m['name'] for m in self._miscs(result)]
        assert names == ['Lactic Acid', 'Whirlfloc']

    def test_flagged_sparge_salt_kept_when_only_mash_adjustment_exists(self):
        """Same substance, wrong stage: mashAdjustments gypsum must not
        swallow a flagged SPARGE gypsum misc."""
        converter = BrewfatherToBeerJSONConverter()
        sparge_gypsum = {'name': 'Gypsum (Calcium Sulfate)', 'type': 'Water Agent',
                         'use': 'Sparge', 'amount': 3.0, 'unit': 'g',
                         'waterAdjustment': True}
        result = converter.convert({
            'name': 'Stage Mismatch',
            'water': {'mashAdjustments': {'calciumSulfate': 9}},
            'miscs': [sparge_gypsum, self.FINING],
        })
        names = [m['name'] for m in self._miscs(result)]
        assert names == ['Gypsum (Calcium Sulfate)', 'Whirlfloc']

    def test_flagged_citric_acid_skipped_when_covered(self):
        converter = BrewfatherToBeerJSONConverter()
        citric = {'name': 'Citric Acid', 'type': 'Water Agent', 'use': 'Mash',
                  'amount': 2.0, 'unit': 'g', 'waterAdjustment': True}
        result = converter.convert({
            'name': 'Citric',
            'water': {'mashAdjustments': {'acids': [{'type': 'citric', 'amount': '2'}]}},
            'miscs': [citric, self.FINING],
        })
        assert [m['name'] for m in self._miscs(result)] == ['Whirlfloc']

    def test_null_acid_type_does_not_crash_and_keeps_misc(self):
        converter = BrewfatherToBeerJSONConverter()
        lactic = {'name': 'Lactic Acid', 'type': 'Water Agent', 'use': 'Mash',
                  'amount': 5.0, 'unit': 'ml', 'waterAdjustment': True}
        result = converter.convert({
            'name': 'Null Acid',
            'water': {'mashAdjustments': {'acids': [{'type': None, 'concentration': 80}]}},
            'miscs': [lactic, self.FINING],
        })
        names = [m['name'] for m in self._miscs(result)]
        assert names == ['Lactic Acid', 'Whirlfloc']

    def test_second_acid_mirror_kept_because_importer_stores_only_first(self):
        """Serializer persists acids[0] only — a flagged mirror for the
        second acid is the sole import path for it."""
        converter = BrewfatherToBeerJSONConverter()
        lactic = {'name': 'Lactic Acid', 'type': 'Water Agent', 'use': 'Mash',
                  'amount': 5.0, 'unit': 'ml', 'waterAdjustment': True}
        phosphoric = {'name': 'Phosphoric Acid', 'type': 'Water Agent', 'use': 'Mash',
                      'amount': 2.0, 'unit': 'ml', 'waterAdjustment': True}
        result = converter.convert({
            'name': 'Two Acids',
            'water': {'mashAdjustments': {'acids': [
                {'type': 'lactic', 'amount': '5'},
                {'type': 'phosphoric', 'amount': '2'},
            ]}},
            'miscs': [lactic, phosphoric, self.FINING],
        })
        names = [m['name'] for m in self._miscs(result)]
        assert names == ['Phosphoric Acid', 'Whirlfloc']

    def test_string_zero_adjustment_does_not_swallow_misc(self):
        """Brewfather sometimes emits amounts as strings; '0' must not count
        as coverage — the flagged misc then carries the only real amount."""
        converter = BrewfatherToBeerJSONConverter()
        result = converter.convert({
            'name': 'String Zero',
            'water': {'mashAdjustments': {'calciumSulfate': '0'}},
            'miscs': [self.SALT, self.FINING],
        })
        names = [m['name'] for m in self._miscs(result)]
        assert names == ['Gypsum (Calcium Sulfate)', 'Whirlfloc']

    def test_string_amount_adjustment_still_covers(self):
        converter = BrewfatherToBeerJSONConverter()
        result = converter.convert({
            'name': 'String Amount',
            'water': {'mashAdjustments': {'calciumSulfate': '9.0'}},
            'miscs': [self.SALT, self.FINING],
        })
        assert [m['name'] for m in self._miscs(result)] == ['Whirlfloc']

    def test_acid_with_zero_amount_does_not_swallow_misc(self):
        """acids[0] naming the acid but with amount 0/missing persists no
        real dose — the flagged misc keeps the true amount."""
        converter = BrewfatherToBeerJSONConverter()
        lactic = {'name': 'Lactic Acid', 'type': 'Water Agent', 'use': 'Mash',
                  'amount': 5.0, 'unit': 'ml', 'waterAdjustment': True}
        for acids in ([{'type': 'lactic', 'amount': '0'}],
                      [{'type': 'lactic'}]):
            result = converter.convert({
                'name': 'Zero Acid',
                'water': {'mashAdjustments': {'acids': acids}},
                'miscs': [lactic, self.FINING],
            })
            names = [m['name'] for m in self._miscs(result)]
            assert names == ['Lactic Acid', 'Whirlfloc'], acids
