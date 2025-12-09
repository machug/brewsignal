"""BrewSignal Recipe Format v1.0 - Validation and Conversion Utilities.

This module provides Pydantic models for BrewSignal format validation and
converters for bidirectional BeerJSON <-> BrewSignal conversion.

Simplifications (based on review feedback):
- Use Pydantic for validation (no custom validator class)
- Single file implementation (~230 lines)
- No round-trip preservation (database is source of truth)
- No business logic warnings (schema validation only)
- Reject non-Celsius temperatures (don't auto-convert)
- Multi-yeast: take first culture only
"""
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field, field_validator


# ==============================================================================
# Pydantic Models (Validation)
# ==============================================================================

class BrewSignalTiming(BaseModel):
    """Timing object for hops and misc additions."""
    use: str  # add_to_boil, add_to_fermentation, etc.
    duration: Optional[Dict[str, Any]] = None  # {value: 60, unit: "min"}
    continuous: Optional[bool] = None


class BrewSignalFermentable(BaseModel):
    """Fermentable ingredient."""
    name: str
    type: Optional[str] = None  # grain, extract, sugar, adjunct
    grain_group: Optional[str] = None  # base, caramel, roasted, specialty
    amount_kg: float = Field(gt=0)
    percentage: Optional[float] = Field(None, ge=0, le=100)
    yield_percent: Optional[float] = Field(None, ge=0, le=100)
    color_srm: Optional[float] = Field(None, ge=0)
    origin: Optional[str] = None
    supplier: Optional[str] = None


class BrewSignalHop(BaseModel):
    """Hop addition."""
    name: str
    origin: Optional[str] = None
    form: Optional[str] = None  # pellet, leaf, plug, extract
    amount_grams: float = Field(gt=0)
    alpha_acid_percent: Optional[float] = Field(None, ge=0, le=25)
    beta_acid_percent: Optional[float] = Field(None, ge=0, le=25)
    timing: BrewSignalTiming


class BrewSignalYeast(BaseModel):
    """Yeast culture (single yeast only in v1.0)."""
    name: str
    producer: Optional[str] = None
    product_id: Optional[str] = None
    type: Optional[str] = None  # ale, lager, wine, etc.
    form: Optional[str] = None  # dry, liquid, slant, culture
    attenuation_percent: Optional[float] = Field(None, ge=0, le=100)
    temp_min_c: Optional[float] = None  # Celsius only
    temp_max_c: Optional[float] = None  # Celsius only
    amount_grams: Optional[float] = Field(None, gt=0)


class BrewSignalMisc(BaseModel):
    """Miscellaneous addition."""
    name: str
    type: Optional[str] = None  # spice, fining, herb, flavor, water agent
    amount_grams: Optional[float] = Field(None, gt=0)
    timing: BrewSignalTiming


class BrewSignalMashStep(BaseModel):
    """Mash step."""
    step_number: int = Field(ge=1)
    type: str  # infusion, temperature, decoction
    temp_c: float  # Celsius only
    time_minutes: int = Field(ge=0)


class BrewSignalFermentationStep(BaseModel):
    """Fermentation step."""
    step_number: int = Field(ge=1)
    type: str  # primary, secondary, conditioning, cold_crash, diacetyl_rest
    temp_c: float  # Celsius only
    time_days: int = Field(ge=0)


class BrewSignalRecipe(BaseModel):
    """BrewSignal Recipe Format v1.0

    Simplified format for fermentation monitoring.
    All temperatures in Celsius. All measurements as raw numbers.
    """
    # Core fields
    name: str = Field(min_length=1, max_length=200)
    author: Optional[str] = Field(None, max_length=100)
    type: Optional[str] = None  # All Grain, Extract, Partial Mash
    style_id: Optional[str] = None

    # Gravity & alcohol
    og: float = Field(ge=1.0, le=1.2)
    fg: float = Field(ge=1.0, le=1.2)
    abv: Optional[float] = Field(None, ge=0, le=20)
    ibu: Optional[float] = Field(None, ge=0, le=200)
    color_srm: Optional[float] = Field(None, ge=0, le=100)

    # Batch parameters
    batch_size_liters: Optional[float] = Field(None, gt=0, le=1000)
    boil_time_minutes: Optional[int] = Field(None, ge=0, le=300)
    efficiency_percent: Optional[float] = Field(None, ge=0, le=100)
    carbonation_vols: Optional[float] = Field(None, ge=0, le=5)

    # Ingredients
    fermentables: Optional[List[BrewSignalFermentable]] = None
    hops: Optional[List[BrewSignalHop]] = None
    yeast: Optional[BrewSignalYeast] = None
    miscs: Optional[List[BrewSignalMisc]] = None

    # Process
    mash_steps: Optional[List[BrewSignalMashStep]] = None
    fermentation_steps: Optional[List[BrewSignalFermentationStep]] = None

    # Extensions (free-form dict)
    brewsignal_extensions: Optional[Dict[str, Any]] = None

    # Metadata
    notes: Optional[str] = None
    created_at: Optional[str] = None  # ISO 8601

    @field_validator('fg')
    @classmethod
    def fg_less_than_og(cls, v, info):
        """Ensure FG < OG"""
        if 'og' in info.data and v >= info.data['og']:
            raise ValueError('FG must be less than OG')
        return v

    model_config = {
        "extra": "forbid",  # Don't allow unknown fields
        "json_schema_extra": {
            "example": {
                "name": "West Coast IPA",
                "og": 1.065,
                "fg": 1.012,
                "abv": 6.9,
                "batch_size_liters": 19.0
            }
        }
    }


# ==============================================================================
# BeerJSON → BrewSignal Converter
# ==============================================================================

class BeerJSONToBrewSignalConverter:
    """Convert BeerJSON 1.0 to BrewSignal Format v1.0."""

    def convert(self, beerjson: dict) -> dict:
        """Convert BeerJSON document to BrewSignal format.

        Args:
            beerjson: BeerJSON 1.0 document

        Returns:
            BrewSignal format dict with root structure

        Raises:
            ValueError: If BeerJSON is invalid or contains non-Celsius temps
        """
        recipe = beerjson["beerjson"]["recipes"][0]

        return {
            "brewsignal_version": "1.0",
            "recipe": self._convert_recipe(recipe)
        }

    def _convert_recipe(self, recipe: dict) -> dict:
        """Convert single BeerJSON recipe to BrewSignal format."""
        result = {
            "name": recipe["name"],
            "author": recipe.get("author"),
            "type": recipe.get("type"),
            "og": self._unwrap_gravity(recipe.get("original_gravity")),
            "fg": self._unwrap_gravity(recipe.get("final_gravity")),
            "abv": self._unwrap_percent(recipe.get("alcohol_by_volume")),
            "ibu": self._unwrap_number(recipe.get("ibu_estimate")),
            "color_srm": self._unwrap_number(recipe.get("color_estimate") or recipe.get("color")),
            "batch_size_liters": self._unwrap_volume(recipe.get("batch_size")),
            "boil_time_minutes": self._unwrap_time_minutes(recipe.get("boil", {}).get("boil_time")),
            "efficiency_percent": self._unwrap_percent(recipe.get("efficiency", {}).get("brewhouse")),
            "carbonation_vols": recipe.get("carbonation"),  # Already raw number in BeerJSON 1.0
            "notes": recipe.get("notes"),
        }

        # Ingredients
        ingredients = recipe.get("ingredients", {})
        if ingredients.get("fermentable_additions"):
            result["fermentables"] = [self._convert_fermentable(f) for f in ingredients["fermentable_additions"]]
        if ingredients.get("hop_additions"):
            result["hops"] = [self._convert_hop(h) for h in ingredients["hop_additions"]]
        if ingredients.get("culture_additions"):
            result["yeast"] = self._convert_yeast(ingredients["culture_additions"])
        if ingredients.get("miscellaneous_additions"):
            result["miscs"] = [self._convert_misc(m) for m in ingredients["miscellaneous_additions"]]

        # Remove None values
        return {k: v for k, v in result.items() if v is not None}

    def _convert_fermentable(self, ferm: dict) -> dict:
        """Convert BeerJSON fermentable to BrewSignal format."""
        return {
            "name": ferm["name"],
            "type": ferm.get("type"),
            "grain_group": ferm.get("grain_group"),
            "amount_kg": self._unwrap_mass_kg(ferm.get("amount")),
            "percentage": self._unwrap_percent(ferm.get("percentage")) if ferm.get("percentage") else None,
            "yield_percent": self._unwrap_percent(ferm.get("yield", {}).get("fine_grind")) if ferm.get("yield") else None,
            "color_srm": self._unwrap_number(ferm.get("color")),
            "origin": ferm.get("origin"),
            "supplier": ferm.get("producer"),
        }

    def _convert_hop(self, hop: dict) -> dict:
        """Convert BeerJSON hop to BrewSignal format."""
        return {
            "name": hop["name"],
            "origin": hop.get("origin"),
            "form": hop.get("form"),
            "amount_grams": self._unwrap_mass_g(hop.get("amount")),
            "alpha_acid_percent": self._unwrap_percent(hop.get("alpha_acid")),
            "beta_acid_percent": self._unwrap_percent(hop.get("beta_acid")),
            "timing": hop.get("timing"),  # Keep nested object as-is
        }

    def _convert_yeast(self, cultures: List[dict]) -> Optional[dict]:
        """Convert BeerJSON cultures array to single BrewSignal yeast.

        BrewSignal v1.0 supports single yeast only.
        Takes first culture from array.
        """
        if not cultures:
            return None

        culture = cultures[0]
        temp_range = culture.get("temperature_range", {})
        attenuation_range = culture.get("attenuation_range", {})

        return {
            "name": culture.get("name"),
            "producer": culture.get("producer"),
            "product_id": culture.get("product_id"),
            "type": culture.get("type"),
            "form": culture.get("form"),
            "attenuation_percent": self._unwrap_percent(attenuation_range.get("minimum") or attenuation_range.get("maximum")),
            "temp_min_c": self._unwrap_temperature(temp_range.get("minimum")),
            "temp_max_c": self._unwrap_temperature(temp_range.get("maximum")),
            "amount_grams": self._unwrap_mass_g(culture.get("amount")) if self._is_mass_unit(culture.get("amount")) else None,
        }

    def _convert_misc(self, misc: dict) -> dict:
        """Convert BeerJSON misc to BrewSignal format."""
        return {
            "name": misc["name"],
            "type": misc.get("type"),
            "amount_grams": self._unwrap_mass_g(misc.get("amount")) if self._is_mass_unit(misc.get("amount")) else None,
            "timing": misc.get("timing"),
        }

    # Unwrap helpers

    def _unwrap_gravity(self, unit_obj: Optional[dict]) -> Optional[float]:
        """Extract gravity value from unit object."""
        return unit_obj["value"] if unit_obj else None

    def _unwrap_volume(self, unit_obj: Optional[dict]) -> Optional[float]:
        """Extract volume in liters from unit object."""
        if not unit_obj:
            return None
        value = unit_obj["value"]
        unit = unit_obj["unit"]
        if unit == "l":
            return value
        elif unit == "gal":
            return value * 3.78541
        else:
            raise ValueError(f"Unknown volume unit: {unit}")

    def _unwrap_temperature(self, unit_obj: Optional[dict]) -> Optional[float]:
        """Extract temperature in Celsius from unit object.

        Raises:
            ValueError: If temperature is not in Celsius
        """
        if not unit_obj:
            return None
        unit = unit_obj["unit"]
        if unit != "C":
            raise ValueError(
                f"Temperature must be in Celsius. Found unit: {unit}. "
                "BrewSignal format requires all temperatures in Celsius."
            )
        return unit_obj["value"]

    def _unwrap_mass_kg(self, unit_obj: Optional[dict]) -> Optional[float]:
        """Extract mass in kg from unit object."""
        if not unit_obj:
            return None
        value = unit_obj["value"]
        unit = unit_obj["unit"]
        if unit == "kg":
            return value
        elif unit == "g":
            return value / 1000
        else:
            raise ValueError(f"Unknown mass unit: {unit}")

    def _unwrap_mass_g(self, unit_obj: Optional[dict]) -> Optional[float]:
        """Extract mass in grams from unit object."""
        if not unit_obj:
            return None
        value = unit_obj["value"]
        unit = unit_obj["unit"]
        if unit == "g":
            return value
        elif unit == "kg":
            return value * 1000
        else:
            raise ValueError(f"Unknown mass unit: {unit}")

    def _unwrap_percent(self, unit_obj: Optional[dict]) -> Optional[float]:
        """Extract percentage value from unit object.

        BeerJSON stores percentages as 0-1 (e.g., 0.069 for 6.9%).
        BrewSignal uses 0-100 scale.
        """
        if not unit_obj:
            return None
        value = unit_obj["value"]
        # Convert from 0-1 to 0-100 scale
        return value * 100 if value <= 1 else value

    def _unwrap_number(self, unit_obj: Optional[dict]) -> Optional[float]:
        """Extract dimensionless number from unit object."""
        return unit_obj["value"] if unit_obj else None

    def _unwrap_time_minutes(self, unit_obj: Optional[dict]) -> Optional[int]:
        """Extract time in minutes from unit object."""
        if not unit_obj:
            return None
        value = unit_obj["value"]
        unit = unit_obj["unit"]
        if unit == "min":
            return int(value)
        elif unit == "hr":
            return int(value * 60)
        else:
            raise ValueError(f"Unknown time unit: {unit}")

    def _is_mass_unit(self, unit_obj: Optional[dict]) -> bool:
        """Check if unit object contains mass (g/kg) vs volume (ml/l)."""
        if not unit_obj:
            return False
        unit = unit_obj.get("unit", "")
        return unit in ["g", "kg"]


# ==============================================================================
# BrewSignal → BeerJSON Converter
# ==============================================================================

class BrewSignalToBeerJSONConverter:
    """Convert BrewSignal Format v1.0 to BeerJSON 1.0."""

    def convert(self, brewsignal: dict) -> dict:
        """Convert BrewSignal document to BeerJSON format.

        Args:
            brewsignal: BrewSignal format dict

        Returns:
            BeerJSON 1.0 compatible dict
        """
        recipe = brewsignal["recipe"]

        return {
            "beerjson": {
                "version": 1.0,
                "recipes": [self._convert_recipe(recipe)]
            }
        }

    def _convert_recipe(self, recipe: dict) -> dict:
        """Convert BrewSignal recipe to BeerJSON format."""
        result = {
            "name": recipe["name"],
            "type": recipe.get("type", "all grain"),
            "author": recipe.get("author", "Unknown"),
            "original_gravity": self._wrap_gravity(recipe.get("og")),
            "final_gravity": self._wrap_gravity(recipe.get("fg")),
        }

        # Optional fields
        if recipe.get("abv") is not None:
            result["alcohol_by_volume"] = self._wrap_percent(recipe["abv"])
        if recipe.get("ibu") is not None:
            result["ibu_estimate"] = self._wrap_number(recipe["ibu"])
        if recipe.get("color_srm") is not None:
            result["color_estimate"] = self._wrap_color(recipe["color_srm"])
        if recipe.get("batch_size_liters") is not None:
            result["batch_size"] = self._wrap_volume(recipe["batch_size_liters"])
        if recipe.get("boil_time_minutes") is not None:
            result["boil"] = {"boil_time": self._wrap_time_minutes(recipe["boil_time_minutes"])}
        if recipe.get("efficiency_percent") is not None:
            result["efficiency"] = {"brewhouse": self._wrap_percent(recipe["efficiency_percent"])}
        if recipe.get("carbonation_vols") is not None:
            result["carbonation"] = recipe["carbonation_vols"]  # Raw number in BeerJSON 1.0
        if recipe.get("notes"):
            result["notes"] = recipe["notes"]

        # Ingredients
        ingredients = {}
        if recipe.get("fermentables"):
            ingredients["fermentable_additions"] = [self._convert_fermentable(f) for f in recipe["fermentables"]]
        if recipe.get("hops"):
            ingredients["hop_additions"] = [self._convert_hop(h) for h in recipe["hops"]]
        if recipe.get("yeast"):
            ingredients["culture_additions"] = [self._convert_yeast(recipe["yeast"])]
        if recipe.get("miscs"):
            ingredients["miscellaneous_additions"] = [self._convert_misc(m) for m in recipe["miscs"]]

        if ingredients:
            result["ingredients"] = ingredients

        return result

    def _convert_fermentable(self, ferm: dict) -> dict:
        """Convert BrewSignal fermentable to BeerJSON format."""
        result = {
            "name": ferm["name"],
            "type": ferm.get("type", "grain"),
            "amount": self._wrap_mass_kg(ferm["amount_kg"]),
        }

        if ferm.get("grain_group"):
            result["grain_group"] = ferm["grain_group"]
        if ferm.get("percentage") is not None:
            result["percentage"] = self._wrap_percent(ferm["percentage"])
        if ferm.get("yield_percent") is not None:
            result["yield"] = {"fine_grind": self._wrap_percent(ferm["yield_percent"])}
        if ferm.get("color_srm") is not None:
            result["color"] = self._wrap_color(ferm["color_srm"])
        if ferm.get("origin"):
            result["origin"] = ferm["origin"]
        if ferm.get("supplier"):
            result["producer"] = ferm["supplier"]

        return result

    def _convert_hop(self, hop: dict) -> dict:
        """Convert BrewSignal hop to BeerJSON format."""
        result = {
            "name": hop["name"],
            "amount": self._wrap_mass_g(hop["amount_grams"]),
            "timing": hop["timing"],
        }

        if hop.get("origin"):
            result["origin"] = hop["origin"]
        if hop.get("form"):
            result["form"] = hop["form"]
        if hop.get("alpha_acid_percent") is not None:
            result["alpha_acid"] = self._wrap_percent(hop["alpha_acid_percent"])
        if hop.get("beta_acid_percent") is not None:
            result["beta_acid"] = self._wrap_percent(hop["beta_acid_percent"])

        return result

    def _convert_yeast(self, yeast: dict) -> dict:
        """Convert BrewSignal yeast to BeerJSON culture."""
        result = {
            "name": yeast["name"],
        }

        if yeast.get("producer"):
            result["producer"] = yeast["producer"]
        if yeast.get("product_id"):
            result["product_id"] = yeast["product_id"]
        if yeast.get("type"):
            result["type"] = yeast["type"]
        if yeast.get("form"):
            result["form"] = yeast["form"]

        # Temperature range
        if yeast.get("temp_min_c") is not None or yeast.get("temp_max_c") is not None:
            temp_range = {}
            if yeast.get("temp_min_c") is not None:
                temp_range["minimum"] = {"value": yeast["temp_min_c"], "unit": "C"}
            if yeast.get("temp_max_c") is not None:
                temp_range["maximum"] = {"value": yeast["temp_max_c"], "unit": "C"}
            result["temperature_range"] = temp_range

        # Attenuation (BeerJSON requires min AND max, use same value)
        if yeast.get("attenuation_percent") is not None:
            att = self._wrap_percent(yeast["attenuation_percent"])
            result["attenuation_range"] = {"minimum": att, "maximum": att}

        # Amount
        if yeast.get("amount_grams") is not None:
            result["amount"] = self._wrap_mass_g(yeast["amount_grams"])

        return result

    def _convert_misc(self, misc: dict) -> dict:
        """Convert BrewSignal misc to BeerJSON format."""
        result = {
            "name": misc["name"],
            "timing": misc["timing"],
        }

        if misc.get("type"):
            result["type"] = misc["type"]
        if misc.get("amount_grams") is not None:
            result["amount"] = self._wrap_mass_g(misc["amount_grams"])

        return result

    # Wrap helpers

    def _wrap_gravity(self, value: Optional[float]) -> Optional[dict]:
        """Wrap raw gravity value in BeerJSON unit object."""
        return {"value": value, "unit": "sg"} if value is not None else None

    def _wrap_volume(self, value: Optional[float]) -> Optional[dict]:
        """Wrap raw volume value (liters) in BeerJSON unit object."""
        return {"value": value, "unit": "l"} if value is not None else None

    def _wrap_mass_kg(self, value: Optional[float]) -> Optional[dict]:
        """Wrap raw mass value (kg) in BeerJSON unit object."""
        return {"value": value, "unit": "kg"} if value is not None else None

    def _wrap_mass_g(self, value: Optional[float]) -> Optional[dict]:
        """Wrap raw mass value (grams) in BeerJSON unit object."""
        return {"value": value, "unit": "g"} if value is not None else None

    def _wrap_percent(self, value: Optional[float]) -> Optional[dict]:
        """Wrap percentage value in BeerJSON unit object.

        BrewSignal uses 0-100 scale (e.g., 6.9 for 6.9%).
        BeerJSON uses 0-1 scale (e.g., 0.069 for 6.9%).
        """
        if value is None:
            return None
        # Convert from 0-100 to 0-1 scale
        return {"value": value / 100, "unit": "%"}

    def _wrap_number(self, value: Optional[float]) -> Optional[dict]:
        """Wrap dimensionless number in BeerJSON unit object."""
        return {"value": value, "unit": "1"} if value is not None else None

    def _wrap_color(self, value: Optional[float]) -> Optional[dict]:
        """Wrap color value in BeerJSON unit object."""
        return {"value": value, "unit": "SRM"} if value is not None else None

    def _wrap_time_minutes(self, value: Optional[int]) -> Optional[dict]:
        """Wrap time value (minutes) in BeerJSON unit object."""
        return {"value": value, "unit": "min"} if value is not None else None
