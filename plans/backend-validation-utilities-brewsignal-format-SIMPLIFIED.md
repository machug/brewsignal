# Backend Validation Utilities for BrewSignal Recipe Format v1.0 (SIMPLIFIED)

**Issue:** tilt_ui-4hu
**Type:** Task
**Priority:** P2
**Status:** Planning - Revised after review feedback
**Created:** 2025-12-10
**Revised:** 2025-12-10

---

## Overview

Create minimal backend utilities for validating and converting BrewSignal Recipe Format v1.0. This is a **significantly simplified** version based on unanimous reviewer feedback to avoid over-engineering.

**Target Implementation:** ~230 lines (down from ~1800 in original plan)

**Location:** `backend/services/brewsignal_format.py` (single file, as specified in issue)

**Blocks:**
- tilt_ui-40f: Add recipe export endpoint with format selection
- tilt_ui-a6v: Add recipe validation endpoint
- tilt_ui-pbp: Round-trip conversion tests (BrewSignal ↔ BeerJSON)

---

## Key Simplifications from Review Feedback

### Removed Features (YAGNI Violations)
1. ❌ **Round-trip preservation** - Don't store original BeerJSON. Database is source of truth.
2. ❌ **Business logic warnings system** - Schema validation is sufficient. Add warnings when users actually need them.
3. ❌ **Model properties** - Access `format_extensions` dict directly. No convenience wrappers.
4. ❌ **Temperature auto-conversion** - Reject non-Celsius temperatures. Don't massage bad data.
5. ❌ **Complex multi-yeast handling** - Take first culture. Document limitation. Done.
6. ❌ **Precision rounding rules** - Let Python handle float serialization.
7. ❌ **Custom ValidationResult models** - Use existing `Tuple[bool, List[str]]` pattern.
8. ❌ **Property-based testing** - Basic validation tests only.

### Design Decisions

**Use Pydantic for Validation:**
- FastAPI already uses Pydantic
- Automatic validation, serialization, documentation
- No need for separate JSON schema validator class

**Build One Converter First:**
- Determine which direction is needed for blocked issues
- Likely: BeerJSON → BrewSignal (for import)
- Add reverse converter only when actually needed

**Simple Multi-Yeast:**
- BrewSignal v1.0 = single yeast object
- BeerJSON = array of cultures
- Solution: Take first culture, ignore rest, document limitation

**Reject Non-Celsius:**
- Spec says "all temperatures in Celsius"
- Don't auto-convert Fahrenheit
- Validation error if unit != "C"
- User fixes source data

---

## Proposed Solution

### Architecture (Simplified)

```
backend/services/brewsignal_format.py
├── BrewSignalRecipe (Pydantic model with validators)
├── BeerJSONToBrewSignalConverter (class)
└── BrewSignalToBeerJSONConverter (class) [OPTIONAL - add later if needed]
```

That's it. One file, ~230 lines.

### Components

#### 1. Pydantic Model (`BrewSignalRecipe`)

**Responsibilities:**
- Define BrewSignal format structure
- Automatic validation via Pydantic
- FastAPI integration (no extra code needed)

**Example:**
```python
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List

class BrewSignalRecipe(BaseModel):
    """BrewSignal Recipe Format v1.0

    Simplified format for fermentation monitoring.
    All temperatures in Celsius. All measurements as raw numbers.
    """
    brewsignal_version: str = Field(default="1.0")
    name: str
    og: float = Field(ge=1.0, le=1.2)
    fg: float = Field(ge=1.0, le=1.2)
    abv: Optional[float] = Field(None, ge=0, le=20)
    ibu: Optional[float] = Field(None, ge=0, le=200)
    color_srm: Optional[float] = Field(None, ge=0, le=100)
    batch_size_liters: Optional[float] = Field(None, gt=0)
    boil_time_minutes: Optional[int] = Field(None, ge=0)
    efficiency_percent: Optional[float] = Field(None, ge=0, le=100)
    carbonation_vols: Optional[float] = Field(None, ge=0, le=5)
    # ... other fields

    @field_validator('fg')
    @classmethod
    def fg_less_than_og(cls, v, info):
        """Ensure FG < OG"""
        if 'og' in info.data and v >= info.data['og']:
            raise ValueError('FG must be less than OG')
        return v

    class Config:
        # Omit None values in dict export
        exclude_none = True
        json_schema_extra = {
            "example": {
                "brewsignal_version": "1.0",
                "name": "West Coast IPA",
                "og": 1.065,
                "fg": 1.012,
                "abv": 6.9
            }
        }
```

**Why Pydantic?**
- FastAPI uses Pydantic for request/response models
- Automatic validation (no manual validator class needed)
- Automatic OpenAPI docs generation
- Type safety
- Already in your stack

#### 2. BeerJSON → BrewSignal Converter

**Responsibilities:**
- Unwrap BeerJSON unit objects → raw values
- Map verbose names → short names
- Take first yeast culture from cultures array
- Extract timing objects to simple format

**Pattern:** Follows existing `BeerXMLToBeerJSONConverter` class pattern

**Example:**
```python
class BeerJSONToBrewSignalConverter:
    """Convert BeerJSON 1.0 to BrewSignal Format v1.0"""

    def convert(self, beerjson: dict) -> dict:
        """Convert BeerJSON document to BrewSignal format.

        Args:
            beerjson: BeerJSON 1.0 document

        Returns:
            BrewSignal format dict

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
        return {
            "name": recipe["name"],
            "og": self._unwrap_gravity(recipe.get("original_gravity")),
            "fg": self._unwrap_gravity(recipe.get("final_gravity")),
            "abv": self._unwrap_percent(recipe.get("alcohol_by_volume")),
            "ibu": self._unwrap_number(recipe.get("ibu_estimate")),
            "color_srm": self._unwrap_number(recipe.get("color")),
            "batch_size_liters": self._unwrap_volume(recipe.get("batch_size")),
            "fermentables": self._convert_fermentables(recipe.get("ingredients", {}).get("fermentable_additions", [])),
            "hops": self._convert_hops(recipe.get("ingredients", {}).get("hop_additions", [])),
            "yeast": self._convert_yeast(recipe.get("ingredients", {}).get("culture_additions", [])),
            # ... other fields
        }

    def _unwrap_gravity(self, unit_obj: Optional[dict]) -> Optional[float]:
        """Extract gravity value from unit object."""
        if not unit_obj:
            return None
        return unit_obj["value"]

    def _unwrap_volume(self, unit_obj: Optional[dict]) -> Optional[float]:
        """Extract volume in liters from unit object."""
        if not unit_obj:
            return None
        value = unit_obj["value"]
        unit = unit_obj["unit"]
        # Convert to liters
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

    def _convert_yeast(self, cultures: List[dict]) -> Optional[dict]:
        """Convert BeerJSON cultures array to single BrewSignal yeast.

        BrewSignal v1.0 supports single yeast only.
        Takes first culture from array.
        """
        if not cultures:
            return None

        # Take first culture
        culture = cultures[0]

        return {
            "name": culture.get("name"),
            "producer": culture.get("producer"),
            "product_id": culture.get("product_id"),
            "type": culture.get("type"),
            "form": culture.get("form"),
            "attenuation_percent": self._unwrap_percent(culture.get("attenuation")),
            "temp_min_c": self._unwrap_temperature(culture.get("temperature_range", {}).get("minimum")),
            "temp_max_c": self._unwrap_temperature(culture.get("temperature_range", {}).get("maximum")),
            "amount_grams": self._unwrap_mass(culture.get("amount")),
        }
```

**Why This Approach?**
- Clean separation of concerns
- Easy to test each helper method
- Follows existing converter pattern in codebase
- No magic - explicit field mapping

#### 3. BrewSignal → BeerJSON Converter (OPTIONAL)

**Build this ONLY if needed for blocked issues.**

Check issues tilt_ui-40f, tilt_ui-a6v, tilt_ui-pbp:
- Do they need export to BeerJSON?
- Or just validation and import?

If export is needed, implement symmetric converter:
```python
class BrewSignalToBeerJSONConverter:
    """Convert BrewSignal Format v1.0 to BeerJSON 1.0"""

    def convert(self, brewsignal: dict) -> dict:
        """Convert BrewSignal to BeerJSON."""
        recipe = brewsignal["recipe"]

        return {
            "beerjson": {
                "version": 1.0,
                "recipes": [self._convert_recipe(recipe)]
            }
        }

    def _convert_recipe(self, recipe: dict) -> dict:
        """Convert BrewSignal recipe to BeerJSON format."""
        return {
            "name": recipe["name"],
            "original_gravity": self._wrap_gravity(recipe.get("og")),
            "final_gravity": self._wrap_gravity(recipe.get("fg")),
            "alcohol_by_volume": self._wrap_percent(recipe.get("abv")),
            # ... wrap all fields with unit objects
        }

    def _wrap_gravity(self, value: Optional[float]) -> Optional[dict]:
        """Wrap raw gravity value in BeerJSON unit object."""
        if value is None:
            return None
        return {"value": value, "unit": "sg"}
```

---

## Field Mapping Reference

### Core Recipe Fields

| BeerJSON Field | BrewSignal Field | Conversion |
|----------------|------------------|------------|
| `original_gravity.value` | `og` | Unwrap |
| `final_gravity.value` | `fg` | Unwrap |
| `alcohol_by_volume.value` | `abv` | Unwrap (already 0-100 scale) |
| `ibu_estimate.value` | `ibu` | Unwrap |
| `color.value` | `color_srm` | Unwrap |
| `batch_size.value` (l) | `batch_size_liters` | Unwrap + convert |
| `boil_time.value` (min) | `boil_time_minutes` | Unwrap |
| `efficiency.brewhouse.value` | `efficiency_percent` | Unwrap |
| `carbonation.value` | `carbonation_vols` | Unwrap |

### Fermentables

| BeerJSON Field | BrewSignal Field | Notes |
|----------------|------------------|-------|
| `fermentable_additions[]` | `fermentables[]` | Array mapping |
| `fermentable.name` | `name` | Direct |
| `fermentable.type` | `type` | Direct |
| `fermentable.yield.fine_grind.value` | `yield_percent` | Unwrap |
| `fermentable.color.value` | `color_srm` | Unwrap |
| `amount.value` (kg) | `amount_kg` | Unwrap + convert |

### Hops

| BeerJSON Field | BrewSignal Field | Notes |
|----------------|------------------|-------|
| `hop_additions[]` | `hops[]` | Array mapping |
| `hop.name` | `name` | Direct |
| `hop.form` | `form` | Direct |
| `alpha_acid.value` | `alpha_acid_percent` | Unwrap |
| `amount.value` (g) | `amount_grams` | Unwrap + convert |
| `timing` | `timing` | Keep nested object |

### Yeast (Multi → Single)

| BeerJSON Field | BrewSignal Field | Notes |
|----------------|------------------|-------|
| `culture_additions[0]` | `yeast` | **Take first culture only** |
| `culture.name` | `name` | Direct |
| `culture.producer` | `producer` | Direct |
| `culture.type` | `type` | Direct |
| `culture.form` | `form` | Direct |
| `attenuation.value` | `attenuation_percent` | Unwrap |
| `temperature_range.minimum.value` | `temp_min_c` | Unwrap (must be C) |
| `temperature_range.maximum.value` | `temp_max_c` | Unwrap (must be C) |
| `amount.value` (g or ml) | `amount_grams` | Unwrap + convert |

---

## Implementation Plan

### Phase 1: Pydantic Model (~80 lines)

**File:** `backend/services/brewsignal_format.py`

**Tasks:**
1. Create `BrewSignalRecipe` Pydantic model
2. Define all fields with types and constraints
3. Add field validators (FG < OG)
4. Add nested models for fermentables, hops, yeast
5. Set `exclude_none=True` config

**Test:**
```python
# Valid recipe
recipe = BrewSignalRecipe(name="IPA", og=1.055, fg=1.012)
assert recipe.og == 1.055

# Invalid range
with pytest.raises(ValidationError):
    BrewSignalRecipe(name="IPA", og=1.5, fg=1.012)
```

### Phase 2: BeerJSON → BrewSignal Converter (~100 lines)

**File:** Same file `backend/services/brewsignal_format.py`

**Tasks:**
1. Create `BeerJSONToBrewSignalConverter` class
2. Implement `convert()` method
3. Implement unwrap helpers:
   - `_unwrap_gravity()`
   - `_unwrap_volume()` with unit conversion
   - `_unwrap_temperature()` with Celsius-only validation
   - `_unwrap_mass()` with unit conversion
   - `_unwrap_percent()`
4. Implement array converters:
   - `_convert_fermentables()`
   - `_convert_hops()`
   - `_convert_yeast()` (take first culture)
5. Handle missing/None fields

**Test:**
```python
beerjson = {
    "beerjson": {
        "version": 1.0,
        "recipes": [{
            "name": "IPA",
            "original_gravity": {"value": 1.055, "unit": "sg"},
            "final_gravity": {"value": 1.012, "unit": "sg"}
        }]
    }
}

converter = BeerJSONToBrewSignalConverter()
brewsignal = converter.convert(beerjson)

assert brewsignal["recipe"]["name"] == "IPA"
assert brewsignal["recipe"]["og"] == 1.055
assert brewsignal["recipe"]["fg"] == 1.012
```

### Phase 3: BrewSignal → BeerJSON Converter (~50 lines) [OPTIONAL]

**Only implement if needed for export endpoint (issue tilt_ui-40f)**

**Tasks:**
1. Create `BrewSignalToBeerJSONConverter` class
2. Implement `convert()` method
3. Implement wrap helpers (symmetric to unwrap)
4. Handle array conversions

**Defer until confirmed needed.**

### Phase 4: Testing (~100 lines)

**File:** `tests/test_brewsignal_format.py`

**Test Cases:**

```python
import pytest
from pydantic import ValidationError
from backend.services.brewsignal_format import (
    BrewSignalRecipe,
    BeerJSONToBrewSignalConverter
)

# === Pydantic Validation Tests ===

def test_minimal_valid_recipe():
    """Minimal recipe with only required fields validates."""
    recipe = BrewSignalRecipe(
        name="Test",
        og=1.050,
        fg=1.010
    )
    assert recipe.name == "Test"
    assert recipe.og == 1.050
    assert recipe.fg == 1.010

def test_missing_required_field():
    """Missing required field raises ValidationError."""
    with pytest.raises(ValidationError) as exc_info:
        BrewSignalRecipe(name="Test", og=1.050)
    assert "fg" in str(exc_info.value)

def test_og_out_of_range():
    """OG above 1.200 fails validation."""
    with pytest.raises(ValidationError):
        BrewSignalRecipe(name="Test", og=1.5, fg=1.010)

def test_fg_greater_than_og():
    """FG >= OG fails custom validator."""
    with pytest.raises(ValidationError) as exc_info:
        BrewSignalRecipe(name="Test", og=1.050, fg=1.055)
    assert "FG must be less than OG" in str(exc_info.value)

def test_exclude_none_fields():
    """None fields are excluded from dict export."""
    recipe = BrewSignalRecipe(name="Test", og=1.050, fg=1.010, abv=None)
    d = recipe.model_dump(exclude_none=True)
    assert "abv" not in d

# === BeerJSON → BrewSignal Conversion Tests ===

def test_convert_minimal_beerjson():
    """Convert minimal BeerJSON recipe."""
    beerjson = {
        "beerjson": {
            "version": 1.0,
            "recipes": [{
                "name": "Test IPA",
                "original_gravity": {"value": 1.065, "unit": "sg"},
                "final_gravity": {"value": 1.012, "unit": "sg"}
            }]
        }
    }

    converter = BeerJSONToBrewSignalConverter()
    result = converter.convert(beerjson)

    assert result["brewsignal_version"] == "1.0"
    assert result["recipe"]["name"] == "Test IPA"
    assert result["recipe"]["og"] == 1.065
    assert result["recipe"]["fg"] == 1.012

def test_convert_volume_units():
    """Volume conversions (gallons to liters)."""
    beerjson = {
        "beerjson": {
            "version": 1.0,
            "recipes": [{
                "name": "Test",
                "original_gravity": {"value": 1.050, "unit": "sg"},
                "final_gravity": {"value": 1.010, "unit": "sg"},
                "batch_size": {"value": 5, "unit": "gal"}
            }]
        }
    }

    converter = BeerJSONToBrewSignalConverter()
    result = converter.convert(beerjson)

    # 5 gallons ≈ 18.927 liters
    assert abs(result["recipe"]["batch_size_liters"] - 18.927) < 0.01

def test_reject_fahrenheit_temperature():
    """Non-Celsius temperatures raise ValueError."""
    beerjson = {
        "beerjson": {
            "version": 1.0,
            "recipes": [{
                "name": "Test",
                "original_gravity": {"value": 1.050, "unit": "sg"},
                "final_gravity": {"value": 1.010, "unit": "sg"},
                "ingredients": {
                    "culture_additions": [{
                        "name": "US-05",
                        "temperature_range": {
                            "minimum": {"value": 60, "unit": "F"}  # Fahrenheit!
                        }
                    }]
                }
            }]
        }
    }

    converter = BeerJSONToBrewSignalConverter()

    with pytest.raises(ValueError) as exc_info:
        converter.convert(beerjson)

    assert "Celsius" in str(exc_info.value)
    assert "F" in str(exc_info.value)

def test_multi_yeast_takes_first():
    """Multiple yeast cultures - take first, ignore rest."""
    beerjson = {
        "beerjson": {
            "version": 1.0,
            "recipes": [{
                "name": "Test",
                "original_gravity": {"value": 1.050, "unit": "sg"},
                "final_gravity": {"value": 1.010, "unit": "sg"},
                "ingredients": {
                    "culture_additions": [
                        {"name": "US-05", "type": "ale"},
                        {"name": "WLP001", "type": "ale"}  # Ignored
                    ]
                }
            }]
        }
    }

    converter = BeerJSONToBrewSignalConverter()
    result = converter.convert(beerjson)

    assert result["recipe"]["yeast"]["name"] == "US-05"
    # Second culture is dropped (documented limitation)

def test_convert_full_recipe(full_beerjson_example):
    """Convert complete BeerJSON recipe with all fields."""
    converter = BeerJSONToBrewSignalConverter()
    result = converter.convert(full_beerjson_example)

    # Validate result with Pydantic model
    recipe = BrewSignalRecipe(**result)

    assert recipe.name == "West Coast IPA"
    assert recipe.og == 1.065
    assert len(recipe.fermentables) == 2
    assert len(recipe.hops) == 3
    assert recipe.yeast.name == "US-05"
```

**Total test lines: ~100**

---

## Success Criteria

### Functionality

- ✅ Pydantic model validates BrewSignal format
- ✅ BeerJSON → BrewSignal conversion works
- ✅ FastAPI endpoints can use `BrewSignalRecipe` directly
- ✅ Non-Celsius temperatures are rejected
- ✅ Multi-yeast BeerJSON converts to single yeast
- ✅ All tests pass

### Code Quality

- ✅ Single file (~230 lines total)
- ✅ Uses existing patterns (Pydantic, converter classes)
- ✅ No unnecessary abstractions
- ✅ Type hints on all methods
- ✅ Docstrings on public methods

### Integration

- ✅ Unblocks issue tilt_ui-a6v (validation endpoint)
- ✅ Unblocks issue tilt_ui-40f (export endpoint) if reverse converter is implemented
- ✅ Compatible with existing `Recipe` model

---

## Risk Analysis

### Risk 1: Multi-Yeast Data Loss

**Mitigation:** Document clearly in:
- Converter docstring
- BrewSignal format spec
- API endpoint documentation

**Alternative:** Store additional cultures in `Recipe.format_extensions` for future use

### Risk 2: Missing Export Converter

**Mitigation:** Verify blocked issues actually need export before implementing reverse converter

### Risk 3: Pydantic Validation Too Strict

**Mitigation:** Use `Optional` fields liberally. Only require name, og, fg. Everything else optional.

---

## Comparison: Original vs Simplified

| Aspect | Original Plan | Simplified Plan | Reduction |
|--------|--------------|-----------------|-----------|
| **Total LOC** | ~1800 lines | ~230 lines | **87% less** |
| **Files** | 5 files | 1 file | **80% fewer** |
| **Validator** | Custom class + schema loader | Pydantic model | Built-in |
| **Warnings** | 11 warning types | None (schema only) | Removed |
| **Round-trip** | Deep merge + storage | Simple conversion | Removed |
| **Properties** | 4 @property methods | None | Removed |
| **Temp handling** | Auto-convert F→C | Reject non-C | Simpler |
| **Multi-yeast** | Complex extraction | Take first | Simpler |
| **Testing** | 5 test files, Hypothesis | 1 test file, basic | 80% less |
| **Directories** | validators/, converters/ | Single file | Simpler |

---

## Implementation Estimate

**Phase 1 (Pydantic):** 1 hour
**Phase 2 (Converter):** 2 hours
**Phase 3 (Tests):** 1 hour
**Total:** ~4 hours

(Original plan: ~20 hours)

---

## Next Steps

1. ✅ Get user approval on simplified approach
2. Determine if reverse converter (BrewSignal → BeerJSON) is needed
3. Implement Phase 1 (Pydantic model)
4. Implement Phase 2 (BeerJSON → BrewSignal)
5. Implement Phase 4 (Tests)
6. Optionally implement Phase 3 (reverse converter) if needed
7. Update blocked issues with implementation status

---

## References

- **Original Plan:** `plans/backend-validation-utilities-brewsignal-format.md`
- **Review Feedback:**
  - DHH Rails Reviewer: "Wildly over-engineered"
  - Kieran Rails Reviewer: "Reduce scope by 30%"
  - Code Simplicity Reviewer: "40% can be removed"
- **BrewSignal Spec:** `docs/BREWSIGNAL_RECIPE_FORMAT_V1.md`
- **JSON Schema:** `backend/schemas/brewsignal-recipe-v1.0.schema.json`
- **Existing Patterns:**
  - `backend/services/validators/beerjson_validator.py`
  - `backend/services/converters/beerxml_to_beerjson.py`
