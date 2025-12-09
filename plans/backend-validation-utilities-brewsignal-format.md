# Backend Validation Utilities for BrewSignal Recipe Format v1.0

**Issue:** tilt_ui-4hu
**Type:** Task
**Priority:** P2
**Status:** Planning
**Created:** 2025-12-10

---

## Overview

Create backend utilities for validating and working with BrewSignal Recipe Format v1.0 - a simplified, human-readable JSON format optimized for fermentation monitoring. This format formalizes the existing API response structure and provides a cleaner alternative to verbose BeerJSON 1.0.

**Location:** `backend/services/brewsignal_format.py`

**Blocks:**
- tilt_ui-40f: Add recipe export endpoint with format selection
- tilt_ui-a6v: Add recipe validation endpoint
- tilt_ui-pbp: Round-trip conversion tests (BrewSignal ↔ BeerJSON)

---

## Problem Statement / Motivation

### Current State

The BrewSignal backend currently:
- Stores recipes using simple field names (`og`, `fg`, `abv`) internally
- Imports from BeerXML and BeerJSON (both verbose formats with unit objects)
- Has no validation or export for the BrewSignal format
- Lacks property methods for accessing format extensions

### Why This Matters

1. **User Experience**: Users want to manually create/edit recipes in a simple, readable format
2. **API Consistency**: Current API responses already use BrewSignal format, but it's undocumented and unvalidated
3. **Interoperability**: Need lossless conversion between BeerJSON (ecosystem standard) and BrewSignal (internal format)
4. **Extensibility**: BrewSignal extensions enable fermentation-specific features (OG validation, temp control defaults)

### Key Design Decisions

**BrewSignal vs BeerJSON:**
- **BrewSignal**: Raw numbers (`og: 1.050`), short names, Celsius-native, fermentation-focused
- **BeerJSON**: Wrapped units (`original_gravity: {value: 1.050, unit: "sg"}`), verbose names, brew-day focused

**Temperature Philosophy:**
- **All temperatures stored in Celsius** (database, API, BrewSignal format)
- Only Tilt hardware broadcasts Fahrenheit (converted at boundary)
- Frontend converts to user preference for display

---

## Proposed Solution

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     BrewSignal Format Layer                  │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────────┐  ┌──────────────────┐                │
│  │   Validator      │  │   Converters     │                │
│  │                  │  │                  │                │
│  │ • Schema load    │  │ • BeerJSON → BS  │                │
│  │ • Validation     │  │ • BS → BeerJSON  │                │
│  │ • Warnings       │  │ • Unit mapping   │                │
│  └──────────────────┘  └──────────────────┘                │
│           │                       │                          │
│           ▼                       ▼                          │
│  ┌────────────────────────────────────────┐                 │
│  │         Recipe Model Properties         │                 │
│  │                                         │                 │
│  │  • brewsignal_extensions                │                 │
│  │  • fermentation_tracking_config         │                 │
│  │  • batch_defaults                       │                 │
│  │  • yeast_management_config              │                 │
│  └────────────────────────────────────────┘                 │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Components

#### 1. Validator (`BrewSignalValidator`)

**Pattern:** Follows existing `BeerJSONValidator` in `backend/services/validators/beerjson_validator.py`

**Responsibilities:**
- Load BrewSignal JSON schema
- Validate recipes against schema
- Format validation errors with field paths
- Check business logic warnings

#### 2. Converters

**BeerJSON → BrewSignal** (`beerjson_to_brewsignal`)
- Unwrap BeerJSON unit objects to raw values
- Map field names (`original_gravity` → `og`)
- Extract `_extensions.brewsignal` to top-level `brewsignal_extensions`
- Handle multi-yeast (take first culture, store others)

**BrewSignal → BeerJSON** (`brewsignal_to_beerjson`)
- Wrap BrewSignal values in BeerJSON unit objects
- Map field names back (`og` → `original_gravity`)
- Embed `brewsignal_extensions` in `_extensions.brewsignal`
- Convert single yeast to `culture_additions` array

#### 3. Model Properties

**Recipe Model Extensions:**
Add `@property` methods to `backend/models.py::Recipe` for easy extension access:

```python
@property
def brewsignal_extensions(self) -> dict:
    if not self.format_extensions:
        return {}
    return self.format_extensions.get('brewsignal', {})

@property
def fermentation_tracking_config(self) -> dict:
    return self.brewsignal_extensions.get('fermentation_tracking', {})

@property
def batch_defaults(self) -> dict:
    return self.brewsignal_extensions.get('batch_defaults', {})

@property
def yeast_management_config(self) -> dict:
    return self.brewsignal_extensions.get('yeast_management', {})
```

---

## Technical Approach

### Implementation Pattern

**Follow Existing Codebase Conventions:**

1. **Validation Returns:** `Tuple[bool, List[str]]`
   Example: `backend/services/validators/beerjson_validator.py:102-127`

2. **Converter Pattern:** Class-based with `convert()` method
   Example: `backend/services/converters/beerxml_to_beerjson.py:5-44`

3. **Schema Loading:** Use `referencing.Registry` for $ref resolution
   Example: `backend/services/validators/beerjson_validator.py:39-100`

4. **Error Formatting:** Custom `_format_validation_error()` method
   Example: `backend/services/validators/beerjson_validator.py:134-162`

### File Structure

```
backend/
├── services/
│   ├── validators/
│   │   ├── brewsignal_validator.py          # NEW
│   │   ├── beerjson_validator.py            # Reference pattern
│   │   └── __init__.py
│   ├── converters/
│   │   ├── beerjson_to_brewsignal.py        # NEW
│   │   ├── brewsignal_to_beerjson.py        # NEW
│   │   ├── beerxml_to_beerjson.py           # Reference pattern
│   │   └── __init__.py
│   └── brewsignal_format.py                 # Public API (deprecated)
├── schemas/
│   └── brewsignal-recipe-v1.0.schema.json   # EXISTS
└── models.py                                 # MODIFY (add properties)
```

**Note:** The issue specifies `backend/services/brewsignal_format.py` but following codebase patterns, we'll split into `validators/` and `converters/` directories. The main file can re-export for convenience.

### Field Mapping Specification

#### Core Fields

| BeerJSON Field | BeerJSON Type | BrewSignal Field | BrewSignal Type | Conversion |
|----------------|---------------|------------------|-----------------|------------|
| `name` | string | `name` | string | Direct copy |
| `type` | string | `type` | string | Direct copy |
| `author` | string | `author` | string | Direct copy |
| `original_gravity` | `{value, unit: "sg"}` | `og` | float | Extract `.value` |
| `final_gravity` | `{value, unit: "sg"}` | `fg` | float | Extract `.value` |
| `alcohol_by_volume` | `{value, unit: "%"}` | `abv` | float | `.value` × 100 |
| `ibu_estimate` | `{value, unit: "IBUs"}` | `ibu` | float | Extract `.value` |
| `color_estimate` | `{value, unit: "SRM"}` | `color_srm` | float | Extract `.value` |
| `batch_size` | `{value, unit: "l"}` | `batch_size_liters` | float | Extract `.value` |
| `boil.boil_time` | `{value, unit: "min"}` | `boil_time_minutes` | int | Extract `.value` |
| `efficiency.brewhouse` | `{value, unit: "%"}` | `efficiency_percent` | float | `.value` × 100 |
| `carbonation` | float | `carbonation_vols` | float | Direct copy (BeerJSON 1.0 uses raw) |

#### Ingredient Fields

**Fermentables:**

| BeerJSON | BrewSignal | Conversion |
|----------|-----------|------------|
| `fermentable_additions[].name` | `fermentables[].name` | Direct |
| `fermentable_additions[].type` | `fermentables[].type` | Map enum |
| `fermentable_additions[].grain_group` | `fermentables[].grain_group` | Map enum |
| `fermentable_additions[].amount.value` | `fermentables[].amount_kg` | Extract (unit: "kg") |
| `fermentable_additions[].yield.fine_grind.value` | `fermentables[].yield_percent` | `.value` × 100 |
| `fermentable_additions[].color.value` | `fermentables[].color_srm` | Extract (unit: "SRM") |

**Hops:**

| BeerJSON | BrewSignal | Conversion |
|----------|-----------|------------|
| `hop_additions[].name` | `hops[].name` | Direct |
| `hop_additions[].amount.value` | `hops[].amount_grams` | Extract (unit: "g") |
| `hop_additions[].alpha_acid.value` | `hops[].alpha_acid_percent` | `.value` × 100 |
| `hop_additions[].beta_acid.value` | `hops[].beta_acid_percent` | `.value` × 100 |
| `hop_additions[].timing` | `hops[].timing` | **Preserve as-is** (complex object) |

**Yeast (Single Culture):**

| BeerJSON | BrewSignal | Conversion |
|----------|-----------|------------|
| `culture_additions[0].name` | `yeast.name` | First culture only |
| `culture_additions[0].type` | `yeast.type` | Map enum |
| `culture_additions[0].form` | `yeast.form` | Map enum |
| `culture_additions[0].producer` | `yeast.producer` | Direct |
| `culture_additions[0].product_id` | `yeast.product_id` | Direct |
| `culture_additions[0].attenuation_range.minimum.value` | `yeast.attenuation_percent` | `.value` × 100 |
| `culture_additions[0].temperature_range.minimum.value` | `yeast.temp_min_c` | Extract (must be °C) |
| `culture_additions[0].temperature_range.maximum.value` | `yeast.temp_max_c` | Extract (must be °C) |
| `culture_additions[0].amount.value` | `yeast.amount_grams` or `yeast.amount_ml` | Extract (check unit) |

**Multi-Yeast Handling:**
- **Import:** Take first culture from `culture_additions` array
- **Export:** Create single-element array from `yeast` object
- **Additional cultures:** Store in `Recipe.cultures` table (already exists) but omit from BrewSignal export (v1.0 limitation)

#### Process Steps

**Mash Steps:**

| BeerJSON | BrewSignal | Conversion |
|----------|-----------|------------|
| `mash.mash_steps[].step_temperature.value` | `mash_steps[].temp_c` | Extract (must be °C) |
| `mash.mash_steps[].step_time.value` | `mash_steps[].time_minutes` | Extract (unit: "min") |

**Fermentation Steps:**

| BeerJSON | BrewSignal | Conversion |
|----------|-----------|------------|
| `fermentation.fermentation_steps[].step_temperature.value` | `fermentation_steps[].temp_c` | Extract (must be °C) |
| `fermentation.fermentation_steps[].step_time.value` | `fermentation_steps[].time_days` | Extract (unit: "day") |

### Extension Preservation

**BeerJSON Extensions:**
```json
{
  "beerjson": {
    "version": 1.0,
    "recipes": [{
      "name": "IPA",
      "_extensions": {
        "brewsignal": {
          "version": "1.0",
          "fermentation_tracking": {...},
          "batch_defaults": {...}
        }
      }
    }]
  }
}
```

**BrewSignal Format:**
```json
{
  "brewsignal_version": "1.0",
  "recipe": {
    "name": "IPA",
    "brewsignal_extensions": {
      "version": "1.0",
      "fermentation_tracking": {...},
      "batch_defaults": {...}
    }
  }
}
```

**Round-Trip Preservation:**
- Store original BeerJSON in `Recipe.format_extensions.beerjson_original` (JSON string)
- On export, merge edited fields with original structure
- Preserve unknown BeerJSON fields that aren't in BrewSignal schema

### Validation Strategy

#### Schema Validation

**Level 1: JSON Schema Validation**
- Required fields: `brewsignal_version`, `recipe.name`, `recipe.og`, `recipe.fg`
- Type validation: Numbers, strings, arrays, nested objects
- Range validation: `og` (1.000-1.200), `abv` (0-20), etc.
- Enum validation: `type`, `yeast.form`, `fermentables[].grain_group`

**Level 2: Business Logic Warnings**

Non-blocking warnings for unusual but valid values:

```python
VALIDATION_WARNINGS = {
    "og_very_high": {
        "threshold": 1.120,
        "message": "Very high original gravity (>1.120). Verify measurement."
    },
    "og_very_low": {
        "threshold": 1.020,
        "message": "Very low original gravity (<1.020). Unusual for beer."
    },
    "fg_higher_than_og": {
        "message": "Final gravity cannot be higher than original gravity."
    },
    "abv_very_high": {
        "threshold": 15.0,
        "message": "Very high ABV (>15%). Verify calculation."
    },
    "ibu_extreme": {
        "threshold": 120,
        "message": "Extreme IBU (>120). Unusual for most styles."
    },
    "boil_time_long": {
        "threshold": 120,
        "message": "Unusually long boil time (>2 hours)."
    },
    "efficiency_high": {
        "threshold": 90,
        "message": "Very high efficiency (>90%). Verify system."
    },
    "batch_size_large": {
        "threshold": 100,
        "message": "Large batch size (>100L). Verify unit."
    },
    "no_fermentation_steps": {
        "message": "No fermentation steps defined."
    },
    "temp_out_of_yeast_range": {
        "message": "Fermentation temperature outside yeast viable range."
    },
    "mixed_temperature_units": {
        "message": "Mixed temperature units detected. BrewSignal requires Celsius."
    }
}
```

**Validation Result Structure:**

```python
from pydantic import BaseModel
from typing import List, Optional, Any

class ValidationErrorDetail(BaseModel):
    field: str                    # Dot notation: "recipe.og"
    message: str                  # Human-readable error
    validator: str                # Schema rule: "minimum", "required", etc.
    invalid_value: Optional[Any]  # The actual value that failed

class ValidationWarning(BaseModel):
    field: str
    message: str
    value: Any
    warning_code: str             # "og_very_high", etc.

class ValidationResult(BaseModel):
    valid: bool
    error_count: int = 0
    warning_count: int = 0
    errors: List[ValidationErrorDetail] = []
    warnings: List[ValidationWarning] = []
```

**Return Signature (Internal):**
```python
def validate_brewsignal_recipe(data: dict) -> Tuple[bool, List[str]]:
    """Returns (is_valid, error_messages) - follows existing pattern."""
```

**API Response (External):**
```python
@app.post("/api/recipes/validate", response_model=ValidationResult)
async def validate_recipe(data: dict, format: str = "brewsignal"):
    """Validates recipe and returns structured result."""
    # Returns HTTP 200 with valid: true/false
    # NOT HTTP 400 - validation is a service, not a state error
```

### Temperature Unit Handling

**Critical Rule:** All temperatures must be Celsius in BrewSignal format.

**Auto-Conversion on Import:**
```python
def normalize_temperature(temp_obj: dict) -> float:
    """Convert temperature unit object to Celsius."""
    value = temp_obj["value"]
    unit = temp_obj["unit"]

    if unit == "C":
        return value
    elif unit == "F":
        return (value - 32) * 5/9
    else:
        raise ValueError(f"Unknown temperature unit: {unit}")
```

**Validation on Export:**
```python
# Ensure all temperature objects use "C" unit
if temp_obj.get("unit") != "C":
    warnings.append({
        "field": field_path,
        "message": "Temperature unit must be Celsius in BrewSignal format.",
        "code": "mixed_temperature_units"
    })
```

### Precision Handling

**Rounding Rules:**
- **Gravity:** 3 decimals (1.050)
- **ABV:** 1 decimal (6.9%)
- **Temperature:** 1 decimal (18.5°C)
- **Weight/Volume:** 2 decimals (5.40 kg)
- **Percentage:** 1 decimal (75.0%)

**Why:** Balance precision with readability while avoiding floating-point accumulation errors.

### Null vs Missing Fields

**Rule:** Omit optional fields entirely, never use `null` for numbers.

**Valid:**
```json
{
  "name": "IPA",
  "og": 1.055,
  "fg": 1.012
  // "abv" omitted - will be calculated
}
```

**Invalid:**
```json
{
  "name": "IPA",
  "og": 1.055,
  "fg": null  // ❌ null not allowed for numbers
}
```

**Exception:** Strings can be null:
```json
{
  "name": "IPA",
  "notes": null  // ✓ OK for optional strings
}
```

---

## Implementation Plan

### Phase 1: Validator (Priority 1)

**File:** `backend/services/validators/brewsignal_validator.py`

**Tasks:**
- [ ] Create `BrewSignalValidator` class
- [ ] Load schema from `backend/schemas/brewsignal-recipe-v1.0.schema.json`
- [ ] Set up Registry for $ref resolution (same pattern as BeerJSON)
- [ ] Implement `validate(data: dict) -> Tuple[bool, List[str]]`
- [ ] Implement `_format_validation_error(error: ValidationError) -> str`
- [ ] Add business logic warnings (VALIDATION_WARNINGS dict)
- [ ] Add `validate_recipe(recipe: dict)` convenience method

**Dependencies:**
- jsonschema >= 4.20 (already in pyproject.toml)
- referencing >= 0.30 (already in pyproject.toml)

**Testing:**
- [ ] Test with `examples/recipes/minimal-pale-ale.brewsignal` (valid)
- [ ] Test with `examples/recipes/west-coast-ipa-complete.brewsignal` (valid with extensions)
- [ ] Test with invalid recipes (missing required fields)
- [ ] Test with out-of-range values (og: 1.250)
- [ ] Test warning triggers (og: 1.150, boil_time: 180)

**Example Usage:**
```python
from backend.services.validators.brewsignal_validator import BrewSignalValidator

validator = BrewSignalValidator()

# Valid recipe
with open("examples/recipes/west-coast-ipa-complete.brewsignal") as f:
    data = json.load(f)

is_valid, errors = validator.validate(data)
assert is_valid is True
assert len(errors) == 0

# Invalid recipe
invalid_data = {"recipe": {"name": "Test", "og": 1.250}}  # Missing fg, OG too high
is_valid, errors = validator.validate(invalid_data)
assert is_valid is False
assert "Missing required property 'fg'" in errors
assert "Value 1.250 exceeds maximum 1.200" in errors
```

### Phase 2: BeerJSON → BrewSignal Converter (Priority 2)

**File:** `backend/services/converters/beerjson_to_brewsignal.py`

**Tasks:**
- [ ] Create `BeerJSONToBrewSignalConverter` class
- [ ] Implement `convert(beerjson: dict) -> dict`
- [ ] Implement unit object unwrappers:
  - [ ] `_extract_gravity(unit_obj) -> float`
  - [ ] `_extract_volume(unit_obj) -> float`
  - [ ] `_extract_temperature(unit_obj) -> float` (auto-convert F→C)
  - [ ] `_extract_mass(unit_obj) -> float`
  - [ ] `_extract_percent(unit_obj) -> float` (×100)
  - [ ] `_extract_time(unit_obj) -> int`
- [ ] Implement field mappers:
  - [ ] `_convert_fermentables(beerjson_ferms) -> List[dict]`
  - [ ] `_convert_hops(beerjson_hops) -> List[dict]`
  - [ ] `_convert_cultures_to_yeast(beerjson_cultures) -> dict` (first only)
  - [ ] `_convert_mash_steps(beerjson_mash) -> List[dict]`
  - [ ] `_convert_fermentation_steps(beerjson_ferm) -> List[dict]`
- [ ] Extract extensions from `_extensions.brewsignal`
- [ ] Store original BeerJSON in result metadata

**Multi-Yeast Strategy:**
```python
def _convert_cultures_to_yeast(self, culture_additions: List[dict]) -> Optional[dict]:
    """Convert BeerJSON culture_additions array to BrewSignal single yeast object.

    Takes first culture. Additional cultures are lost in BrewSignal export but
    preserved in database via Recipe.cultures table.
    """
    if not culture_additions:
        return None

    first_culture = culture_additions[0]

    return {
        "name": first_culture["name"],
        "producer": first_culture.get("producer"),
        "product_id": first_culture.get("product_id"),
        "type": self._map_culture_type(first_culture.get("type")),
        "form": self._map_culture_form(first_culture.get("form")),
        "attenuation_percent": self._extract_percent(
            first_culture.get("attenuation_range", {}).get("minimum")
        ),
        "temp_min_c": self._extract_temperature(
            first_culture.get("temperature_range", {}).get("minimum")
        ),
        "temp_max_c": self._extract_temperature(
            first_culture.get("temperature_range", {}).get("maximum")
        ),
        # Handle both dry yeast (grams) and liquid yeast (ml)
        "amount_grams": self._extract_mass(first_culture.get("amount"))
            if first_culture.get("amount", {}).get("unit") in ["g", "kg"]
            else None,
        "amount_ml": self._extract_volume(first_culture.get("amount"))
            if first_culture.get("amount", {}).get("unit") in ["ml", "l"]
            else None,
    }
```

**Testing:**
- [ ] Test with existing BeerJSON fixtures
- [ ] Test multi-yeast handling (first culture extraction)
- [ ] Test temperature unit conversion (F → C)
- [ ] Test percentage conversion (0-1 → 0-100)
- [ ] Test extension extraction
- [ ] Test with minimal BeerJSON (required fields only)

### Phase 3: BrewSignal → BeerJSON Converter (Priority 2)

**File:** `backend/services/converters/brewsignal_to_beerjson.py`

**Tasks:**
- [ ] Create `BrewSignalToBeerJSONConverter` class
- [ ] Implement `convert(brewsignal: dict) -> dict`
- [ ] Implement unit object wrappers:
  - [ ] `_make_gravity(value: float) -> dict` (returns `{value, unit: "sg"}`)
  - [ ] `_make_volume(value: float) -> dict` (returns `{value, unit: "l"}`)
  - [ ] `_make_temperature(value: float) -> dict` (returns `{value, unit: "C"}`)
  - [ ] `_make_mass(value: float) -> dict` (returns `{value, unit: "kg"}` or `{value, unit: "g"}`)
  - [ ] `_make_percent(value: float) -> dict` (returns `{value: value/100, unit: "%"}`)
  - [ ] `_make_time(value: int, unit: str) -> dict`
- [ ] Implement reverse field mappers:
  - [ ] `_convert_fermentables(bs_ferms) -> List[dict]`
  - [ ] `_convert_hops(bs_hops) -> List[dict]`
  - [ ] `_convert_yeast_to_cultures(bs_yeast) -> List[dict]` (single → array)
  - [ ] `_convert_mash_steps(bs_mash) -> dict`
  - [ ] `_convert_fermentation_steps(bs_ferm) -> dict`
- [ ] Embed extensions in `_extensions.brewsignal`
- [ ] Merge with original BeerJSON if available

**Yeast Array Wrapping:**
```python
def _convert_yeast_to_cultures(self, yeast: Optional[dict]) -> List[dict]:
    """Convert BrewSignal single yeast object to BeerJSON culture_additions array."""
    if not yeast:
        return []

    culture = {
        "name": yeast["name"],
        "type": self._map_yeast_type(yeast.get("type")),
        "form": self._map_yeast_form(yeast.get("form")),
    }

    if yeast.get("producer"):
        culture["producer"] = yeast["producer"]

    if yeast.get("product_id"):
        culture["product_id"] = yeast["product_id"]

    # Attenuation as range (BeerJSON requires min AND max)
    if yeast.get("attenuation_percent"):
        att = self._make_percent(yeast["attenuation_percent"])
        culture["attenuation_range"] = {
            "minimum": att,
            "maximum": att  # Use same value for both
        }

    # Temperature range
    if yeast.get("temp_min_c") or yeast.get("temp_max_c"):
        temp_range = {}
        if yeast.get("temp_min_c"):
            temp_range["minimum"] = self._make_temperature(yeast["temp_min_c"])
        if yeast.get("temp_max_c"):
            temp_range["maximum"] = self._make_temperature(yeast["temp_max_c"])
        culture["temperature_range"] = temp_range

    # Amount (check which unit)
    if yeast.get("amount_grams"):
        culture["amount"] = self._make_mass(yeast["amount_grams"])
    elif yeast.get("amount_ml"):
        culture["amount"] = self._make_volume(yeast["amount_ml"])

    return [culture]  # Return as single-element array
```

**Round-Trip Merge:**
```python
def convert_with_roundtrip(self, brewsignal: dict, original_beerjson: Optional[str]) -> dict:
    """Convert BrewSignal to BeerJSON, preserving original structure if available."""
    # Convert BrewSignal to BeerJSON
    converted = self.convert(brewsignal)

    if not original_beerjson:
        return converted

    # Load original
    original = json.loads(original_beerjson)

    # Deep merge: edited fields override original, unknown fields preserved
    merged = self._deep_merge(original, converted)

    return merged

def _deep_merge(self, base: dict, overlay: dict) -> dict:
    """Recursively merge overlay into base, preserving unknown base keys."""
    result = base.copy()

    for key, value in overlay.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = self._deep_merge(result[key], value)
        else:
            result[key] = value

    return result
```

**Testing:**
- [ ] Test with BrewSignal examples
- [ ] Test yeast array wrapping
- [ ] Test percentage conversion (0-100 → 0-1)
- [ ] Test extension embedding
- [ ] Test round-trip merge with original BeerJSON
- [ ] Test field preservation (unknown BeerJSON fields)

### Phase 4: Model Properties (Priority 3)

**File:** `backend/models.py`

**Tasks:**
- [ ] Add `@property brewsignal_extensions(self) -> dict` to Recipe model
- [ ] Add `@property fermentation_tracking_config(self) -> dict`
- [ ] Add `@property batch_defaults(self) -> dict`
- [ ] Add `@property yeast_management_config(self) -> dict`
- [ ] Update type hints for `format_extensions` column

**Implementation:**

```python
# backend/models.py (add to Recipe class)

from typing import Dict, Any

class Recipe(Base):
    # ... existing fields ...

    format_extensions: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)

    @property
    def brewsignal_extensions(self) -> Dict[str, Any]:
        """Extract BrewSignal extensions from format_extensions JSON.

        Returns empty dict if not present (never None for easier access).
        """
        if not self.format_extensions:
            return {}
        return self.format_extensions.get('brewsignal', {})

    @property
    def fermentation_tracking_config(self) -> Dict[str, Any]:
        """Get fermentation tracking configuration from extensions.

        Example:
            {
                "og_validation": {"enabled": true, "tolerance_sg": 0.003},
                "fg_prediction": {"enabled": true, "ml_model": "kalman_exponential"},
                "anomaly_detection": {"stuck_fermentation": true}
            }
        """
        return self.brewsignal_extensions.get('fermentation_tracking', {})

    @property
    def batch_defaults(self) -> Dict[str, Any]:
        """Get batch defaults configuration from extensions.

        Example:
            {
                "auto_link_device": true,
                "temperature_control": {
                    "enabled": true,
                    "target_c": 18.0,
                    "hysteresis_c": 1.0
                }
            }
        """
        return self.brewsignal_extensions.get('batch_defaults', {})

    @property
    def yeast_management_config(self) -> Dict[str, Any]:
        """Get yeast management configuration from extensions.

        Example:
            {
                "pitch_rate_million_cells_ml_plato": 0.75,
                "starter_required": false,
                "rehydration_temp_c": 35.0,
                "rehydration_time_minutes": 15
            }
        """
        return self.brewsignal_extensions.get('yeast_management', {})
```

**Testing:**
- [ ] Test property access with extensions present
- [ ] Test property access with empty format_extensions
- [ ] Test property access with format_extensions = None
- [ ] Test property access with partial extensions
- [ ] Integration test with batch creation using `batch_defaults`

### Phase 5: Testing & Documentation (Priority 4)

**Test Files:**
- `tests/test_brewsignal_validator.py` - Validator unit tests
- `tests/test_beerjson_to_brewsignal.py` - BeerJSON → BrewSignal conversion
- `tests/test_brewsignal_to_beerjson.py` - BrewSignal → BeerJSON conversion
- `tests/test_brewsignal_roundtrip.py` - Round-trip conversion tests
- `tests/test_recipe_properties.py` - Model property tests

**Round-Trip Test Strategy:**

```python
@pytest.mark.asyncio
async def test_beerjson_brewsignal_beerjson_roundtrip():
    """Test lossless round-trip conversion."""
    # Load BeerJSON example
    with open("examples/beerjson/west-coast-ipa.json") as f:
        original_beerjson = json.load(f)

    # Convert to BrewSignal
    converter_to_bs = BeerJSONToBrewSignalConverter()
    brewsignal = converter_to_bs.convert(original_beerjson)

    # Convert back to BeerJSON
    converter_to_bj = BrewSignalToBeerJSONConverter()
    roundtrip_beerjson = converter_to_bj.convert(brewsignal)

    # Key fields should match (allowing for precision loss)
    original_recipe = original_beerjson["beerjson"]["recipes"][0]
    roundtrip_recipe = roundtrip_beerjson["beerjson"]["recipes"][0]

    assert original_recipe["name"] == roundtrip_recipe["name"]
    assert_gravity_equal(original_recipe["original_gravity"], roundtrip_recipe["original_gravity"])
    assert_gravity_equal(original_recipe["final_gravity"], roundtrip_recipe["final_gravity"])

    # Extensions should be preserved
    original_ext = original_recipe.get("_extensions", {}).get("brewsignal", {})
    roundtrip_ext = roundtrip_recipe.get("_extensions", {}).get("brewsignal", {})
    assert original_ext == roundtrip_ext

def assert_gravity_equal(a: dict, b: dict, tolerance=0.001):
    """Compare gravity values with tolerance for floating point precision."""
    assert abs(a["value"] - b["value"]) < tolerance
    assert a["unit"] == b["unit"]
```

**Documentation Tasks:**
- [ ] Update `docs/BREWSIGNAL_RECIPE_FORMAT_V1.md` with implementation notes
- [ ] Add converter usage examples to docstrings
- [ ] Update `CLAUDE.md` with BrewSignal format patterns
- [ ] Add API documentation for validation endpoint (when created)

---

## Success Criteria

### Functional Requirements

- [ ] **Validation**: Can validate `.brewsignal` file and receive detailed errors with field paths
- [ ] **BeerJSON Import**: Can convert BeerJSON to BrewSignal format (unwrap units, map fields)
- [ ] **BrewSignal Export**: Can convert BrewSignal to BeerJSON format (wrap units, preserve extensions)
- [ ] **Round-Trip**: BeerJSON → BrewSignal → BeerJSON preserves all data (lossless)
- [ ] **Model Access**: Recipe properties provide easy access to extensions
- [ ] **Warnings**: Validation warnings catch unusual but valid values
- [ ] **Multi-Yeast**: BeerJSON multi-yeast converts predictably to single yeast
- [ ] **Temperature**: All temperatures in Celsius, auto-convert Fahrenheit on import

### Quality Requirements

- [ ] **Pattern Compliance**: Follows existing codebase patterns (tuple returns, Registry, etc.)
- [ ] **Test Coverage**: >90% coverage for validators and converters
- [ ] **Performance**: Validation completes in <100ms for typical recipe
- [ ] **Error Messages**: Clear, actionable error messages with field paths
- [ ] **Documentation**: All public methods have docstrings with examples

### Non-Functional Requirements

- [ ] **Backward Compatibility**: Doesn't break existing BeerJSON/BeerXML import
- [ ] **Database Migration**: Recipe.format_extensions structure backwards compatible
- [ ] **Type Safety**: Full type hints for all functions
- [ ] **Extensibility**: Easy to add new warnings or field mappings

---

## Dependencies & Risks

### Dependencies

**Internal:**
- Existing validator pattern: `backend/services/validators/beerjson_validator.py`
- Existing converter pattern: `backend/services/converters/beerxml_to_beerjson.py`
- Recipe model: `backend/models.py::Recipe`
- JSON schema: `backend/schemas/brewsignal-recipe-v1.0.schema.json` (EXISTS)

**External:**
- jsonschema >= 4.20 ✓ (installed)
- referencing >= 0.30 ✓ (installed)

**Blocks:**
- tilt_ui-40f: Export endpoint needs converters from this task
- tilt_ui-a6v: Validation endpoint needs validator from this task
- tilt_ui-pbp: Round-trip tests need converters from this task

### Risks

**Risk 1: Multi-Yeast Data Loss**
- **Mitigation:** Document limitation in BrewSignal v1.0, store additional cultures in database
- **Impact:** Users with multi-yeast recipes may lose data in export
- **Future:** BrewSignal v1.1 could support `yeasts` array

**Risk 2: Precision Loss in Round-Trips**
- **Mitigation:** Define rounding rules, test with property-based tests
- **Impact:** Repeated conversions may accumulate floating-point errors
- **Solution:** Store original BeerJSON for lossless export

**Risk 3: Extension Version Incompatibility**
- **Mitigation:** Version check with warning (not error)
- **Impact:** Future extension changes may break old recipes
- **Solution:** Extension migration system in future

**Risk 4: Temperature Unit Confusion**
- **Mitigation:** Auto-convert F→C on import, validate C-only on export
- **Impact:** Users may not realize their Fahrenheit values were converted
- **Solution:** Log warning when auto-conversion occurs

---

## References & Research

### Internal Code References

**Validation Pattern:**
- `backend/services/validators/beerjson_validator.py:1-183` - BeerJSONValidator class structure
- `backend/services/validators/beerjson_validator.py:102-127` - validate() method pattern
- `backend/services/validators/beerjson_validator.py:134-162` - Error formatting pattern

**Converter Pattern:**
- `backend/services/converters/beerxml_to_beerjson.py:5-508` - BeerXMLToBeerJSONConverter class
- `backend/services/converters/beerxml_to_beerjson.py:367-429` - Unit conversion helpers
- `backend/services/serializers/recipe_serializer.py:16-574` - RecipeSerializer (DB storage)

**Model Structure:**
- `backend/models.py:247-338` - Recipe model with format_extensions JSON column
- `backend/models.py:439-583` - RecipeHop property methods example

### Specification Files

- `docs/BREWSIGNAL_RECIPE_FORMAT_V1.md` - Full format specification (13 sections)
- `backend/schemas/brewsignal-recipe-v1.0.schema.json` - JSON Schema Draft 07
- `examples/recipes/minimal-pale-ale.brewsignal` - Minimal valid example
- `examples/recipes/west-coast-ipa-complete.brewsignal` - Complete example with extensions

### External Documentation

**jsonschema:**
- [jsonschema 4.25.1 Documentation](https://python-jsonschema.readthedocs.io/en/stable/)
- [Handling Validation Errors](https://python-jsonschema.readthedocs.io/en/stable/errors/)
- [Schema Referencing](https://python-jsonschema.readthedocs.io/en/stable/referencing/)

**SQLAlchemy:**
- [JSON Types - SQLAlchemy 2.0](https://docs.sqlalchemy.org/en/20/core/type_basics.html#sqlalchemy.types.JSON)
- [Hybrid Attributes](https://docs.sqlalchemy.org/en/20/orm/extensions/hybrid.html)

**Best Practices:**
- [Property-Based Testing with Hypothesis](https://hypothesis.readthedocs.io/)
- [Lossless Round-Trip Conversion Patterns](https://www.peterbe.com/plog/jsonschema-validate-10x-faster-in-python)

### Similar Issues

- BeerJSON validator implementation (reference pattern)
- BeerXML to BeerJSON converter (reference pattern)
- Recipe import pipeline (integration point)

---

## Notes

### Critical Decisions Made

**Decision 1: Split into validators/ and converters/**
- **Reasoning:** Follows existing codebase structure, better separation of concerns
- **Alternative:** Single `brewsignal_format.py` file (as in issue description)
- **Chosen:** Directory structure for consistency with BeerJSON implementation

**Decision 2: Multi-Yeast Handling**
- **Reasoning:** BrewSignal v1.0 targets single fermentation scenarios
- **Alternative:** Support `yeasts` array in BrewSignal format
- **Chosen:** Single yeast object, document limitation, defer array support to v1.1

**Decision 3: Round-Trip Preservation**
- **Reasoning:** Ecosystem interoperability requires lossless BeerJSON export
- **Alternative:** Lossy conversion (simpler but breaks workflows)
- **Chosen:** Store original BeerJSON, merge on export

**Decision 4: Temperature Philosophy**
- **Reasoning:** Celsius is international standard, brewing science standard, Home Assistant default
- **Alternative:** Store user's original unit
- **Chosen:** Always Celsius, convert at boundaries (Tilt ingestion, UI display)

**Decision 5: Validation Warnings**
- **Reasoning:** Help users catch mistakes without blocking workflow
- **Alternative:** Schema-only validation
- **Chosen:** Two-level validation (schema + business logic warnings)

### Open Questions (Resolved)

**Q: Where to store original BeerJSON for round-trip?**
- **Answer:** `Recipe.format_extensions.beerjson_original` as JSON string

**Q: HTTP status for validation endpoint?**
- **Answer:** HTTP 200 with `{valid: false}` (validation is a service, not a state error)

**Q: Null vs missing for optional fields?**
- **Answer:** Omit optional fields, don't use null for numbers (except strings)

**Q: Export filename pattern?**
- **Answer:** `{recipe-name-slug}-{YYYY-MM-DD}.brewsignal`

**Q: Temperature unit in hop timing?**
- **Answer:** Auto-convert F→C on import, warn if mixed units detected

### Future Enhancements (Out of Scope for v1.0)

- Batch import endpoint (multiple recipes at once)
- BrewSignal format support for multiple yeasts (`yeasts` array)
- Extension migration system for version upgrades
- Content-Type negotiation via Accept header
- Localization for error messages
- Recipe diff/merge tool for resolving conflicts

---

**Created:** 2025-12-10
**Last Updated:** 2025-12-10
**Status:** Ready for Review
