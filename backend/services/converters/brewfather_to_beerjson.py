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
                'version': '1.0',
                'recipes': [beerjson_recipe]
            }
        }

    def _convert_recipe(self, bf_recipe: Dict[str, Any]) -> Dict[str, Any]:
        """Convert single Brewfather recipe to BeerJSON recipe."""
        recipe = {
            'name': bf_recipe.get('name', ''),
            'type': bf_recipe.get('type', ''),
            'author': bf_recipe.get('author', ''),
            'batch_size': self._make_volume(bf_recipe.get('batchSize')),
            'original_gravity': self._make_gravity(bf_recipe.get('og')),
            'final_gravity': self._make_gravity(bf_recipe.get('fg')),
            'alcohol_by_volume': self._make_percent(bf_recipe.get('abv')),
            'ibu_estimate': self._make_dimensionless(bf_recipe.get('ibu')),
            'color_estimate': self._make_color(bf_recipe.get('color')),
            'carbonation': self._make_dimensionless(bf_recipe.get('carbonation')),
            'notes': bf_recipe.get('notes', ''),
        }

        # Boil
        if bf_recipe.get('boilTime'):
            recipe['boil'] = {
                'boil_time': self._make_time_minutes(bf_recipe['boilTime'])
            }

        # Efficiency
        if bf_recipe.get('efficiency'):
            recipe['efficiency'] = {
                'brewhouse': self._make_percent(bf_recipe['efficiency'])
            }

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

        # Water chemistry (Brewfather extension)
        if 'water' in bf_recipe:
            recipe['water'] = self._convert_water(bf_recipe['water'])

        # Brewfather extensions
        extensions = {}
        if bf_recipe.get('_id'):
            extensions['_id'] = bf_recipe['_id']
        if bf_recipe.get('_version'):
            extensions['_version'] = bf_recipe['_version']
        if bf_recipe.get('_timestamp'):
            extensions['_timestamp'] = bf_recipe['_timestamp']
        if bf_recipe.get('equipment'):
            extensions['equipment'] = bf_recipe['equipment']

        if extensions:
            recipe['_extensions'] = {'brewfather': extensions}

        return recipe

    def _convert_ingredients(self, bf_recipe: Dict[str, Any]) -> Dict[str, Any]:
        """Convert ingredients section."""
        ingredients = {}

        # Fermentables
        if 'fermentables' in bf_recipe:
            ingredients['fermentables'] = [
                self._convert_fermentable(f) for f in bf_recipe['fermentables']
            ]

        # Hops
        if 'hops' in bf_recipe:
            ingredients['hops'] = [
                self._convert_hop(h) for h in bf_recipe['hops']
            ]

        # Yeasts/Cultures
        if 'yeasts' in bf_recipe:
            ingredients['cultures'] = [
                self._convert_culture(y) for y in bf_recipe['yeasts']
            ]

        # Miscs
        if 'miscs' in bf_recipe:
            ingredients['miscellaneous_ingredients'] = [
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

        # Grain category
        if bf_ferm.get('grainCategory'):
            ferm['grain_group'] = bf_ferm['grainCategory']

        # Percentage
        if bf_ferm.get('percentage'):
            ferm['percentage'] = bf_ferm['percentage']

        # Brewfather extensions
        if bf_ferm.get('_id'):
            ferm['_extensions'] = {
                'brewfather': {
                    'id': bf_ferm['_id']
                }
            }

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

        # Brewfather extensions
        extensions = {}
        if bf_hop.get('_id'):
            extensions['id'] = bf_hop['_id']

        if extensions:
            hop['_extensions'] = {'brewfather': extensions}

        return hop

    def _convert_hop_timing(self, bf_hop: Dict[str, Any]) -> Dict[str, Any]:
        """Convert Brewfather hop use/time/temp to BeerJSON timing object."""
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
            'use': use_mapping.get(use, 'add_to_boil'),
            'continuous': False
        }

        # Duration
        if use in ['Boil', 'Aroma', 'Whirlpool'] and time and time > 0:
            timing['duration'] = {
                'value': float(time),
                'unit': 'min'
            }

        # Hopstand/whirlpool temperature (Brewfather extension)
        if bf_hop.get('temp'):
            timing['temperature'] = {
                'value': float(bf_hop['temp']),
                'unit': 'C'
            }

        # Dry hop
        if use == 'Dry Hop':
            timing['phase'] = 'primary'
            if time and time > 0:
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

        # Attenuation
        if bf_yeast.get('attenuation'):
            culture['attenuation'] = {
                'maximum': self._make_percent(bf_yeast['attenuation'])
            }

        # Amount
        if bf_yeast.get('amount'):
            amount_val = float(bf_yeast['amount'])
            unit = bf_yeast.get('unit', 'pkg')

            culture['amount'] = {
                'value': amount_val,
                'unit': unit
            }

        # Flocculation
        if bf_yeast.get('flocculation'):
            if '_extensions' not in culture:
                culture['_extensions'] = {}
            if 'brewfather' not in culture['_extensions']:
                culture['_extensions']['brewfather'] = {}
            culture['_extensions']['brewfather']['flocculation'] = bf_yeast['flocculation']

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

        # Water adjustment flag
        if bf_misc.get('waterAdjustment'):
            if '_extensions' not in misc:
                misc['_extensions'] = {}
            if 'brewfather' not in misc['_extensions']:
                misc['_extensions']['brewfather'] = {}
            misc['_extensions']['brewfather']['waterAdjustment'] = True

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
            'use': use_mapping.get(use, 'add_to_boil'),
            'continuous': False
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
            'name': bf_mash.get('name', ''),
            'mash_steps': []
        }

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
            'type': bf_style.get('type', '')
        }

    def _convert_fermentation(self, bf_ferm: Dict[str, Any]) -> Dict[str, Any]:
        """Convert Brewfather fermentation to BeerJSON."""
        fermentation = {
            'name': bf_ferm.get('name', ''),
            'fermentation_steps': []
        }

        # Fermentation steps
        if 'steps' in bf_ferm:
            fermentation['fermentation_steps'] = [
                self._convert_fermentation_step(s) for s in bf_ferm['steps']
            ]

        return fermentation

    def _convert_fermentation_step(self, bf_step: Dict[str, Any]) -> Dict[str, Any]:
        """Convert Brewfather fermentation step to BeerJSON."""
        step = {
            'type': bf_step.get('type', 'primary').lower(),
            'step_temperature': self._make_temperature(bf_step.get('stepTemp')),
            'step_time': {
                'value': float(bf_step.get('stepTime', 0)),
                'unit': 'day'
            }
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
