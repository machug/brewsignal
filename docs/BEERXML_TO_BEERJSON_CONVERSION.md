# BeerXML to BeerJSON Conversion Strategy

## Overview

This document provides a comprehensive analysis of converting BeerXML 1.0 recipes to BeerJSON 1.0 format. The conversion is **feasible with acceptable data loss** - BeerJSON is a superset of BeerXML with enhanced capabilities, so most BeerXML data maps cleanly to BeerJSON fields.

## Conversion Feasibility Summary

**✅ Fully Convertible:**
- Recipe metadata (name, author, type, batch size)
- Fermentables (grains, extracts, sugars)
- Hops (additions with alpha acids, timing)
- Yeasts (basic culture information)
- Styles (BJCP guidelines)
- Water chemistry (basic profiles)
- Mash profiles and steps

**⚠️ Partial Conversion:**
- Yeast → Culture (maps to subset of Culture schema)
- Simple timing → Timing objects (loses granularity)
- Single temperature → Temperature ranges
- Miscs → Ingredients (limited type mapping)

**❌ Data Loss:**
- BeerJSON's advanced timing (temperature/gravity-based additions)
- Culture details (POF+/-, glucoamylase, attenuation range)
- Hop oil profiles (beta acids, cohumulone)
- Fermentation/packaging procedures (not in BeerXML)
- Enhanced efficiency components

## Field Mapping Tables

### Recipe-Level Fields

| BeerXML Field | BeerJSON Field | Conversion Notes |
|---------------|----------------|------------------|
| `NAME` | `name` | Direct mapping |
| `VERSION` | - | Not used (BeerJSON has schema version) |
| `TYPE` | `type` | Direct mapping (Extract, Partial Mash, All Grain) |
| `BREWER` | `author` | Direct mapping |
| `BATCH_SIZE` | `batch_size.value` | Convert liters → BeerJSON volume object |
| `BOIL_SIZE` | `boil_size.value` | Convert liters → BeerJSON volume object |
| `BOIL_TIME` | `boil.boil_time.value` | Convert minutes → BeerJSON time object |
| `EFFICIENCY` | `efficiency.brewhouse` | Map to brewhouse efficiency (0-100%) |
| `NOTES` | `notes` | Direct mapping |
| `STYLE` | `style` | Maps to BeerJSON StyleType (see Style mapping) |
| `OG` | `original_gravity.value` | Convert to specific gravity (1.xxx) |
| `FG` | `final_gravity.value` | Convert to specific gravity (1.xxx) |
| `IBU` | `ibu_estimate.value` | Direct mapping (with IBU unit) |
| `ABV` | `alcohol_by_volume.value` | Direct mapping (with % unit) |
| `COLOR` | `color_estimate.value` | Convert SRM → BeerJSON color object |
| `CARBONATION` | `carbonation.value` | Convert volumes → BeerJSON carbonation object |

### Fermentables Mapping

| BeerXML Field | BeerJSON Field | Conversion Notes |
|---------------|----------------|------------------|
| `NAME` | `name` | Direct mapping |
| `TYPE` | `type` | Map to FermentableType (Grain, Extract, Sugar, Dry Extract) |
| `AMOUNT` | `amount.value` | Convert kg → BeerJSON mass object |
| `YIELD` | `yield.potential` | Convert % → specific gravity contribution |
| `COLOR` | `color.value` | Convert SRM/Lovibond → BeerJSON color object |
| `ORIGIN` | `origin` | Direct mapping (country/region) |
| `SUPPLIER` | `producer` | Maps to producer field |
| `NOTES` | `notes` | Direct mapping |
| `COARSE_FINE_DIFF` | `grain_group` | **Data loss** - no direct equivalent |
| `MOISTURE` | - | **Data loss** - not in BeerJSON |
| `DIASTATIC_POWER` | `diastatic_power.value` | Convert Lintner → BeerJSON diastatic power object |
| `PROTEIN` | `protein.value` | Convert % → BeerJSON percent object |
| `MAX_IN_BATCH` | `max_in_batch.value` | Convert % → BeerJSON percent object |
| - | `timing` | **Enrichment** - BeerJSON timing object (default to mash) |

**Conversion Logic:**
```python
def convert_fermentable(beerxml_fermentable):
    return {
        "name": beerxml_fermentable.name,
        "type": map_fermentable_type(beerxml_fermentable.type),
        "amount": {
            "value": beerxml_fermentable.amount,
            "unit": "kg"
        },
        "yield": {
            "fine_grind": {
                "value": beerxml_fermentable.yield_pct,
                "unit": "%"
            }
        },
        "color": {
            "value": beerxml_fermentable.color,
            "unit": "SRM"
        },
        "origin": beerxml_fermentable.origin,
        "producer": beerxml_fermentable.supplier,
        "notes": beerxml_fermentable.notes,
        # Default timing to mash (BeerXML doesn't have timing objects)
        "timing": {
            "use": "add_to_mash"
        }
    }

def map_fermentable_type(beerxml_type):
    mapping = {
        "Grain": "grain",
        "Extract": "extract",
        "Sugar": "sugar",
        "Dry Extract": "dry extract",
        "Adjunct": "adjunct"
    }
    return mapping.get(beerxml_type, "grain")
```

### Hops Mapping

| BeerXML Field | BeerJSON Field | Conversion Notes |
|---------------|----------------|------------------|
| `NAME` | `name` | Direct mapping |
| `ALPHA` | `alpha_acid.value` | Convert % → BeerJSON percent object |
| `AMOUNT` | `amount.value` | Convert kg → BeerJSON mass object |
| `USE` | `timing.use` | Map to HopAdditionType (see timing conversion) |
| `TIME` | `timing.duration.value` | Convert minutes → BeerJSON time object |
| `FORM` | `form` | Map to HopForm (pellet, leaf, plug, extract) |
| `ORIGIN` | `origin` | Direct mapping |
| `NOTES` | `notes` | Direct mapping |
| `BETA` | `beta_acid.value` | **Data loss in BeerXML** - often missing |
| - | `oil_content` | **Enrichment** - BeerJSON hop oil profiles (unavailable) |
| - | `percent_lost` | **Enrichment** - BeerJSON utilization (use defaults) |

**Timing Conversion:**
```python
def convert_hop_timing(beerxml_hop):
    use_mapping = {
        "Boil": "add_to_boil",
        "Dry Hop": "add_to_fermentation",
        "Mash": "add_to_mash",
        "First Wort": "add_to_boil",  # Approximate as boil
        "Aroma": "add_to_boil"  # Flame out = end of boil
    }

    return {
        "use": use_mapping.get(beerxml_hop.use, "add_to_boil"),
        "duration": {
            "value": beerxml_hop.time,
            "unit": "min"
        } if beerxml_hop.use == "Boil" else None,
        "continuous": False  # BeerJSON feature, default to false
    }
```

### Yeast → Culture Mapping

| BeerXML Field | BeerJSON Field | Conversion Notes |
|---------------|----------------|------------------|
| `NAME` | `name` | Direct mapping |
| `TYPE` | `type` | Map to CultureType (ale, lager, other, bacteria, brett) |
| `FORM` | `form` | Map to CultureForm (liquid, dry, slant, culture) |
| `AMOUNT` | `amount.value` | Convert to appropriate unit (L, kg, pkg, each) |
| `LABORATORY` | `producer` | Direct mapping |
| `PRODUCT_ID` | `product_id` | Direct mapping |
| `MIN_TEMPERATURE` | `temperature_range.minimum.value` | Convert °F → °C → BeerJSON temp object |
| `MAX_TEMPERATURE` | `temperature_range.maximum.value` | Convert °F → °C → BeerJSON temp object |
| `ATTENUATION` | `attenuation.value` | **Data loss** - BeerXML single value, BeerJSON has min/max |
| `NOTES` | `notes` | Direct mapping |
| - | `pof` | **Enrichment** - POF+/- (phenolic off-flavor) - unavailable |
| - | `glucoamylase` | **Enrichment** - STA1 gene info - unavailable |
| - | `alcohol_tolerance` | **Enrichment** - unavailable in BeerXML |
| - | `timing` | **Enrichment** - BeerJSON timing (default to primary) |

**Conversion Logic:**
```python
def convert_yeast_to_culture(beerxml_yeast):
    return {
        "name": beerxml_yeast.name,
        "type": map_culture_type(beerxml_yeast.type),
        "form": map_culture_form(beerxml_yeast.form),
        "producer": beerxml_yeast.laboratory,
        "product_id": beerxml_yeast.product_id,
        "temperature_range": {
            "minimum": {
                "value": fahrenheit_to_celsius(beerxml_yeast.min_temperature),
                "unit": "C"
            },
            "maximum": {
                "value": fahrenheit_to_celsius(beerxml_yeast.max_temperature),
                "unit": "C"
            }
        },
        "attenuation": {
            "minimum": {
                "value": beerxml_yeast.attenuation,
                "unit": "%"
            },
            "maximum": {
                "value": beerxml_yeast.attenuation,
                "unit": "%"
            }
        },
        "notes": beerxml_yeast.notes,
        # Default timing to primary fermentation
        "timing": {
            "use": "add_to_fermentation",
            "phase": "primary"
        }
    }

def map_culture_type(beerxml_type):
    mapping = {
        "Ale": "ale",
        "Lager": "lager",
        "Wheat": "ale",  # Most wheat yeasts are ale strains
        "Wine": "wine",
        "Champagne": "champagne"
    }
    return mapping.get(beerxml_type, "ale")

def map_culture_form(beerxml_form):
    mapping = {
        "Liquid": "liquid",
        "Dry": "dry",
        "Slant": "slant",
        "Culture": "culture"
    }
    return mapping.get(beerxml_form, "liquid")
```

### Style Mapping

| BeerXML Field | BeerJSON Field | Conversion Notes |
|---------------|----------------|------------------|
| `NAME` | `name` | Direct mapping |
| `CATEGORY` | `category` | Direct mapping (BJCP category) |
| `CATEGORY_NUMBER` | `category_number` | Direct mapping (e.g., "18") |
| `STYLE_LETTER` | `style_letter` | Direct mapping (e.g., "B") |
| `STYLE_GUIDE` | `style_guide` | Direct mapping (e.g., "BJCP 2015") |
| `TYPE` | `type` | Map to StyleType (lager, ale, mead, cider, etc.) |
| `OG_MIN` | `original_gravity.minimum.value` | Convert to specific gravity |
| `OG_MAX` | `original_gravity.maximum.value` | Convert to specific gravity |
| `FG_MIN` | `final_gravity.minimum.value` | Convert to specific gravity |
| `FG_MAX` | `final_gravity.maximum.value` | Convert to specific gravity |
| `IBU_MIN` | `international_bitterness_units.minimum.value` | Direct mapping |
| `IBU_MAX` | `international_bitterness_units.maximum.value` | Direct mapping |
| `COLOR_MIN` | `color.minimum.value` | Convert SRM → BeerJSON color |
| `COLOR_MAX` | `color.maximum.value` | Convert SRM → BeerJSON color |
| `ABV_MIN` | `alcohol_by_volume.minimum.value` | Direct mapping (%) |
| `ABV_MAX` | `alcohol_by_volume.maximum.value` | Direct mapping (%) |
| `NOTES` | `notes` | Direct mapping |
| `PROFILE` | `aroma` / `appearance` / `flavor` / `mouthfeel` | Split into separate fields |

### Mash Profile Mapping

| BeerXML Field | BeerJSON Field | Conversion Notes |
|---------------|----------------|------------------|
| `NAME` | `name` | Direct mapping |
| `GRAIN_TEMP` | `grain_temperature.value` | Convert °F → °C → BeerJSON temp |
| `SPARGE_TEMP` | `sparge_temperature.value` | Convert °F → °C → BeerJSON temp |
| `PH` | `ph` | Direct mapping (0-14) |
| `NOTES` | `notes` | Direct mapping |
| `MASH_STEPS[]` | `mash_steps[]` | Array of mash steps (see below) |

**Mash Step Mapping:**

| BeerXML Field | BeerJSON Field | Conversion Notes |
|---------------|----------------|------------------|
| `NAME` | `name` | Direct mapping |
| `TYPE` | `type` | Map to MashStepType (infusion, temperature, decoction) |
| `STEP_TEMP` | `step_temperature.value` | Convert °F → °C → BeerJSON temp |
| `STEP_TIME` | `step_time.value` | Convert minutes → BeerJSON time |
| `INFUSE_AMOUNT` | `amount.value` | Convert liters → BeerJSON volume |
| `DESCRIPTION` | `description` | Direct mapping |

### Water Profile Mapping

| BeerXML Field | BeerJSON Field | Conversion Notes |
|---------------|----------------|------------------|
| `NAME` | `name` | Direct mapping |
| `CALCIUM` | `calcium.value` | Convert ppm → BeerJSON concentration |
| `BICARBONATE` | `bicarbonate.value` | Convert ppm → BeerJSON concentration |
| `SULFATE` | `sulfate.value` | Convert ppm → BeerJSON concentration |
| `CHLORIDE` | `chloride.value` | Convert ppm → BeerJSON concentration |
| `SODIUM` | `sodium.value` | Convert ppm → BeerJSON concentration |
| `MAGNESIUM` | `magnesium.value` | Convert ppm → BeerJSON concentration |
| `PH` | `ph` | Direct mapping (0-14) |
| `NOTES` | `notes` | Direct mapping |

### Miscs → Ingredients Mapping

BeerXML's `MISC` is a catch-all for ingredients that don't fit other categories. BeerJSON has a more structured approach with specific ingredient types.

| BeerXML Field | BeerJSON Field | Conversion Notes |
|---------------|----------------|------------------|
| `NAME` | `name` | Direct mapping |
| `TYPE` | `type` | **Complex mapping** - see below |
| `USE` | `timing.use` | Map to timing object |
| `TIME` | `timing.duration.value` | Convert minutes → BeerJSON time |
| `AMOUNT` | `amount.value` | Convert to appropriate unit |
| `NOTES` | `notes` | Direct mapping |

**Misc Type Mapping:**
- `Spice` → BeerJSON `ingredient` with type "spice"
- `Fining` → BeerJSON `ingredient` with type "fining"
- `Water Agent` → BeerJSON `water_agent` (separate type)
- `Herb` → BeerJSON `ingredient` with type "herb"
- `Flavor` → BeerJSON `ingredient` with type "flavor"
- `Other` → BeerJSON `ingredient` with type "other"

## Data Loss Analysis

### Minor Data Loss (Acceptable)

1. **BeerXML `VERSION` field**: Not needed (BeerJSON has schema version)
2. **Fermentable moisture/coarse-fine diff**: Rarely used in practice
3. **Single attenuation value**: BeerJSON expects min/max range (use same value for both)
4. **Simple timing**: BeerXML only has time-based additions, loses BeerJSON's temperature/gravity-based timing

### Moderate Data Loss (Workaround Possible)

1. **Hop oil profiles**: BeerXML doesn't track myrcene, humulene, caryophyllene, farnesene
   - **Workaround**: Use default values for hop variety or leave null

2. **Culture enhancements**: BeerXML missing POF, glucoamylase, alcohol tolerance
   - **Workaround**: Use yeast database lookup by product ID to enrich data

3. **Efficiency components**: BeerXML has single efficiency, BeerJSON has conversion/lauter/mash/brewhouse
   - **Workaround**: Map BeerXML efficiency to brewhouse, calculate others from defaults

4. **Procedures**: BeerJSON has explicit fermentation/packaging procedures not in BeerXML
   - **Workaround**: Create default procedures based on recipe type

### Significant Data Loss (Not Recoverable)

1. **Advanced timing objects**: Temperature/gravity-based additions (e.g., "add hops at 80°C" or "dry hop at 1.020 SG")
2. **Hop pellet types**: T90 vs Cryo vs BBC pellets
3. **Packaging carbonation methods**: Force carbonation vs bottle conditioning details
4. **IBU calculation method**: BeerJSON tracks which formula was used (Tinseth, Rager, etc.)

## Conversion Strategy

### Architecture

**Recommended Approach: Multi-Format Support**

Instead of converting BeerXML → BeerJSON and discarding BeerXML, support both formats:

```
┌─────────────────┐
│   File Upload   │
└────────┬────────┘
         │
         ├──── .xml ───→ BeerXML Parser ───┐
         │                                  │
         └──── .json ──→ BeerJSON Parser ──┤
                                            │
                                            ↓
                                  ┌─────────────────┐
                                  │  Internal Model │
                                  │   (Database)    │
                                  └─────────────────┘
                                            │
                                            ↓
                                  ┌─────────────────┐
                                  │  Export Format  │
                                  ├─────────────────┤
                                  │ • BeerXML 1.0   │
                                  │ • BeerJSON 1.0  │
                                  │ • Brewfather*   │
                                  └─────────────────┘
```

**Benefits:**
- Users can import either format
- Export to either format based on compatibility needs
- Internal database model is format-agnostic
- Future-proof for new standards

### Implementation Plan

**Phase 1: Internal Model Enhancement**
1. Add BeerJSON fields to existing database models (Culture, Ingredient, Timing)
2. Make BeerXML-specific fields nullable
3. Create migration to add new columns

**Phase 2: BeerJSON Parser**
1. Implement JSON Schema validation using BeerJSON schemas
2. Create BeerJSON → Internal Model parser
3. Handle timing objects, culture types, enhanced fermentable/hop data
4. Add BeerJSON import endpoint: `POST /api/recipes/import/beerjson`

**Phase 3: BeerXML → BeerJSON Converter**
1. Implement field mapping functions (as documented above)
2. Add data enrichment (yeast database lookup, default timing)
3. Validate output against BeerJSON schema
4. Add optional converter endpoint: `POST /api/recipes/convert/beerxml-to-beerjson`

**Phase 4: Export Functionality**
1. Implement BeerJSON exporter from internal model
2. Implement BeerXML exporter (maintain compatibility)
3. Add export endpoints:
   - `GET /api/recipes/{id}/export?format=beerjson`
   - `GET /api/recipes/{id}/export?format=beerxml`

### Code Example: BeerXML to BeerJSON Converter Service

```python
# backend/services/beerxml_to_beerjson_converter.py

from typing import Any
from decimal import Decimal
from datetime import datetime

class BeerXMLToBeerJSONConverter:
    """Convert BeerXML recipes to BeerJSON format."""

    def convert_recipe(self, beerxml_recipe: dict) -> dict:
        """Convert a BeerXML recipe dict to BeerJSON format."""
        return {
            "name": beerxml_recipe["NAME"],
            "type": self._convert_recipe_type(beerxml_recipe["TYPE"]),
            "author": beerxml_recipe.get("BREWER"),
            "created": datetime.utcnow().isoformat() + "Z",

            "batch_size": self._convert_volume(beerxml_recipe["BATCH_SIZE"]),
            "boil_size": self._convert_volume(beerxml_recipe["BOIL_SIZE"]),

            "boil": {
                "boil_time": self._convert_time(beerxml_recipe["BOIL_TIME"])
            },

            "efficiency": {
                "brewhouse": {
                    "value": float(beerxml_recipe.get("EFFICIENCY", 75)),
                    "unit": "%"
                }
            },

            "style": self._convert_style(beerxml_recipe.get("STYLE")),

            "ingredients": {
                "fermentables": [
                    self._convert_fermentable(f)
                    for f in beerxml_recipe.get("FERMENTABLES", {}).get("FERMENTABLE", [])
                ],
                "hops": [
                    self._convert_hop(h)
                    for h in beerxml_recipe.get("HOPS", {}).get("HOP", [])
                ],
                "cultures": [
                    self._convert_yeast_to_culture(y)
                    for y in beerxml_recipe.get("YEASTS", {}).get("YEAST", [])
                ],
                "miscellaneous_ingredients": [
                    self._convert_misc(m)
                    for m in beerxml_recipe.get("MISCS", {}).get("MISC", [])
                ]
            },

            "mash": self._convert_mash(beerxml_recipe.get("MASH")),

            "notes": beerxml_recipe.get("NOTES"),

            "original_gravity": self._convert_gravity(beerxml_recipe.get("OG")),
            "final_gravity": self._convert_gravity(beerxml_recipe.get("FG")),
            "alcohol_by_volume": self._convert_percent(beerxml_recipe.get("ABV")),
            "ibu_estimate": self._convert_ibu(beerxml_recipe.get("IBU")),
            "color_estimate": self._convert_color(beerxml_recipe.get("COLOR"))
        }

    def _convert_fermentable(self, beerxml_ferm: dict) -> dict:
        """Convert BeerXML fermentable to BeerJSON format."""
        return {
            "name": beerxml_ferm["NAME"],
            "type": self._map_fermentable_type(beerxml_ferm["TYPE"]),
            "origin": beerxml_ferm.get("ORIGIN"),
            "producer": beerxml_ferm.get("SUPPLIER"),
            "grain_group": self._map_grain_group(beerxml_ferm["TYPE"]),

            "yield": {
                "fine_grind": {
                    "value": float(beerxml_ferm.get("YIELD", 0)),
                    "unit": "%"
                }
            },

            "color": {
                "value": float(beerxml_ferm.get("COLOR", 0)),
                "unit": "SRM"
            },

            "amount": {
                "value": float(beerxml_ferm["AMOUNT"]),
                "unit": "kg"
            },

            # Default timing to mash (BeerXML doesn't specify)
            "timing": {
                "use": "add_to_mash"
            },

            "notes": beerxml_ferm.get("NOTES")
        }

    def _convert_hop(self, beerxml_hop: dict) -> dict:
        """Convert BeerXML hop to BeerJSON format."""
        return {
            "name": beerxml_hop["NAME"],
            "origin": beerxml_hop.get("ORIGIN"),
            "form": self._map_hop_form(beerxml_hop.get("FORM", "Pellet")),

            "alpha_acid": {
                "value": float(beerxml_hop.get("ALPHA", 0)),
                "unit": "%"
            },

            "beta_acid": {
                "value": float(beerxml_hop.get("BETA", 0)),
                "unit": "%"
            } if beerxml_hop.get("BETA") else None,

            "amount": {
                "value": float(beerxml_hop["AMOUNT"]) * 1000,  # kg to g
                "unit": "g"
            },

            "timing": self._convert_hop_timing(beerxml_hop),

            "notes": beerxml_hop.get("NOTES")
        }

    def _convert_hop_timing(self, beerxml_hop: dict) -> dict:
        """Convert BeerXML hop timing to BeerJSON timing object."""
        use_mapping = {
            "Boil": "add_to_boil",
            "Dry Hop": "add_to_fermentation",
            "Mash": "add_to_mash",
            "First Wort": "add_to_boil",
            "Aroma": "add_to_boil"  # Flame out
        }

        use = use_mapping.get(beerxml_hop.get("USE", "Boil"), "add_to_boil")
        time_val = float(beerxml_hop.get("TIME", 0))

        timing = {
            "use": use,
            "continuous": False
        }

        # Only add duration for boil additions
        if use == "add_to_boil" and time_val > 0:
            timing["duration"] = {
                "value": time_val,
                "unit": "min"
            }

        # Add fermentation phase for dry hop
        if use == "add_to_fermentation":
            timing["phase"] = "primary"

        return timing

    def _convert_yeast_to_culture(self, beerxml_yeast: dict) -> dict:
        """Convert BeerXML yeast to BeerJSON culture."""
        attenuation = float(beerxml_yeast.get("ATTENUATION", 75))

        return {
            "name": beerxml_yeast["NAME"],
            "type": self._map_culture_type(beerxml_yeast.get("TYPE", "Ale")),
            "form": self._map_culture_form(beerxml_yeast.get("FORM", "Liquid")),
            "producer": beerxml_yeast.get("LABORATORY"),
            "product_id": beerxml_yeast.get("PRODUCT_ID"),

            "temperature_range": {
                "minimum": {
                    "value": self._fahrenheit_to_celsius(
                        float(beerxml_yeast.get("MIN_TEMPERATURE", 60))
                    ),
                    "unit": "C"
                },
                "maximum": {
                    "value": self._fahrenheit_to_celsius(
                        float(beerxml_yeast.get("MAX_TEMPERATURE", 75))
                    ),
                    "unit": "C"
                }
            },

            "attenuation": {
                "minimum": {
                    "value": attenuation,
                    "unit": "%"
                },
                "maximum": {
                    "value": attenuation,
                    "unit": "%"
                }
            },

            "timing": {
                "use": "add_to_fermentation",
                "phase": "primary"
            },

            "notes": beerxml_yeast.get("NOTES")
        }

    # Helper methods for type mapping

    @staticmethod
    def _map_fermentable_type(beerxml_type: str) -> str:
        mapping = {
            "Grain": "grain",
            "Extract": "extract",
            "Sugar": "sugar",
            "Dry Extract": "dry extract",
            "Adjunct": "adjunct"
        }
        return mapping.get(beerxml_type, "grain")

    @staticmethod
    def _map_grain_group(beerxml_type: str) -> str:
        # BeerJSON grain groups: base, caramel, flaked, roasted, specialty, smoked, adjunct
        if beerxml_type in ["Grain"]:
            return "base"  # Default, can be enhanced with name matching
        elif beerxml_type == "Adjunct":
            return "adjunct"
        return "specialty"

    @staticmethod
    def _map_hop_form(beerxml_form: str) -> str:
        mapping = {
            "Pellet": "pellet",
            "Plug": "plug",
            "Leaf": "leaf",
            "Extract": "extract",
            "Whole": "leaf"
        }
        return mapping.get(beerxml_form, "pellet")

    @staticmethod
    def _map_culture_type(beerxml_type: str) -> str:
        mapping = {
            "Ale": "ale",
            "Lager": "lager",
            "Wheat": "ale",
            "Wine": "wine",
            "Champagne": "champagne"
        }
        return mapping.get(beerxml_type, "ale")

    @staticmethod
    def _map_culture_form(beerxml_form: str) -> str:
        mapping = {
            "Liquid": "liquid",
            "Dry": "dry",
            "Slant": "slant",
            "Culture": "culture"
        }
        return mapping.get(beerxml_form, "liquid")

    # Unit conversion helpers

    @staticmethod
    def _fahrenheit_to_celsius(fahrenheit: float) -> float:
        return round((fahrenheit - 32) * 5/9, 1)

    @staticmethod
    def _convert_volume(liters: float) -> dict:
        return {"value": float(liters), "unit": "l"}

    @staticmethod
    def _convert_time(minutes: float) -> dict:
        return {"value": float(minutes), "unit": "min"}

    @staticmethod
    def _convert_gravity(sg: float) -> dict:
        return {"value": float(sg), "unit": "sg"}

    @staticmethod
    def _convert_percent(value: float) -> dict:
        return {"value": float(value), "unit": "%"}

    @staticmethod
    def _convert_ibu(ibu: float) -> dict:
        return {"value": float(ibu), "unit": "IBUs"}

    @staticmethod
    def _convert_color(srm: float) -> dict:
        return {"value": float(srm), "unit": "SRM"}
```

## Brewfather JSON Conversion

**Status: Limited Feasibility**

Brewfather JSON is a **proprietary format** without public schema documentation. Based on available information:

**✅ Possible:**
- Basic recipe metadata (name, author, batch size)
- Fermentables, hops, yeasts (similar to BeerXML)
- Style information

**❌ Unknown:**
- Exact field names and structure
- Advanced features (timers, procedures, equipment profiles)
- Validation rules

**Recommendation:**
1. Request schema from Brewfather or reverse-engineer from export files
2. If format is similar to BeerXML, conversion is likely straightforward
3. If format is close to BeerJSON, minimal conversion needed

## Validation Strategy

All conversions should validate against official JSON Schemas:

```python
import json
import jsonschema

def validate_beerjson(recipe_data: dict) -> bool:
    """Validate converted recipe against BeerJSON schema."""
    with open('beerjson_schemas/recipe.json') as f:
        schema = json.load(f)

    try:
        jsonschema.validate(instance=recipe_data, schema=schema)
        return True
    except jsonschema.ValidationError as e:
        print(f"Validation error: {e.message}")
        return False
```

## Implementation Recommendations

### Priority 1: BeerJSON Import (Highest Value)

Support native BeerJSON imports first - this is the modern standard and provides the most comprehensive data.

**Estimated Effort:** 2-3 days
- Parse BeerJSON (JSON parsing is simpler than XML)
- Map to internal database models
- Validate against schema
- Add import endpoint

### Priority 2: BeerXML to BeerJSON Conversion

Enable users to import BeerXML and optionally convert to BeerJSON for future-proofing.

**Estimated Effort:** 3-4 days
- Implement converter service (code examples above)
- Add field mapping logic
- Handle data enrichment (yeast database lookup)
- Add optional conversion endpoint
- Add tests for all mappings

### Priority 3: Dual Export (BeerXML + BeerJSON)

Allow users to export recipes in both formats for maximum compatibility.

**Estimated Effort:** 2-3 days
- BeerJSON serializer from internal models
- BeerXML serializer (maintain existing format)
- Add export endpoints with format parameter

### Priority 4: Brewfather JSON Support

Only implement if users specifically request it and provide sample files.

**Estimated Effort:** Unknown (depends on format similarity)

## Testing Strategy

**Unit Tests:**
- Test each field mapping function independently
- Test unit conversions (°F → °C, kg → g, etc.)
- Test edge cases (missing fields, invalid values)

**Integration Tests:**
- End-to-end BeerXML → BeerJSON conversion
- Validate converted output against BeerJSON schema
- Round-trip test (BeerXML → BeerJSON → Export BeerJSON)

**Sample Recipes:**
- Use official BeerXML sample recipes
- Test recipes with all ingredient types
- Test recipes with complex mash profiles
- Test recipes with missing optional fields

## Migration Path for Existing Data

If you already have BeerXML recipes in the database:

```python
async def migrate_existing_recipes_to_beerjson():
    """Migrate existing BeerXML recipes to include BeerJSON fields."""
    converter = BeerXMLToBeerJSONConverter()

    # Fetch all existing recipes
    recipes = await db.execute(select(Recipe).options(
        selectinload(Recipe.fermentables),
        selectinload(Recipe.hops),
        selectinload(Recipe.yeasts)
    ))

    for recipe in recipes.scalars():
        # Convert to BeerXML dict
        beerxml_dict = recipe_to_beerxml_dict(recipe)

        # Convert to BeerJSON
        beerjson_dict = converter.convert_recipe(beerxml_dict)

        # Update recipe with BeerJSON fields
        recipe.beerjson_data = beerjson_dict  # Store as JSON column

        await db.commit()
```

## Conclusion

**BeerXML to BeerJSON conversion is highly feasible** with acceptable data loss. The main limitations are BeerJSON's advanced features (timing objects, culture details, hop oils) which aren't present in BeerXML source data.

**Recommended Approach:**
1. Support both BeerXML and BeerJSON imports natively
2. Provide optional BeerXML → BeerJSON conversion for users who want to modernize their recipes
3. Export in both formats for maximum compatibility
4. Use BeerJSON as the internal format going forward (more comprehensive)

**Next Steps:**
1. Review this document with the team
2. Prioritize implementation phases
3. Set up BeerJSON schema validation
4. Implement BeerJSON parser and validator
5. Implement converter service
6. Add comprehensive tests
7. Update documentation
