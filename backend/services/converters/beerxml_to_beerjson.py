"""Convert BeerXML dict to BeerJSON dict."""
from typing import Dict, Any, List, Optional


class BeerXMLToBeerJSONConverter:
    """Convert BeerXML format to BeerJSON 1.0."""

    def convert(self, beerxml_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Convert BeerXML dict to BeerJSON dict.

        Args:
            beerxml_dict: Parsed BeerXML as nested dict

        Returns:
            BeerJSON 1.0 compatible dict
        """
        recipes_root = beerxml_dict.get('RECIPES', {})
        recipe_data = recipes_root.get('RECIPE', {})

        # Handle single recipe or list
        if isinstance(recipe_data, list):
            recipe_data = recipe_data[0]

        beerjson_recipe = self._convert_recipe(recipe_data)

        return {
            'beerjson': {
                'version': '1.0',
                'recipes': [beerjson_recipe]
            }
        }

    def _convert_recipe(self, beerxml_recipe: Dict[str, Any]) -> Dict[str, Any]:
        """Convert single BeerXML recipe to BeerJSON recipe."""
        recipe = {
            'name': beerxml_recipe.get('NAME', ''),
            'type': beerxml_recipe.get('TYPE', ''),
            'author': beerxml_recipe.get('BREWER', ''),
            'batch_size': self._make_volume(beerxml_recipe.get('BATCH_SIZE')),
            'original_gravity': self._make_gravity(beerxml_recipe.get('OG')),
            'final_gravity': self._make_gravity(beerxml_recipe.get('FG')),
            'alcohol_by_volume': self._make_percent(beerxml_recipe.get('ABV')),
            'ibu_estimate': self._make_dimensionless(beerxml_recipe.get('IBU')),
            'color_estimate': self._make_color(beerxml_recipe.get('EST_COLOR')),
            'carbonation': self._make_dimensionless(beerxml_recipe.get('CARBONATION')),
            'notes': beerxml_recipe.get('NOTES', ''),
        }

        # Boil
        if beerxml_recipe.get('BOIL_TIME'):
            recipe['boil'] = {
                'boil_time': self._make_time_minutes(beerxml_recipe['BOIL_TIME'])
            }

        # Efficiency
        if beerxml_recipe.get('EFFICIENCY'):
            recipe['efficiency'] = {
                'brewhouse': self._make_percent(beerxml_recipe['EFFICIENCY'])
            }

        # Ingredients
        recipe['ingredients'] = self._convert_ingredients(beerxml_recipe)

        # Mash
        if 'MASH' in beerxml_recipe:
            recipe['mash'] = self._convert_mash(beerxml_recipe['MASH'])

        # Style
        if 'STYLE' in beerxml_recipe:
            recipe['style'] = self._convert_style(beerxml_recipe['STYLE'])

        return recipe

    def _convert_ingredients(self, beerxml_recipe: Dict[str, Any]) -> Dict[str, Any]:
        """Convert ingredients section."""
        ingredients = {}

        # Fermentables
        if 'FERMENTABLES' in beerxml_recipe:
            ferms = beerxml_recipe['FERMENTABLES'].get('FERMENTABLE', [])
            if not isinstance(ferms, list):
                ferms = [ferms]
            ingredients['fermentables'] = [
                self._convert_fermentable(f) for f in ferms
            ]

        # Hops
        if 'HOPS' in beerxml_recipe:
            hops = beerxml_recipe['HOPS'].get('HOP', [])
            if not isinstance(hops, list):
                hops = [hops]
            ingredients['hops'] = [
                self._convert_hop(h) for h in hops
            ]

        # Yeasts/Cultures
        if 'YEASTS' in beerxml_recipe:
            yeasts = beerxml_recipe['YEASTS'].get('YEAST', [])
            if not isinstance(yeasts, list):
                yeasts = [yeasts]
            ingredients['cultures'] = [
                self._convert_culture(y) for y in yeasts
            ]

        # Miscs
        if 'MISCS' in beerxml_recipe:
            miscs = beerxml_recipe['MISCS'].get('MISC', [])
            if not isinstance(miscs, list):
                miscs = [miscs]
            ingredients['miscellaneous_ingredients'] = [
                self._convert_misc(m) for m in miscs
            ]

        return ingredients

    def _convert_fermentable(self, beerxml_ferm: Dict[str, Any]) -> Dict[str, Any]:
        """Convert BeerXML fermentable to BeerJSON."""
        ferm = {
            'name': beerxml_ferm.get('NAME', ''),
            'type': self._map_fermentable_type(beerxml_ferm.get('TYPE', '')),
            'amount': self._make_mass_kg(beerxml_ferm.get('AMOUNT')),
            'origin': beerxml_ferm.get('ORIGIN', ''),
            'producer': beerxml_ferm.get('SUPPLIER', ''),
            'color': self._make_color(beerxml_ferm.get('COLOR')),
        }

        # Yield
        if beerxml_ferm.get('YIELD'):
            ferm['yield'] = {
                'fine_grind': self._make_percent(beerxml_ferm['YIELD'])
            }

        # Brewfather extensions
        if beerxml_ferm.get('BF_ID'):
            ferm['_extensions'] = {
                'brewfather': {
                    'id': beerxml_ferm['BF_ID']
                }
            }

        return ferm

    def _convert_hop(self, beerxml_hop: Dict[str, Any]) -> Dict[str, Any]:
        """Convert BeerXML hop to BeerJSON."""
        hop = {
            'name': beerxml_hop.get('NAME', ''),
            'origin': beerxml_hop.get('ORIGIN', ''),
            'form': self._map_hop_form(beerxml_hop.get('FORM', '')),
            'alpha_acid': self._make_percent(beerxml_hop.get('ALPHA')),
            'amount': self._make_mass_g(beerxml_hop.get('AMOUNT')),
            'timing': self._convert_hop_timing(beerxml_hop)
        }

        # Beta acid
        if beerxml_hop.get('BETA'):
            hop['beta_acid'] = self._make_percent(beerxml_hop['BETA'])

        # Brewfather extensions
        extensions = {}
        if beerxml_hop.get('BF_ID'):
            extensions['id'] = beerxml_hop['BF_ID']

        if extensions:
            hop['_extensions'] = {'brewfather': extensions}

        return hop

    def _convert_hop_timing(self, beerxml_hop: Dict[str, Any]) -> Dict[str, Any]:
        """Convert BeerXML hop use/time to BeerJSON timing object."""
        use = beerxml_hop.get('USE', 'Boil')
        time = float(beerxml_hop.get('TIME', 0)) if beerxml_hop.get('TIME') else 0

        # Map use to BeerJSON
        use_mapping = {
            'Boil': 'add_to_boil',
            'Dry Hop': 'add_to_fermentation',
            'Mash': 'add_to_mash',
            'First Wort': 'add_to_boil',
            'Aroma': 'add_to_boil'
        }

        timing = {
            'use': use_mapping.get(use, 'add_to_boil'),
            'continuous': False
        }

        # Duration
        if use in ['Boil', 'Aroma'] and time > 0:
            timing['duration'] = {
                'value': time,
                'unit': 'min'
            }

        # Hopstand temperature (Brewfather extension)
        if beerxml_hop.get('TEMPERATURE') or beerxml_hop.get('HOP_TEMP'):
            temp = beerxml_hop.get('TEMPERATURE') or beerxml_hop.get('HOP_TEMP')
            timing['temperature'] = {
                'value': float(temp),
                'unit': 'C'
            }

        # Dry hop
        if use == 'Dry Hop':
            timing['phase'] = 'primary'
            if time > 0:
                # BeerXML stores dry hop time in minutes - convert to days
                timing['duration'] = {
                    'value': int(time / 1440),
                    'unit': 'day'
                }

        return timing

    def _convert_culture(self, beerxml_yeast: Dict[str, Any]) -> Dict[str, Any]:
        """Convert BeerXML yeast to BeerJSON culture."""
        culture = {
            'name': beerxml_yeast.get('NAME', ''),
            'type': self._map_yeast_type(beerxml_yeast.get('TYPE', '')),
            'form': self._map_yeast_form(beerxml_yeast.get('FORM', '')),
            'producer': beerxml_yeast.get('LABORATORY', ''),
            'product_id': beerxml_yeast.get('PRODUCT_ID', ''),
        }

        # Temperature range
        if beerxml_yeast.get('MIN_TEMPERATURE') or beerxml_yeast.get('MAX_TEMPERATURE'):
            temp_range = {}
            if beerxml_yeast.get('MIN_TEMPERATURE'):
                temp_range['minimum'] = {
                    'value': float(beerxml_yeast['MIN_TEMPERATURE']),
                    'unit': 'C'
                }
            if beerxml_yeast.get('MAX_TEMPERATURE'):
                temp_range['maximum'] = {
                    'value': float(beerxml_yeast['MAX_TEMPERATURE']),
                    'unit': 'C'
                }
            culture['temperature_range'] = temp_range

        # Attenuation
        if beerxml_yeast.get('ATTENUATION'):
            culture['attenuation'] = {
                'maximum': self._make_percent(beerxml_yeast['ATTENUATION'])
            }

        # Amount
        if beerxml_yeast.get('AMOUNT'):
            amount_val = float(beerxml_yeast['AMOUNT'])
            # BeerXML amount is in liters for liquid, or count for dry
            form = beerxml_yeast.get('FORM', '').lower()
            unit = 'ml' if form == 'liquid' else 'pkg'

            culture['amount'] = {
                'value': amount_val * 1000 if unit == 'ml' else amount_val,
                'unit': unit
            }

        return culture

    def _convert_misc(self, beerxml_misc: Dict[str, Any]) -> Dict[str, Any]:
        """Convert BeerXML misc to BeerJSON."""
        misc = {
            'name': beerxml_misc.get('NAME', ''),
            'type': self._map_misc_type(beerxml_misc.get('TYPE', '')),
        }

        # Amount
        amount_val = float(beerxml_misc.get('AMOUNT', 0))
        is_weight = beerxml_misc.get('AMOUNT_IS_WEIGHT', 'false').lower() == 'true'

        misc['amount'] = {
            'value': amount_val * 1000,  # kg→g or l→ml
            'unit': 'g' if is_weight else 'ml'
        }

        # Timing
        use = beerxml_misc.get('USE', 'Boil')
        time = float(beerxml_misc.get('TIME', 0)) if beerxml_misc.get('TIME') else 0

        timing = self._convert_misc_timing(use, time)
        misc['timing'] = timing

        return misc

    def _convert_misc_timing(self, use: str, time: float) -> Dict[str, Any]:
        """Convert misc use/time to BeerJSON timing."""
        use_mapping = {
            'Boil': 'add_to_boil',
            'Mash': 'add_to_mash',
            'Primary': 'add_to_fermentation',
            'Secondary': 'add_to_fermentation',
            'Bottling': 'add_to_package',
            'Sparge': 'add_to_mash'  # Map Sparge to mash
        }

        timing = {
            'use': use_mapping.get(use, 'add_to_boil'),
            'continuous': False
        }

        if time > 0:
            timing['duration'] = {
                'value': time,
                'unit': 'min'
            }

        return timing

    def _convert_mash(self, beerxml_mash: Dict[str, Any]) -> Dict[str, Any]:
        """Convert BeerXML mash to BeerJSON."""
        mash = {
            'name': beerxml_mash.get('NAME', ''),
            'grain_temperature': self._make_temperature(beerxml_mash.get('GRAIN_TEMP')),
            'mash_steps': []
        }

        # Mash steps
        if 'MASH_STEPS' in beerxml_mash:
            steps = beerxml_mash['MASH_STEPS'].get('MASH_STEP', [])
            if not isinstance(steps, list):
                steps = [steps]

            mash['mash_steps'] = [
                self._convert_mash_step(s) for s in steps
            ]

        return mash

    def _convert_mash_step(self, beerxml_step: Dict[str, Any]) -> Dict[str, Any]:
        """Convert BeerXML mash step to BeerJSON."""
        step = {
            'name': beerxml_step.get('NAME', ''),
            'type': beerxml_step.get('TYPE', 'temperature').lower(),
            'step_temperature': self._make_temperature(beerxml_step.get('STEP_TEMP')),
            'step_time': self._make_time_minutes(beerxml_step.get('STEP_TIME'))
        }

        # Infusion
        if beerxml_step.get('INFUSE_AMOUNT'):
            step['infusion_amount'] = self._make_volume(beerxml_step['INFUSE_AMOUNT'])

        return step

    def _convert_style(self, beerxml_style: Dict[str, Any]) -> Dict[str, Any]:
        """Convert BeerXML style to BeerJSON."""
        return {
            'name': beerxml_style.get('NAME', ''),
            'category': beerxml_style.get('CATEGORY', ''),
            'style_guide': beerxml_style.get('STYLE_GUIDE', ''),
            'type': beerxml_style.get('TYPE', '')
        }

    # Unit conversion helpers
    def _make_volume(self, value: Optional[str]) -> Optional[Dict[str, Any]]:
        """Convert to BeerJSON volume (liters)."""
        if value is None or value == '':
            return None
        return {'value': float(value), 'unit': 'l'}

    def _make_mass_kg(self, value: Optional[str]) -> Optional[Dict[str, Any]]:
        """Convert to BeerJSON mass (kg)."""
        if value is None or value == '':
            return None
        return {'value': float(value), 'unit': 'kg'}

    def _make_mass_g(self, value: Optional[str]) -> Optional[Dict[str, Any]]:
        """Convert kg to grams for BeerJSON."""
        if value is None or value == '':
            return None
        # BeerXML hops in kg, BeerJSON uses g
        return {'value': float(value) * 1000, 'unit': 'g'}

    def _make_temperature(self, value: Optional[str]) -> Optional[Dict[str, Any]]:
        """Convert to BeerJSON temperature (Celsius)."""
        if value is None or value == '':
            return None
        return {'value': float(value), 'unit': 'C'}

    def _make_time_minutes(self, value: Optional[str]) -> Optional[Dict[str, Any]]:
        """Convert to BeerJSON time (minutes)."""
        if value is None or value == '':
            return None
        return {'value': float(value), 'unit': 'min'}

    def _make_gravity(self, value: Optional[str]) -> Optional[Dict[str, Any]]:
        """Convert to BeerJSON gravity (specific gravity)."""
        if value is None or value == '':
            return None
        return {'value': float(value), 'unit': 'sg'}

    def _make_percent(self, value: Optional[str]) -> Optional[Dict[str, Any]]:
        """Convert to BeerJSON percent."""
        if value is None or value == '':
            return None
        # Extract numeric value from "4.2 %" or "81"
        val_str = str(value).split()[0]
        val = float(val_str)
        # BeerXML stores as 0-100, BeerJSON uses 0-1
        if val > 1:
            val = val / 100
        return {'value': val, 'unit': '%'}

    def _make_dimensionless(self, value: Optional[str]) -> Optional[Dict[str, Any]]:
        """Convert to BeerJSON dimensionless unit."""
        if value is None or value == '':
            return None
        return {'value': float(value), 'unit': '1'}

    def _make_color(self, value: Optional[str]) -> Optional[Dict[str, Any]]:
        """Convert to BeerJSON color (SRM)."""
        if value is None or value == '':
            return None
        # Extract numeric value from "3.8 SRM"
        val_str = str(value).split()[0]
        return {'value': float(val_str), 'unit': 'SRM'}

    # Type mappers
    def _map_fermentable_type(self, beerxml_type: str) -> str:
        """Map BeerXML fermentable type to BeerJSON."""
        mapping = {
            'Grain': 'grain',
            'Extract': 'extract',
            'Sugar': 'sugar',
            'Dry Extract': 'dry extract',
            'Adjunct': 'adjunct'
        }
        return mapping.get(beerxml_type, 'grain')

    def _map_hop_form(self, beerxml_form: str) -> str:
        """Map BeerXML hop form to BeerJSON."""
        mapping = {
            'Pellet': 'pellet',
            'Plug': 'plug',
            'Leaf': 'leaf',
            'Extract': 'extract'
        }
        return mapping.get(beerxml_form, 'pellet')

    def _map_yeast_type(self, beerxml_type: str) -> str:
        """Map BeerXML yeast type to BeerJSON."""
        mapping = {
            'Ale': 'ale',
            'Lager': 'lager',
            'Wheat': 'ale',
            'Wine': 'wine',
            'Champagne': 'wine'
        }
        return mapping.get(beerxml_type, 'ale')

    def _map_yeast_form(self, beerxml_form: str) -> str:
        """Map BeerXML yeast form to BeerJSON."""
        mapping = {
            'Liquid': 'liquid',
            'Dry': 'dry',
            'Slant': 'slant',
            'Culture': 'culture'
        }
        return mapping.get(beerxml_form, 'dry')

    def _map_misc_type(self, beerxml_type: str) -> str:
        """Map BeerXML misc type to BeerJSON."""
        mapping = {
            'Spice': 'spice',
            'Fining': 'fining',
            'Herb': 'herb',
            'Flavor': 'flavor',
            'Water Agent': 'water agent',
            'Other': 'other'
        }
        return mapping.get(beerxml_type, 'other')
