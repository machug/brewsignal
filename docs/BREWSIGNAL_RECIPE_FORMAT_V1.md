# BrewSignal Recipe Format v1.0

**Status:** Draft Specification
**Date:** 2025-12-09
**Author:** BrewSignal Development Team

---

## 1. Overview

The **BrewSignal Recipe Format v1.0** is a simplified, human-readable JSON format optimized for fermentation monitoring and temperature control. It formalizes the current API response format used by BrewSignal and provides a cleaner alternative to verbose BeerJSON 1.0 for manual recipe creation and editing.

### Key Principles

1. **Simplicity**: Gravity as raw numbers (`1.050` not `{"value": 1.050, "unit": "sg"}`)
2. **Readability**: Intuitive field names (`og` not `original_gravity`, `abv` not `alcohol_by_volume`)
3. **Fermentation-First**: Optimized for tracking fermentation, not brew day complexity
4. **Celsius-Native**: All temperatures in Celsius (BrewSignal's internal standard)
5. **BeerJSON Compatibility**: Can convert to/from BeerJSON 1.0 for ecosystem interop

### Format Goals

- ✅ **Human-editable**: Simple enough to write by hand or edit in a text editor
- ✅ **Fermentation-focused**: Captures OG, FG, yeast, and temperature control settings
- ✅ **Extensible**: `brewsignal_extensions` for custom features
- ✅ **API-aligned**: Matches existing API response format (no breaking changes)

---

## 2. File Format

### Extension

- **Primary**: `.brewsignal` (distinctive, memorable)
- **Alternative**: `.brewsignal.json` (explicit JSON indication)

### MIME Type

```
application/vnd.brewsignal.v1+json
```

### Encoding

- **Character Set**: UTF-8 (required)
- **Line Endings**: LF (`\n`) preferred, CRLF (`\r\n`) accepted
- **Compression**: Optional gzip (`.brewsignal.gz`)

---

## 3. Schema Structure

### 3.1 Root Object

```json
{
  "brewsignal_version": "1.0",
  "recipe": { /* Recipe object */ }
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `brewsignal_version` | string | **Yes** | Format version (semantic versioning) |
| `recipe` | object | **Yes** | Recipe data object |

### 3.2 Recipe Object

```json
{
  "name": "West Coast IPA",
  "author": "Brewer Name",
  "type": "All Grain",
  "style_id": "bjcp-2021-21a",

  // Gravity & ABV
  "og": 1.065,
  "fg": 1.012,
  "abv": 6.9,
  "ibu": 65.0,
  "color_srm": 7.0,

  // Batch parameters
  "batch_size_liters": 19.0,
  "boil_time_minutes": 60,
  "efficiency_percent": 75.0,

  // Carbonation
  "carbonation_vols": 2.5,

  // Ingredients
  "fermentables": [ /* ... */ ],
  "hops": [ /* ... */ ],
  "yeast": { /* ... */ },
  "miscs": [ /* ... */ ],

  // Process
  "mash_steps": [ /* ... */ ],
  "fermentation_steps": [ /* ... */ ],

  // BrewSignal Extensions
  "brewsignal_extensions": { /* ... */ },

  // Metadata
  "notes": "Brew notes here",
  "created_at": "2025-12-09T08:00:00Z"
}
```

#### Core Fields

| Field | Type | Required | Range | Description |
|-------|------|----------|-------|-------------|
| `name` | string | **Yes** | 1-200 chars | Recipe name |
| `author` | string | No | 0-100 chars | Recipe author |
| `type` | string | No | - | "All Grain", "Extract", "Partial Mash" |
| `style_id` | string | No | - | Style reference (e.g., "bjcp-2021-21a") |

#### Gravity & Alcohol

| Field | Type | Required | Range | Description |
|-------|------|----------|-------|-------------|
| `og` | number | **Yes** | 1.000-1.200 | Original gravity (SG) |
| `fg` | number | **Yes** | 1.000-1.200 | Final gravity (SG) |
| `abv` | number | No | 0-20 | Alcohol by volume (percent, 0-100 scale) |
| `ibu` | number | No | 0-200 | International Bitterness Units |
| `color_srm` | number | No | 0-100 | Color in SRM |

**Note**: Gravity values are always in Specific Gravity (SG) format. No unit wrapping.

#### Batch Parameters

| Field | Type | Required | Range | Description |
|-------|------|----------|-------|-------------|
| `batch_size_liters` | number | No | 1-1000 | Batch size in liters |
| `boil_time_minutes` | integer | No | 0-300 | Boil time in minutes |
| `efficiency_percent` | number | No | 0-100 | Brewhouse efficiency (percent) |
| `carbonation_vols` | number | No | 0-5 | CO2 volumes |

#### Metadata

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `notes` | string | No | Brew notes (markdown supported) |
| `created_at` | string | No | ISO 8601 timestamp (UTC, with 'Z' suffix) |

---

### 3.3 Fermentables Array

```json
"fermentables": [
  {
    "name": "Pale Malt",
    "type": "grain",
    "grain_group": "base",
    "amount_kg": 5.0,
    "percentage": 83.3,
    "yield_percent": 80.0,
    "color_srm": 2.0,
    "origin": "United States",
    "supplier": "Rahr"
  }
]
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | **Yes** | Fermentable name |
| `type` | string | No | "grain", "extract", "sugar", "adjunct" |
| `grain_group` | string | No | "base", "caramel", "roasted", "specialty" |
| `amount_kg` | number | **Yes** | Amount in kilograms |
| `percentage` | number | No | % of grain bill (0-100) |
| `yield_percent` | number | No | Extract yield (0-100) |
| `color_srm` | number | No | Color in SRM or Lovibond |
| `origin` | string | No | Country of origin |
| `supplier` | string | No | Supplier/maltster |

---

### 3.4 Hops Array

```json
"hops": [
  {
    "name": "Cascade",
    "origin": "United States",
    "form": "pellet",
    "amount_grams": 30.0,
    "alpha_acid_percent": 5.5,
    "beta_acid_percent": 4.5,
    "timing": {
      "use": "add_to_boil",
      "duration": { "value": 60, "unit": "min" }
    }
  }
]
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | **Yes** | Hop variety name |
| `origin` | string | No | Country of origin |
| `form` | string | No | "pellet", "leaf", "plug", "powder" |
| `amount_grams` | number | **Yes** | Amount in grams |
| `alpha_acid_percent` | number | **Yes** | Alpha acids (0-20%) |
| `beta_acid_percent` | number | No | Beta acids (0-20%) |
| `timing` | object | **Yes** | BeerJSON timing object (see below) |

#### Timing Object (BeerJSON-Compatible)

```json
"timing": {
  "use": "add_to_boil",           // Required
  "duration": {                    // Optional
    "value": 60,
    "unit": "min"                  // "min", "day", "hour"
  },
  "continuous": false,             // Optional
  "temperature": {                 // Optional (for hopstands)
    "value": 80,
    "unit": "C"
  }
}
```

**Valid `use` values:**
- `add_to_mash` - First wort hop
- `add_to_boil` - Boil addition
- `add_to_fermentation` - Dry hop
- `add_to_package` - Bottling/kegging

---

### 3.5 Yeast Object

**Note**: BrewSignal simplifies yeast to a single object (not an array), representing the primary yeast strain.

```json
"yeast": {
  "name": "US-05",
  "producer": "Fermentis",
  "product_id": "US-05",
  "type": "ale",
  "form": "dry",
  "attenuation_percent": 81.0,
  "temp_min_c": 15.0,
  "temp_max_c": 24.0,
  "amount_grams": 11.5
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | **Yes** | Yeast strain name |
| `producer` | string | No | Lab/manufacturer (e.g., "Wyeast", "White Labs") |
| `product_id` | string | No | Product code (e.g., "1056", "WLP001") |
| `type` | string | No | "ale", "lager", "wine", "champagne" |
| `form` | string | No | "liquid", "dry", "slant", "culture" |
| `attenuation_percent` | number | No | Expected attenuation (0-100%) |
| `temp_min_c` | number | No | Min fermentation temp (Celsius) |
| `temp_max_c` | number | No | Max fermentation temp (Celsius) |
| `amount_grams` | number | No | Amount in grams (for dry yeast) |
| `amount_ml` | number | No | Amount in milliliters (for liquid yeast) |

**Temperature Units**: Always Celsius. BrewSignal converts to Fahrenheit in UI based on user preference.

---

### 3.6 Fermentation Steps Array

```json
"fermentation_steps": [
  {
    "step_number": 1,
    "type": "primary",
    "temp_c": 18.0,
    "time_days": 10
  },
  {
    "step_number": 2,
    "type": "diacetyl_rest",
    "temp_c": 20.0,
    "time_days": 2
  },
  {
    "step_number": 3,
    "type": "cold_crash",
    "temp_c": 2.0,
    "time_days": 3
  }
]
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `step_number` | integer | **Yes** | Step order (1-based) |
| `type` | string | **Yes** | "primary", "secondary", "conditioning", "diacetyl_rest", "cold_crash" |
| `temp_c` | number | **Yes** | Target temperature (Celsius) |
| `time_days` | integer | **Yes** | Duration in days |

---

### 3.7 BrewSignal Extensions

**Purpose**: Fermentation-specific features not found in standard recipe formats.

```json
"brewsignal_extensions": {
  "version": "1.0",

  "fermentation_tracking": {
    "og_validation": {
      "enabled": true,
      "tolerance_sg": 0.003
    },
    "fg_prediction": {
      "enabled": true,
      "ml_model": "kalman_exponential"
    },
    "anomaly_detection": {
      "stuck_fermentation": true,
      "temperature_alerts": true,
      "min_sg_change_24h": 0.001
    }
  },

  "batch_defaults": {
    "auto_link_device": true,
    "temperature_control": {
      "enabled": true,
      "target_c": 18.0,
      "hysteresis_c": 1.0,
      "min_cycle_time_minutes": 5
    }
  },

  "yeast_management": {
    "pitch_rate_million_cells_ml_plato": 0.75,
    "starter_required": false,
    "rehydration_temp_c": 35.0,
    "rehydration_time_minutes": 15
  }
}
```

#### Extension Fields

**Fermentation Tracking:**
- `og_validation.enabled` (bool) - Enable OG validation on batch start
- `og_validation.tolerance_sg` (number) - Allowed OG deviation (default: 0.003)
- `fg_prediction.enabled` (bool) - Enable ML-based FG prediction
- `fg_prediction.ml_model` (string) - Model type ("kalman_exponential")
- `anomaly_detection.stuck_fermentation` (bool) - Alert on stuck fermentation
- `anomaly_detection.temperature_alerts` (bool) - Alert on temp out of range
- `anomaly_detection.min_sg_change_24h` (number) - Min gravity change/24h

**Batch Defaults:**
- `auto_link_device` (bool) - Auto-link device when creating batch
- `temperature_control.enabled` (bool) - Enable temp control for this recipe
- `temperature_control.target_c` (number) - Default target temp (Celsius)
- `temperature_control.hysteresis_c` (number) - Default hysteresis (Celsius)
- `temperature_control.min_cycle_time_minutes` (integer) - Min on/off time

**Yeast Management:**
- `pitch_rate_million_cells_ml_plato` (number) - Pitch rate (M cells/mL/°P)
- `starter_required` (bool) - Starter calculation flag
- `rehydration_temp_c` (number) - Rehydration temperature (dry yeast)
- `rehydration_time_minutes` (integer) - Rehydration duration

**Privacy/Security Rules:**
- ❌ **NEVER** include Home Assistant entity IDs
- ❌ **NEVER** include device calibration data
- ❌ **NEVER** include network configuration
- ✅ **OK** to include generic equipment profiles
- ✅ **OK** to include temperature control parameters (generic values)

---

## 4. Minimal Recipe Example

**Simplest valid BrewSignal recipe:**

```json
{
  "brewsignal_version": "1.0",
  "recipe": {
    "name": "Simple Pale Ale",
    "og": 1.050,
    "fg": 1.012,
    "fermentables": [
      {
        "name": "Pale Malt",
        "amount_kg": 4.5
      }
    ],
    "hops": [
      {
        "name": "Cascade",
        "amount_grams": 30,
        "alpha_acid_percent": 5.5,
        "timing": {
          "use": "add_to_boil",
          "duration": { "value": 60, "unit": "min" }
        }
      }
    ],
    "yeast": {
      "name": "US-05"
    }
  }
}
```

---

## 5. Complete Recipe Example

**Full-featured BrewSignal recipe with extensions:**

```json
{
  "brewsignal_version": "1.0",
  "recipe": {
    "name": "West Coast IPA",
    "author": "John Brewer",
    "type": "All Grain",
    "style_id": "bjcp-2021-21a",

    "og": 1.065,
    "fg": 1.012,
    "abv": 6.9,
    "ibu": 65.0,
    "color_srm": 7.0,

    "batch_size_liters": 19.0,
    "boil_time_minutes": 60,
    "efficiency_percent": 75.0,
    "carbonation_vols": 2.5,

    "fermentables": [
      {
        "name": "2-Row Pale Malt",
        "type": "grain",
        "grain_group": "base",
        "amount_kg": 5.4,
        "percentage": 90.0,
        "yield_percent": 80.0,
        "color_srm": 2.0,
        "origin": "United States",
        "supplier": "Rahr"
      },
      {
        "name": "Carapils",
        "type": "grain",
        "grain_group": "caramel",
        "amount_kg": 0.6,
        "percentage": 10.0,
        "yield_percent": 75.0,
        "color_srm": 2.0
      }
    ],

    "hops": [
      {
        "name": "Warrior",
        "origin": "United States",
        "form": "pellet",
        "amount_grams": 15.0,
        "alpha_acid_percent": 15.0,
        "timing": {
          "use": "add_to_boil",
          "duration": { "value": 60, "unit": "min" }
        }
      },
      {
        "name": "Cascade",
        "origin": "United States",
        "form": "pellet",
        "amount_grams": 30.0,
        "alpha_acid_percent": 5.5,
        "timing": {
          "use": "add_to_boil",
          "duration": { "value": 10, "unit": "min" }
        }
      },
      {
        "name": "Cascade",
        "form": "pellet",
        "amount_grams": 60.0,
        "alpha_acid_percent": 5.5,
        "timing": {
          "use": "add_to_fermentation",
          "duration": { "value": 7, "unit": "day" }
        }
      }
    ],

    "yeast": {
      "name": "US-05",
      "producer": "Fermentis",
      "product_id": "US-05",
      "type": "ale",
      "form": "dry",
      "attenuation_percent": 81.0,
      "temp_min_c": 15.0,
      "temp_max_c": 24.0,
      "amount_grams": 11.5
    },

    "fermentation_steps": [
      {
        "step_number": 1,
        "type": "primary",
        "temp_c": 18.0,
        "time_days": 10
      },
      {
        "step_number": 2,
        "type": "diacetyl_rest",
        "temp_c": 20.0,
        "time_days": 2
      },
      {
        "step_number": 3,
        "type": "cold_crash",
        "temp_c": 2.0,
        "time_days": 3
      }
    ],

    "brewsignal_extensions": {
      "version": "1.0",
      "fermentation_tracking": {
        "og_validation": {
          "enabled": true,
          "tolerance_sg": 0.003
        },
        "fg_prediction": {
          "enabled": true,
          "ml_model": "kalman_exponential"
        },
        "anomaly_detection": {
          "stuck_fermentation": true,
          "temperature_alerts": true,
          "min_sg_change_24h": 0.001
        }
      },
      "batch_defaults": {
        "auto_link_device": true,
        "temperature_control": {
          "enabled": true,
          "target_c": 18.0,
          "hysteresis_c": 1.0,
          "min_cycle_time_minutes": 5
        }
      },
      "yeast_management": {
        "pitch_rate_million_cells_ml_plato": 0.75,
        "starter_required": false,
        "rehydration_temp_c": 35.0,
        "rehydration_time_minutes": 15
      }
    },

    "notes": "Dry hop on day 7. Keg at 30 PSI for 48 hours to carbonate.",
    "created_at": "2025-12-09T08:00:00Z"
  }
}
```

---

## 6. Validation Rules

### Required Fields

**Root level:**
- `brewsignal_version` (string, must be "1.0")
- `recipe` (object)

**Recipe level:**
- `name` (string, 1-200 chars)
- `og` (number, 1.000-1.200)
- `fg` (number, 1.000-1.200)

**Fermentables:**
- `name` (string)
- `amount_kg` (number, > 0)

**Hops:**
- `name` (string)
- `amount_grams` (number, > 0)
- `alpha_acid_percent` (number, 0-20)
- `timing` (object with valid `use` value)

**Yeast:**
- `name` (string)

### Data Type Validation

```typescript
interface BrewSignalRecipe {
  brewsignal_version: "1.0";
  recipe: {
    // Core
    name: string;                    // 1-200 chars
    author?: string;                 // 0-100 chars
    type?: string;
    style_id?: string;

    // Gravity (SG format)
    og: number;                      // 1.000-1.200
    fg: number;                      // 1.000-1.200
    abv?: number;                    // 0-20
    ibu?: number;                    // 0-200
    color_srm?: number;              // 0-100

    // Batch
    batch_size_liters?: number;      // 1-1000
    boil_time_minutes?: number;      // 0-300
    efficiency_percent?: number;     // 0-100
    carbonation_vols?: number;       // 0-5

    // Ingredients
    fermentables?: Fermentable[];
    hops?: Hop[];
    yeast?: Yeast;
    miscs?: Misc[];

    // Process
    mash_steps?: MashStep[];
    fermentation_steps?: FermentationStep[];

    // Extensions
    brewsignal_extensions?: BrewSignalExtensions;

    // Metadata
    notes?: string;
    created_at?: string;             // ISO 8601 UTC
  };
}
```

### Validation Errors

**Example validation error response:**

```json
{
  "valid": false,
  "errors": [
    {
      "field": "recipe.og",
      "value": 1.250,
      "error": "Value 1.250 exceeds maximum 1.200"
    },
    {
      "field": "recipe.yeast.temp_min_c",
      "value": "cold",
      "error": "Expected number, got string"
    }
  ]
}
```

---

## 7. Conversion to/from BeerJSON 1.0

### BrewSignal → BeerJSON

```python
# Pseudo-code for conversion
def brewsignal_to_beerjson(bs_recipe):
    return {
        "beerjson": {
            "version": 1.0,
            "recipes": [{
                "name": bs_recipe["name"],
                "original_gravity": {
                    "value": bs_recipe["og"],
                    "unit": "sg"
                },
                "final_gravity": {
                    "value": bs_recipe["fg"],
                    "unit": "sg"
                },
                # ... wrap all fields
                "_extensions": {
                    "brewsignal": bs_recipe.get("brewsignal_extensions", {})
                }
            }]
        }
    }
```

### BeerJSON → BrewSignal

```python
# Pseudo-code for conversion
def beerjson_to_brewsignal(bj_recipe):
    return {
        "brewsignal_version": "1.0",
        "recipe": {
            "name": bj_recipe["name"],
            "og": bj_recipe["original_gravity"]["value"],
            "fg": bj_recipe["final_gravity"]["value"],
            # ... unwrap all fields
            "brewsignal_extensions": bj_recipe.get("_extensions", {}).get("brewsignal", {})
        }
    }
```

### Lossless Round-Trip

**Requirement**: BeerJSON → BrewSignal → BeerJSON must preserve all data.

**Strategy**:
1. Store original BeerJSON in `format_extensions.beerjson_original`
2. On export, merge BrewSignal changes with original BeerJSON
3. Preserve unknown fields in extensions

---

## 8. API Integration

### 8.1 Current API Endpoints

**GET /api/recipes**
- **Returns**: Array of `RecipeResponse` (already BrewSignal format!)
- **No changes needed**

**GET /api/recipes/{id}**
- **Returns**: `RecipeDetailResponse` (already BrewSignal format!)
- **No changes needed**

**POST /api/recipes**
- **Accepts**: `RecipeCreate` (BrewSignal format)
- **No changes needed**

**PUT /api/recipes/{id}**
- **Accepts**: `RecipeUpdate` (BrewSignal format)
- **No changes needed**

### 8.2 New Export Endpoint

**GET /api/recipes/{id}/export**

Query parameters:
- `format`: "brewsignal" (default), "beerjson", "beerxml", "brewfather"
- `include_extensions`: true/false (include BrewSignal extensions)

Response:
```json
{
  "brewsignal_version": "1.0",
  "recipe": { /* ... */ }
}
```

**Content-Type**: `application/vnd.brewsignal.v1+json`

**Content-Disposition**: `attachment; filename="West-Coast-IPA-2025-12-09.brewsignal"`

### 8.3 Validation Endpoint

**POST /api/recipes/validate**

Request:
```json
{
  "format": "brewsignal",
  "data": { /* recipe data */ }
}
```

Response (valid):
```json
{
  "valid": true,
  "warnings": [
    {
      "field": "recipe.boil_time_minutes",
      "warning": "Unusual boil time of 180 minutes"
    }
  ]
}
```

Response (invalid):
```json
{
  "valid": false,
  "errors": [
    {
      "field": "recipe.og",
      "value": 1.250,
      "error": "Value exceeds maximum 1.200"
    }
  ]
}
```

---

## 9. Implementation Checklist

### Phase 1: Documentation (Week 1)
- [x] Draft specification (this document)
- [ ] JSON Schema file (`schemas/brewsignal-recipe-v1.0.schema.json`)
- [ ] Example recipes in `/examples`
- [ ] API documentation updates

### Phase 2: Backend Utilities (Week 2)
- [ ] `backend/services/brewsignal_format.py` - Validation helpers
- [ ] `backend/models.py` - Add `@property` methods for extension access
- [ ] `backend/routers/recipes.py` - Add export endpoint
- [ ] `backend/routers/recipes.py` - Add validation endpoint

### Phase 3: Testing (Week 3)
- [ ] Unit tests for validation
- [ ] Round-trip tests (BrewSignal → BeerJSON → BrewSignal)
- [ ] Example recipe validation
- [ ] API endpoint tests

### Phase 4: Documentation (Week 4)
- [ ] Update CLAUDE.md with format reference
- [ ] Update API.md with new endpoints
- [ ] Create migration guide (BeerJSON → BrewSignal)
- [ ] Update frontend documentation

---

## 10. Version History

### v1.0 (2025-12-09)
- Initial specification
- Formalizes existing API response format
- Adds BrewSignal extensions
- Defines validation rules
- Documents BeerJSON conversion

---

## 11. Future Considerations

### v1.1 (Future)
- Equipment profiles (fermenter volume, geometry)
- Water chemistry (simplified)
- Batch history statistics (success rate, avg attenuation)
- Recipe scaling helpers

### v2.0 (Future)
- Multi-yeast support (blends)
- Pressure fermentation profiles
- Advanced mash schedules (step mash, RIMS, HERMS)
- Integration with brewing calculators

---

## 12. References

- BeerJSON 1.0 Specification: https://github.com/beerjson/beerjson
- BrewSignal API Documentation: `/docs/API.md`
- BrewSignal Project Instructions: `/CLAUDE.md`
- JSON Schema: https://json-schema.org/

---

**End of Specification**
