# BeerJSON Import Design Fixes

**Date:** 2025-12-08
**Status:** Critical Fixes to Design and Implementation Plan

## Issues Found

Six critical design flaws that would break "zero data loss" and "fail gracefully" promises:

1. **Unit conversion loss** - _extract_value strips units
2. **Water adjustments not persisted** - RecipeWaterAdjustment never populated
3. **Missing field guards** - KeyError on optional BeerJSON fields
4. **Brewfather detection too strict** - Rejects valid exports without _id
5. **Async inspector not awaited** - Migration tests will error
6. **Hop timing mutation** - Missing use/time defaults to 60-min boil

---

## Fix 1: Unit Conversion Loss

### Problem

```python
# docs/plans/2025-12-08-beerjson-multi-format-import-design.md:827-833
def _extract_value(self, obj: Optional[dict]) -> Optional[float]:
    """Extract value from BeerJSON unit object."""
    if obj is None:
        return None
    if isinstance(obj, dict) and 'value' in obj:
        return float(obj['value'])  # ❌ LOSES UNIT
    return None
```

Non-metric BeerJSON (gallons, oz, °F) will be stored as raw numbers without conversion.

### Solution

Store the full unit object in format_extensions and convert to metric on extraction:

```python
def _extract_value_with_unit(
    self,
    obj: Optional[dict],
    target_unit: str,
    conversion_map: Optional[Dict[str, Union[float, Callable]]] = None
) -> Optional[float]:
    """Extract value from BeerJSON unit object and convert to target unit.

    Args:
        obj: BeerJSON unit object {'value': X, 'unit': 'Y'}
        target_unit: Target unit to convert to (e.g., 'l', 'C', 'kg')
        conversion_map: Optional conversion factors (float or callable)

    Returns:
        Converted value in target units

    Raises:
        ValueError: Unknown unit conversion
    """
    if obj is None:
        return None

    if not isinstance(obj, dict) or 'value' not in obj:
        return None

    value = float(obj['value'])
    unit = obj.get('unit', target_unit)

    # No conversion needed
    if unit == target_unit:
        return value

    # Default conversion maps
    if conversion_map is None:
        conversion_map = self._get_default_conversions(target_unit)

    # Apply conversion
    if unit in conversion_map:
        converter = conversion_map[unit]

        # Handle callable converters (e.g., temperature)
        if callable(converter):
            return converter(value)
        else:
            # Simple multiplication for linear conversions
            return value * converter

    # Unknown unit - preserve in format_extensions
    raise ValueError(f"Unknown unit conversion: {unit} → {target_unit}")


def _get_default_conversions(self, target_unit: str) -> Dict[str, float]:
    """Get default unit conversion factors."""
    conversions = {
        'l': {  # Volume to liters
            'gal': 3.78541,
            'qt': 0.946353,
            'ml': 0.001,
            'l': 1.0
        },
        'kg': {  # Mass to kilograms
            'lb': 0.453592,
            'oz': 0.0283495,
            'g': 0.001,
            'kg': 1.0
        },
        'g': {  # Mass to grams
            'lb': 453.592,
            'oz': 28.3495,
            'kg': 1000.0,
            'g': 1.0
        },
        'C': {  # Temperature to Celsius
            'F': lambda f: (f - 32) * 5/9,
            'K': lambda k: k - 273.15,
            'C': 1.0
        }
    }
    return conversions.get(target_unit, {})


def _build_format_extensions(self, recipe_data: dict) -> Optional[dict]:
    """Build format_extensions with original units preserved.

    Preserves non-metric units for round-trip export, including per-ingredient units.
    """
    extensions = recipe_data.get('_extensions', {})

    # Metric units we store natively
    metric_units = {'l', 'kg', 'g', 'C', 'min', 'day', 'sg', '%', '1', 'SRM', 'ppm'}

    # Track original units (both recipe-level and per-ingredient)
    original_units = {}
    ingredient_units = {}

    # Check recipe-level fields
    recipe_fields = {
        'batch_size': recipe_data.get('batch_size'),
        'boil_size': recipe_data.get('boil', {}).get('boil_size'),
        'original_gravity': recipe_data.get('original_gravity'),
        'final_gravity': recipe_data.get('final_gravity'),
        'color_estimate': recipe_data.get('color_estimate'),
    }

    for field_name, obj in recipe_fields.items():
        if isinstance(obj, dict) and 'unit' in obj:
            unit = obj['unit']
            if unit not in metric_units:
                original_units[field_name] = unit

    # Check ALL ingredient units (not just first)
    ingredients = recipe_data.get('ingredients', {})

    # Fermentables
    for idx, ferm in enumerate(ingredients.get('fermentables', [])):
        if isinstance(ferm.get('amount'), dict) and 'unit' in ferm['amount']:
            unit = ferm['amount']['unit']
            if unit not in metric_units:
                ingredient_units[f'fermentable_{idx}_amount'] = unit

        # Color units
        if isinstance(ferm.get('color'), dict) and 'unit' in ferm['color']:
            unit = ferm['color']['unit']
            if unit not in metric_units:
                ingredient_units[f'fermentable_{idx}_color'] = unit

    # Hops
    for idx, hop in enumerate(ingredients.get('hops', [])):
        if isinstance(hop.get('amount'), dict) and 'unit' in hop['amount']:
            unit = hop['amount']['unit']
            if unit not in metric_units:
                ingredient_units[f'hop_{idx}_amount'] = unit

        # Temperature units in timing
        timing = hop.get('timing', {})
        if isinstance(timing.get('temperature'), dict) and 'unit' in timing['temperature']:
            unit = timing['temperature']['unit']
            if unit not in metric_units:
                ingredient_units[f'hop_{idx}_timing_temp'] = unit

    # Cultures
    for idx, culture in enumerate(ingredients.get('cultures', [])):
        if isinstance(culture.get('amount'), dict) and 'unit' in culture['amount']:
            unit = culture['amount']['unit']
            if unit not in metric_units:
                ingredient_units[f'culture_{idx}_amount'] = unit

    # Miscs
    for idx, misc in enumerate(ingredients.get('miscellaneous_ingredients', [])):
        if isinstance(misc.get('amount'), dict) and 'unit' in misc['amount']:
            unit = misc['amount']['unit']
            if unit not in metric_units:
                ingredient_units[f'misc_{idx}_amount'] = unit

    # Combine all original units
    if original_units:
        extensions['original_units'] = original_units
    if ingredient_units:
        extensions['ingredient_original_units'] = ingredient_units

    return extensions if extensions else None
```

**Updated serializer usage:**

```python
# In from_beerjson():
recipe = Recipe(
    name=recipe_data['name'],
    batch_size_liters=self._extract_value_with_unit(
        recipe_data.get('batch_size'),
        target_unit='l'
    ),
    # ... other fields

    # Preserve original units and other extensions
    format_extensions=self._build_format_extensions(recipe_data)
)
```

---

## Fix 2: Water Adjustments Not Persisted

### Problem

```python
# docs/plans/2025-12-08-beerjson-multi-format-import-design.md:782-796
# Water profiles
for water_data in recipe_data.get('water_additions', []):
    profile = RecipeWaterProfile(...)  # ❌ Only creates profiles
    recipe.water_profiles.append(profile)

# ❌ RecipeWaterAdjustment is NEVER populated
```

Brewfather water salt additions are never persisted.

### Solution

Brewfather stores salt additions in a different location. Parse both water profiles AND adjustments:

```python
# In from_beerjson():

# Water profiles (ion concentrations)
water_additions = recipe_data.get('water_additions', [])
for water_data in water_additions:
    profile = RecipeWaterProfile(
        profile_type=self._infer_water_profile_type(water_data),
        name=water_data.get('name'),
        calcium_ppm=self._extract_value_with_unit(water_data.get('calcium'), 'ppm'),
        magnesium_ppm=self._extract_value_with_unit(water_data.get('magnesium'), 'ppm'),
        sodium_ppm=self._extract_value_with_unit(water_data.get('sodium'), 'ppm'),
        chloride_ppm=self._extract_value_with_unit(water_data.get('chloride'), 'ppm'),
        sulfate_ppm=self._extract_value_with_unit(water_data.get('sulfate'), 'ppm'),
        bicarbonate_ppm=self._extract_value_with_unit(water_data.get('bicarbonate'), 'ppm'),
        ph=water_data.get('ph'),
        format_extensions=water_data.get('_extensions')
    )
    recipe.water_profiles.append(profile)

# Water adjustments (salt/acid additions) - from Brewfather extensions
brewfather_ext = recipe_data.get('_extensions', {}).get('brewfather', {})
water_adj_data = brewfather_ext.get('water_adjustments', [])

for adj_data in water_adj_data:
    # Note: Brewfather converter emits volume_liters as plain number (not unit object)
    # Handle both cases: plain number or BeerJSON unit object
    volume = adj_data.get('volume_liters') or adj_data.get('volume')
    if isinstance(volume, dict):
        volume = self._extract_value_with_unit(volume, 'l')

    adjustment = RecipeWaterAdjustment(
        stage=adj_data.get('stage', 'mash'),  # mash, sparge, total
        volume_liters=volume,

        # Salt additions (grams)
        calcium_sulfate_g=adj_data.get('calcium_sulfate_g'),  # Gypsum
        calcium_chloride_g=adj_data.get('calcium_chloride_g'),  # CaCl2
        magnesium_sulfate_g=adj_data.get('magnesium_sulfate_g'),  # Epsom
        sodium_bicarbonate_g=adj_data.get('sodium_bicarbonate_g'),  # Baking soda
        calcium_carbonate_g=adj_data.get('calcium_carbonate_g'),  # Chalk
        calcium_hydroxide_g=adj_data.get('calcium_hydroxide_g'),  # Slaked lime
        magnesium_chloride_g=adj_data.get('magnesium_chloride_g'),
        sodium_chloride_g=adj_data.get('sodium_chloride_g'),  # Table salt

        # Acid additions
        acid_type=adj_data.get('acid_type'),
        acid_ml=adj_data.get('acid_ml'),
        acid_concentration_percent=adj_data.get('acid_concentration_percent'),

        format_extensions=adj_data.get('_extensions')
    )
    recipe.water_adjustments.append(adjustment)
```

**Updated BrewfatherToBeerJSONConverter:**

```python
def convert(self, brewfather_dict: dict) -> dict:
    """Convert Brewfather JSON to BeerJSON."""
    beerjson = {
        'beerjson': {
            'version': '1.0',
            'recipes': [self._convert_recipe(brewfather_dict)]
        }
    }
    return beerjson

def _convert_recipe(self, bf_recipe: dict) -> dict:
    """Convert Brewfather recipe to BeerJSON."""
    recipe = {
        'name': bf_recipe.get('name', ''),
        # ... standard fields

        '_extensions': {
            'brewfather': self._extract_brewfather_extensions(bf_recipe)
        }
    }
    return recipe

def _extract_brewfather_extensions(self, bf_recipe: dict) -> dict:
    """Extract Brewfather-specific data to extensions."""
    extensions = {}

    # Water adjustments (salt additions)
    if 'water' in bf_recipe:
        water = bf_recipe['water']

        # Build water adjustments for mash, sparge, total
        adjustments = []

        for stage in ['mash', 'sparge', 'total']:
            stage_key = f'{stage}Water' if stage != 'total' else 'total'
            stage_data = water.get(stage_key, {})

            if not stage_data:
                continue

            adj = {
                'stage': stage,
                'volume_liters': stage_data.get('amount'),

                # Salt additions from Brewfather
                'calcium_sulfate_g': stage_data.get('calciumSulfate'),
                'calcium_chloride_g': stage_data.get('calciumChloride'),
                'magnesium_sulfate_g': stage_data.get('magnesiumSulfate'),
                'sodium_bicarbonate_g': stage_data.get('sodiumBicarbonate'),
                'calcium_carbonate_g': stage_data.get('calciumCarbonate'),
                'calcium_hydroxide_g': stage_data.get('calciumHydroxide'),
                'magnesium_chloride_g': stage_data.get('magnesiumChloride'),
                'sodium_chloride_g': stage_data.get('sodiumChloride'),

                # Acids
                'acid_type': stage_data.get('acidType'),
                'acid_ml': stage_data.get('acidAmount'),
                'acid_concentration_percent': stage_data.get('acidConcentration')
            }

            # Only add if has salt or acid data
            has_salts = any(v for k, v in adj.items() if k.endswith('_g') and v is not None)
            has_acids = adj.get('acid_type') or adj.get('acid_ml')

            if has_salts or has_acids:
                adjustments.append(adj)

        if adjustments:
            extensions['water_adjustments'] = adjustments

    return extensions
```

---

## Fix 3: Missing Field Guards

### Problem

```python
# docs/plans/2025-12-08-beerjson-multi-format-import-design.md:730-779
hop = RecipeHop(
    name=hop_data['name'],  # ❌ KeyError if 'name' missing
    origin=hop_data.get('origin'),  # ✅ OK
    form=hop_data.get('form'),
    alpha_acid_percent=self._extract_value(hop_data.get('alpha_acid')),
    amount_grams=self._extract_value(hop_data['amount']),  # ❌ KeyError
    timing=hop_data['timing'],  # ❌ KeyError
)
```

Valid BeerJSON can omit optional fields, causing KeyError.

### Solution

Add safe getters and validation:

```python
def from_beerjson(self, beerjson_dict: dict, db: AsyncSession) -> Recipe:
    """Deserialize BeerJSON dict → SQLAlchemy Recipe model.

    Raises:
        ValueError: Missing required fields or invalid data
    """
    # Validate structure
    if 'beerjson' not in beerjson_dict:
        raise ValueError("Invalid BeerJSON: missing 'beerjson' root")

    if 'recipes' not in beerjson_dict['beerjson']:
        raise ValueError("Invalid BeerJSON: missing 'recipes' array")

    recipes = beerjson_dict['beerjson']['recipes']
    if not recipes or len(recipes) == 0:
        raise ValueError("Invalid BeerJSON: empty 'recipes' array")

    recipe_data = recipes[0]

    # Validate required fields
    if 'name' not in recipe_data:
        raise ValueError("Invalid BeerJSON: recipe missing required 'name' field")

    # Create Recipe with safe field access
    recipe = Recipe(
        name=recipe_data['name'],
        type=recipe_data.get('type'),
        author=recipe_data.get('author'),
        batch_size_liters=self._safe_extract_value(
            recipe_data.get('batch_size'),
            target_unit='l'
        ),
        # ... other fields with safe extraction
    )

    # Deserialize ingredients with validation
    ingredients = recipe_data.get('ingredients', {})

    # Fermentables
    for ferm_data in ingredients.get('fermentables', []):
        try:
            fermentable = self._deserialize_fermentable(ferm_data)
            recipe.fermentables.append(fermentable)
        except ValueError as e:
            # Log and skip invalid fermentable
            logger.warning(f"Skipping invalid fermentable: {e}")
            continue

    # Hops
    for hop_data in ingredients.get('hops', []):
        try:
            hop = self._deserialize_hop(hop_data)
            recipe.hops.append(hop)
        except ValueError as e:
            logger.warning(f"Skipping invalid hop: {e}")
            continue

    # ... similar for other ingredients

    return recipe


def _deserialize_hop(self, hop_data: dict) -> RecipeHop:
    """Deserialize hop with field validation.

    Raises:
        ValueError: Missing required fields
    """
    # Validate required fields
    if 'name' not in hop_data:
        raise ValueError("Hop missing required 'name' field")

    if 'amount' not in hop_data:
        raise ValueError(f"Hop '{hop_data['name']}' missing required 'amount' field")

    if 'timing' not in hop_data:
        raise ValueError(f"Hop '{hop_data['name']}' missing required 'timing' field")

    # Extract with safe defaults
    hop = RecipeHop(
        name=hop_data['name'],
        origin=hop_data.get('origin'),
        form=hop_data.get('form', 'pellet'),  # Default to pellet
        alpha_acid_percent=self._safe_extract_value(
            hop_data.get('alpha_acid'),
            target_unit='%',
            default=0.0  # Default AA if missing
        ),
        beta_acid_percent=self._safe_extract_value(
            hop_data.get('beta_acid'),
            target_unit='%'
        ),
        amount_grams=self._safe_extract_value(
            hop_data['amount'],
            target_unit='g'
        ),
        timing=hop_data['timing'],
        format_extensions=hop_data.get('_extensions')
    )

    return hop


def _safe_extract_value(
    self,
    obj: Optional[dict],
    target_unit: str,
    default: Optional[float] = None
) -> Optional[float]:
    """Safely extract value with unit conversion and default.

    Args:
        obj: BeerJSON unit object or None
        target_unit: Target unit
        default: Default value if obj is None

    Returns:
        Converted value or default
    """
    if obj is None:
        return default

    try:
        return self._extract_value_with_unit(obj, target_unit)
    except (ValueError, KeyError) as e:
        logger.warning(f"Unit conversion failed: {e}, using default {default}")
        return default
```

---

## Fix 4: Brewfather Detection Too Strict

### Problem

```python
# docs/plans/2025-12-08-beerjson-multi-format-import-design.md:664-672
def _is_brewfather_format(self, data: dict) -> bool:
    """Detect Brewfather JSON format."""
    # ❌ Rejects Brewfather exports without _id
    return '_id' in data and 'fermentables' in data and 'hops' in data
```

Brewfather exports sanitized or from some APIs lack `_id`.

### Solution

Use more flexible detection with multiple heuristics:

```python
def _is_brewfather_format(self, data: dict) -> bool:
    """Detect Brewfather JSON format.

    Brewfather indicators:
    - Has top-level 'fermentables', 'hops', 'yeasts'
    - Has 'equipment' with Brewfather-specific fields
    - Has 'water' with 'mashWater', 'spargeWater'
    - Missing 'beerjson' wrapper
    """
    # Must NOT be BeerJSON (which has 'beerjson' wrapper)
    if 'beerjson' in data:
        return False

    # Check for Brewfather-specific structure
    brewfather_indicators = [
        # Core ingredients at root level (not wrapped in 'ingredients')
        'fermentables' in data and isinstance(data['fermentables'], list),
        'hops' in data and isinstance(data['hops'], list),
        'yeasts' in data and isinstance(data['yeasts'], list),

        # Brewfather-specific fields
        'equipment' in data and isinstance(data['equipment'], dict),
        'water' in data and isinstance(data['water'], dict),

        # Brewfather water structure
        'water' in data and (
            'mashWater' in data.get('water', {}) or
            'spargeWater' in data.get('water', {})
        ),

        # Has _id (optional but strong indicator)
        '_id' in data
    ]

    # Need at least 3 indicators to be confident
    indicator_count = sum(1 for ind in brewfather_indicators if ind)

    return indicator_count >= 3


def _is_beerjson_format(self, data: dict) -> bool:
    """Detect BeerJSON format."""
    # BeerJSON has 'beerjson' root with 'version' and 'recipes'
    if 'beerjson' not in data:
        return False

    beerjson_obj = data['beerjson']

    return (
        isinstance(beerjson_obj, dict) and
        'version' in beerjson_obj and
        'recipes' in beerjson_obj and
        isinstance(beerjson_obj['recipes'], list)
    )


def _parse_json(self, content: bytes) -> dict:
    """Parse JSON (Brewfather or BeerJSON)."""
    try:
        raw_data = json.loads(content.decode('utf-8'))
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON: {e}")

    # Detect format with priority order
    if self._is_beerjson_format(raw_data):
        # Native BeerJSON - no conversion needed
        return raw_data

    elif self._is_brewfather_format(raw_data):
        # Brewfather JSON - convert to BeerJSON
        return self.brewfather_converter.convert(raw_data)

    else:
        # Unknown format - provide helpful error
        hints = []
        if 'recipes' in raw_data:
            hints.append("has 'recipes' but missing 'beerjson' wrapper")
        if 'fermentables' in raw_data:
            hints.append("has 'fermentables' at root (possibly Brewfather)")

        hint_str = "; ".join(hints) if hints else "structure not recognized"

        raise ValueError(
            f"Unknown JSON format: {hint_str}. "
            f"Expected BeerJSON 1.0 or Brewfather JSON."
        )
```

---

## Fix 5: Async Inspector Not Awaited

### Problem

```python
# .worktrees/beerjson-import/docs/plans/2025-12-08-beerjson-import-implementation-plan.md:33-41
async with engine.connect() as conn:
    inspector = inspect(conn)  # ❌ Returns AsyncInspector
    columns = {col['name'] for col in inspector.get_columns('recipes')}
    # ❌ get_columns() returns coroutine, not list
```

Migration tests will error before exercising migrations.

### Solution

Use synchronous inspection or await properly:

```python
@pytest.mark.asyncio
async def test_recipe_table_has_beerjson_columns():
    """Test that Recipe table has BeerJSON columns after migration."""
    await init_db()

    # Use run_sync for inspection (SQLAlchemy pattern)
    def _check_columns(conn):
        inspector = inspect(conn)
        columns = {col['name'] for col in inspector.get_columns('recipes')}

        # New BeerJSON columns
        assert 'batch_size_liters' in columns
        assert 'boil_time_minutes' in columns
        assert 'efficiency_percent' in columns
        assert 'beerjson_version' in columns
        assert 'format_extensions' in columns
        assert 'carbonation_vols' in columns

        # Renamed columns
        assert 'og' in columns
        assert 'fg' in columns
        assert 'color_srm' in columns

        # Old names should not exist
        assert 'og_target' not in columns
        assert 'fg_target' not in columns
        assert 'srm_target' not in columns

    # Run synchronous inspection
    async with engine.connect() as conn:
        await conn.run_sync(_check_columns)
```

**Alternative: Direct SQL inspection:**

```python
@pytest.mark.asyncio
async def test_recipe_table_has_beerjson_columns():
    """Test that Recipe table has BeerJSON columns after migration."""
    await init_db()

    async with engine.connect() as conn:
        # Use PRAGMA table_info (SQLite-specific but reliable)
        result = await conn.execute(text("PRAGMA table_info(recipes)"))
        rows = result.fetchall()
        columns = {row[1] for row in rows}  # row[1] is column name

        # New BeerJSON columns
        assert 'batch_size_liters' in columns
        assert 'boil_time_minutes' in columns
        assert 'efficiency_percent' in columns
        assert 'beerjson_version' in columns
        assert 'format_extensions' in columns
        assert 'carbonation_vols' in columns

        # Renamed columns
        assert 'og' in columns
        assert 'fg' in columns
        assert 'color_srm' in columns

        # Old names should not exist
        assert 'og_target' not in columns
        assert 'fg_target' not in columns
        assert 'srm_target' not in columns
```

---

## Fix 6: Hop Timing Mutation

### Problem

```python
# .worktrees/beerjson-import/docs/plans/2025-12-08-beerjson-import-implementation-plan.md:570-577
def _convert_hop_timing(hop_row) -> str:
    use = hop_row[7] if len(hop_row) > 7 else 'Boil'  # ❌ Defaults to Boil
    time = hop_row[8] if len(hop_row) > 8 else 60     # ❌ Defaults to 60 min
    # ... mutates hops without use/time to 60-minute boil
```

Historical hops without timing will be incorrectly set to 60-minute boil.

### Solution

Preserve NULL timing for missing data, convert only valid rows:

```python
async def migrate_enhance_ingredient_tables(conn: AsyncConnection) -> None:
    """Add timing and format_extensions to ingredient tables."""
    # ... existing migration code ...

    # Rename hop columns with safe timing migration
    if await _check_column_exists(conn, 'recipe_hops', 'alpha'):
        logger.info("Renaming recipe_hops columns")

        await conn.execute(text("""
            CREATE TABLE recipe_hops_new (
                id INTEGER PRIMARY KEY,
                recipe_id INTEGER NOT NULL,
                name VARCHAR(100) NOT NULL,
                origin VARCHAR(50),
                form VARCHAR(20),
                alpha_acid_percent REAL NOT NULL,
                beta_acid_percent REAL,
                amount_grams REAL NOT NULL,
                timing JSON,  -- ✅ NULLABLE (not required)
                format_extensions JSON,
                FOREIGN KEY (recipe_id) REFERENCES recipes(id) ON DELETE CASCADE
            )
        """))

        # Migrate data with safe timing conversion
        result = await conn.execute(text("""
            SELECT id, recipe_id, name, origin, form, alpha, amount, use, time
            FROM recipe_hops
        """))
        hops = result.fetchall()

        for hop in hops:
            hop_id, recipe_id, name, origin, form, alpha, amount, use, time = hop

            # Only build timing if we have valid use field
            timing_dict = None
            if use is not None and use != '':
                timing_dict = _convert_hop_timing_safe(use, time)

            # SQLAlchemy will JSON-encode the dict automatically
            # We store dict/None, NOT json.dumps(dict)
            await conn.execute(text("""
                INSERT INTO recipe_hops_new (
                    id, recipe_id, name, origin, form,
                    alpha_acid_percent, amount_grams, timing
                )
                VALUES (:id, :recipe_id, :name, :origin, :form,
                        :alpha, :amount, :timing)
            """), {
                "id": hop_id,
                "recipe_id": recipe_id,
                "name": name,
                "origin": origin,
                "form": form or 'pellet',
                "alpha": alpha or 0,
                "amount": amount or 0,
                "timing": timing_dict  # ✅ Dict or None (SQLAlchemy handles JSON encoding)
            })

        await conn.execute(text("DROP TABLE recipe_hops"))
        await conn.execute(text("ALTER TABLE recipe_hops_new RENAME TO recipe_hops"))

        # Log migration stats
        hops_with_timing = sum(1 for h in hops if h[7] is not None and h[7] != '')
        hops_without_timing = len(hops) - hops_with_timing

        logger.info(
            f"Migrated {len(hops)} hops to new schema: "
            f"{hops_with_timing} with timing, "
            f"{hops_without_timing} preserved NULL timing"
        )


def _convert_hop_timing_safe(use: str, time: Optional[float]) -> Optional[dict]:
    """Convert old hop use/time to BeerJSON timing object.

    Only creates timing if use is valid. Returns None for invalid data.

    Returns:
        Dict (not JSON string) for SQLAlchemy JSON column, or None
    """
    if not use or use == '':
        return None

    use_mapping = {
        "Boil": "add_to_boil",
        "Dry Hop": "add_to_fermentation",
        "Mash": "add_to_mash",
        "First Wort": "add_to_boil",
        "Aroma": "add_to_boil"
    }

    # Unknown use value - preserve NULL
    if use not in use_mapping:
        logger.warning(f"Unknown hop use '{use}', preserving NULL timing")
        return None

    timing = {
        "use": use_mapping[use],
        "continuous": False
    }

    # Add duration if time is valid
    if time is not None and time > 0:
        if use in ["Boil", "Aroma"]:
            timing["duration"] = {"value": time, "unit": "min"}
        elif use == "Dry Hop":
            # Convert minutes to days (BeerXML quirk)
            timing["duration"] = {"value": int(time / 1440), "unit": "day"}
            timing["phase"] = "primary"

    return timing  # ✅ Return dict, not json.dumps()
```

**Important: SQLAlchemy JSON Column Handling**

When inserting into JSON columns with SQLAlchemy:
- ✅ **DO**: Pass Python dict/list/None directly
- ❌ **DON'T**: Call `json.dumps()` before inserting

SQLAlchemy automatically handles JSON encoding/decoding for JSON columns. If you manually call `json.dumps()`, the JSON string gets stored as a string in the JSON column, causing:
- Type errors when reading (consumers expect dict, get string)
- Round-trip failures (re-importing treats string as invalid JSON structure)
- Need for double-decoding (`json.loads(json.loads(value))`)

**Correct pattern:**
```python
# ✅ Correct - dict stored as JSON
timing_dict = {"use": "add_to_boil", "duration": {"value": 60, "unit": "min"}}
await conn.execute(text("INSERT INTO hops (timing) VALUES (:timing)"), {"timing": timing_dict})

# ❌ Wrong - JSON string stored as JSON (creates nested encoding)
timing_json = json.dumps({"use": "add_to_boil", ...})
await conn.execute(text("INSERT INTO hops (timing) VALUES (:timing)"), {"timing": timing_json})
```

---

## Summary of Fixes

| Issue | Impact | Fix |
|-------|--------|-----|
| 1. Unit conversion loss | Non-metric imports lose data | Add unit conversion with callable support + preserve originals |
| 1a. Temperature lambda TypeError | °F/K conversions crash | Handle callable converters (not just multiplication) |
| 1b. Missing _get_nested_value | NameError on unit preservation | Replace with direct field checking in _build_format_extensions |
| 1c. Per-ingredient units not preserved | Only first ingredient unit preserved | Loop through ALL ingredients, store in ingredient_original_units |
| 2. Water adjustments not persisted | Brewfather water chemistry lost | Parse `_extensions.brewfather.water_adjustments` |
| 2a. Acid-only adjustments dropped | Acid treatments silently lost | Check for salts OR acids before appending |
| 2b. Water adjustment volumes dropped | Converter/serializer mismatch | Handle both volume_liters (number) and volume (unit object) |
| 3. Missing field guards | KeyError on optional fields | Add safe getters + validation with helpful errors |
| 4. Brewfather detection too strict | Rejects valid exports | Use flexible multi-indicator detection |
| 5. Async inspector not awaited | Migration tests error | Use `run_sync()` or PRAGMA for inspection |
| 6. Hop timing mutation | Historical data corrupted | Preserve NULL timing, only convert valid rows |
| 6a. JSON double-encoding | Timing stored as string | Return dict (not json.dumps) for SQLAlchemy JSON columns |

**Additional Fixes:**
- **SQLAlchemy JSON Column Pattern**: Never call `json.dumps()` before inserting - pass dict/list/None directly
- **Per-Ingredient Unit Preservation**: Loop through ALL ingredients (not just first) to preserve units
- **Water Volume Handling**: Accept both plain numbers and unit objects for converter/serializer compatibility

**Round-Trip Data Integrity:**

The fixes ensure complete round-trip preservation:

```
Import (gal/oz/°F) → Convert to metric (l/g/C) → Store in DB
                   ↓
              Preserve originals in format_extensions:
              {
                "original_units": {"batch_size": "gal"},
                "ingredient_original_units": {
                  "fermentable_0_amount": "lb",
                  "fermentable_1_amount": "oz",
                  "hop_0_amount": "oz",
                  "hop_0_timing_temp": "F"
                }
              }
                   ↓
Export → Read from format_extensions → Convert back to original units → Match original
```

This ensures:
- ✅ Multi-ingredient recipes with mixed units (lb + oz) round-trip correctly
- ✅ Hopstand temperatures in °F preserve original unit
- ✅ Water adjustments with volumes preserve all data
- ✅ Acid-only water treatments not dropped

---

## Implementation Order

1. **Fix 5 first** - Migration tests must work to verify other fixes
2. **Fix 1** - Foundation for correct unit handling
3. **Fix 3** - Fail gracefully before processing data
4. **Fix 4** - Detect formats correctly
5. **Fix 2** - Parse water adjustments correctly
6. **Fix 6** - Migrate existing data safely

All fixes maintain the "zero data loss" and "fail gracefully" promises.
