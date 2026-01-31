# BeerJSON Multi-Format Recipe Import Design

**Date:** 2025-12-08
**Status:** Design
**Related Docs:**
- `docs/BEERXML_TO_BEERJSON_CONVERSION.md` (conversion strategy)
- `docs/BREWFATHER_FORMAT_ANALYSIS.md` (format analysis)
- `docs/Brewfather_BeerXML_PhilterXPAClone_20251207.xml` (reference export)
- `docs/Brewfather_RECIPE_PhilterXPAClone_20251207.json` (reference export)

## Overview

Implement comprehensive recipe import supporting BeerJSON 1.0, BeerXML 1.0, and Brewfather JSON/XML formats. Store recipes in fully normalized database tables following BeerJSON schema structure. Future-proof for brew day features while serving current fermentation tracking needs.

## Goals

1. **Multi-format import:** BeerJSON, BeerXML, Brewfather JSON/XML
2. **Zero data loss:** Preserve all format-specific extensions
3. **Full normalization:** Relational tables following BeerJSON schema
4. **Round-trip export:** Import → Export → Import with data integrity
5. **Future-proof:** Ready for brew day features (mash, hop schedules, water chemistry)
6. **Backward compatible:** Migrate existing BeerXML recipes without data loss

## Non-Goals

- Recipe designer/calculator UI (future phase)
- Inventory management (future phase)
- Real-time collaboration (future phase)

## Design Principles

1. **BeerJSON as the standard:** Internal schema follows BeerJSON 1.0 spec
2. **Preserve everything:** Store format-specific data in extension fields
3. **Validate early:** JSON Schema validation on import
4. **Fail gracefully:** Clear error messages for invalid files
5. **Test with real data:** Use Philter XPA exports as reference implementation

## Architecture

### Three-Phase Import Pipeline

```
┌─────────────────────────────────────────┐
│  Phase 1: Format Detection & Parsing    │
├─────────────────────────────────────────┤
│  ├─ BeerXML (.xml)                      │
│  │   └─ Parse XML → BeerXML Dict        │
│  ├─ Brewfather XML (.xml)               │
│  │   └─ Parse XML → BeerXML Dict        │
│  │       (with Brewfather extensions)   │
│  └─ JSON (.json)                        │
│      ├─ Detect BeerJSON                 │
│      │   └─ Validate → BeerJSON Dict    │
│      └─ Detect Brewfather               │
│          └─ Parse → Brewfather Dict     │
└─────────────┬───────────────────────────┘
              │
              ↓
┌─────────────────────────────────────────┐
│  Phase 2: Normalization to BeerJSON     │
├─────────────────────────────────────────┤
│  All formats → BeerJSON Dict            │
│  • BeerXML Converter                    │
│  • Brewfather Converter                 │
│  • Identity (native BeerJSON)           │
└─────────────┬───────────────────────────┘
              │
              ↓
┌─────────────────────────────────────────┐
│  Phase 3: Database Persistence          │
├─────────────────────────────────────────┤
│  BeerJSON Dict → SQLAlchemy ORM         │
│  • Recipe (main table)                  │
│  • RecipeFermentable                    │
│  • RecipeHop                            │
│  • RecipeCulture                        │
│  • RecipeMisc                           │
│  • RecipeWaterProfile                   │
│  • RecipeWaterAdjustment                │
│  • RecipeMashStep                       │
│  • RecipeFermentationStep               │
└─────────────────────────────────────────┘
```

## Database Schema

### Core Recipe Table

```python
class Recipe(Base):
    """Recipes following BeerJSON 1.0 schema."""
    __tablename__ = "recipes"

    id: Mapped[int] = mapped_column(primary_key=True)

    # BeerJSON core fields
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    type: Mapped[Optional[str]] = mapped_column(String(50))  # "All Grain", "Extract", etc.
    author: Mapped[Optional[str]] = mapped_column(String(100))

    # Recipe vitals
    batch_size_liters: Mapped[Optional[float]] = mapped_column()
    boil_time_minutes: Mapped[Optional[int]] = mapped_column()
    efficiency_percent: Mapped[Optional[float]] = mapped_column()

    # Gravity targets (Celsius for all temps)
    og: Mapped[Optional[float]] = mapped_column()
    fg: Mapped[Optional[float]] = mapped_column()
    abv: Mapped[Optional[float]] = mapped_column()
    ibu: Mapped[Optional[float]] = mapped_column()
    color_srm: Mapped[Optional[float]] = mapped_column()
    carbonation_vols: Mapped[Optional[float]] = mapped_column()

    # Style reference
    style_id: Mapped[Optional[str]] = mapped_column(ForeignKey("styles.id"))

    # BeerJSON version tracking
    beerjson_version: Mapped[str] = mapped_column(String(10), default="1.0")

    # Format-specific extensions (JSON)
    # Stores Brewfather nutrition, water settings, metadata, etc.
    format_extensions: Mapped[Optional[dict]] = mapped_column(JSON)

    # Notes
    notes: Mapped[Optional[str]] = mapped_column(Text)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    style: Mapped[Optional["Style"]] = relationship(back_populates="recipes")
    batches: Mapped[list["Batch"]] = relationship(back_populates="recipe")
    fermentables: Mapped[list["RecipeFermentable"]] = relationship(
        back_populates="recipe",
        cascade="all, delete-orphan"
    )
    hops: Mapped[list["RecipeHop"]] = relationship(
        back_populates="recipe",
        cascade="all, delete-orphan"
    )
    cultures: Mapped[list["RecipeCulture"]] = relationship(
        back_populates="recipe",
        cascade="all, delete-orphan"
    )
    miscs: Mapped[list["RecipeMisc"]] = relationship(
        back_populates="recipe",
        cascade="all, delete-orphan"
    )
    water_profiles: Mapped[list["RecipeWaterProfile"]] = relationship(
        back_populates="recipe",
        cascade="all, delete-orphan"
    )
    water_adjustments: Mapped[list["RecipeWaterAdjustment"]] = relationship(
        back_populates="recipe",
        cascade="all, delete-orphan"
    )
    mash_steps: Mapped[list["RecipeMashStep"]] = relationship(
        back_populates="recipe",
        cascade="all, delete-orphan",
        order_by="RecipeMashStep.step_number"
    )
    fermentation_steps: Mapped[list["RecipeFermentationStep"]] = relationship(
        back_populates="recipe",
        cascade="all, delete-orphan",
        order_by="RecipeFermentationStep.step_number"
    )
```

### Ingredient Tables

```python
class RecipeFermentable(Base):
    """Grains, extracts, sugars following BeerJSON fermentable schema."""
    __tablename__ = "recipe_fermentables"

    id: Mapped[int] = mapped_column(primary_key=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id"), nullable=False)

    # BeerJSON fields
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    type: Mapped[str] = mapped_column(String(50))  # grain, extract, sugar, dry extract, adjunct
    grain_group: Mapped[Optional[str]] = mapped_column(String(50))  # base, caramel, roasted, etc.

    # Amounts
    amount_kg: Mapped[float] = mapped_column(nullable=False)
    percentage: Mapped[Optional[float]] = mapped_column()  # % of grain bill

    # Properties
    color_srm: Mapped[Optional[float]] = mapped_column()
    yield_percent: Mapped[Optional[float]] = mapped_column()  # Extract potential
    origin: Mapped[Optional[str]] = mapped_column(String(50))
    supplier: Mapped[Optional[str]] = mapped_column(String(100))

    # BeerJSON timing object (when to add: mash, boil, fermentation)
    timing: Mapped[Optional[dict]] = mapped_column(JSON)

    # Format extensions
    format_extensions: Mapped[Optional[dict]] = mapped_column(JSON)

    # Relationships
    recipe: Mapped["Recipe"] = relationship(back_populates="fermentables")


class RecipeHop(Base):
    """Hop additions following BeerJSON hop schema."""
    __tablename__ = "recipe_hops"

    id: Mapped[int] = mapped_column(primary_key=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id"), nullable=False)

    # BeerJSON fields
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    origin: Mapped[Optional[str]] = mapped_column(String(50))
    form: Mapped[str] = mapped_column(String(20))  # pellet, leaf, plug, extract

    # Alpha acids
    alpha_acid_percent: Mapped[float] = mapped_column(nullable=False)
    beta_acid_percent: Mapped[Optional[float]] = mapped_column()

    # Amount
    amount_grams: Mapped[float] = mapped_column(nullable=False)

    # BeerJSON timing object
    # Critical fields: use, duration, temperature (for hopstand), phase (for dry hop)
    # Example: {"use": "add_to_boil", "duration": {"value": 60, "unit": "min"}}
    # Example: {"use": "add_to_boil", "duration": {"value": 30, "unit": "min"}, "temperature": {"value": 80, "unit": "C"}}
    # Example: {"use": "add_to_fermentation", "phase": "primary", "duration": {"value": 4, "unit": "day"}}
    timing: Mapped[dict] = mapped_column(JSON, nullable=False)

    # Format extensions (Brewfather: usage, day, actualTime)
    format_extensions: Mapped[Optional[dict]] = mapped_column(JSON)

    # Relationships
    recipe: Mapped["Recipe"] = relationship(back_populates="hops")


class RecipeCulture(Base):
    """Yeasts and cultures following BeerJSON culture schema."""
    __tablename__ = "recipe_cultures"

    id: Mapped[int] = mapped_column(primary_key=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id"), nullable=False)

    # BeerJSON fields
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    type: Mapped[str] = mapped_column(String(20))  # ale, lager, wine, brett, bacteria, other
    form: Mapped[str] = mapped_column(String(20))  # liquid, dry, slant, culture

    # Producer info
    producer: Mapped[Optional[str]] = mapped_column(String(100))  # Laboratory
    product_id: Mapped[Optional[str]] = mapped_column(String(50))  # e.g., "US-05"

    # Temperature range (Celsius)
    temp_min_c: Mapped[Optional[float]] = mapped_column()
    temp_max_c: Mapped[Optional[float]] = mapped_column()

    # Attenuation range
    attenuation_min_percent: Mapped[Optional[float]] = mapped_column()
    attenuation_max_percent: Mapped[Optional[float]] = mapped_column()

    # Amount
    amount: Mapped[Optional[float]] = mapped_column()
    amount_unit: Mapped[Optional[str]] = mapped_column(String(10))  # pkg, ml, g, each

    # BeerJSON timing
    timing: Mapped[Optional[dict]] = mapped_column(JSON)

    # Format extensions
    format_extensions: Mapped[Optional[dict]] = mapped_column(JSON)

    # Relationships
    recipe: Mapped["Recipe"] = relationship(back_populates="cultures")


class RecipeMisc(Base):
    """Miscellaneous ingredients (spices, finings, etc.)."""
    __tablename__ = "recipe_miscs"

    id: Mapped[int] = mapped_column(primary_key=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id"), nullable=False)

    # BeerJSON fields
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    type: Mapped[str] = mapped_column(String(50))  # spice, fining, herb, flavor, other

    # Amount
    amount: Mapped[float] = mapped_column(nullable=False)
    amount_unit: Mapped[str] = mapped_column(String(10))  # g, ml, tsp, items, pkg

    # BeerJSON timing
    timing: Mapped[Optional[dict]] = mapped_column(JSON)

    # Format extensions (Brewfather: waterAdjustment flag)
    format_extensions: Mapped[Optional[dict]] = mapped_column(JSON)

    # Relationships
    recipe: Mapped["Recipe"] = relationship(back_populates="miscs")
```

### Water Chemistry Tables

```python
class RecipeWaterProfile(Base):
    """Water chemistry profiles (source, target, mash, sparge)."""
    __tablename__ = "recipe_water_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id"), nullable=False)

    profile_type: Mapped[str] = mapped_column(String(20))  # source, target, mash, sparge, total
    name: Mapped[Optional[str]] = mapped_column(String(100))

    # Ion concentrations (ppm)
    calcium_ppm: Mapped[Optional[float]] = mapped_column()
    magnesium_ppm: Mapped[Optional[float]] = mapped_column()
    sodium_ppm: Mapped[Optional[float]] = mapped_column()
    chloride_ppm: Mapped[Optional[float]] = mapped_column()
    sulfate_ppm: Mapped[Optional[float]] = mapped_column()
    bicarbonate_ppm: Mapped[Optional[float]] = mapped_column()

    # pH and alkalinity
    ph: Mapped[Optional[float]] = mapped_column()
    alkalinity: Mapped[Optional[float]] = mapped_column()

    # Brewfather extensions (hardness, residual alkalinity, ion balance, etc.)
    format_extensions: Mapped[Optional[dict]] = mapped_column(JSON)

    # Relationships
    recipe: Mapped["Recipe"] = relationship(back_populates="water_profiles")


class RecipeWaterAdjustment(Base):
    """Water salt and acid additions (Brewfather specific)."""
    __tablename__ = "recipe_water_adjustments"

    id: Mapped[int] = mapped_column(primary_key=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id"), nullable=False)

    stage: Mapped[str] = mapped_column(String(20))  # mash, sparge, total
    volume_liters: Mapped[Optional[float]] = mapped_column()

    # Salt additions (grams)
    calcium_sulfate_g: Mapped[Optional[float]] = mapped_column()  # Gypsum (CaSO4)
    calcium_chloride_g: Mapped[Optional[float]] = mapped_column()  # CaCl2
    magnesium_sulfate_g: Mapped[Optional[float]] = mapped_column()  # Epsom (MgSO4)
    sodium_bicarbonate_g: Mapped[Optional[float]] = mapped_column()  # Baking soda
    calcium_carbonate_g: Mapped[Optional[float]] = mapped_column()  # Chalk
    calcium_hydroxide_g: Mapped[Optional[float]] = mapped_column()  # Slaked lime
    magnesium_chloride_g: Mapped[Optional[float]] = mapped_column()  # MgCl2
    sodium_chloride_g: Mapped[Optional[float]] = mapped_column()  # Table salt

    # Acid additions
    acid_type: Mapped[Optional[str]] = mapped_column(String(20))  # lactic, phosphoric, etc.
    acid_ml: Mapped[Optional[float]] = mapped_column()
    acid_concentration_percent: Mapped[Optional[float]] = mapped_column()

    # Format extensions
    format_extensions: Mapped[Optional[dict]] = mapped_column(JSON)

    # Relationships
    recipe: Mapped["Recipe"] = relationship(back_populates="water_adjustments")
```

### Procedure Tables

```python
class RecipeMashStep(Base):
    """Mash steps following BeerJSON mash schema."""
    __tablename__ = "recipe_mash_steps"

    id: Mapped[int] = mapped_column(primary_key=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id"), nullable=False)

    step_number: Mapped[int] = mapped_column(nullable=False)  # Order in sequence
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    type: Mapped[str] = mapped_column(String(20))  # infusion, temperature, decoction

    # Temperature and time
    temp_c: Mapped[float] = mapped_column(nullable=False)
    time_minutes: Mapped[int] = mapped_column(nullable=False)

    # Infusion details
    infusion_amount_liters: Mapped[Optional[float]] = mapped_column()
    infusion_temp_c: Mapped[Optional[float]] = mapped_column()

    # Ramp time
    ramp_time_minutes: Mapped[Optional[int]] = mapped_column()

    # Format extensions
    format_extensions: Mapped[Optional[dict]] = mapped_column(JSON)

    # Relationships
    recipe: Mapped["Recipe"] = relationship(back_populates="mash_steps")


class RecipeFermentationStep(Base):
    """Fermentation steps following BeerJSON fermentation schema."""
    __tablename__ = "recipe_fermentation_steps"

    id: Mapped[int] = mapped_column(primary_key=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id"), nullable=False)

    step_number: Mapped[int] = mapped_column(nullable=False)
    type: Mapped[str] = mapped_column(String(20))  # primary, secondary, conditioning

    # Temperature and time
    temp_c: Mapped[float] = mapped_column(nullable=False)
    time_days: Mapped[int] = mapped_column(nullable=False)

    # Format extensions
    format_extensions: Mapped[Optional[dict]] = mapped_column(JSON)

    # Relationships
    recipe: Mapped["Recipe"] = relationship(back_populates="fermentation_steps")
```

## Migration Strategy

### Phase 1: Add New Tables and Columns

```python
# Alembic migration: add_beerjson_support

def upgrade():
    # 1. Add BeerJSON fields to existing Recipe table
    op.add_column('recipes', sa.Column('batch_size_liters', sa.Float(), nullable=True))
    op.add_column('recipes', sa.Column('boil_time_minutes', sa.Integer(), nullable=True))
    op.add_column('recipes', sa.Column('efficiency_percent', sa.Float(), nullable=True))
    op.add_column('recipes', sa.Column('beerjson_version', sa.String(10), nullable=True, default='1.0'))
    op.add_column('recipes', sa.Column('format_extensions', sa.JSON(), nullable=True))

    # Rename columns for clarity
    op.alter_column('recipes', 'og_target', new_column_name='og')
    op.alter_column('recipes', 'fg_target', new_column_name='fg')
    op.alter_column('recipes', 'ibu_target', new_column_name='ibu')
    op.alter_column('recipes', 'srm_target', new_column_name='color_srm')
    op.alter_column('recipes', 'abv_target', new_column_name='abv')

    # 2. Enhance existing ingredient tables
    # RecipeFermentable
    op.add_column('recipe_fermentables', sa.Column('grain_group', sa.String(50), nullable=True))
    op.add_column('recipe_fermentables', sa.Column('percentage', sa.Float(), nullable=True))
    op.add_column('recipe_fermentables', sa.Column('timing', sa.JSON(), nullable=True))
    op.add_column('recipe_fermentables', sa.Column('format_extensions', sa.JSON(), nullable=True))
    op.alter_column('recipe_fermentables', 'amount', new_column_name='amount_kg')
    op.alter_column('recipe_fermentables', 'color', new_column_name='color_srm')

    # RecipeHop
    op.add_column('recipe_hops', sa.Column('beta_acid_percent', sa.Float(), nullable=True))
    op.add_column('recipe_hops', sa.Column('timing', sa.JSON(), nullable=True))
    op.add_column('recipe_hops', sa.Column('format_extensions', sa.JSON(), nullable=True))
    op.alter_column('recipe_hops', 'alpha', new_column_name='alpha_acid_percent')
    op.alter_column('recipe_hops', 'amount', new_column_name='amount_grams')

    # Rename RecipeYeast → RecipeCulture
    op.rename_table('recipe_yeasts', 'recipe_cultures')
    op.add_column('recipe_cultures', sa.Column('timing', sa.JSON(), nullable=True))
    op.add_column('recipe_cultures', sa.Column('format_extensions', sa.JSON(), nullable=True))

    # RecipeMisc
    op.add_column('recipe_miscs', sa.Column('amount_unit', sa.String(10), nullable=True))
    op.add_column('recipe_miscs', sa.Column('timing', sa.JSON(), nullable=True))
    op.add_column('recipe_miscs', sa.Column('format_extensions', sa.JSON(), nullable=True))

    # 3. Create new tables
    op.create_table('recipe_water_profiles',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('recipe_id', sa.Integer(), nullable=False),
        sa.Column('profile_type', sa.String(20), nullable=False),
        sa.Column('name', sa.String(100), nullable=True),
        sa.Column('calcium_ppm', sa.Float(), nullable=True),
        sa.Column('magnesium_ppm', sa.Float(), nullable=True),
        sa.Column('sodium_ppm', sa.Float(), nullable=True),
        sa.Column('chloride_ppm', sa.Float(), nullable=True),
        sa.Column('sulfate_ppm', sa.Float(), nullable=True),
        sa.Column('bicarbonate_ppm', sa.Float(), nullable=True),
        sa.Column('ph', sa.Float(), nullable=True),
        sa.Column('alkalinity', sa.Float(), nullable=True),
        sa.Column('format_extensions', sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(['recipe_id'], ['recipes.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table('recipe_water_adjustments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('recipe_id', sa.Integer(), nullable=False),
        sa.Column('stage', sa.String(20), nullable=False),
        sa.Column('volume_liters', sa.Float(), nullable=True),
        sa.Column('calcium_sulfate_g', sa.Float(), nullable=True),
        sa.Column('calcium_chloride_g', sa.Float(), nullable=True),
        sa.Column('magnesium_sulfate_g', sa.Float(), nullable=True),
        sa.Column('sodium_bicarbonate_g', sa.Float(), nullable=True),
        sa.Column('calcium_carbonate_g', sa.Float(), nullable=True),
        sa.Column('calcium_hydroxide_g', sa.Float(), nullable=True),
        sa.Column('magnesium_chloride_g', sa.Float(), nullable=True),
        sa.Column('sodium_chloride_g', sa.Float(), nullable=True),
        sa.Column('acid_type', sa.String(20), nullable=True),
        sa.Column('acid_ml', sa.Float(), nullable=True),
        sa.Column('acid_concentration_percent', sa.Float(), nullable=True),
        sa.Column('format_extensions', sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(['recipe_id'], ['recipes.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table('recipe_mash_steps',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('recipe_id', sa.Integer(), nullable=False),
        sa.Column('step_number', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('type', sa.String(20), nullable=False),
        sa.Column('temp_c', sa.Float(), nullable=False),
        sa.Column('time_minutes', sa.Integer(), nullable=False),
        sa.Column('infusion_amount_liters', sa.Float(), nullable=True),
        sa.Column('infusion_temp_c', sa.Float(), nullable=True),
        sa.Column('ramp_time_minutes', sa.Integer(), nullable=True),
        sa.Column('format_extensions', sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(['recipe_id'], ['recipes.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table('recipe_fermentation_steps',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('recipe_id', sa.Integer(), nullable=False),
        sa.Column('step_number', sa.Integer(), nullable=False),
        sa.Column('type', sa.String(20), nullable=False),
        sa.Column('temp_c', sa.Float(), nullable=False),
        sa.Column('time_days', sa.Integer(), nullable=False),
        sa.Column('format_extensions', sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(['recipe_id'], ['recipes.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
```

### Phase 2: Data Migration for Existing Recipes

```python
def migrate_existing_hop_timing():
    """Convert existing hop 'use' + 'time' to BeerJSON timing object."""
    connection = op.get_bind()

    # Fetch all existing hops
    hops = connection.execute(sa.text(
        "SELECT id, use, time FROM recipe_hops WHERE timing IS NULL"
    ))

    for hop in hops:
        # Map BeerXML use to BeerJSON timing
        use_mapping = {
            "Boil": "add_to_boil",
            "Dry Hop": "add_to_fermentation",
            "Mash": "add_to_mash",
            "First Wort": "add_to_boil",
            "Aroma": "add_to_boil"
        }

        timing = {
            "use": use_mapping.get(hop.use, "add_to_boil"),
            "continuous": False
        }

        # Add duration for boil additions
        if hop.use == "Boil" and hop.time > 0:
            timing["duration"] = {
                "value": hop.time,
                "unit": "min"
            }

        # Dry hop phase
        if hop.use == "Dry Hop":
            timing["phase"] = "primary"
            if hop.time > 0:
                # Convert minutes to days (BeerXML quirk)
                timing["duration"] = {
                    "value": int(hop.time / 1440),
                    "unit": "day"
                }

        # Update timing column
        connection.execute(
            sa.text("UPDATE recipe_hops SET timing = :timing WHERE id = :id"),
            {"timing": json.dumps(timing), "id": hop.id}
        )
```

## Service Layer Implementation

### Core Services

```python
# backend/services/recipe_importer.py

class RecipeImporter:
    """Multi-format recipe import orchestrator."""

    def __init__(self):
        self.beerxml_parser = BeerXMLParser()
        self.beerxml_converter = BeerXMLToBeerJSONConverter()
        self.brewfather_converter = BrewfatherToBeerJSONConverter()
        self.beerjson_validator = BeerJSONValidator()
        self.serializer = RecipeSerializer()

    async def import_file(
        self,
        file_content: bytes,
        filename: str,
        db: AsyncSession
    ) -> Recipe:
        """Auto-detect format and import recipe.

        Raises:
            ValueError: Unsupported file format or invalid data
            ValidationError: Invalid BeerJSON schema
        """
        # Phase 1: Detect and parse
        beerjson_dict = self._detect_and_parse(file_content, filename)

        # Phase 2: Validate
        self.beerjson_validator.validate(beerjson_dict)

        # Phase 3: Persist
        recipe = await self.serializer.from_beerjson(beerjson_dict, db)

        db.add(recipe)
        await db.commit()
        await db.refresh(recipe)

        return recipe

    def _detect_and_parse(self, content: bytes, filename: str) -> dict:
        """Detect file format and parse to BeerJSON."""
        if filename.endswith('.xml'):
            return self._parse_xml(content)
        elif filename.endswith('.json'):
            return self._parse_json(content)
        else:
            raise ValueError(f"Unsupported file format: {filename}")

    def _parse_xml(self, content: bytes) -> dict:
        """Parse BeerXML (with optional Brewfather extensions)."""
        xml_content = content.decode('utf-8')
        beerxml_dict = self.beerxml_parser.parse(xml_content)

        # Convert to BeerJSON
        return self.beerxml_converter.convert(beerxml_dict)

    def _parse_json(self, content: bytes) -> dict:
        """Parse JSON (Brewfather or BeerJSON)."""
        raw_data = json.loads(content.decode('utf-8'))

        # Detect format
        if self._is_brewfather_format(raw_data):
            # Brewfather JSON
            return self.brewfather_converter.convert(raw_data)
        elif self._is_beerjson_format(raw_data):
            # Native BeerJSON
            return raw_data
        else:
            raise ValueError("Unknown JSON format (not Brewfather or BeerJSON)")

    def _is_brewfather_format(self, data: dict) -> bool:
        """Detect Brewfather JSON format."""
        # Brewfather has '_id', 'fermentables', 'hops' at root level
        return '_id' in data and 'fermentables' in data and 'hops' in data

    def _is_beerjson_format(self, data: dict) -> bool:
        """Detect BeerJSON format."""
        # BeerJSON has 'beerjson' root with 'version' and 'recipes'
        return 'beerjson' in data and 'version' in data['beerjson']
```

```python
# backend/services/recipe_serializer.py

class RecipeSerializer:
    """Serialize/deserialize between BeerJSON dict and SQLAlchemy models."""

    async def from_beerjson(self, beerjson_dict: dict, db: AsyncSession) -> Recipe:
        """Deserialize BeerJSON dict → SQLAlchemy Recipe model."""
        # Extract recipe from beerjson wrapper
        recipe_data = beerjson_dict['beerjson']['recipes'][0]

        # Create Recipe
        recipe = Recipe(
            name=recipe_data['name'],
            type=recipe_data.get('type'),
            author=recipe_data.get('author'),
            batch_size_liters=self._extract_value(recipe_data.get('batch_size')),
            boil_time_minutes=self._extract_value(recipe_data.get('boil', {}).get('boil_time')),
            efficiency_percent=self._extract_value(
                recipe_data.get('efficiency', {}).get('brewhouse')
            ),
            og=self._extract_value(recipe_data.get('original_gravity')),
            fg=self._extract_value(recipe_data.get('final_gravity')),
            abv=self._extract_value(recipe_data.get('alcohol_by_volume')),
            ibu=self._extract_value(recipe_data.get('ibu_estimate')),
            color_srm=self._extract_value(recipe_data.get('color_estimate')),
            carbonation_vols=self._extract_value(recipe_data.get('carbonation')),
            beerjson_version=beerjson_dict['beerjson']['version'],
            format_extensions=recipe_data.get('_extensions'),
            notes=recipe_data.get('notes')
        )

        # Deserialize ingredients
        ingredients = recipe_data.get('ingredients', {})

        # Fermentables
        for ferm_data in ingredients.get('fermentables', []):
            fermentable = RecipeFermentable(
                name=ferm_data['name'],
                type=ferm_data.get('type'),
                grain_group=ferm_data.get('grain_group'),
                amount_kg=self._extract_value(ferm_data['amount']),
                percentage=ferm_data.get('percentage'),
                color_srm=self._extract_value(ferm_data.get('color')),
                yield_percent=self._extract_value(
                    ferm_data.get('yield', {}).get('fine_grind')
                ),
                origin=ferm_data.get('origin'),
                supplier=ferm_data.get('producer'),
                timing=ferm_data.get('timing'),
                format_extensions=ferm_data.get('_extensions')
            )
            recipe.fermentables.append(fermentable)

        # Hops
        for hop_data in ingredients.get('hops', []):
            hop = RecipeHop(
                name=hop_data['name'],
                origin=hop_data.get('origin'),
                form=hop_data.get('form'),
                alpha_acid_percent=self._extract_value(hop_data.get('alpha_acid')),
                beta_acid_percent=self._extract_value(hop_data.get('beta_acid')),
                amount_grams=self._extract_value(hop_data['amount']),
                timing=hop_data['timing'],
                format_extensions=hop_data.get('_extensions')
            )
            recipe.hops.append(hop)

        # Cultures (yeasts)
        for culture_data in ingredients.get('cultures', []):
            culture = RecipeCulture(
                name=culture_data['name'],
                type=culture_data.get('type'),
                form=culture_data.get('form'),
                producer=culture_data.get('producer'),
                product_id=culture_data.get('product_id'),
                temp_min_c=self._extract_value(
                    culture_data.get('temperature_range', {}).get('minimum')
                ),
                temp_max_c=self._extract_value(
                    culture_data.get('temperature_range', {}).get('maximum')
                ),
                attenuation_min_percent=self._extract_value(
                    culture_data.get('attenuation', {}).get('minimum')
                ),
                attenuation_max_percent=self._extract_value(
                    culture_data.get('attenuation', {}).get('maximum')
                ),
                amount=self._extract_value(culture_data.get('amount')),
                amount_unit=culture_data.get('amount', {}).get('unit'),
                timing=culture_data.get('timing'),
                format_extensions=culture_data.get('_extensions')
            )
            recipe.cultures.append(culture)

        # Miscs
        for misc_data in ingredients.get('miscellaneous_ingredients', []):
            misc = RecipeMisc(
                name=misc_data['name'],
                type=misc_data.get('type'),
                amount=self._extract_value(misc_data['amount']),
                amount_unit=misc_data.get('amount', {}).get('unit'),
                timing=misc_data.get('timing'),
                format_extensions=misc_data.get('_extensions')
            )
            recipe.miscs.append(misc)

        # Water profiles
        for water_data in recipe_data.get('water_additions', []):
            profile = RecipeWaterProfile(
                profile_type=self._infer_water_profile_type(water_data),
                name=water_data.get('name'),
                calcium_ppm=self._extract_value(water_data.get('calcium')),
                magnesium_ppm=self._extract_value(water_data.get('magnesium')),
                sodium_ppm=self._extract_value(water_data.get('sodium')),
                chloride_ppm=self._extract_value(water_data.get('chloride')),
                sulfate_ppm=self._extract_value(water_data.get('sulfate')),
                bicarbonate_ppm=self._extract_value(water_data.get('bicarbonate')),
                ph=water_data.get('ph'),
                format_extensions=water_data.get('_extensions')
            )
            recipe.water_profiles.append(profile)

        # Mash steps
        mash_data = recipe_data.get('mash', {})
        for idx, step_data in enumerate(mash_data.get('mash_steps', []), start=1):
            step = RecipeMashStep(
                step_number=idx,
                name=step_data['name'],
                type=step_data['type'],
                temp_c=self._extract_value(step_data['step_temperature']),
                time_minutes=int(self._extract_value(step_data['step_time'])),
                infusion_amount_liters=self._extract_value(step_data.get('infusion_amount')),
                ramp_time_minutes=self._extract_value(step_data.get('ramp_time')),
                format_extensions=step_data.get('_extensions')
            )
            recipe.mash_steps.append(step)

        # Fermentation steps
        fermentation_data = recipe_data.get('fermentation', {})
        for idx, step_data in enumerate(fermentation_data.get('fermentation_steps', []), start=1):
            step = RecipeFermentationStep(
                step_number=idx,
                type=step_data['type'],
                temp_c=self._extract_value(step_data['step_temperature']),
                time_days=int(self._extract_value(step_data['step_time'])),
                format_extensions=step_data.get('_extensions')
            )
            recipe.fermentation_steps.append(step)

        return recipe

    def _extract_value(self, obj: Optional[dict]) -> Optional[float]:
        """Extract value from BeerJSON unit object."""
        if obj is None:
            return None
        if isinstance(obj, dict) and 'value' in obj:
            return float(obj['value'])
        return None

    def _infer_water_profile_type(self, water_data: dict) -> str:
        """Infer water profile type from name."""
        name = water_data.get('name', '').lower()
        if 'source' in name:
            return 'source'
        elif 'target' in name:
            return 'target'
        elif 'mash' in name:
            return 'mash'
        elif 'sparge' in name:
            return 'sparge'
        else:
            return 'source'  # Default
```

## Testing Strategy

### Test Data

Use real Brewfather exports as integration test fixtures:
- `docs/Brewfather_BeerXML_PhilterXPAClone_20251207.xml`
- `docs/Brewfather_RECIPE_PhilterXPAClone_20251207.json`

### Test Cases

```python
# tests/test_recipe_import.py

class TestRecipeImport:
    """Integration tests for recipe import."""

    async def test_import_brewfather_xml(self, db):
        """Test import of Brewfather BeerXML export."""
        with open("docs/Brewfather_BeerXML_PhilterXPAClone_20251207.xml", "rb") as f:
            content = f.read()

        importer = RecipeImporter()
        recipe = await importer.import_file(content, "test.xml", db)

        # Verify recipe basics
        assert recipe.name == "Philter XPA - Clone"
        assert recipe.type == "All Grain"
        assert recipe.author == "Pig Den Brewing"
        assert recipe.og == pytest.approx(1.040)
        assert recipe.fg == pytest.approx(1.008)
        assert recipe.abv == pytest.approx(4.2)

        # Verify ingredients
        assert len(recipe.fermentables) == 4
        assert len(recipe.hops) == 6
        assert len(recipe.cultures) == 1
        assert len(recipe.miscs) == 8

        # Verify hopstand temperature (Brewfather extension)
        citra_hop = next(h for h in recipe.hops if h.name == "Citra" and h.amount_grams == 46)
        assert citra_hop.timing['temperature']['value'] == 80
        assert citra_hop.timing['temperature']['unit'] == "C"

        # Verify mash steps
        assert len(recipe.mash_steps) == 3
        assert recipe.mash_steps[0].name == "Mash in"
        assert recipe.mash_steps[0].temp_c == 55

    async def test_import_brewfather_json(self, db):
        """Test import of Brewfather JSON export."""
        with open("docs/Brewfather_RECIPE_PhilterXPAClone_20251207.json", "rb") as f:
            content = f.read()

        importer = RecipeImporter()
        recipe = await importer.import_file(content, "test.json", db)

        # Same assertions as XML test
        assert recipe.name == "Philter XPA - Clone"

        # Verify water chemistry (only in JSON export)
        assert len(recipe.water_profiles) > 0
        source_water = next(w for w in recipe.water_profiles if w.profile_type == "source")
        assert source_water.calcium_ppm == pytest.approx(9.98)

        # Verify water adjustments
        assert len(recipe.water_adjustments) > 0
        mash_adj = next(w for w in recipe.water_adjustments if w.stage == "mash")
        assert mash_adj.calcium_sulfate_g == pytest.approx(4.47)

    async def test_round_trip_brewfather_json(self, db):
        """Test import → export → import preserves data."""
        # Import
        with open("docs/Brewfather_RECIPE_PhilterXPAClone_20251207.json", "rb") as f:
            original_content = f.read()

        importer = RecipeImporter()
        recipe1 = await importer.import_file(original_content, "test.json", db)

        # Export
        exporter = RecipeExporter()
        exported = await exporter.export_brewfather_json(recipe1)

        # Re-import
        recipe2 = await importer.import_file(
            json.dumps(exported).encode(),
            "test2.json",
            db
        )

        # Verify data integrity
        assert recipe2.name == recipe1.name
        assert recipe2.og == recipe1.og
        assert len(recipe2.hops) == len(recipe1.hops)
        assert len(recipe2.water_profiles) == len(recipe1.water_profiles)
```

## API Endpoints

### Import Endpoint

```python
# backend/routers/recipes.py

@router.post("/import", response_model=RecipeResponse)
async def import_recipe(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
):
    """Import recipe from BeerXML, BeerJSON, or Brewfather JSON.

    Supports:
    - .xml: BeerXML 1.0 (with Brewfather extensions)
    - .json: BeerJSON 1.0 or Brewfather JSON

    Returns the imported recipe with all ingredients and procedures.
    """
    # Validate file size
    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="File is empty")
    if len(content) > 5_000_000:  # 5MB limit
        raise HTTPException(status_code=400, detail="File too large (max 5MB)")

    # Import
    try:
        importer = RecipeImporter()
        recipe = await importer.import_file(content, file.filename, db)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=f"Invalid recipe format: {e}")

    return recipe
```

### Export Endpoints

```python
@router.get("/{recipe_id}/export/beerjson")
async def export_beerjson(
    recipe_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Export recipe as BeerJSON 1.0."""
    recipe = await get_recipe_with_relationships(recipe_id, db)
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")

    exporter = RecipeExporter()
    beerjson = await exporter.export_beerjson(recipe)

    return JSONResponse(
        content=beerjson,
        headers={
            "Content-Disposition": f'attachment; filename="{recipe.name}.json"'
        }
    )


@router.get("/{recipe_id}/export/beerxml")
async def export_beerxml(
    recipe_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Export recipe as BeerXML 1.0 (compatibility)."""
    recipe = await get_recipe_with_relationships(recipe_id, db)
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")

    exporter = RecipeExporter()
    beerxml_str = await exporter.export_beerxml(recipe)

    return Response(
        content=beerxml_str,
        media_type="application/xml",
        headers={
            "Content-Disposition": f'attachment; filename="{recipe.name}.xml"'
        }
    )


@router.get("/{recipe_id}/export/brewfather")
async def export_brewfather(
    recipe_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Export recipe as Brewfather JSON (preserves all extensions)."""
    recipe = await get_recipe_with_relationships(recipe_id, db)
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")

    exporter = RecipeExporter()
    brewfather_json = await exporter.export_brewfather_json(recipe)

    return JSONResponse(
        content=brewfather_json,
        headers={
            "Content-Disposition": f'attachment; filename="{recipe.name}.json"'
        }
    )
```

## Success Criteria

1. **✅ Multi-format import works:**
   - Import Brewfather BeerXML (Philter XPA example)
   - Import Brewfather JSON (Philter XPA example)
   - Import native BeerJSON
   - All imports pass without errors

2. **✅ Data preservation:**
   - Hopstand temperatures preserved (80°C from Philter XPA)
   - Water chemistry preserved (6 salt additions from Philter XPA)
   - Mash steps preserved (3 steps from Philter XPA)
   - Dry hop timing preserved (day 10 from Philter XPA)

3. **✅ Round-trip integrity:**
   - Import Brewfather JSON → Export Brewfather JSON → Re-import
   - Critical fields match (name, OG, FG, hop count, etc.)
   - Hopstand temps preserved through round trip

4. **✅ Database query performance:**
   - Find recipes by hop variety: `SELECT * FROM recipes JOIN recipe_hops ON ... WHERE name = 'Citra'`
   - Find recipes by mash temp: `SELECT * FROM recipes JOIN recipe_mash_steps ON ... WHERE temp_c BETWEEN 65 AND 68`
   - Query performance < 100ms for typical recipe library (< 1000 recipes)

5. **✅ Backward compatibility:**
   - Existing BeerXML recipes migrate successfully
   - No data loss from current schema
   - Existing batches still link to recipes

## Future Enhancements

- **Phase 2:** Recipe designer UI (drag-drop ingredients, auto-calculations)
- **Phase 3:** Ingredient inventory tracking (track stock levels)
- **Phase 4:** Recipe scaling (adjust batch size, maintain ratios)
- **Phase 5:** Brew day mode (step-by-step guidance, timers)
- **Phase 6:** Recipe sharing (public recipe library, ratings)

## References

- **BeerJSON 1.0 Spec:** https://github.com/beerjson/beerjson
- **BeerXML 1.0 Spec:** http://www.beerxml.com/
- **Brewfather Documentation:** https://docs.brewfather.app/
- **Test Data:** Real Philter XPA exports in `docs/`
