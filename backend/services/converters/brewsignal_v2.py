"""BrewSignal Recipe Format v2 — brewsignal-block applier and DB->v2 exporter.

v2 documents pair a BeerJSON-1.0-shaped `recipe` with one namespaced
`brewsignal` block (design: docs/recipe-format-v2-design.md, tilt_ui-0jkg).
Import: the recipe block rides the existing BeerJSON RecipeSerializer;
apply_v2_extensions() then maps the brewsignal block onto ORM columns where
they exist and preserves the rest under format_extensions['brewsignal'] so
nothing is silently dropped. Export (Task 5) mirrors the same shapes back out.
"""
import copy
from typing import Any, Dict, List, Optional

from sqlalchemy import inspect as sa_inspect

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


def _is_loaded(obj, name: str) -> bool:
    """True if relationship `name` is already populated on ORM object `obj`.

    Used only for the `style` relationship (see _convert_recipe): a freshly
    imported Recipe sets style_id via FK but never touches `.style`, so it
    stays unloaded even on a persistent instance, and that's fine — style is
    non-lossy to omit since style_id round-trips separately. Collections use
    _require_loaded() instead, which fails loudly on persistent instances
    per the lossless-export contract.
    """
    return name not in sa_inspect(obj).unloaded


def _require_loaded(recipe: Recipe, name: str):
    """Return collection relationship `name`, or raise if it's unloaded on
    a persistent Recipe.

    A freshly imported (transient/pending) Recipe only has relationships
    populated that the importer/apply_v2_extensions() actually touched via
    .append(); every other relationship genuinely has zero rows for that
    not-yet-persisted recipe, so treating "unloaded" as "empty" is correct
    there (unit tests build bare Recipe() objects the same way). But once a
    Recipe is persistent (loaded from an existing row), an unloaded
    collection here means the caller forgot to eager-load it — for a
    lossless-export feature, silently emitting a truncated document is
    worse than crashing. Callers MUST eager-load relationships
    (selectinload) per CLAUDE.md "Database: Eager Loading Required" before
    calling convert() on a persistent Recipe; touching an unloaded
    relationship here would otherwise trigger an implicit lazy load and
    raise MissingGreenlet outside the async session's greenlet context, so
    we raise our own clearer error first.
    """
    insp = sa_inspect(recipe)
    if name in insp.unloaded and insp.persistent:
        raise RuntimeError(
            f"Recipe.{name} is unloaded on a persistent recipe (id={recipe.id}). "
            f"Eager-load it via selectinload(Recipe.{name}) before calling "
            "RecipeToBrewSignalV2Converter.convert() — required for lossless export."
        )
    return getattr(recipe, name)


_COLLECTION_RELATIONSHIPS = (
    'fermentables', 'hops', 'cultures', 'miscs', 'mash_steps',
    'fermentation_steps', 'water_profiles', 'water_adjustments',
)


def _touch_collections(recipe: Recipe) -> None:
    """Mark every collection relationship "loaded" on `recipe`, even the
    ones with zero items.

    RecipeSerializer.serialize() only appends to a relationship when the
    source document actually has that ingredient/step category, so e.g. a
    recipe with zero miscellaneous_additions never touches Recipe.miscs and
    it stays unloaded. That's harmless while the recipe is transient, but
    by the time the importer flushes it, the recipe is "persistent" per
    SQLAlchemy — and _require_loaded()'s guard can no longer distinguish
    "genuinely empty" from "existing row, caller forgot to eager-load"
    (both look identical: unloaded + persistent). Called from
    apply_v2_extensions(), the last import-side hook before flush, so every
    freshly-imported recipe is fully materialized before it can ever be
    exported.
    """
    for name in _COLLECTION_RELATIONSHIPS:
        if name in sa_inspect(recipe).unloaded:
            setattr(recipe, name, [])


def apply_v2_extensions(recipe: Recipe, brewsignal: Optional[Dict[str, Any]]) -> None:
    """Apply a v2 `brewsignal` block onto an ORM Recipe in place.

    Must be called on EVERY v2 import, even when the doc has no brewsignal
    block — _touch_collections() has to run regardless (deliberately before
    the falsy early-return below), or a minimal v2 import would leave its
    collections unloaded and a later export would false-positive
    _require_loaded()'s persistent+unloaded guard.
    """
    _touch_collections(recipe)
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


class RecipeToBrewSignalV2Converter:
    """Export an ORM Recipe (relationships loaded) as a BrewSignal v2 doc.

    The `recipe` block mirrors the key names RecipeSerializer._create_*
    read on import, so an exported doc re-imports without loss.
    """

    def convert(self, recipe: Recipe) -> Dict[str, Any]:
        doc: Dict[str, Any] = {
            'brewsignal_version': '2.0',
            'based_on': {'standard': 'BeerJSON', 'version': '1.0'},
            'recipe': self._convert_recipe(recipe),
        }
        brewsignal = self._convert_brewsignal_block(recipe)
        if brewsignal:
            doc['brewsignal'] = brewsignal
        if recipe.notes:
            doc['notes'] = recipe.notes
        if recipe.created_at:
            doc['created_at'] = recipe.created_at.isoformat()
        return doc

    # -- recipe block (BeerJSON shapes) --

    def _convert_recipe(self, recipe: Recipe) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            'name': recipe.name,
            'type': recipe.type or 'all grain',
        }
        if recipe.author:
            out['author'] = recipe.author
        if recipe.batch_size_liters is not None:
            out['batch_size'] = {'value': recipe.batch_size_liters, 'unit': 'l'}
        if recipe.efficiency_percent is not None:
            out['efficiency'] = {
                'brewhouse': {'value': recipe.efficiency_percent, 'unit': '%'}
            }
        if recipe.og is not None:
            out['original_gravity'] = {'value': recipe.og, 'unit': 'sg'}
        if recipe.fg is not None:
            out['final_gravity'] = {'value': recipe.fg, 'unit': 'sg'}
        if recipe.abv is not None:
            out['alcohol_by_volume'] = {'value': recipe.abv, 'unit': '%'}
        if recipe.ibu is not None:
            out['ibu_estimate'] = {'value': recipe.ibu, 'unit': 'IBUs'}
        if recipe.color_srm is not None:
            out['color_estimate'] = {'value': recipe.color_srm, 'unit': 'SRM'}
        if recipe.carbonation_vols is not None:
            out['carbonation'] = recipe.carbonation_vols
        # Recipe.style is a lazy relationship the importer never populates
        # (it only sets style_id); see _is_loaded() docstring.
        if _is_loaded(recipe, 'style') and recipe.style is not None:
            out['style'] = {'name': recipe.style.name}

        boil: Dict[str, Any] = {}
        if recipe.boil_time_minutes is not None:
            boil['boil_time'] = {'value': recipe.boil_time_minutes, 'unit': 'min'}
        if recipe.boil_size_l is not None:
            boil['pre_boil_size'] = {'value': recipe.boil_size_l, 'unit': 'l'}
        if boil:
            out['boil'] = boil

        ingredients: Dict[str, Any] = {}
        fermentables = _require_loaded(recipe, 'fermentables')
        if fermentables:
            ingredients['fermentable_additions'] = [
                self._convert_fermentable(f) for f in fermentables
            ]
        hops = _require_loaded(recipe, 'hops')
        if hops:
            ingredients['hop_additions'] = [
                self._convert_hop(h) for h in hops
            ]
        cultures = _require_loaded(recipe, 'cultures')
        if cultures:
            ingredients['culture_additions'] = [
                self._convert_culture(c) for c in cultures
            ]
        miscs = _require_loaded(recipe, 'miscs')
        if miscs:
            ingredients['miscellaneous_additions'] = [
                self._convert_misc(m) for m in miscs
            ]
        if ingredients:
            out['ingredients'] = ingredients

        mash_steps = _require_loaded(recipe, 'mash_steps')
        if mash_steps:
            out['mash'] = {
                'name': 'Mash',
                'mash_steps': [self._convert_mash_step(s) for s in
                               sorted(mash_steps, key=lambda s: s.step_number)],
            }
        fermentation_steps = _require_loaded(recipe, 'fermentation_steps')
        if fermentation_steps:
            out['fermentation'] = {
                'name': 'Fermentation',
                'fermentation_steps': [
                    self._convert_fermentation_step(s) for s in
                    sorted(fermentation_steps, key=lambda s: s.step_number)
                ],
            }
        return out

    def _convert_fermentable(self, ferm) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            'name': ferm.name,
            'type': ferm.type or 'grain',
            'amount': {'value': ferm.amount_kg, 'unit': 'kg'},
        }
        if ferm.grain_group:
            out['grain_group'] = ferm.grain_group
        if ferm.color_srm is not None:
            out['color'] = {'value': ferm.color_srm, 'unit': 'SRM'}
        if ferm.yield_percent is not None:
            out['yield'] = {'fine_grind': {'value': ferm.yield_percent, 'unit': '%'}}
        if ferm.origin:
            out['origin'] = ferm.origin
        if ferm.supplier:
            out['producer'] = ferm.supplier
        if ferm.timing:
            out['timing'] = ferm.timing
        return out

    def _convert_hop(self, hop) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            'name': hop.name,
            'amount': {'value': hop.amount_grams, 'unit': 'g'},
            'timing': hop.timing or {'use': 'add_to_boil'},
        }
        if hop.origin:
            out['origin'] = hop.origin
        if hop.form:
            out['form'] = hop.form
        if hop.alpha_acid_percent is not None and hop.alpha_acid_percent > 0:
            out['alpha_acid'] = {'value': hop.alpha_acid_percent, 'unit': '%'}
        if hop.beta_acid_percent is not None:
            out['beta_acid'] = {'value': hop.beta_acid_percent, 'unit': '%'}
        # Extract semantics (tilt_ui-0l5): mL is the canonical dose for
        # liquid extracts; these keys are what _create_hop reads back.
        if hop.is_extract:
            out['is_extract'] = True
        if hop.amount_ml is not None:
            out['amount_ml'] = hop.amount_ml
        return out

    def _convert_culture(self, culture) -> Dict[str, Any]:
        out: Dict[str, Any] = {'name': culture.name}
        if culture.type:
            out['type'] = culture.type
        if culture.form:
            out['form'] = culture.form
        if culture.producer:
            out['producer'] = culture.producer
        if culture.product_id:
            out['product_id'] = culture.product_id
        atten_min = culture.attenuation_min_percent
        atten_max = culture.attenuation_max_percent
        if atten_min is not None or atten_max is not None:
            low = atten_min if atten_min is not None else atten_max
            high = atten_max if atten_max is not None else atten_min
            out['attenuation_range'] = {
                'minimum': {'value': low, 'unit': '%'},
                'maximum': {'value': high, 'unit': '%'},
            }
        if culture.temp_min_c is not None or culture.temp_max_c is not None:
            temp_range: Dict[str, Any] = {}
            if culture.temp_min_c is not None:
                temp_range['minimum'] = {'value': culture.temp_min_c, 'unit': 'C'}
            if culture.temp_max_c is not None:
                temp_range['maximum'] = {'value': culture.temp_max_c, 'unit': 'C'}
            out['temperature_range'] = temp_range
        if culture.amount is not None:
            out['amount'] = {'value': culture.amount, 'unit': culture.amount_unit or '1'}
        if culture.timing:
            out['timing'] = culture.timing
        return out

    def _convert_misc(self, misc) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            'name': misc.name,
            'type': misc.type or 'other',
            'timing': misc.timing or {'use': 'add_to_boil'},
        }
        if misc.amount_kg is not None:
            out['amount'] = {'value': misc.amount_kg,
                             'unit': misc.amount_unit or 'kg'}
        return out

    def _convert_mash_step(self, step) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            'name': step.name,
            'type': step.type,
            'step_temperature': {'value': step.temp_c, 'unit': 'C'},
            'step_time': {'value': step.time_minutes, 'unit': 'min'},
        }
        if step.infusion_amount_liters is not None:
            out['infusion_amount'] = {'value': step.infusion_amount_liters, 'unit': 'l'}
        if step.infusion_temp_c is not None:
            out['infusion_temperature'] = {'value': step.infusion_temp_c, 'unit': 'C'}
        if step.ramp_time_minutes is not None:
            out['ramp_time'] = {'value': step.ramp_time_minutes, 'unit': 'min'}
        return out

    def _convert_fermentation_step(self, step) -> Dict[str, Any]:
        return {
            'name': step.type.replace('_', ' ').title(),
            'step_type': step.type,
            'step_temperature': {'value': step.temp_c, 'unit': 'C'},
            'step_time': {'value': step.time_days, 'unit': 'day'},
        }

    # -- brewsignal block --

    def _convert_brewsignal_block(self, recipe: Recipe) -> Dict[str, Any]:
        block: Dict[str, Any] = {}
        leftovers = dict((recipe.format_extensions or {}).get('brewsignal') or {})
        water_leftovers = leftovers.pop('water', None)
        # Pop unconditionally: a stale style_id left in leftovers would
        # otherwise survive into `block.update(leftovers)` below and clobber
        # the authoritative FK value set from recipe.style_id just above.
        stale_style_id = leftovers.pop('style_id', None)

        if recipe.style_id:
            block['style_id'] = recipe.style_id
        elif stale_style_id:
            block['style_id'] = stale_style_id

        water: Dict[str, Any] = {}
        water_profiles = _require_loaded(recipe, 'water_profiles')
        if water_profiles:
            water['profiles'] = [self._convert_profile(p) for p in water_profiles]
        water_adjustments = _require_loaded(recipe, 'water_adjustments')
        if water_adjustments:
            water['adjustments'] = [
                self._convert_adjustment(a) for a in water_adjustments
            ]
        if isinstance(water_leftovers, dict):
            water.update(water_leftovers)
        if water:
            block['water'] = water

        hop_entries = []
        hops = _require_loaded(recipe, 'hops')
        for idx, hop in enumerate(hops):
            extras = (hop.format_extensions or {}).get('brewsignal')
            if extras:
                hop_entries.append({'index': idx, 'name': hop.name, **extras})
        if hop_entries:
            block['hop_additions'] = hop_entries

        block.update(leftovers)
        return block

    def _convert_profile(self, profile) -> Dict[str, Any]:
        out: Dict[str, Any] = {'profile_type': profile.profile_type}
        if profile.name:
            out['name'] = profile.name
        for key in ION_KEYS + ('ph', 'alkalinity'):
            value = getattr(profile, key)
            if value is not None:
                out[key] = value
        if profile.format_extensions:
            out.update(profile.format_extensions)
        return out

    def _convert_adjustment(self, adjustment) -> Dict[str, Any]:
        out: Dict[str, Any] = {'stage': adjustment.stage}
        if adjustment.volume_liters is not None:
            out['volume_liters'] = adjustment.volume_liters
        salts = {key: getattr(adjustment, key) for key in SALT_KEYS
                 if getattr(adjustment, key) is not None}
        extras = dict(adjustment.format_extensions or {})
        extra_salts = extras.pop('salts', None)
        if isinstance(extra_salts, dict):
            salts.update(extra_salts)
        if salts:
            out['salts'] = salts
        if adjustment.acid_type or adjustment.acid_ml is not None:
            out['acid'] = {
                'type': adjustment.acid_type,
                'ml': adjustment.acid_ml,
                'concentration_percent': adjustment.acid_concentration_percent,
            }
        out.update(extras)
        return out


def to_strict_beerjson(recipe_block: Dict[str, Any], notes: Optional[str] = None) -> Dict[str, Any]:
    """Reshape a v2 `recipe` block into strict BeerJSON 1.0.

    RecipeToBrewSignalV2Converter.convert()'s `recipe` block mirrors the key
    names the importer's serializer reads back (serializer dialect) so v2
    round-trips losslessly. That dialect isn't byte-for-byte the official
    BeerJSON 1.0 schema, though — the schemas set `additionalProperties:
    false`, so a few serializer-dialect keys make the doc schema-invalid:
    fermentation steps use `step_temperature`/`step_type` (BeerJSON wants
    `start_temperature`; has no `step_type`), and hops carry non-standard
    `is_extract`/`amount_ml`. This is the GET /export/beerjson post-processing
    step that fixes those up for interchange with vanilla BeerJSON tools.
    It never mutates `recipe_block` — /export/brewsignal must keep emitting
    the unmodified serializer-dialect doc.

    Schema-required fields with no BrewSignal-side source data get
    documented placeholders rather than failing the export. Placeholder
    values are deliberately obvious fakes (0, 'Unknown', 'other') so a
    consumer can't mistake them for real measurements:
    - recipe `author` missing -> "Unknown"
    - recipe `batch_size` missing -> {"value": 0, "unit": "l"}
    - recipe `efficiency` missing -> {"brewhouse": {"value": 0, "unit": "%"}}
    - `ingredients.fermentable_additions` missing (schema requires the key
      even for an ingredient-less recipe) -> []
    - hop `alpha_acid` missing (extract hops don't have one) ->
      {"value": 0, "unit": "%"}
    - culture `amount` missing -> {"value": 1, "unit": "1"} (UnitType)
    - culture `type`/`form` missing -> "other" / "dry" (CultureBase enums)
    - fermentable `yield` missing (BrewSignal doesn't track it for every
      grain, e.g. imports that omitted it) -> {"fine_grind": {"value": 0,
      "unit": "%"}}
    - fermentable `color` missing -> {"value": 0, "unit": "SRM"}
    - mash `grain_temperature` missing (not a BrewSignal field at all) ->
      {"value": 20, "unit": "C"} (room temperature)
    Serializer-dialect `_extensions` keys (recipe level and per item) are
    stripped — they're the round-trip side channel for foreign-format
    extras and never schema-valid under additionalProperties: false.
    A `style` block that's missing any of BeerJSON's required
    name/category/style_guide/type is dropped rather than padded with
    placeholders — style is optional at the recipe level, and BrewSignal
    only carries the style *name* today (category/style_guide/type would
    have to be fabricated, unlike the numeric placeholders above).
    """
    recipe = copy.deepcopy(recipe_block)
    recipe.pop('_extensions', None)

    if not recipe.get('author'):
        recipe['author'] = 'Unknown'
    if 'batch_size' not in recipe:
        recipe['batch_size'] = {'value': 0, 'unit': 'l'}
    if 'efficiency' not in recipe:
        recipe['efficiency'] = {'brewhouse': {'value': 0, 'unit': '%'}}

    style = recipe.get('style')
    if isinstance(style, dict) and not {'category', 'style_guide', 'type'} <= style.keys():
        recipe.pop('style', None)

    fermentation = recipe.get('fermentation')
    if isinstance(fermentation, dict):
        steps = fermentation.get('fermentation_steps')
        if isinstance(steps, list):
            for step in steps:
                if not isinstance(step, dict):
                    continue
                step.pop('step_type', None)
                step.pop('_extensions', None)
                if 'step_temperature' in step:
                    step['start_temperature'] = step.pop('step_temperature')

    mash = recipe.get('mash')
    if isinstance(mash, dict):
        if 'grain_temperature' not in mash:
            mash['grain_temperature'] = {'value': 20, 'unit': 'C'}
        mash_steps = mash.get('mash_steps')
        if isinstance(mash_steps, list):
            for step in mash_steps:
                if isinstance(step, dict):
                    step.pop('_extensions', None)

    ingredients = recipe.setdefault('ingredients', {})
    if isinstance(ingredients, dict):
        if 'fermentable_additions' not in ingredients:
            ingredients['fermentable_additions'] = []
        fermentables = ingredients.get('fermentable_additions')
        if isinstance(fermentables, list):
            for ferm in fermentables:
                if not isinstance(ferm, dict):
                    continue
                ferm.pop('_extensions', None)
                if 'yield' not in ferm:
                    ferm['yield'] = {'fine_grind': {'value': 0, 'unit': '%'}}
                if 'color' not in ferm:
                    ferm['color'] = {'value': 0, 'unit': 'SRM'}
        hops = ingredients.get('hop_additions')
        if isinstance(hops, list):
            for hop in hops:
                if not isinstance(hop, dict):
                    continue
                hop.pop('is_extract', None)
                hop.pop('amount_ml', None)
                hop.pop('_extensions', None)
                if 'alpha_acid' not in hop:
                    hop['alpha_acid'] = {'value': 0, 'unit': '%'}
        cultures = ingredients.get('culture_additions')
        if isinstance(cultures, list):
            for culture in cultures:
                if not isinstance(culture, dict):
                    continue
                culture.pop('_extensions', None)
                if 'amount' not in culture:
                    culture['amount'] = {'value': 1, 'unit': '1'}
                if not culture.get('type'):
                    culture['type'] = 'other'
                if not culture.get('form'):
                    culture['form'] = 'dry'
        miscs = ingredients.get('miscellaneous_additions')
        if isinstance(miscs, list):
            for misc in miscs:
                if isinstance(misc, dict):
                    misc.pop('_extensions', None)

    if notes:
        recipe['notes'] = notes

    return recipe
