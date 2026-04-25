"""Convert native BrewSignal recipe format to BeerJSON 1.0.

The /api/recipes/import endpoint already accepts BeerXML, Brewfather JSON,
and BeerJSON. Native BrewSignal JSON had no import path even though the
/api/recipes/validate endpoint accepted the format — agents had to fall
back to a multi-step validate-then-create flow that bypassed the standard
import pipeline. This converter closes the gap (tilt_ui-kew).
"""
from typing import Any, Dict, List, Optional


class BrewSignalToBeerJSONConverter:
    """Convert validated BrewSignal recipe dict to BeerJSON 1.0 dict."""

    def convert(self, brewsignal_dict: Dict[str, Any]) -> Dict[str, Any]:
        return {
            'beerjson': {
                'version': 1.0,
                'recipes': [self._convert_recipe(brewsignal_dict)],
            }
        }

    def _convert_recipe(self, bs: Dict[str, Any]) -> Dict[str, Any]:
        recipe: Dict[str, Any] = {
            'name': bs.get('name', ''),
            'type': bs.get('type', 'all grain'),
            'author': bs.get('author', 'Unknown'),
        }

        if bs.get('og') is not None:
            recipe['original_gravity'] = {'value': float(bs['og']), 'unit': 'sg'}
        if bs.get('fg') is not None:
            recipe['final_gravity'] = {'value': float(bs['fg']), 'unit': 'sg'}
        if bs.get('abv') is not None:
            recipe['alcohol_by_volume'] = {'value': float(bs['abv']), 'unit': '%'}
        if bs.get('ibu') is not None:
            recipe['ibu_estimate'] = {'value': float(bs['ibu']), 'unit': 'IBUs'}
        if bs.get('color_srm') is not None:
            recipe['color_estimate'] = {'value': float(bs['color_srm']), 'unit': 'SRM'}
        if bs.get('batch_size_liters') is not None:
            recipe['batch_size'] = {'value': float(bs['batch_size_liters']), 'unit': 'l'}

        boil: Dict[str, Any] = {}
        if bs.get('boil_time_minutes') is not None:
            boil['boil_time'] = {'value': int(bs['boil_time_minutes']), 'unit': 'min'}
        if boil:
            recipe['boil'] = boil

        if bs.get('efficiency_percent') is not None:
            recipe['efficiency'] = {
                'brewhouse': {'value': float(bs['efficiency_percent']), 'unit': '%'}
            }

        if bs.get('carbonation_vols') is not None:
            recipe['carbonation'] = float(bs['carbonation_vols'])

        if bs.get('style_id'):
            recipe['style'] = {'name': bs['style_id'], 'category': '', 'category_number': 0,
                               'style_letter': '', 'style_guide': 'BJCP', 'type': 'beer'}

        if bs.get('notes'):
            recipe['notes'] = bs['notes']

        recipe['ingredients'] = self._convert_ingredients(bs)

        if bs.get('mash_steps'):
            recipe['mash'] = self._convert_mash(bs['mash_steps'])
        if bs.get('fermentation_steps'):
            recipe['fermentation'] = self._convert_fermentation(bs['fermentation_steps'])

        return recipe

    def _convert_ingredients(self, bs: Dict[str, Any]) -> Dict[str, Any]:
        ingredients: Dict[str, Any] = {}

        if bs.get('fermentables'):
            ingredients['fermentable_additions'] = [
                self._convert_fermentable(f) for f in bs['fermentables']
            ]
        if bs.get('hops'):
            ingredients['hop_additions'] = [
                self._convert_hop(h) for h in bs['hops']
            ]
        if bs.get('yeast'):
            ingredients['culture_additions'] = [self._convert_yeast(bs['yeast'])]
        if bs.get('miscs'):
            ingredients['miscellaneous_additions'] = [
                self._convert_misc(m) for m in bs['miscs']
            ]
        return ingredients

    def _convert_fermentable(self, f: Dict[str, Any]) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            'name': f.get('name', ''),
            'type': f.get('type', 'grain'),
            'amount': {'value': float(f['amount_kg']), 'unit': 'kg'},
        }
        if f.get('yield_percent') is not None:
            out['yield'] = {
                'fine_grind': {'value': float(f['yield_percent']), 'unit': '%'}
            }
        if f.get('color_srm') is not None:
            out['color'] = {'value': float(f['color_srm']), 'unit': 'SRM'}
        if f.get('origin'):
            out['origin'] = f['origin']
        if f.get('supplier'):
            out['supplier'] = f['supplier']
        return out

    def _convert_hop(self, h: Dict[str, Any]) -> Dict[str, Any]:
        # alpha_acid_percent is optional in the BrewSignal schema but the
        # underlying RecipeHop column is non-nullable. Default missing AA
        # to 0 so the import flushes; users can edit later.
        alpha = h.get('alpha_acid_percent')
        out: Dict[str, Any] = {
            'name': h.get('name', ''),
            'amount': {'value': float(h['amount_grams']), 'unit': 'g'},
            'timing': h.get('timing') or {'use': 'add_to_boil'},
            'alpha_acid': {'value': float(alpha) if alpha is not None else 0.0, 'unit': '%'},
        }
        if h.get('origin'):
            out['origin'] = h['origin']
        if h.get('form'):
            out['form'] = h['form']
        if h.get('beta_acid_percent') is not None:
            out['beta_acid'] = {'value': float(h['beta_acid_percent']), 'unit': '%'}
        return out

    def _convert_yeast(self, y: Dict[str, Any]) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            'name': y.get('name', ''),
            'type': y.get('type', 'ale'),
            'form': y.get('form', 'dry'),
        }
        if y.get('producer'):
            out['producer'] = y['producer']
        if y.get('product_id'):
            out['product_id'] = y['product_id']
        if y.get('attenuation_percent') is not None:
            out['attenuation'] = {'value': float(y['attenuation_percent']), 'unit': '%'}
        if y.get('temp_min_c') is not None or y.get('temp_max_c') is not None:
            tr: Dict[str, Any] = {}
            if y.get('temp_min_c') is not None:
                tr['minimum'] = {'value': float(y['temp_min_c']), 'unit': 'C'}
            if y.get('temp_max_c') is not None:
                tr['maximum'] = {'value': float(y['temp_max_c']), 'unit': 'C'}
            out['temperature_range'] = tr
        if y.get('amount_grams') is not None:
            out['amount'] = {'value': float(y['amount_grams']), 'unit': 'g'}
        return out

    def _convert_misc(self, m: Dict[str, Any]) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            'name': m.get('name', ''),
            'type': m.get('type', 'other'),
            'timing': m.get('timing') or {'use': 'add_to_boil'},
        }
        if m.get('amount_grams') is not None:
            out['amount'] = {'value': float(m['amount_grams']), 'unit': 'g'}
        return out

    def _convert_mash(self, steps: List[Dict[str, Any]]) -> Dict[str, Any]:
        # The serializer reads step_dict['type'] (not 'step_type'), so we
        # emit BrewSignal step type values directly under that key. Names
        # mirror the type for clarity in the editor.
        return {
            'name': 'Mash',
            'mash_steps': [
                {
                    'name': f"Step {s['step_number']}",
                    'type': s.get('type', 'infusion'),
                    'step_temperature': {'value': float(s['temp_c']), 'unit': 'C'},
                    'step_time': {'value': int(s['time_minutes']), 'unit': 'min'},
                }
                for s in steps
            ],
        }

    def _convert_fermentation(self, steps: List[Dict[str, Any]]) -> Dict[str, Any]:
        return {
            'name': 'Fermentation',
            'fermentation_steps': [
                {
                    'name': s.get('type', 'primary').replace('_', ' ').title(),
                    'step_type': s.get('type', 'primary'),
                    'step_temperature': {'value': float(s['temp_c']), 'unit': 'C'},
                    'step_time': {'value': int(s['time_days']), 'unit': 'day'},
                }
                for s in steps
            ],
        }
