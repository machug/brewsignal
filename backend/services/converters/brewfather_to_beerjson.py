"""Convert Brewfather JSON to BeerJSON 1.0."""
from typing import Dict, Any, List, Optional


class BrewfatherToBeerJSONConverter:
    """Convert Brewfather JSON format to BeerJSON 1.0."""

    def convert(self, brewfather_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Convert Brewfather JSON to BeerJSON dict.

        Args:
            brewfather_dict: Brewfather recipe as dict

        Returns:
            BeerJSON 1.0 compatible dict
        """
        beerjson_recipe = self._convert_recipe(brewfather_dict)

        return {
            'beerjson': {
                'version': 1.0,
                'recipes': [beerjson_recipe]
            }
        }

    def _convert_recipe(self, bf_recipe: Dict[str, Any]) -> Dict[str, Any]:
        """Convert single Brewfather recipe to BeerJSON recipe."""
        recipe = {
            'name': bf_recipe.get('name', ''),
            'type': self._map_recipe_type(bf_recipe.get('type', '')),
            'author': bf_recipe.get('author', 'Unknown'),
            'batch_size': self._make_volume(bf_recipe.get('batchSize')),
            'original_gravity': self._make_gravity(bf_recipe.get('og')),
            'final_gravity': self._make_gravity(bf_recipe.get('fg')),
            'alcohol_by_volume': self._make_percent(bf_recipe.get('abv')),
            'ibu_estimate': self._make_dimensionless(bf_recipe.get('ibu')),
            'color_estimate': self._make_color(bf_recipe.get('color')),
            'notes': bf_recipe.get('notes', ''),
        }

        # Boil
        if bf_recipe.get('boilTime'):
            recipe['boil'] = {
                'boil_time': self._make_time_minutes(bf_recipe['boilTime'])
            }

        # Efficiency (required field - ensure it's always present)
        if bf_recipe.get('efficiency'):
            recipe['efficiency'] = {
                'brewhouse': self._make_percent(bf_recipe['efficiency'])
            }
        else:
            # Default to 75% if not specified
            recipe['efficiency'] = {
                'brewhouse': {'value': 0.75, 'unit': '%'}
            }

        # Carbonation (BeerJSON expects a number, not an object)
        if bf_recipe.get('carbonation'):
            recipe['carbonation'] = float(bf_recipe['carbonation'])

        # Ingredients
        recipe['ingredients'] = self._convert_ingredients(bf_recipe)

        # Mash
        if 'mash' in bf_recipe and bf_recipe['mash'].get('steps'):
            recipe['mash'] = self._convert_mash(bf_recipe['mash'])

        # Style
        if 'style' in bf_recipe:
            recipe['style'] = self._convert_style(bf_recipe['style'])

        # Fermentation
        if 'fermentation' in bf_recipe and bf_recipe['fermentation'].get('steps'):
            recipe['fermentation'] = self._convert_fermentation(bf_recipe['fermentation'])

        # NOTE: BeerJSON 1.0 schema has additionalProperties: false
        # Extensions like _extensions and water are not allowed at recipe level
        # They are omitted for spec compliance

        return recipe

    def _convert_ingredients(self, bf_recipe: Dict[str, Any]) -> Dict[str, Any]:
        """Convert ingredients section."""
        ingredients = {}

        # Fermentables (BeerJSON uses fermentable_additions)
        if 'fermentables' in bf_recipe:
            ingredients['fermentable_additions'] = [
                self._convert_fermentable(f) for f in bf_recipe['fermentables']
            ]

        # Hops (BeerJSON uses hop_additions)
        if 'hops' in bf_recipe:
            ingredients['hop_additions'] = [
                self._convert_hop(h) for h in bf_recipe['hops']
            ]

        # Yeasts/Cultures (BeerJSON uses culture_additions)
        if 'yeasts' in bf_recipe:
            ingredients['culture_additions'] = [
                self._convert_culture(y) for y in bf_recipe['yeasts']
            ]

        # Miscs
        if 'miscs' in bf_recipe:
            ingredients['miscellaneous_additions'] = [
                self._convert_misc(m) for m in bf_recipe['miscs']
            ]

        return ingredients

    def _convert_fermentable(self, bf_ferm: Dict[str, Any]) -> Dict[str, Any]:
        """Convert Brewfather fermentable to BeerJSON."""
        ferm = {
            'name': bf_ferm.get('name', ''),
            'type': self._map_fermentable_type(bf_ferm.get('type', '')),
            'amount': self._make_mass_kg(bf_ferm.get('amount')),
            'origin': bf_ferm.get('origin', ''),
            'producer': bf_ferm.get('supplier', ''),
            'color': self._make_color(bf_ferm.get('color')),
        }

        # Yield
        if bf_ferm.get('potentialPercentage'):
            ferm['yield'] = {
                'fine_grind': self._make_percent(bf_ferm['potentialPercentage'])
            }

        # Grain category (map to lowercase enum values)
        if bf_ferm.get('grainCategory'):
            ferm['grain_group'] = self._map_grain_group(bf_ferm['grainCategory'])

        # NOTE: BeerJSON 1.0 schema doesn't allow percentage or _extensions
        # These fields are omitted for spec compliance

        return ferm

    def _convert_hop(self, bf_hop: Dict[str, Any]) -> Dict[str, Any]:
        """Convert Brewfather hop to BeerJSON."""
        hop = {
            'name': bf_hop.get('name', ''),
            'origin': bf_hop.get('origin', ''),
            'form': self._map_hop_form(bf_hop.get('type', '')),
            'alpha_acid': self._make_percent(bf_hop.get('alpha')),
            'amount': self._make_mass_g(bf_hop.get('amount')),
            'timing': self._convert_hop_timing(bf_hop)
        }

        # Beta acid (if present)
        if bf_hop.get('beta'):
            hop['beta_acid'] = self._make_percent(bf_hop['beta'])

        # NOTE: BeerJSON 1.0 schema doesn't allow _extensions
        # Brewfather IDs are omitted for spec compliance

        return hop

    def _convert_hop_timing(self, bf_hop: Dict[str, Any]) -> Dict[str, Any]:
        """Convert Brewfather hop use/time/temp to BeerJSON timing object.

        NOTE: BeerJSON 1.0 TimingType schema doesn't allow 'temperature' or 'phase' fields.
        These are omitted for spec compliance.
        """
        use = bf_hop.get('use', 'Boil')
        time = bf_hop.get('time', 0)

        # Map use to BeerJSON
        use_mapping = {
            'Boil': 'add_to_boil',
            'Dry Hop': 'add_to_fermentation',
            'Mash': 'add_to_mash',
            'First Wort': 'add_to_boil',
            'Aroma': 'add_to_boil',
            'Whirlpool': 'add_to_boil'
        }

        timing = {
            'use': use_mapping.get(use, 'add_to_boil')
        }

        # Duration
        if use in ['Boil', 'Aroma', 'Whirlpool'] and time and time > 0:
            timing['duration'] = {
                'value': float(time),
                'unit': 'min'
            }
        elif use == 'Dry Hop' and time and time > 0:
            # Brewfather stores dry hop time in days
            timing['duration'] = {
                'value': int(time),
                'unit': 'day'
            }

        return timing

    def _convert_culture(self, bf_yeast: Dict[str, Any]) -> Dict[str, Any]:
        """Convert Brewfather yeast to BeerJSON culture."""
        culture = {
            'name': bf_yeast.get('name', ''),
            'type': self._map_yeast_type(bf_yeast.get('type', '')),
            'form': self._map_yeast_form(bf_yeast.get('form', '')),
            'producer': bf_yeast.get('laboratory', ''),
            'product_id': bf_yeast.get('productId', ''),
        }

        # Temperature range
        if bf_yeast.get('minTemp') or bf_yeast.get('maxTemp'):
            temp_range = {}
            if bf_yeast.get('minTemp'):
                temp_range['minimum'] = {
                    'value': float(bf_yeast['minTemp']),
                    'unit': 'C'
                }
            if bf_yeast.get('maxTemp'):
                temp_range['maximum'] = {
                    'value': float(bf_yeast['maxTemp']),
                    'unit': 'C'
                }
            culture['temperature_range'] = temp_range

        # Attenuation (BeerJSON uses attenuation_range with minimum and maximum)
        if bf_yeast.get('attenuation'):
            att_value = self._make_percent(bf_yeast['attenuation'])
            culture['attenuation_range'] = {
                'minimum': att_value,
                'maximum': att_value
            }

        # Amount
        if bf_yeast.get('amount'):
            amount_val = float(bf_yeast['amount'])
            unit = bf_yeast.get('unit', 'pkg')

            culture['amount'] = {
                'value': amount_val,
                'unit': unit
            }

        # NOTE: BeerJSON 1.0 schema doesn't allow flocculation or _extensions
        # These fields are omitted for spec compliance

        return culture

    def _convert_misc(self, bf_misc: Dict[str, Any]) -> Dict[str, Any]:
        """Convert Brewfather misc to BeerJSON."""
        misc = {
            'name': bf_misc.get('name', ''),
            'type': self._map_misc_type(bf_misc.get('type', '')),
        }

        # Amount
        amount_val = float(bf_misc.get('amount', 0))
        unit = bf_misc.get('unit', 'g')

        misc['amount'] = {
            'value': amount_val,
            'unit': unit
        }

        # Timing
        use = bf_misc.get('use', 'Boil')
        time = bf_misc.get('time', 0)

        timing = self._convert_misc_timing(use, time)
        misc['timing'] = timing

        # NOTE: BeerJSON 1.0 schema doesn't allow _extensions
        # Water adjustment flag is omitted for spec compliance

        return misc

    def _convert_misc_timing(self, use: str, time: Optional[float]) -> Dict[str, Any]:
        """Convert misc use/time to BeerJSON timing."""
        use_mapping = {
            'Boil': 'add_to_boil',
            'Mash': 'add_to_mash',
            'Primary': 'add_to_fermentation',
            'Secondary': 'add_to_fermentation',
            'Bottling': 'add_to_package',
            'Sparge': 'add_to_mash'
        }

        timing = {
            'use': use_mapping.get(use, 'add_to_boil')
        }

        if time and time > 0:
            timing['duration'] = {
                'value': float(time),
                'unit': 'min'
            }

        return timing

    def _convert_mash(self, bf_mash: Dict[str, Any]) -> Dict[str, Any]:
        """Convert Brewfather mash to BeerJSON."""
        mash = {
            'name': bf_mash.get('name', 'Mash'),
            'mash_steps': []
        }

        # Grain temperature (required field - default to room temp if not specified)
        if 'grainTemp' in bf_mash:
            mash['grain_temperature'] = self._make_temperature(bf_mash['grainTemp'])
        else:
            mash['grain_temperature'] = {'value': 20.0, 'unit': 'C'}

        # Mash steps
        if 'steps' in bf_mash:
            mash['mash_steps'] = [
                self._convert_mash_step(s) for s in bf_mash['steps']
            ]

        return mash

    def _convert_mash_step(self, bf_step: Dict[str, Any]) -> Dict[str, Any]:
        """Convert Brewfather mash step to BeerJSON."""
        step = {
            'name': bf_step.get('name', ''),
            'type': bf_step.get('type', 'temperature').lower(),
            'step_temperature': self._make_temperature(bf_step.get('stepTemp')),
            'step_time': self._make_time_minutes(bf_step.get('stepTime'))
        }

        # Ramp time
        if bf_step.get('rampTime'):
            step['ramp_time'] = self._make_time_minutes(bf_step['rampTime'])

        return step

    def _convert_style(self, bf_style: Dict[str, Any]) -> Dict[str, Any]:
        """Convert Brewfather style to BeerJSON."""
        return {
            'name': bf_style.get('name', ''),
            'category': bf_style.get('category', ''),
            'style_guide': bf_style.get('styleGuide', ''),
            'type': self._map_style_type(bf_style.get('type', ''))
        }

    def _convert_fermentation(self, bf_ferm: Dict[str, Any]) -> Dict[str, Any]:
        """Convert Brewfather fermentation to BeerJSON."""
        fermentation = {
            'name': bf_ferm.get('name', 'Fermentation'),
            'fermentation_steps': []
        }

        # Fermentation steps
        if 'steps' in bf_ferm:
            fermentation['fermentation_steps'] = [
                self._convert_fermentation_step(s) for s in bf_ferm['steps']
            ]

        return fermentation

    def _convert_fermentation_step(self, bf_step: Dict[str, Any]) -> Dict[str, Any]:
        """Convert Brewfather fermentation step to BeerJSON.

        BeerJSON uses name, start_temperature, end_temperature, step_time
        Brewfather uses type, stepTemp, stepTime
        """
        step_type = bf_step.get('type', 'primary')
        step = {
            'name': step_type.capitalize()
        }

        # Temperature (use same for start and end if only one value)
        if bf_step.get('stepTemp'):
            temp = self._make_temperature(bf_step['stepTemp'])
            step['start_temperature'] = temp
            step['end_temperature'] = temp

        # Duration
        if bf_step.get('stepTime'):
            step['step_time'] = {
                'value': float(bf_step['stepTime']),
                'unit': 'day'
            }

        return step

    def _convert_water(self, bf_water: Dict[str, Any]) -> Dict[str, Any]:
        """Convert Brewfather water chemistry to BeerJSON extension."""
        water = {}

        # Source water profile
        if 'source' in bf_water:
            source = bf_water['source']
            water['source'] = {
                'name': source.get('name', ''),
                'calcium': {'value': float(source.get('calcium', 0)), 'unit': 'ppm'},
                'magnesium': {'value': float(source.get('magnesium', 0)), 'unit': 'ppm'},
                'sodium': {'value': float(source.get('sodium', 0)), 'unit': 'ppm'},
                'chloride': {'value': float(source.get('chloride', 0)), 'unit': 'ppm'},
                'sulfate': {'value': float(source.get('sulfate', 0)), 'unit': 'ppm'},
                'bicarbonate': {'value': float(source.get('bicarbonate', 0)), 'unit': 'ppm'},
            }
            if source.get('ph'):
                water['source']['ph'] = float(source['ph'])

        # Target water profile
        if 'target' in bf_water:
            target = bf_water['target']
            water['target'] = {
                'name': target.get('name', ''),
                'calcium': {'value': float(target.get('calcium', 0)), 'unit': 'ppm'},
                'magnesium': {'value': float(target.get('magnesium', 0)), 'unit': 'ppm'},
                'sodium': {'value': float(target.get('sodium', 0)), 'unit': 'ppm'},
                'chloride': {'value': float(target.get('chloride', 0)), 'unit': 'ppm'},
                'sulfate': {'value': float(target.get('sulfate', 0)), 'unit': 'ppm'},
                'bicarbonate': {'value': float(target.get('bicarbonate', 0)), 'unit': 'ppm'},
            }

        # Mash water additions
        if 'mashAdjustments' in bf_water:
            adj = bf_water['mashAdjustments']
            water['mash_water_additions'] = []

            # Map common salts
            salt_mapping = {
                'calciumChloride': 'Calcium Chloride (CaCl2)',
                'calciumSulfate': 'Gypsum (CaSO4)',
                'magnesiumSulfate': 'Epsom Salt (MgSO4)',
                'sodiumBicarbonate': 'Sodium Bicarbonate (NaHCO3)',
                'calciumCarbonate': 'Calcium Carbonate (CaCO3)',
                'calciumHydroxide': 'Calcium Hydroxide (Ca(OH)2)',
            }

            for bf_key, name in salt_mapping.items():
                if adj.get(bf_key) and float(adj[bf_key]) > 0:
                    water['mash_water_additions'].append({
                        'name': name,
                        'amount': {'value': float(adj[bf_key]), 'unit': 'g'}
                    })

            # Acid additions
            if adj.get('acids'):
                for acid in adj['acids']:
                    if acid.get('amount') and float(acid['amount']) > 0:
                        water['mash_water_additions'].append({
                            'name': f"{acid.get('type', 'lactic').title()} Acid",
                            'amount': {'value': float(acid['amount']), 'unit': 'ml'},
                            'concentration': {'value': float(acid.get('concentration', 0)), 'unit': '%'}
                        })

        # Sparge water additions
        if 'spargeAdjustments' in bf_water:
            adj = bf_water['spargeAdjustments']
            water['sparge_water_additions'] = []

            salt_mapping = {
                'calciumChloride': 'Calcium Chloride (CaCl2)',
                'calciumSulfate': 'Gypsum (CaSO4)',
                'magnesiumSulfate': 'Epsom Salt (MgSO4)',
                'sodiumBicarbonate': 'Sodium Bicarbonate (NaHCO3)',
                'calciumCarbonate': 'Calcium Carbonate (CaCO3)',
                'calciumHydroxide': 'Calcium Hydroxide (Ca(OH)2)',
            }

            for bf_key, name in salt_mapping.items():
                if adj.get(bf_key) and float(adj[bf_key]) > 0:
                    water['sparge_water_additions'].append({
                        'name': name,
                        'amount': {'value': float(adj[bf_key]), 'unit': 'g'}
                    })

        return water

    # Unit conversion helpers
    def _make_volume(self, value: Optional[float]) -> Optional[Dict[str, Any]]:
        """Convert to BeerJSON volume (liters)."""
        if value is None:
            return None
        return {'value': float(value), 'unit': 'l'}

    def _make_mass_kg(self, value: Optional[float]) -> Optional[Dict[str, Any]]:
        """Convert to BeerJSON mass (kg)."""
        if value is None:
            return None
        return {'value': float(value), 'unit': 'kg'}

    def _make_mass_g(self, value: Optional[float]) -> Optional[Dict[str, Any]]:
        """Convert to BeerJSON mass (grams)."""
        if value is None:
            return None
        return {'value': float(value), 'unit': 'g'}

    def _make_temperature(self, value: Optional[float]) -> Optional[Dict[str, Any]]:
        """Convert to BeerJSON temperature (Celsius)."""
        if value is None:
            return None
        return {'value': float(value), 'unit': 'C'}

    def _make_time_minutes(self, value: Optional[float]) -> Optional[Dict[str, Any]]:
        """Convert to BeerJSON time (minutes)."""
        if value is None:
            return None
        return {'value': float(value), 'unit': 'min'}

    def _make_gravity(self, value: Optional[float]) -> Optional[Dict[str, Any]]:
        """Convert to BeerJSON gravity (specific gravity)."""
        if value is None:
            return None
        return {'value': float(value), 'unit': 'sg'}

    def _make_percent(self, value: Optional[float]) -> Optional[Dict[str, Any]]:
        """Convert to BeerJSON percent (0-1 range)."""
        if value is None:
            return None
        val = float(value)
        # Brewfather stores as 0-100, BeerJSON uses 0-1
        if val > 1:
            val = val / 100
        return {'value': val, 'unit': '%'}

    def _make_dimensionless(self, value: Optional[float]) -> Optional[Dict[str, Any]]:
        """Convert to BeerJSON dimensionless unit."""
        if value is None:
            return None
        return {'value': float(value), 'unit': '1'}

    def _make_color(self, value: Optional[float]) -> Optional[Dict[str, Any]]:
        """Convert to BeerJSON color (SRM)."""
        if value is None:
            return None
        return {'value': float(value), 'unit': 'SRM'}

    # Type mappers
    def _map_recipe_type(self, bf_type: str) -> str:
        """Map Brewfather recipe type to BeerJSON."""
        mapping = {
            'All Grain': 'all grain',
            'Partial Mash': 'partial mash',
            'Extract': 'extract',
            'BIAB': 'all grain',
        }
        return mapping.get(bf_type, 'all grain')

    def _map_style_type(self, bf_type: str) -> str:
        """Map Brewfather style type to BeerJSON."""
        if not bf_type:
            return 'beer'
        mapping = {
            'Ale': 'beer',
            'Lager': 'beer',
            'Wheat': 'beer',
            'Beer': 'beer',
            'Cider': 'cider',
            'Mead': 'mead',
            'Wine': 'wine',
            'Kombucha': 'kombucha',
            'Soda': 'soda',
            'Other': 'other'
        }
        return mapping.get(bf_type, 'beer')

    def _map_grain_group(self, bf_grain_group: str) -> str:
        """Map Brewfather grain category to BeerJSON grain_group enum."""
        mapping = {
            'Base': 'base',
            'base': 'base',
            'Caramel': 'caramel',
            'caramel': 'caramel',
            'Crystal/Caramel': 'caramel',
            'Flaked': 'flaked',
            'flaked': 'flaked',
            'Roasted': 'roasted',
            'roasted': 'roasted',
            'Specialty': 'specialty',
            'specialty': 'specialty',
            'Smoked': 'smoked',
            'smoked': 'smoked',
            'Adjunct': 'adjunct',
            'adjunct': 'adjunct'
        }
        return mapping.get(bf_grain_group, 'base')

    def _map_fermentable_type(self, bf_type: str) -> str:
        """Map Brewfather fermentable type to BeerJSON."""
        mapping = {
            'Grain': 'grain',
            'Extract': 'extract',
            'Sugar': 'sugar',
            'Dry Extract': 'dry extract',
            'Adjunct': 'adjunct'
        }
        return mapping.get(bf_type, 'grain')

    def _map_hop_form(self, bf_form: str) -> str:
        """Map Brewfather hop form to BeerJSON."""
        mapping = {
            'Pellet': 'pellet',
            'Plug': 'plug',
            'Leaf': 'leaf',
            'Extract': 'extract'
        }
        return mapping.get(bf_form, 'pellet')

    def _map_yeast_type(self, bf_type: str) -> str:
        """Map Brewfather yeast type to BeerJSON."""
        mapping = {
            'Ale': 'ale',
            'Lager': 'lager',
            'Wheat': 'ale',
            'Wine': 'wine',
            'Champagne': 'wine'
        }
        return mapping.get(bf_type, 'ale')

    def _map_yeast_form(self, bf_form: str) -> str:
        """Map Brewfather yeast form to BeerJSON."""
        mapping = {
            'Liquid': 'liquid',
            'Dry': 'dry',
            'Slant': 'slant',
            'Culture': 'culture'
        }
        return mapping.get(bf_form, 'dry')

    def _map_misc_type(self, bf_type: str) -> str:
        """Map Brewfather misc type to BeerJSON."""
        mapping = {
            'Spice': 'spice',
            'Fining': 'fining',
            'Herb': 'herb',
            'Flavor': 'flavor',
            'Water Agent': 'water agent',
            'Other': 'other'
        }
        return mapping.get(bf_type, 'other')
