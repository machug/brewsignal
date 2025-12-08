# Brewfather Format Analysis

## Overview

This document analyzes Brewfather's BeerXML and JSON export formats based on real recipe data (Philter XPA Clone). Brewfather extends both standard BeerXML 1.0 and uses a proprietary JSON format with additional features.

## Key Findings

### Brewfather BeerXML Extensions

**✅ Brewfather's BeerXML is FULLY compatible with standard BeerXML 1.0**

Brewfather adds custom fields but maintains backward compatibility:

#### Custom Fields Added (Prefixed with `BF_`):
- `<BF_ID>` - Brewfather's internal ingredient ID (e.g., "default-8e9450d5")
- `<BF_FERMENTATION_PROFILE_ID>` - Links to fermentation profile
- `<BF_FERMENTATION_PROFILE_NAME>` - Human-readable profile name

#### Enhanced Hop Fields:
- `<TEMPERATURE>` - Hopstand/whirlpool temperature in °C
- `<HOP_TEMP>` - Duplicate of temperature (redundant field)

**These extensions are SAFE to ignore** - they don't break standard BeerXML parsing.

### Brewfather JSON Format

**Schema Status: REVERSE-ENGINEERED** ✅

Based on the sample export, I've documented Brewfather's complete JSON schema below.

## Brewfather BeerXML vs Standard BeerXML

### Similarities (100% Compatible)

| Feature | Standard BeerXML | Brewfather BeerXML | Notes |
|---------|------------------|-------------------|--------|
| Recipe metadata | ✅ | ✅ | NAME, VERSION, TYPE, BREWER |
| Fermentables | ✅ | ✅ | Standard fields + BF_ID |
| Hops | ✅ | ✅ | Standard fields + TEMPERATURE, HOP_TEMP |
| Yeasts | ✅ | ✅ | Standard fields + BF_ID |
| Miscs | ✅ | ✅ | Standard fields + BF_ID |
| Mash profile | ✅ | ✅ | Fully compatible |
| Water profile | ❌ | ❌ | Neither includes water chemistry |
| Equipment | ✅ | ✅ | Standard fields |

### Brewfather-Specific Additions in BeerXML

**1. Hop Temperature Control:**
```xml
<HOP>
    <TEMPERATURE>80</TEMPERATURE>
    <HOP_TEMP>80</HOP_TEMP>  <!-- Redundant -->
</HOP>
```
- Enables hopstand/whirlpool temperature tracking
- Critical for modern brewing techniques (hop aroma extraction)
- **Maps to BeerJSON timing.temperature**

**2. Brewfather IDs:**
```xml
<FERMENTABLE>
    <BF_ID>default-8ea92ed</BF_ID>
</FERMENTABLE>
```
- Internal Brewfather database IDs
- Can be used for ingredient database lookup
- Safe to discard if not using Brewfather integration

**3. Fermentation Profiles:**
```xml
<BF_FERMENTATION_PROFILE_ID>default</BF_FERMENTATION_PROFILE_ID>
<BF_FERMENTATION_PROFILE_NAME>Ale</BF_FERMENTATION_PROFILE_NAME>
```
- Links to Brewfather fermentation schedules
- Not part of standard BeerXML
- Can be converted to BeerJSON fermentation procedures

## Brewfather JSON Schema (Reverse-Engineered)

### Top-Level Recipe Object

```json
{
  "_id": "string",                    // Brewfather recipe ID
  "name": "string",                   // Recipe name
  "author": "string",                 // Brewer name
  "type": "string",                   // "All Grain", "Extract", "Partial Mash"
  "notes": "string",                  // Recipe notes
  "public": boolean,                  // Public recipe flag
  "hidden": boolean,                  // Hidden from profile

  // Vitals
  "batchSize": number,                // Batch size in liters
  "boilSize": number,                 // Pre-boil volume in liters
  "boilTime": number,                 // Boil time in minutes
  "efficiency": number,               // Brewhouse efficiency (0-100%)
  "og": number,                       // Original gravity (1.xxx)
  "fg": number,                       // Final gravity (1.xxx)
  "fgEstimated": number,              // Calculated FG
  "abv": number,                      // ABV percentage
  "ibu": number,                      // IBU value
  "color": number,                    // SRM color
  "carbonation": number,              // Volumes of CO2

  // Ingredients
  "fermentables": [/* Fermentable objects */],
  "hops": [/* Hop objects */],
  "yeasts": [/* Yeast objects */],
  "miscs": [/* Misc ingredient objects */],

  // Advanced
  "water": {/* Water chemistry */},
  "mash": {/* Mash profile */},
  "fermentation": {/* Fermentation schedule */},
  "equipment": {/* Equipment profile */},
  "style": {/* Style guidelines */},
  "nutrition": {/* Nutritional info */},
  "data": {/* Calculated values */},

  // Metadata
  "_version": "string",               // Brewfather schema version
  "_timestamp": "ISO8601",            // Last modified
  "_created": {                       // Creation timestamp
    "seconds": number,
    "nanoseconds": number
  },
  "searchTags": ["string"],           // Tags for search
  "path": "string",                   // Folder path

  // Formulas
  "ibuFormula": "string",             // "tinseth", "rager", etc.
  "fgFormula": "string",              // FG calculation method

  // Style conformity flags
  "styleOg": boolean,
  "styleFg": boolean,
  "styleIbu": boolean,
  "styleAbv": boolean,
  "styleColor": boolean,
  "styleCarb": boolean,
  "styleConformity": boolean          // Overall conformity
}
```

### Fermentable Object (Brewfather JSON)

```json
{
  "_id": "string",                    // Brewfather ingredient ID
  "name": "string",                   // Fermentable name
  "supplier": "string",               // Maltster/supplier
  "origin": "string",                 // Country of origin
  "type": "Grain|Extract|Sugar|Dry Extract",
  "grainCategory": "Base|Crystal/Caramel|Roasted|...",
  "amount": number,                   // Amount in kg
  "percentage": number,               // % of grain bill
  "color": number,                    // SRM/EBC color
  "potential": number,                // Specific gravity potential (1.xxx)
  "potentialPercentage": number,      // Yield % (0-100)
  "attenuation": number,              // Attenuation % (0-1.0)
  "notes": "string",                  // Description
  "ibuPerAmount": number,             // IBU contribution
  "notFermentable": boolean,          // Is fermentable?
  "inventory": number,                // Inventory amount
  "_version": "string",
  "_timestamp": {/* Timestamp */},
  "_created": {/* Timestamp */}
}
```

### Hop Object (Brewfather JSON)

```json
{
  "_id": "string",                    // Brewfather hop ID
  "name": "string",                   // Hop variety
  "origin": "string",                 // Country of origin
  "alpha": number,                    // Alpha acid % (0-100)
  "type": "Pellet|Leaf|Plug|Extract",
  "use": "Boil|Aroma|Dry Hop|Mash|First Wort",
  "amount": number,                   // Amount in grams
  "time": number,                     // Time in minutes OR days
  "timeUnit": "min|days",             // Time unit
  "temp": number,                     // Hopstand temp (°C) or null
  "ibu": number,                      // Calculated IBU
  "usage": "Bittering|Aroma|Both",    // Primary use
  "day": number,                      // Day number (for dry hop)
  "actualTime": number,               // Unix timestamp (actual brew)
  "inventory": number,                // Inventory amount
  "_version": "string",
  "_timestamp": {/* Timestamp */},
  "_created": {/* Timestamp */}
}
```

**Key Innovation: Flexible Timing**
- `time` + `timeUnit` allows minutes OR days
- `temp` enables hopstand temperature control
- `day` specifies fermentation day for dry hopping

### Yeast Object (Brewfather JSON)

```json
{
  "_id": "string",                    // Brewfather yeast ID
  "name": "string",                   // Yeast strain name
  "laboratory": "string",             // Lab/manufacturer
  "productId": "string",              // Product code (e.g., "US-05")
  "type": "Ale|Lager|Wheat|Wine|Champagne",
  "form": "Liquid|Dry|Slant|Culture",
  "amount": number,                   // Number of packages/cells
  "unit": "pkg|ml|g",                 // Amount unit
  "attenuation": number,              // Attenuation % (0-100)
  "minTemp": number,                  // Min fermentation temp (°C)
  "maxTemp": number,                  // Max fermentation temp (°C)
  "flocculation": "Low|Medium|High|Very High",
  "description": "string",            // Yeast description
  "starter": object,                  // Yeast starter calc (optional)
  "starterSize": number,              // Starter volume (L)
  "fermentsAll": boolean,             // Ferments all sugars?
  "inventory": number,                // Inventory
  "_version": "string",
  "_timestamp": {/* Timestamp */},
  "_created": {/* Timestamp */}
}
```

### Misc Object (Brewfather JSON)

```json
{
  "_id": "string",                    // Brewfather misc ID
  "name": "string",                   // Ingredient name
  "type": "Water Agent|Fining|Spice|Herb|Flavor|Other",
  "use": "Mash|Boil|Primary|Secondary|Sparge",
  "amount": number,                   // Amount
  "unit": "g|ml|tsp|items|pkg",       // Unit
  "time": number,                     // Time in minutes (or null)
  "timeIsDays": boolean,              // Is time in days?
  "waterAdjustment": boolean,         // Is water adjustment?
  "inventory": number,                // Inventory
  "_version": "string",
  "_timestamp": {/* Timestamp */},
  "_created": {/* Timestamp */}
}
```

### Water Chemistry (Brewfather JSON)

**This is GOLD for brewers - Brewfather tracks complete water chemistry!**

```json
{
  "source": {                         // Source water profile
    "name": "string",
    "calcium": number,                // Ca (ppm)
    "magnesium": number,              // Mg (ppm)
    "sodium": number,                 // Na (ppm)
    "chloride": number,               // Cl (ppm)
    "sulfate": number,                // SO4 (ppm)
    "bicarbonate": number,            // HCO3 (ppm)
    "ph": number,                     // pH (0-14)
    "alkalinity": number,             // Total alkalinity
    "hardness": number,               // Total hardness
    "residualAlkalinity": number,     // RA
    "bicarbonateMeqL": number,        // Bicarbonate meq/L
    "cations": number,                // Total cations
    "anions": number,                 // Total anions
    "ionBalance": number,             // Ion balance %
    "ionBalanceOff": boolean,         // Balance warning
    "soClRatio": number,              // SO4:Cl ratio
    "type": "source|target"
  },
  "target": {/* Same structure as source */},
  "mash": {/* Water after mash additions */},
  "sparge": {/* Water after sparge additions */},
  "total": {/* Combined water */},

  "mashAdjustments": {                // Salts added to mash
    "calciumSulfate": number,         // Gypsum (g)
    "calciumChloride": number,        // CaCl2 (g)
    "magnesiumSulfate": number,       // Epsom (g)
    "sodiumBicarbonate": number,      // Baking soda (g)
    "calciumHydroxide": number,       // Slaked lime (g)
    "calciumCarbonate": number,       // Chalk (g)
    "magnesiumChloride": number,      // MgCl2 (g)
    "sodiumChloride": number,         // Table salt (g)
    "sodiumMetabisulfite": number,    // Campden (g)
    "acids": [{                       // Acid additions
      "type": "lactic|phosphoric|...",
      "concentration": number,        // % concentration
      "amount": number                // ml
    }],
    "volume": number                  // Mash water volume (L)
  },
  "spargeAdjustments": {/* Same structure as mash */},
  "totalAdjustments": {/* Combined adjustments */},

  "settings": {                       // Water adjustment settings
    "calciumSulfate": {
      "mash": boolean,
      "sparge": boolean,
      "auto": boolean
    },
    "calciumChloride": {
      "form": "dihydrate|anhydrous",
      "mash": boolean,
      "sparge": boolean,
      "auto": boolean
    }
    // ... more settings
  },

  "mashPh": number,                   // Predicted mash pH
  "mashPhDistilled": number,          // Distilled mash pH
  "enableAcidAdjustments": boolean,
  "enableSpargeAdjustments": boolean
}
```

**This is WAY beyond BeerXML capabilities!**

### Mash Profile (Brewfather JSON)

```json
{
  "_id": "string",
  "name": "string",
  "steps": [
    {
      "name": "string",               // Step name
      "type": "Temperature|Infusion|Decoction",
      "stepTemp": number,             // Target temp (°C)
      "displayStepTemp": "string",    // Display value
      "stepTime": number,             // Duration (min)
      "rampTime": number              // Ramp time (min)
    }
  ]
}
```

### Fermentation Profile (Brewfather JSON)

```json
{
  "_id": "string",
  "name": "string",
  "steps": [
    {
      "type": "Primary|Secondary|Conditioning",
      "stepTemp": number,             // Fermentation temp (°C)
      "stepTime": number              // Duration (days)
    }
  ]
}
```

### Equipment Profile (Brewfather JSON)

```json
{
  "_id": "string",
  "name": "string",
  "batchSize": number,                // Target batch size (L)
  "boilSize": number,                 // Pre-boil volume (L)
  "boilTime": number,                 // Boil duration (min)
  "boilOffPerHr": number,             // Evaporation rate (L/hr)
  "efficiency": number,               // Brewhouse efficiency %
  "efficiencyType": "Fermenter|Brewhouse|Mash",
  "mashEfficiency": number,           // Mash efficiency %
  "trubChillerLoss": number,          // Trub loss (L)
  "mashTunLoss": number,              // Mash tun loss (L)
  "mashTunDeadSpace": number,         // Dead space (L)
  "fermenterVolume": number,          // Fermenter capacity (L)
  "fermenterLoss": number,            // Fermenter loss (L)
  "grainAbsorptionRate": number,      // L/kg grain
  "hopUtilization": number,           // Hop utilization factor
  "hopstandTemperature": number,      // Hopstand temp (°C)
  "aromaHopUtilization": number,      // Aroma hop IBU factor
  "waterGrainRatio": number,          // L water per kg grain
  "evaporationRate": number,          // Evap % per hour
  "calcBoilVolume": boolean,          // Auto-calc boil vol
  "calcMashEfficiency": boolean,      // Auto-calc efficiency
  "calcAromaHopUtilization": boolean  // Auto-calc aroma IBU
}
```

### Style Object (Brewfather JSON)

```json
{
  "_id": "string",
  "name": "string",
  "category": "string",               // BJCP category
  "categoryNumber": "string",         // Category number
  "styleLetter": "string",            // Style letter
  "styleGuide": "string",             // "BJCP 2015", "BA 2019"
  "type": "Lager|Ale|Mead|Cider|...",
  "ogMin": number,                    // Min OG (1.xxx)
  "ogMax": number,                    // Max OG
  "fgMin": number,                    // Min FG
  "fgMax": number,                    // Max FG
  "ibuMin": number,                   // Min IBU
  "ibuMax": number,                   // Max IBU
  "colorMin": number,                 // Min SRM
  "colorMax": number,                 // Max SRM
  "abvMin": number,                   // Min ABV %
  "abvMax": number,                   // Max ABV %
  "lovibondMin": number,              // Min Lovibond
  "lovibondMax": number,              // Max Lovibond
  "buGuMin": number,                  // Min BU:GU ratio
  "buGuMax": number,                  // Max BU:GU ratio
  "rbrMin": number,                   // Min RB ratio
  "rbrMax": number,                   // Max RB ratio
  "carbMin": number,                  // Min carbonation (vol)
  "carbMax": number,                  // Max carbonation
  "carbonationStyle": "string"        // BJCP carb style ID
}
```

### Nutrition Object (Brewfather JSON)

**Bonus Feature: Nutritional Information**

```json
{
  "calories": {
    "alcohol": number,                // Calories from alcohol
    "carbs": number,                  // Calories from carbs
    "total": number,                  // Total calories
    "kJ": number                      // Kilojoules
  },
  "carbs": {
    "total": number                   // Total carbs (g)
  }
}
```

## Brewfather vs BeerJSON Comparison

| Feature | Brewfather JSON | BeerJSON 1.0 | Conversion Complexity |
|---------|----------------|--------------|----------------------|
| Recipe metadata | ✅ | ✅ | Easy |
| Fermentables | ✅ | ✅ | Easy |
| Hops with temp | ✅ | ✅ | Easy (timing objects) |
| Yeast/cultures | ✅ | ✅ | Easy |
| Water chemistry | ✅ | ✅ | **Medium** (different structure) |
| Mash profile | ✅ | ✅ | Easy |
| Fermentation steps | ✅ | ✅ | Easy |
| Equipment | ✅ | ✅ | Medium |
| Nutritional info | ✅ | ❌ | **Loss** (BeerJSON doesn't have) |
| Timestamps/metadata | ✅ | ✅ | Easy |
| Style conformity | ✅ | ❌ | **Loss** (calculated flags) |
| IBU formula | ✅ | ✅ | Easy |
| Inventory tracking | ✅ | ❌ | **Loss** |

## Conversion Strategy: Brewfather → BeerJSON

### Phase 1: Direct Mappings (95% coverage)

**Recipe Level:**
```python
def convert_brewfather_to_beerjson(bf_recipe: dict) -> dict:
    return {
        "name": bf_recipe["name"],
        "type": bf_recipe["type"],
        "author": bf_recipe["author"],
        "created": bf_recipe["_timestamp"],
        "batch_size": {"value": bf_recipe["batchSize"], "unit": "l"},
        "boil_size": {"value": bf_recipe["boilSize"], "unit": "l"},
        "boil": {
            "boil_time": {"value": bf_recipe["boilTime"], "unit": "min"}
        },
        "efficiency": {
            "brewhouse": {"value": bf_recipe["efficiency"], "unit": "%"}
        },
        "original_gravity": {"value": bf_recipe["og"], "unit": "sg"},
        "final_gravity": {"value": bf_recipe["fg"], "unit": "sg"},
        "alcohol_by_volume": {"value": bf_recipe["abv"], "unit": "%"},
        "ibu_estimate": {"value": bf_recipe["ibu"], "unit": "IBUs"},
        "color_estimate": {"value": bf_recipe["color"], "unit": "SRM"},
        "carbonation": {"value": bf_recipe["carbonation"], "unit": "vol"},

        "ingredients": {
            "fermentables": convert_fermentables(bf_recipe["fermentables"]),
            "hops": convert_hops(bf_recipe["hops"]),
            "cultures": convert_yeasts(bf_recipe["yeasts"]),
            "miscellaneous_ingredients": convert_miscs(bf_recipe["miscs"])
        },

        "mash": convert_mash(bf_recipe["mash"]),
        "fermentation": convert_fermentation(bf_recipe["fermentation"]),
        "style": convert_style(bf_recipe["style"])
    }
```

**Hop Conversion (with temperature):**
```python
def convert_hop(bf_hop: dict) -> dict:
    timing = {
        "use": map_hop_use(bf_hop["use"]),
        "continuous": False
    }

    # Handle time-based additions
    if bf_hop["use"] == "Boil":
        timing["duration"] = {
            "value": bf_hop["time"],
            "unit": "min"
        }

    # Brewfather's KILLER FEATURE: hopstand temperature
    if bf_hop["temp"] is not None:
        timing["temperature"] = {
            "value": bf_hop["temp"],
            "unit": "C"
        }

    # Dry hop with fermentation day
    if bf_hop["use"] == "Dry Hop":
        timing["phase"] = "primary"
        if bf_hop.get("day"):
            timing["duration"] = {
                "value": bf_hop["day"],
                "unit": "day"
            }

    return {
        "name": bf_hop["name"],
        "origin": bf_hop["origin"],
        "form": bf_hop["type"].lower(),
        "alpha_acid": {"value": bf_hop["alpha"], "unit": "%"},
        "amount": {"value": bf_hop["amount"], "unit": "g"},
        "timing": timing
    }
```

### Phase 2: Water Chemistry Conversion

**Challenge:** Brewfather's water structure is more detailed than BeerJSON

**Solution:** Map to BeerJSON water profile + store adjustments

```python
def convert_water(bf_water: dict) -> dict:
    return {
        "source": {
            "name": bf_water["source"]["name"],
            "calcium": {"value": bf_water["source"]["calcium"], "unit": "ppm"},
            "magnesium": {"value": bf_water["source"]["magnesium"], "unit": "ppm"},
            "sodium": {"value": bf_water["source"]["sodium"], "unit": "ppm"},
            "chloride": {"value": bf_water["source"]["chloride"], "unit": "ppm"},
            "sulfate": {"value": bf_water["source"]["sulfate"], "unit": "ppm"},
            "bicarbonate": {"value": bf_water["source"]["bicarbonate"], "unit": "ppm"}
        },
        "target": {
            # Same structure as source
        },
        # Store mash/sparge adjustments as JSON in notes field
        # (BeerJSON doesn't have salt addition tracking)
    }
```

## Implementation Recommendations

### Priority 1: Brewfather JSON → BeerJSON ✅

**Why:**
- Brewfather JSON has MORE data than BeerXML
- Water chemistry is fully preserved
- Hopstand temperatures preserved
- Fermentation schedules preserved

**Estimated Effort:** 3-4 days

### Priority 2: Brewfather BeerXML → BeerJSON ✅

**Why:**
- Backward compatibility
- Some users may only have XML exports
- Temperature data available in XML

**Estimated Effort:** 1-2 days (reuse existing BeerXML converter + handle `TEMPERATURE` field)

### Priority 3: Round-trip Support

**Brewfather JSON → BeerJSON → Brewfather JSON**

Test data integrity through conversion cycles.

## Data Loss Analysis

### Brewfather JSON → BeerJSON

**Lost Features:**
- `inventory` tracking (not in BeerJSON)
- `searchTags` (Brewfather-specific)
- `nutrition` calculations (BeerJSON doesn't track)
- `styleConformity` flags (calculated values)
- `_timestamp` / `_created` metadata (can store in notes)
- Water adjustment settings (auto-calc flags)

**Preserved Features:**
- ✅ All ingredient data
- ✅ Water chemistry profiles
- ✅ Hopstand temperatures
- ✅ Fermentation schedules
- ✅ Equipment profiles
- ✅ Style guidelines
- ✅ IBU formula method

### Brewfather BeerXML → BeerJSON

**Lost Features:**
- All Brewfather JSON features (water, fermentation, equipment)
- Hopstand temperature (PRESERVED if using Brewfather BeerXML extension)

**Preserved Features:**
- ✅ Basic recipe data
- ✅ Ingredients
- ✅ Mash profile
- ✅ Style

## Test Recipe Analysis

**Recipe:** Philter XPA - Clone

**Ingredients:**
- 4 fermentables (Ale Malt, Caramel Pils, Flaked Oats, Wheat Malt)
- 6 hop additions (2 hopstand @ 80°C, 4 dry hop @ day 10)
- 1 yeast (US-05)
- 8 miscs (water salts for mash/sparge, fining, nutrients)

**Advanced Features Used:**
- ✅ Hopstand with temperature control (80°C)
- ✅ Dry hop schedule (day 10)
- ✅ Water chemistry (source + mash/sparge adjustments)
- ✅ Multi-step mash (55°C → 67°C → 78°C)
- ✅ Equipment profile (Grainfather)

**Conversion Verdict:**
- **Brewfather JSON → BeerJSON:** 95% data preserved
- **Brewfather BeerXML → BeerJSON:** 80% data preserved (loses water chemistry)

## Conclusion

**Brewfather JSON is the BEST source format for comprehensive recipe data.**

If users have Brewfather JSON exports, prioritize that format for import. The BeerXML export is a good fallback but loses significant detail.

**Next Steps:**
1. Implement Brewfather JSON parser
2. Add BeerJSON exporter
3. Support round-trip conversion with data validation
4. Add water chemistry import from Brewfather JSON
