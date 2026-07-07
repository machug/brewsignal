"""BrewSignal Recipe Format v2 — brewsignal-block applier and DB->v2 exporter.

v2 documents pair a BeerJSON-1.0-shaped `recipe` with one namespaced
`brewsignal` block (design: docs/recipe-format-v2-design.md, tilt_ui-0jkg).
Import: the recipe block rides the existing BeerJSON RecipeSerializer;
apply_v2_extensions() then maps the brewsignal block onto ORM columns where
they exist and preserves the rest under format_extensions['brewsignal'] so
nothing is silently dropped. Export (Task 5) mirrors the same shapes back out.
"""
from typing import Any, Dict, List, Optional

from backend.models import Recipe, RecipeWaterAdjustment, RecipeWaterProfile

# Column names shared by the v2 wire format and the ORM (self-documenting
# units per design §1.4 — _ppm / _g suffixes ARE the unit declaration).
ION_KEYS = (
    'calcium_ppm', 'magnesium_ppm', 'sodium_ppm',
    'chloride_ppm', 'sulfate_ppm', 'bicarbonate_ppm',
)
SALT_KEYS = (
    'calcium_sulfate_g', 'calcium_chloride_g', 'magnesium_sulfate_g',
    'sodium_bicarbonate_g', 'calcium_carbonate_g', 'calcium_hydroxide_g',
    'magnesium_chloride_g', 'sodium_chloride_g',
)
# brewsignal.hop_additions entries align to ingredients.hop_additions by
# index; name/ref_use are a human-readable echo, not payload.
_HOP_ALIGNMENT_KEYS = ('index', 'name', 'ref_use')


def apply_v2_extensions(recipe: Recipe, brewsignal: Optional[Dict[str, Any]]) -> None:
    """Apply a v2 `brewsignal` block onto an ORM Recipe in place."""
    if not brewsignal:
        return

    leftovers: Dict[str, Any] = {}
    for key, value in brewsignal.items():
        if key == 'water' and isinstance(value, dict):
            water_leftovers = _apply_water(recipe, value)
            if water_leftovers:
                leftovers['water'] = water_leftovers
        elif key == 'hop_additions' and isinstance(value, list):
            _apply_hop_extras(recipe, value)
        else:
            leftovers[key] = value

    if leftovers:
        ext = dict(recipe.format_extensions or {})
        ext['brewsignal'] = leftovers
        recipe.format_extensions = ext


def _apply_water(recipe: Recipe, water: Dict[str, Any]) -> Dict[str, Any]:
    leftovers: Dict[str, Any] = {}
    for key, value in water.items():
        if key == 'profiles' and isinstance(value, list):
            for profile_dict in value:
                recipe.water_profiles.append(_profile_from_dict(profile_dict))
        elif key == 'target_profile' and isinstance(value, dict):
            recipe.water_profiles.append(
                _profile_from_dict({**value, 'profile_type': 'target'})
            )
        elif key == 'adjustments' and isinstance(value, list):
            for adj_dict in value:
                recipe.water_adjustments.append(_adjustment_from_dict(adj_dict))
        else:
            leftovers[key] = value
    return leftovers


def _profile_from_dict(profile_dict: Dict[str, Any]) -> RecipeWaterProfile:
    profile = RecipeWaterProfile(
        profile_type=profile_dict.get('profile_type', 'target'),
        name=profile_dict.get('name'),
    )
    extras: Dict[str, Any] = {}
    for key, value in profile_dict.items():
        if key in ('profile_type', 'name'):
            continue
        if key in ION_KEYS or key in ('ph', 'alkalinity'):
            setattr(profile, key, value)
        else:
            extras[key] = value
    if extras:
        profile.format_extensions = extras
    return profile


def _adjustment_from_dict(adj_dict: Dict[str, Any]) -> RecipeWaterAdjustment:
    adjustment = RecipeWaterAdjustment(stage=adj_dict.get('stage', 'mash'))
    extras: Dict[str, Any] = {}
    for key, value in adj_dict.items():
        if key == 'stage':
            continue
        if key == 'volume_liters':
            adjustment.volume_liters = value
        elif key == 'salts' and isinstance(value, dict):
            for salt, grams in value.items():
                if salt in SALT_KEYS:
                    setattr(adjustment, salt, grams)
                else:
                    extras.setdefault('salts', {})[salt] = grams
        elif key == 'acid' and isinstance(value, dict):
            adjustment.acid_type = value.get('type')
            adjustment.acid_ml = value.get('ml')
            adjustment.acid_concentration_percent = value.get('concentration_percent')
        else:
            extras[key] = value
    if extras:
        adjustment.format_extensions = extras
    return adjustment


def _apply_hop_extras(recipe: Recipe, entries: List[Dict[str, Any]]) -> None:
    for entry in entries:
        idx = entry.get('index')
        if not isinstance(idx, int) or not (0 <= idx < len(recipe.hops)):
            continue
        extras = {k: v for k, v in entry.items() if k not in _HOP_ALIGNMENT_KEYS}
        if not extras:
            continue
        hop = recipe.hops[idx]
        ext = dict(hop.format_extensions or {})
        ext['brewsignal'] = extras
        hop.format_extensions = ext
