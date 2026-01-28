# BrewSignal Recipe Examples

This directory contains example recipes in BrewSignal Recipe Format v1.0.

## Files

### `minimal-pale-ale.brewsignal`
**Simplest valid recipe** - demonstrates minimum required fields:
- Name, OG, FG
- One fermentable
- One hop
- Yeast name

**Use case**: Quick recipe entry, testing validation

### `west-coast-ipa-complete.brewsignal`
**Full-featured recipe** - demonstrates all available fields:
- Complete recipe metadata (author, style, batch size)
- Multiple fermentables with detailed info
- Multi-hop schedule (bittering, flavor, dry hop)
- Detailed yeast information
- Fermentation schedule (primary, diacetyl rest, cold crash)
- **BrewSignal extensions** for fermentation tracking and temperature control

**Use case**: Production recipes, showcasing all features

## Format Reference

See **[docs/BREWSIGNAL_RECIPE_FORMAT_V1.md](../../docs/BREWSIGNAL_RECIPE_FORMAT_V1.md)** for full specification.

## Validation

Validate recipes using JSON Schema:

```bash
# Using Python jsonschema
python3 -c "
import json
from jsonschema import validate

with open('examples/recipes/minimal-pale-ale.brewsignal') as f:
    recipe = json.load(f)

with open('backend/schemas/brewsignal-recipe-v1.0.schema.json') as f:
    schema = json.load(f)

validate(recipe, schema)
print('✅ Valid BrewSignal recipe!')
"
```

## Importing

### Via API

```bash
curl -X POST http://localhost:8080/api/recipes/import \
  -H "Content-Type: application/vnd.brewsignal.v1+json" \
  -d @examples/recipes/west-coast-ipa-complete.brewsignal
```

### Via Frontend

1. Navigate to **Recipes** page
2. Click **Import Recipe**
3. Select `.brewsignal` file
4. Recipe auto-detected and imported

## Converting from BeerJSON

```python
# Backend converter (future implementation)
from services.brewsignal_format import beerjson_to_brewsignal

# Read BeerJSON file
with open('recipe.json') as f:
    beerjson = json.load(f)

# Convert to BrewSignal format
brewsignal = beerjson_to_brewsignal(beerjson['beerjson']['recipes'][0])

# Save as .brewsignal file
with open('recipe.brewsignal', 'w') as f:
    json.dump(brewsignal, f, indent=2)
```

## BrewSignal Extensions

The `brewsignal_extensions` field enables fermentation-specific features:

### Fermentation Tracking
- **OG Validation**: Alert if measured OG differs from recipe
- **FG Prediction**: ML-based final gravity prediction
- **Anomaly Detection**: Stuck fermentation alerts

### Batch Defaults
- **Auto-link Device**: Automatically pair device when creating batch
- **Temperature Control**: Default temp control settings for this recipe

### Yeast Management
- **Pitch Rate**: Recommended pitch rate (M cells/mL/°P)
- **Starter Required**: Flag for starter calculator
- **Rehydration**: Dry yeast rehydration instructions

## File Format

- **Extension**: `.brewsignal`
- **MIME Type**: `application/vnd.brewsignal.v1+json`
- **Encoding**: UTF-8
- **Format**: JSON (human-readable, editable in any text editor)

## Temperature Units

**All temperatures in Celsius** (BrewSignal's internal standard).

Frontend converts to user's preferred unit (C/F) for display.

## Comparison with BeerJSON

| Feature | BeerJSON 1.0 | BrewSignal v1.0 |
|---------|--------------|-----------------|
| Gravity format | `{"value": 1.050, "unit": "sg"}` | `1.050` |
| ABV format | `{"value": 0.069, "unit": "%"}` (0-1 scale) | `6.9` (0-100 scale) |
| Field names | `original_gravity`, `alcohol_by_volume` | `og`, `abv` |
| Ingredients | Nested in `ingredients.fermentable_additions` | Direct `fermentables` array |
| Extensions | `_extensions.custom` | `brewsignal_extensions` |
| Verbosity | High (unit objects everywhere) | Low (raw numbers) |
| Readability | Medium (JSON Schema validated) | High (human-editable) |

**Both formats** convert losslessly via BrewSignal's import/export pipeline.
