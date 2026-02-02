"""Serialize BeerJSON dict to SQLAlchemy models.

This module converts validated BeerJSON dictionaries to database models,
extracting values from BeerJSON unit objects and mapping to the appropriate
database columns.
"""
from typing import Dict, Any, Optional, List
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import (
    Recipe, RecipeFermentable, RecipeHop, RecipeCulture, RecipeMisc,
    RecipeMashStep, RecipeFermentationStep, RecipeWaterProfile, RecipeWaterAdjustment
)


class RecipeSerializer:
    """Convert validated BeerJSON dict to SQLAlchemy Recipe model."""

    async def serialize(self, beerjson_recipe: Dict[str, Any], session: AsyncSession) -> Recipe:
        """Convert BeerJSON recipe dict to Recipe model with all relationships.

        Args:
            beerjson_recipe: Validated BeerJSON recipe dict (single recipe, not full document)
            session: Async SQLAlchemy session for database operations

        Returns:
            Recipe model instance with all relationships populated (not yet committed)
        """
        # Create Recipe instance
        recipe = Recipe(
            name=beerjson_recipe['name'],
            type=beerjson_recipe.get('type'),
            author=beerjson_recipe.get('author'),
            notes=beerjson_recipe.get('notes'),
            beerjson_version='1.0'
        )

        # Extract values from BeerJSON unit objects
        self._extract_recipe_vitals(recipe, beerjson_recipe)
        self._extract_boil_info(recipe, beerjson_recipe)
        self._extract_efficiency(recipe, beerjson_recipe)
        self._extract_carbonation(recipe, beerjson_recipe)

        # Process ingredients
        if 'ingredients' in beerjson_recipe:
            self._serialize_ingredients(recipe, beerjson_recipe['ingredients'])

        # Process mash steps
        if 'mash' in beerjson_recipe:
            self._serialize_mash(recipe, beerjson_recipe['mash'])

        # Process fermentation steps
        if 'fermentation' in beerjson_recipe:
            self._serialize_fermentation(recipe, beerjson_recipe['fermentation'])

        # Process water chemistry
        if 'waters' in beerjson_recipe:
            self._serialize_water(recipe, beerjson_recipe['waters'])

        # Store format extensions if present
        if '_extensions' in beerjson_recipe:
            recipe.format_extensions = beerjson_recipe['_extensions']

        # Process Brewfather water profiles (not in BeerJSON spec)
        if '_brewfather_water' in beerjson_recipe:
            self._serialize_brewfather_water(recipe, beerjson_recipe['_brewfather_water'])

        return recipe

    def _extract_recipe_vitals(self, recipe: Recipe, beerjson_recipe: Dict[str, Any]) -> None:
        """Extract gravity, ABV, IBU, color from BeerJSON unit objects."""
        # Batch size
        if 'batch_size' in beerjson_recipe:
            recipe.batch_size_liters = self._extract_volume(beerjson_recipe['batch_size'])

        # Original gravity
        if 'original_gravity' in beerjson_recipe:
            recipe.og = self._extract_gravity(beerjson_recipe['original_gravity'])

        # Final gravity
        if 'final_gravity' in beerjson_recipe:
            recipe.fg = self._extract_gravity(beerjson_recipe['final_gravity'])

        # ABV (stored as decimal 0-1)
        if 'alcohol_by_volume' in beerjson_recipe:
            recipe.abv = self._extract_percent(beerjson_recipe['alcohol_by_volume'])

        # IBU
        if 'ibu_estimate' in beerjson_recipe:
            recipe.ibu = self._extract_dimensionless(beerjson_recipe['ibu_estimate'])

        # Color (SRM)
        if 'color_estimate' in beerjson_recipe:
            recipe.color_srm = self._extract_color(beerjson_recipe['color_estimate'])

    def _extract_boil_info(self, recipe: Recipe, beerjson_recipe: Dict[str, Any]) -> None:
        """Extract boil time and size from BeerJSON."""
        if 'boil' in beerjson_recipe:
            boil = beerjson_recipe['boil']
            if 'boil_time' in boil:
                recipe.boil_time_minutes = int(self._extract_time_minutes(boil['boil_time']))
            if 'boil_size' in boil:
                recipe.boil_size_l = self._extract_volume(boil['boil_size'])

    def _extract_efficiency(self, recipe: Recipe, beerjson_recipe: Dict[str, Any]) -> None:
        """Extract brewhouse efficiency from BeerJSON."""
        if 'efficiency' in beerjson_recipe:
            efficiency = beerjson_recipe['efficiency']
            if 'brewhouse' in efficiency:
                # Convert from 0-1 to 0-100
                eff_value = self._extract_percent(efficiency['brewhouse'])
                recipe.efficiency_percent = eff_value * 100 if eff_value < 1 else eff_value

    def _extract_carbonation(self, recipe: Recipe, beerjson_recipe: Dict[str, Any]) -> None:
        """Extract carbonation level (may be raw number or unit object)."""
        if 'carbonation' in beerjson_recipe:
            carb = beerjson_recipe['carbonation']
            if isinstance(carb, dict):
                recipe.carbonation_vols = carb.get('value')
            else:
                # Raw number (volumes CO2)
                recipe.carbonation_vols = float(carb) if carb is not None else None

    def _serialize_ingredients(self, recipe: Recipe, ingredients: Dict[str, Any]) -> None:
        """Serialize all ingredient types."""
        # Fermentables
        if 'fermentable_additions' in ingredients:
            for ferm_dict in ingredients['fermentable_additions']:
                ferm = self._create_fermentable(ferm_dict)
                recipe.fermentables.append(ferm)

        # Hops
        if 'hop_additions' in ingredients:
            for hop_dict in ingredients['hop_additions']:
                hop = self._create_hop(hop_dict)
                recipe.hops.append(hop)

        # Cultures (yeast)
        if 'culture_additions' in ingredients:
            for idx, culture_dict in enumerate(ingredients['culture_additions']):
                culture = self._create_culture(culture_dict)
                recipe.cultures.append(culture)

                # Extract first culture to populate Recipe's top-level yeast fields
                # (for backward compatibility with BeerXML imports)
                if idx == 0:
                    recipe.yeast_name = culture_dict.get('name')
                    recipe.yeast_lab = culture_dict.get('producer')
                    recipe.yeast_product_id = culture_dict.get('product_id')

                    # Extract temperature range
                    if 'temperature_range' in culture_dict:
                        temp_range = culture_dict['temperature_range']
                        if 'minimum' in temp_range:
                            recipe.yeast_temp_min = self._extract_temperature(temp_range['minimum'])
                        if 'maximum' in temp_range:
                            recipe.yeast_temp_max = self._extract_temperature(temp_range['maximum'])

                    # Extract attenuation (use minimum if range, or single value)
                    atten = culture_dict.get('attenuation') or culture_dict.get('attenuation_range')
                    if atten:
                        if 'minimum' in atten:
                            recipe.yeast_attenuation = self._extract_percent(atten['minimum'])
                        elif 'maximum' in atten:
                            # Fallback to maximum if no minimum
                            recipe.yeast_attenuation = self._extract_percent(atten['maximum'])

        # Miscellaneous
        if 'miscellaneous_additions' in ingredients:
            for misc_dict in ingredients['miscellaneous_additions']:
                misc = self._create_misc(misc_dict)
                recipe.miscs.append(misc)

    def _create_fermentable(self, ferm_dict: Dict[str, Any]) -> RecipeFermentable:
        """Create RecipeFermentable from BeerJSON fermentable_addition."""
        ferm = RecipeFermentable(
            name=ferm_dict['name'],
            type=ferm_dict.get('type'),
            grain_group=ferm_dict.get('grain_group'),
            origin=ferm_dict.get('origin'),
            supplier=ferm_dict.get('producer')
        )

        # Amount (kg)
        if 'amount' in ferm_dict:
            ferm.amount_kg = self._extract_mass_kg(ferm_dict['amount'])

        # Color (SRM)
        if 'color' in ferm_dict:
            ferm.color_srm = self._extract_color(ferm_dict['color'])

        # Yield (percent)
        if 'yield' in ferm_dict and 'fine_grind' in ferm_dict['yield']:
            # Convert from 0-1 to 0-100
            yield_val = self._extract_percent(ferm_dict['yield']['fine_grind'])
            ferm.yield_percent = yield_val * 100 if yield_val < 1 else yield_val

        # Timing
        if 'timing' in ferm_dict:
            ferm.timing = ferm_dict['timing']

        # Format extensions
        if '_extensions' in ferm_dict:
            ferm.format_extensions = ferm_dict['_extensions']

        return ferm

    def _create_hop(self, hop_dict: Dict[str, Any]) -> RecipeHop:
        """Create RecipeHop from BeerJSON hop_addition."""
        hop = RecipeHop(
            name=hop_dict['name'],
            origin=hop_dict.get('origin'),
            form=hop_dict.get('form')
        )

        # Alpha acid (convert from 0-1 to 0-100)
        if 'alpha_acid' in hop_dict:
            alpha_val = self._extract_percent(hop_dict['alpha_acid'])
            hop.alpha_acid_percent = alpha_val * 100 if alpha_val < 1 else alpha_val

        # Beta acid (convert from 0-1 to 0-100)
        if 'beta_acid' in hop_dict:
            beta_val = self._extract_percent(hop_dict['beta_acid'])
            hop.beta_acid_percent = beta_val * 100 if beta_val < 1 else beta_val

        # Amount (grams)
        if 'amount' in hop_dict:
            hop.amount_grams = self._extract_mass_g(hop_dict['amount'])

        # Timing (store as JSON)
        if 'timing' in hop_dict:
            hop.timing = hop_dict['timing']

        # Format extensions
        if '_extensions' in hop_dict:
            hop.format_extensions = hop_dict['_extensions']

        return hop

    def _create_culture(self, culture_dict: Dict[str, Any]) -> RecipeCulture:
        """Create RecipeCulture from BeerJSON culture_addition."""
        culture = RecipeCulture(
            name=culture_dict['name'],
            type=culture_dict.get('type'),
            form=culture_dict.get('form'),
            producer=culture_dict.get('producer'),
            product_id=culture_dict.get('product_id')
        )

        # Temperature range
        if 'temperature_range' in culture_dict:
            temp_range = culture_dict['temperature_range']
            if 'minimum' in temp_range:
                culture.temp_min_c = self._extract_temperature(temp_range['minimum'])
            if 'maximum' in temp_range:
                culture.temp_max_c = self._extract_temperature(temp_range['maximum'])

        # Attenuation (can be 'attenuation' or 'attenuation_range')
        atten = culture_dict.get('attenuation') or culture_dict.get('attenuation_range')
        if atten:
            if 'minimum' in atten:
                atten_min = self._extract_percent(atten['minimum'])
                culture.attenuation_min_percent = atten_min * 100 if atten_min < 1 else atten_min
            if 'maximum' in atten:
                atten_max = self._extract_percent(atten['maximum'])
                culture.attenuation_max_percent = atten_max * 100 if atten_max < 1 else atten_max

        # Amount with unit
        if 'amount' in culture_dict:
            amount = culture_dict['amount']
            if isinstance(amount, dict):
                culture.amount = amount.get('value')
                culture.amount_unit = amount.get('unit')

        # Timing
        if 'timing' in culture_dict:
            culture.timing = culture_dict['timing']

        # Format extensions
        if '_extensions' in culture_dict:
            culture.format_extensions = culture_dict['_extensions']

        return culture

    def _create_misc(self, misc_dict: Dict[str, Any]) -> RecipeMisc:
        """Create RecipeMisc from BeerJSON miscellaneous_addition."""
        misc = RecipeMisc(
            name=misc_dict['name'],
            type=misc_dict.get('type', 'other'),
            use=misc_dict.get('use', 'boil'),  # Legacy field
            use_for=misc_dict.get('use_for'),
            notes=misc_dict.get('notes')
        )

        # Amount with unit
        if 'amount' in misc_dict:
            amount = misc_dict['amount']
            if isinstance(amount, dict):
                misc.amount_kg = amount.get('value')
                misc.amount_unit = amount.get('unit')

        # Timing
        if 'timing' in misc_dict:
            misc.timing = misc_dict['timing']
            # Also set legacy use field from timing
            if 'use' in misc_dict['timing']:
                misc.use = self._map_timing_use_to_legacy(misc_dict['timing']['use'])

        # Format extensions
        if '_extensions' in misc_dict:
            misc.format_extensions = misc_dict['_extensions']

        return misc

    def _serialize_mash(self, recipe: Recipe, mash: Dict[str, Any]) -> None:
        """Serialize mash steps from BeerJSON mash object."""
        if 'mash_steps' not in mash:
            return

        for idx, step_dict in enumerate(mash['mash_steps'], start=1):
            step = RecipeMashStep(
                step_number=idx,
                name=step_dict['name'],
                type=step_dict.get('type', 'temperature')
            )

            # Temperature
            if 'step_temperature' in step_dict:
                step.temp_c = self._extract_temperature(step_dict['step_temperature'])

            # Time
            if 'step_time' in step_dict:
                step.time_minutes = int(self._extract_time_minutes(step_dict['step_time']))

            # Infusion
            if 'infusion_amount' in step_dict:
                step.infusion_amount_liters = self._extract_volume(step_dict['infusion_amount'])
            if 'infusion_temperature' in step_dict:
                step.infusion_temp_c = self._extract_temperature(step_dict['infusion_temperature'])

            # Ramp time
            if 'ramp_time' in step_dict:
                step.ramp_time_minutes = int(self._extract_time_minutes(step_dict['ramp_time']))

            # Format extensions
            if '_extensions' in step_dict:
                step.format_extensions = step_dict['_extensions']

            recipe.mash_steps.append(step)

    def _serialize_fermentation(self, recipe: Recipe, fermentation: Dict[str, Any]) -> None:
        """Serialize fermentation steps from BeerJSON fermentation object."""
        if 'fermentation_steps' not in fermentation:
            return

        for idx, step_dict in enumerate(fermentation['fermentation_steps'], start=1):
            step = RecipeFermentationStep(
                step_number=idx,
                type=self._infer_fermentation_type(step_dict)
            )

            # Temperature (can be step_temperature, start_temperature, or end_temperature)
            if 'step_temperature' in step_dict:
                step.temp_c = self._extract_temperature(step_dict['step_temperature'])
            elif 'start_temperature' in step_dict:
                step.temp_c = self._extract_temperature(step_dict['start_temperature'])
            elif 'end_temperature' in step_dict:
                step.temp_c = self._extract_temperature(step_dict['end_temperature'])

            # Time (convert to days)
            if 'step_time' in step_dict:
                time_val = step_dict['step_time']
                if isinstance(time_val, dict):
                    unit = time_val.get('unit', 'day')
                    value = time_val.get('value', 0)
                    if unit == 'day':
                        step.time_days = int(value)
                    elif unit == 'hour':
                        step.time_days = int(value / 24)
                    elif unit == 'min':
                        step.time_days = int(value / 1440)
                    else:
                        step.time_days = int(value)  # Assume days
                else:
                    step.time_days = int(time_val)

            # Format extensions
            if '_extensions' in step_dict:
                step.format_extensions = step_dict['_extensions']

            recipe.fermentation_steps.append(step)

    def _serialize_water(self, recipe: Recipe, waters: Dict[str, Any]) -> None:
        """Serialize water profiles and adjustments from BeerJSON."""
        # Water profiles
        if 'water_profiles' in waters:
            for profile_dict in waters['water_profiles']:
                profile = RecipeWaterProfile(
                    profile_type=profile_dict.get('type', 'source'),
                    name=profile_dict.get('name')
                )

                # Ion concentrations
                if 'calcium' in profile_dict:
                    profile.calcium_ppm = profile_dict['calcium'].get('value')
                if 'magnesium' in profile_dict:
                    profile.magnesium_ppm = profile_dict['magnesium'].get('value')
                if 'sodium' in profile_dict:
                    profile.sodium_ppm = profile_dict['sodium'].get('value')
                if 'chloride' in profile_dict:
                    profile.chloride_ppm = profile_dict['chloride'].get('value')
                if 'sulfate' in profile_dict:
                    profile.sulfate_ppm = profile_dict['sulfate'].get('value')
                if 'bicarbonate' in profile_dict:
                    profile.bicarbonate_ppm = profile_dict['bicarbonate'].get('value')

                # Water characteristics
                if 'ph' in profile_dict:
                    profile.ph = profile_dict['ph'].get('value') if isinstance(profile_dict['ph'], dict) else profile_dict['ph']
                if 'alkalinity' in profile_dict:
                    profile.alkalinity = profile_dict['alkalinity'].get('value')

                if '_extensions' in profile_dict:
                    profile.format_extensions = profile_dict['_extensions']

                recipe.water_profiles.append(profile)

        # Water adjustments
        if 'water_adjustments' in waters:
            for adj_dict in waters['water_adjustments']:
                adjustment = RecipeWaterAdjustment(
                    stage=adj_dict.get('stage', 'mash')
                )

                # Volume
                if 'volume' in adj_dict:
                    adjustment.volume_liters = self._extract_volume(adj_dict['volume'])

                # Salt additions (extract from additions array)
                if 'additions' in adj_dict:
                    for addition in adj_dict['additions']:
                        name = addition.get('name', '').lower()
                        amount = addition.get('amount', {}).get('value', 0)

                        if 'gypsum' in name or 'calcium sulfate' in name:
                            adjustment.calcium_sulfate_g = amount
                        elif 'calcium chloride' in name:
                            adjustment.calcium_chloride_g = amount
                        elif 'epsom' in name or 'magnesium sulfate' in name:
                            adjustment.magnesium_sulfate_g = amount
                        elif 'baking soda' in name or 'sodium bicarbonate' in name:
                            adjustment.sodium_bicarbonate_g = amount
                        elif 'chalk' in name or 'calcium carbonate' in name:
                            adjustment.calcium_carbonate_g = amount
                        elif 'slaked lime' in name or 'calcium hydroxide' in name:
                            adjustment.calcium_hydroxide_g = amount
                        elif 'magnesium chloride' in name:
                            adjustment.magnesium_chloride_g = amount
                        elif 'table salt' in name or 'sodium chloride' in name:
                            adjustment.sodium_chloride_g = amount
                        elif 'acid' in name:
                            adjustment.acid_type = name.split()[0]  # e.g., "lactic acid" -> "lactic"
                            adjustment.acid_ml = amount

                if '_extensions' in adj_dict:
                    adjustment.format_extensions = adj_dict['_extensions']

                recipe.water_adjustments.append(adjustment)

    # Unit extraction helpers

    def _extract_volume(self, unit_obj: Optional[Dict[str, Any]]) -> Optional[float]:
        """Extract volume value (liters) from BeerJSON unit object."""
        if unit_obj is None or not isinstance(unit_obj, dict):
            return None
        return unit_obj.get('value')

    def _extract_mass_kg(self, unit_obj: Optional[Dict[str, Any]]) -> Optional[float]:
        """Extract mass value (kg) from BeerJSON unit object."""
        if unit_obj is None or not isinstance(unit_obj, dict):
            return None
        return unit_obj.get('value')

    def _extract_mass_g(self, unit_obj: Optional[Dict[str, Any]]) -> Optional[float]:
        """Extract mass value (grams) from BeerJSON unit object."""
        if unit_obj is None or not isinstance(unit_obj, dict):
            return None
        return unit_obj.get('value')

    def _extract_temperature(self, unit_obj: Optional[Dict[str, Any]]) -> Optional[float]:
        """Extract temperature value (Celsius) from BeerJSON unit object."""
        if unit_obj is None or not isinstance(unit_obj, dict):
            return None
        return unit_obj.get('value')

    def _extract_time_minutes(self, unit_obj: Optional[Dict[str, Any]]) -> Optional[float]:
        """Extract time value (minutes) from BeerJSON unit object."""
        if unit_obj is None or not isinstance(unit_obj, dict):
            return None
        return unit_obj.get('value')

    def _extract_gravity(self, unit_obj: Optional[Dict[str, Any]]) -> Optional[float]:
        """Extract gravity value (SG) from BeerJSON unit object.

        Round to 3 decimal places for consistency with brewing conventions
        and frontend input constraints (step="0.001").
        """
        if unit_obj is None or not isinstance(unit_obj, dict):
            return None

        value = unit_obj.get('value')
        if value is None:
            return None

        # Round to 3 decimal places (e.g., 1.050)
        return round(value, 3)

    def _extract_percent(self, unit_obj: Optional[Dict[str, Any]]) -> Optional[float]:
        """Extract percent value from BeerJSON unit object.

        BeerJSON stores percentages as decimal fractions (0-1 range).
        Convert to percentage format (0-100 range) for our database.

        Example: BeerJSON {"value": 0.042, "unit": "%"} -> 4.2
        """
        if unit_obj is None or not isinstance(unit_obj, dict):
            return None

        value = unit_obj.get('value')
        if value is None:
            return None

        # BeerJSON percentages are stored as decimals (0-1 range)
        # Convert to percentage (0-100 range)
        if value < 1.0:
            return value * 100

        # Already in percentage format
        return value

    def _extract_dimensionless(self, unit_obj: Optional[Dict[str, Any]]) -> Optional[float]:
        """Extract dimensionless value from BeerJSON unit object."""
        if unit_obj is None or not isinstance(unit_obj, dict):
            return None
        return unit_obj.get('value')

    def _extract_color(self, unit_obj: Optional[Dict[str, Any]]) -> Optional[float]:
        """Extract color value (SRM) from BeerJSON unit object."""
        if unit_obj is None or not isinstance(unit_obj, dict):
            return None
        return unit_obj.get('value')

    # Helper methods

    def _map_timing_use_to_legacy(self, use: str) -> str:
        """Map BeerJSON timing use to legacy BeerXML use field."""
        mapping = {
            'add_to_mash': 'mash',
            'add_to_boil': 'boil',
            'add_to_sparge': 'sparge',
            'add_to_fermentation': 'primary',
            'add_to_package': 'bottling'
        }
        return mapping.get(use, 'boil')

    def _infer_fermentation_type(self, step_dict: Dict[str, Any]) -> str:
        """Infer fermentation step type from step name or properties."""
        name = step_dict.get('name', '').lower()

        if 'primary' in name:
            return 'primary'
        elif 'secondary' in name:
            return 'secondary'
        elif 'conditioning' in name or 'bottle' in name or 'keg' in name:
            return 'conditioning'
        else:
            # Default to primary
            return 'primary'

    def _serialize_brewfather_water(self, recipe: Recipe, water_data: Dict[str, Any]) -> None:
        """Serialize water profiles and adjustments from Brewfather's water object.

        Brewfather stores water chemistry data in a format not covered by BeerJSON 1.0.
        This method extracts source, target, mash, and sparge water profiles,
        as well as mash and sparge water adjustments (salts and acids).

        Args:
            recipe: Recipe model to add water profiles and adjustments to
            water_data: Brewfather water object with source, target, mash, sparge,
                        mashAdjustments, and spargeAdjustments keys
        """
        # Extract water profiles
        profile_types = ['source', 'target', 'mash', 'sparge']

        for profile_type in profile_types:
            if profile_type not in water_data:
                continue

            profile_dict = water_data[profile_type]
            if not profile_dict:
                continue

            profile = RecipeWaterProfile(
                profile_type=profile_type,
                name=profile_dict.get('name')
            )

            # Extract ion concentrations - Brewfather stores them as raw numbers or strings
            profile.calcium_ppm = self._extract_numeric(profile_dict.get('calcium'))
            profile.magnesium_ppm = self._extract_numeric(profile_dict.get('magnesium'))
            profile.sodium_ppm = self._extract_numeric(profile_dict.get('sodium'))
            profile.chloride_ppm = self._extract_numeric(profile_dict.get('chloride'))
            profile.sulfate_ppm = self._extract_numeric(profile_dict.get('sulfate'))
            profile.bicarbonate_ppm = self._extract_numeric(profile_dict.get('bicarbonate'))

            # Extract pH (can be string or number in Brewfather)
            profile.ph = self._extract_numeric(profile_dict.get('ph'))

            # Extract alkalinity if present
            profile.alkalinity = self._extract_numeric(profile_dict.get('alkalinity'))

            recipe.water_profiles.append(profile)

        # Extract water adjustments (mash and sparge)
        adjustment_stages = [
            ('mashAdjustments', 'mash'),
            ('spargeAdjustments', 'sparge'),
        ]

        for bf_key, stage in adjustment_stages:
            if bf_key not in water_data:
                continue

            adj_dict = water_data[bf_key]
            if not adj_dict:
                continue

            adjustment = RecipeWaterAdjustment(stage=stage)

            # Volume
            adjustment.volume_liters = self._extract_numeric(adj_dict.get('volume'))

            # Salt additions - map Brewfather keys to database columns
            adjustment.calcium_sulfate_g = self._extract_numeric(adj_dict.get('calciumSulfate'))
            adjustment.calcium_chloride_g = self._extract_numeric(adj_dict.get('calciumChloride'))
            adjustment.magnesium_sulfate_g = self._extract_numeric(adj_dict.get('magnesiumSulfate'))
            adjustment.sodium_bicarbonate_g = self._extract_numeric(adj_dict.get('sodiumBicarbonate'))
            adjustment.calcium_carbonate_g = self._extract_numeric(adj_dict.get('calciumCarbonate'))
            adjustment.calcium_hydroxide_g = self._extract_numeric(adj_dict.get('calciumHydroxide'))
            adjustment.magnesium_chloride_g = self._extract_numeric(adj_dict.get('magnesiumChloride'))
            adjustment.sodium_chloride_g = self._extract_numeric(adj_dict.get('sodiumChloride'))

            # Acid info from acids array (take first acid if present)
            acids = adj_dict.get('acids', [])
            if acids and len(acids) > 0:
                acid = acids[0]
                adjustment.acid_type = acid.get('type')
                adjustment.acid_ml = self._extract_numeric(acid.get('amount'))
                adjustment.acid_concentration_percent = self._extract_numeric(acid.get('concentration'))

            recipe.water_adjustments.append(adjustment)

    def _extract_numeric(self, value: Any) -> Optional[float]:
        """Extract numeric value from a field that may be string, int, or float.

        Brewfather stores some numeric values as strings (e.g., "9.98" instead of 9.98).

        Args:
            value: Value to extract (may be str, int, float, or None)

        Returns:
            Float value or None if not convertible
        """
        if value is None:
            return None

        if isinstance(value, (int, float)):
            return float(value)

        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                return None

        return None
