"""Convert internal Recipe model to Brewfather JSON format for export."""
from typing import Any, Optional

from backend.models import (
    Recipe,
    RecipeFermentable,
    RecipeHop,
    RecipeCulture,
    RecipeMisc,
    RecipeMashStep,
    RecipeFermentationStep,
)


class RecipeToBrewfatherConverter:
    """Convert internal Recipe model to Brewfather JSON format."""

    def convert(self, recipe: Recipe) -> dict[str, Any]:
        """Convert Recipe to Brewfather JSON dict.

        Args:
            recipe: SQLAlchemy Recipe model with relationships loaded

        Returns:
            Brewfather-compatible JSON dict
        """
        bf_recipe: dict[str, Any] = {
            "_type": "recipe",  # Required by Brewfather import
            "name": recipe.name or "",
            "type": self._map_recipe_type(recipe.type),
            "author": recipe.author or "",
            "notes": recipe.notes or "",
        }

        # Core vitals
        if recipe.batch_size_liters is not None:
            bf_recipe["batchSize"] = recipe.batch_size_liters
        if recipe.boil_time_minutes is not None:
            bf_recipe["boilTime"] = recipe.boil_time_minutes
        if recipe.efficiency_percent is not None:
            bf_recipe["efficiency"] = recipe.efficiency_percent

        # Equipment object required by Brewfather import
        bf_recipe["equipment"] = {
            "efficiency": recipe.efficiency_percent or 75,
            "boilTime": recipe.boil_time_minutes or 60,
            "batchSize": recipe.batch_size_liters or 20,
        }
        if recipe.og is not None:
            bf_recipe["og"] = recipe.og
        if recipe.fg is not None:
            bf_recipe["fg"] = recipe.fg
        if recipe.abv is not None:
            bf_recipe["abv"] = recipe.abv
        if recipe.ibu is not None:
            bf_recipe["ibu"] = recipe.ibu
        if recipe.color_srm is not None:
            bf_recipe["color"] = recipe.color_srm
        if recipe.carbonation_vols is not None:
            bf_recipe["carbonation"] = recipe.carbonation_vols

        # Style
        if recipe.style:
            bf_recipe["style"] = {
                "name": recipe.style.name or "",
                "category": recipe.style.category or "",
                "styleGuide": "BJCP 2021",
                "type": recipe.style.type or "Ale",
            }

        # Ingredients
        if recipe.fermentables:
            bf_recipe["fermentables"] = [
                self._convert_fermentable(f) for f in recipe.fermentables
            ]

        if recipe.hops:
            bf_recipe["hops"] = [self._convert_hop(h) for h in recipe.hops]

        if recipe.cultures:
            bf_recipe["yeasts"] = [
                self._convert_culture(c) for c in recipe.cultures
            ]
        elif recipe.yeast_name:
            # Fallback to legacy yeast fields
            bf_recipe["yeasts"] = [self._convert_legacy_yeast(recipe)]

        if recipe.miscs:
            bf_recipe["miscs"] = [self._convert_misc(m) for m in recipe.miscs]

        # Mash profile
        if recipe.mash_steps:
            bf_recipe["mash"] = self._convert_mash(recipe.mash_steps)

        # Fermentation profile
        if recipe.fermentation_steps:
            bf_recipe["fermentation"] = self._convert_fermentation(
                recipe.fermentation_steps
            )

        return bf_recipe

    def _convert_fermentable(self, ferm: RecipeFermentable) -> dict[str, Any]:
        """Convert fermentable to Brewfather format."""
        bf_ferm: dict[str, Any] = {
            "name": ferm.name or "",
            "type": self._map_fermentable_type(ferm.type),
            "amount": ferm.amount_kg or 0,
        }

        if ferm.color_srm is not None:
            bf_ferm["color"] = ferm.color_srm
        if ferm.origin:
            bf_ferm["origin"] = ferm.origin
        if ferm.supplier:
            bf_ferm["supplier"] = ferm.supplier
        if ferm.yield_percent is not None:
            bf_ferm["potentialPercentage"] = ferm.yield_percent
        if ferm.grain_group:
            bf_ferm["grainCategory"] = self._map_grain_category(ferm.grain_group)

        return bf_ferm

    def _convert_hop(self, hop: RecipeHop) -> dict[str, Any]:
        """Convert hop to Brewfather format."""
        bf_hop: dict[str, Any] = {
            "name": hop.name or "",
            "amount": hop.amount_grams or 0,
        }

        if hop.origin:
            bf_hop["origin"] = hop.origin
        # Brewfather uses 'type' for the hop form (Pellet, Leaf, etc.)
        bf_hop["type"] = self._map_hop_form(hop.form) if hop.form else "Pellet"
        if hop.alpha_acid_percent is not None:
            bf_hop["alpha"] = hop.alpha_acid_percent
        if hop.beta_acid_percent is not None:
            bf_hop["beta"] = hop.beta_acid_percent

        # Timing from JSON field - Brewfather uses 'use' for when (Boil, Dry Hop, etc.)
        use, time = self._extract_hop_timing(hop.timing)
        bf_hop["use"] = use
        if time is not None:
            bf_hop["time"] = time

        return bf_hop

    def _extract_hop_timing(
        self, timing: Optional[dict]
    ) -> tuple[str, Optional[float]]:
        """Extract use and time from BeerJSON timing object."""
        if not timing:
            return "Boil", 60

        use_mapping = {
            "add_to_boil": "Boil",
            "add_to_fermentation": "Dry Hop",
            "add_to_mash": "Mash",
            "add_to_package": "Bottling",
        }

        use = timing.get("use", "add_to_boil")
        bf_use = use_mapping.get(use, "Boil")

        # Duration
        duration = timing.get("duration")
        time_val = None
        if duration:
            if isinstance(duration, dict):
                time_val = duration.get("value")
            else:
                time_val = duration

        return bf_use, time_val

    def _convert_culture(self, culture: RecipeCulture) -> dict[str, Any]:
        """Convert culture/yeast to Brewfather format."""
        bf_yeast: dict[str, Any] = {
            "name": culture.name or "",
        }

        # Brewfather expects both type and form
        bf_yeast["type"] = self._map_yeast_type(culture.type) if culture.type else "Ale"
        bf_yeast["form"] = self._map_yeast_form(culture.form) if culture.form else "Dry"
        if culture.producer:
            bf_yeast["laboratory"] = culture.producer
        if culture.product_id:
            bf_yeast["productId"] = culture.product_id
        if culture.temp_min_c is not None:
            bf_yeast["minTemp"] = culture.temp_min_c
        if culture.temp_max_c is not None:
            bf_yeast["maxTemp"] = culture.temp_max_c

        # Attenuation (use min or average)
        if culture.attenuation_min_percent is not None:
            if culture.attenuation_max_percent is not None:
                bf_yeast["attenuation"] = (
                    culture.attenuation_min_percent + culture.attenuation_max_percent
                ) / 2
            else:
                bf_yeast["attenuation"] = culture.attenuation_min_percent

        if culture.amount is not None:
            bf_yeast["amount"] = culture.amount
            bf_yeast["unit"] = culture.amount_unit or "pkg"

        return bf_yeast

    def _convert_legacy_yeast(self, recipe: Recipe) -> dict[str, Any]:
        """Convert legacy Recipe yeast fields to Brewfather yeast."""
        bf_yeast: dict[str, Any] = {
            "name": recipe.yeast_name or "",
            "type": "Ale",  # Default, Brewfather requires this
            "form": "Dry",  # Default, Brewfather requires this
            "amount": 1,
            "unit": "pkg",
        }

        if recipe.yeast_lab:
            bf_yeast["laboratory"] = recipe.yeast_lab
        if recipe.yeast_product_id:
            bf_yeast["productId"] = recipe.yeast_product_id
        if recipe.yeast_temp_min is not None:
            bf_yeast["minTemp"] = recipe.yeast_temp_min
        if recipe.yeast_temp_max is not None:
            bf_yeast["maxTemp"] = recipe.yeast_temp_max
        if recipe.yeast_attenuation is not None:
            bf_yeast["attenuation"] = recipe.yeast_attenuation

        return bf_yeast

    def _convert_misc(self, misc: RecipeMisc) -> dict[str, Any]:
        """Convert misc ingredient to Brewfather format."""
        bf_misc: dict[str, Any] = {
            "name": misc.name or "",
            "type": self._map_misc_type(misc.type),
        }

        if misc.amount_kg is not None:
            # Convert kg to g for Brewfather
            if misc.amount_is_weight:
                bf_misc["amount"] = misc.amount_kg * 1000
                bf_misc["unit"] = "g"
            else:
                bf_misc["amount"] = misc.amount_kg
                bf_misc["unit"] = "ml"
        else:
            bf_misc["amount"] = 0
            bf_misc["unit"] = "g"

        # Use/timing
        use, time = self._extract_misc_timing(misc)
        bf_misc["use"] = use
        if time is not None:
            bf_misc["time"] = time

        return bf_misc

    def _extract_misc_timing(
        self, misc: RecipeMisc
    ) -> tuple[str, Optional[float]]:
        """Extract use and time from misc timing."""
        use_mapping = {
            "add_to_boil": "Boil",
            "add_to_mash": "Mash",
            "add_to_fermentation": "Primary",
            "add_to_package": "Bottling",
        }

        if misc.timing:
            timing = misc.timing
            use = timing.get("use", "add_to_boil")
            bf_use = use_mapping.get(use, "Boil")

            duration = timing.get("duration")
            time_val = None
            if duration:
                if isinstance(duration, dict):
                    time_val = duration.get("value")
                else:
                    time_val = duration

            return bf_use, time_val

        # Fallback to legacy use field
        bf_use = misc.use or "Boil"
        return bf_use, misc.time_min

    def _convert_mash(self, steps: list[RecipeMashStep]) -> dict[str, Any]:
        """Convert mash steps to Brewfather mash profile."""
        bf_mash: dict[str, Any] = {
            "name": "Mash",
            "grainTemp": 20,  # Default grain temp
            "steps": [],
        }

        for step in sorted(steps, key=lambda s: s.step_number or 0):
            bf_step: dict[str, Any] = {
                "name": step.name or f"Step {step.step_number}",
                "type": self._map_mash_step_type(step.type),
                "stepTemp": step.temp_c or 67,
                "stepTime": step.time_minutes or 60,
            }

            if step.ramp_time_minutes is not None:
                bf_step["rampTime"] = step.ramp_time_minutes

            bf_mash["steps"].append(bf_step)

        return bf_mash

    def _convert_fermentation(
        self, steps: list[RecipeFermentationStep]
    ) -> dict[str, Any]:
        """Convert fermentation steps to Brewfather fermentation profile."""
        bf_ferm: dict[str, Any] = {
            "name": "Fermentation",
            "steps": [],
        }

        for step in sorted(steps, key=lambda s: s.step_number or 0):
            bf_step: dict[str, Any] = {
                "type": step.type or "primary",
                "stepTemp": step.temp_c or 18,
                "stepTime": step.time_days or 14,
            }
            bf_ferm["steps"].append(bf_step)

        return bf_ferm

    # Type mappers (reverse of import)
    def _map_recipe_type(self, internal_type: Optional[str]) -> str:
        """Map internal recipe type to Brewfather."""
        if not internal_type:
            return "All Grain"
        mapping = {
            "all grain": "All Grain",
            "partial mash": "Partial Mash",
            "extract": "Extract",
        }
        return mapping.get(internal_type.lower(), "All Grain")

    def _map_fermentable_type(self, internal_type: Optional[str]) -> str:
        """Map internal fermentable type to Brewfather."""
        if not internal_type:
            return "Grain"
        mapping = {
            "grain": "Grain",
            "extract": "Extract",
            "sugar": "Sugar",
            "dry extract": "Dry Extract",
            "adjunct": "Adjunct",
        }
        return mapping.get(internal_type.lower(), "Grain")

    def _map_grain_category(self, grain_group: Optional[str]) -> str:
        """Map internal grain group to Brewfather grain category."""
        if not grain_group:
            return "Base"
        mapping = {
            "base": "Base",
            "caramel": "Crystal/Caramel",
            "flaked": "Flaked",
            "roasted": "Roasted",
            "specialty": "Specialty",
            "smoked": "Smoked",
            "adjunct": "Adjunct",
        }
        return mapping.get(grain_group.lower(), "Base")

    def _map_hop_form(self, form: Optional[str]) -> str:
        """Map internal hop form to Brewfather."""
        if not form:
            return "Pellet"
        mapping = {
            "pellet": "Pellet",
            "plug": "Plug",
            "leaf": "Leaf",
            "extract": "Extract",
        }
        return mapping.get(form.lower(), "Pellet")

    def _map_yeast_type(self, internal_type: Optional[str]) -> str:
        """Map internal yeast type to Brewfather."""
        if not internal_type:
            return "Ale"
        mapping = {
            "ale": "Ale",
            "lager": "Lager",
            "wheat": "Wheat",
            "wine": "Wine",
        }
        return mapping.get(internal_type.lower(), "Ale")

    def _map_yeast_form(self, form: Optional[str]) -> str:
        """Map internal yeast form to Brewfather."""
        if not form:
            return "Dry"
        mapping = {
            "liquid": "Liquid",
            "dry": "Dry",
            "slant": "Slant",
            "culture": "Culture",
        }
        return mapping.get(form.lower(), "Dry")

    def _map_misc_type(self, internal_type: Optional[str]) -> str:
        """Map internal misc type to Brewfather."""
        if not internal_type:
            return "Other"
        mapping = {
            "spice": "Spice",
            "fining": "Fining",
            "herb": "Herb",
            "flavor": "Flavor",
            "water agent": "Water Agent",
            "other": "Other",
        }
        return mapping.get(internal_type.lower(), "Other")

    def _map_mash_step_type(self, step_type: Optional[str]) -> str:
        """Map internal mash step type to Brewfather."""
        if not step_type:
            return "Temperature"
        mapping = {
            "temperature": "Temperature",
            "infusion": "Infusion",
            "decoction": "Decoction",
        }
        return mapping.get(step_type.lower(), "Temperature")
