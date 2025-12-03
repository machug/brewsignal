# Ingredients Database & Recipe Builder Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create an ingredients library database that enables recipe editing and building from scratch, replacing read-only BeerXML imports with a flexible ingredient-based system.

**Architecture:** Add four ingredient library tables (Fermentable, Hop, Yeast, Misc) as master data sources. Modify existing RecipeFermentable/RecipeHop/RecipeYeast/RecipeMisc tables to reference library items via foreign keys while preserving recipe-specific amounts. Create Brewfather API sync service to populate library from recipes. Build REST API endpoints for CRUD operations on ingredients and recipes.

**Tech Stack:** FastAPI, SQLAlchemy 2.0, Alembic (migrations), Pydantic (validation), httpx (Brewfather API), pytest

---

## Phase 1: Ingredient Library Schema

### Task 1: Create Fermentable Library Model

**Files:**
- Modify: `backend/models.py` (add after line 477)
- Create: `backend/alembic/versions/XXXX_add_ingredient_library.py`
- Create: `backend/tests/test_fermentable_library.py`

**Step 1: Write the failing test**

Create `backend/tests/test_fermentable_library.py`:

```python
"""Tests for ingredient library models."""
import pytest
from sqlalchemy import select

from backend.models import Fermentable


@pytest.mark.asyncio
async def test_create_fermentable(db_session):
    """Test creating a fermentable ingredient."""
    fermentable = Fermentable(
        name="Pale Ale Malt",
        supplier="BestMalz",
        origin="Germany",
        type="Grain",
        yield_percent=82.8,
        color_lovibond=3.0,
        grain_category="Base",
        potential_percentage=82.8,
        notes="Excellent base malt for pale ales",
    )
    db_session.add(fermentable)
    await db_session.commit()
    await db_session.refresh(fermentable)

    # Verify
    assert fermentable.id is not None
    assert fermentable.name == "Pale Ale Malt"
    assert fermentable.supplier == "BestMalz"


@pytest.mark.asyncio
async def test_fermentable_unique_brewfather_id(db_session):
    """Test that brewfather_id must be unique."""
    # Create first fermentable with brewfather_id
    f1 = Fermentable(
        name="Pale Ale",
        type="Grain",
        brewfather_id="default-592f3ac",
    )
    db_session.add(f1)
    await db_session.commit()

    # Try to create duplicate brewfather_id
    f2 = Fermentable(
        name="Different Name",
        type="Grain",
        brewfather_id="default-592f3ac",
    )
    db_session.add(f2)

    with pytest.raises(Exception):  # IntegrityError
        await db_session.commit()
```

**Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_fermentable_library.py -v`
Expected: FAIL with "no such table: fermentables" or "ImportError: cannot import name 'Fermentable'"

**Step 3: Write Fermentable model**

Add to `backend/models.py` after RecipeMisc class (after line 477):

```python
# Ingredient Library Models

class Fermentable(Base):
    """Master library of fermentable ingredients."""
    __tablename__ = "fermentables"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Brewfather integration
    brewfather_id: Mapped[Optional[str]] = mapped_column(String(100), unique=True, index=True)

    # Core fields
    name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    supplier: Mapped[Optional[str]] = mapped_column(String(100))
    origin: Mapped[Optional[str]] = mapped_column(String(50))
    type: Mapped[str] = mapped_column(String(50), nullable=False)  # Grain, Sugar, Extract, Dry Extract, Adjunct

    # Brewing characteristics
    yield_percent: Mapped[Optional[float]] = mapped_column()  # % yield (0-100)
    color_lovibond: Mapped[Optional[float]] = mapped_column()  # SRM/Lovibond
    potential_percentage: Mapped[Optional[float]] = mapped_column()  # Potential extract %

    # Classification
    grain_category: Mapped[Optional[str]] = mapped_column(String(50))  # Base, Crystal/Caramel, Roasted, etc

    # Metadata
    notes: Mapped[Optional[str]] = mapped_column(Text)

    # Advanced fields (optional)
    coarse_fine_diff: Mapped[Optional[float]] = mapped_column()  # %
    moisture: Mapped[Optional[float]] = mapped_column()  # %
    diastatic_power: Mapped[Optional[float]] = mapped_column()  # Lintner
    protein: Mapped[Optional[float]] = mapped_column()  # %
    max_in_batch: Mapped[Optional[float]] = mapped_column()  # %
    recommend_mash: Mapped[Optional[bool]] = mapped_column()

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )

    # Composite index for fast lookups
    __table_args__ = (
        Index('ix_fermentables_name_supplier', 'name', 'supplier'),
    )
```

**Step 4: Create migration**

Run: `cd backend && alembic revision --autogenerate -m "Add ingredient library tables"`

This creates a migration file. Review it to ensure it creates the fermentables table.

**Step 5: Run migration**

Run: `cd backend && alembic upgrade head`
Expected: Migration applies successfully

**Step 6: Run test to verify it passes**

Run: `pytest backend/tests/test_fermentable_library.py -v`
Expected: PASS (2 tests)

**Step 7: Commit**

```bash
git add backend/models.py backend/tests/test_fermentable_library.py backend/alembic/versions/*_add_ingredient_library.py
git commit -m "feat: add Fermentable library model with Brewfather integration"
```

---

### Task 2: Create Hop Library Model

**Files:**
- Modify: `backend/models.py` (add after Fermentable class)
- Modify: `backend/tests/test_fermentable_library.py` → rename to `backend/tests/test_ingredient_library.py`

**Step 1: Write the failing test**

Add to `backend/tests/test_ingredient_library.py`:

```python
from backend.models import Hop


@pytest.mark.asyncio
async def test_create_hop(db_session):
    """Test creating a hop ingredient."""
    hop = Hop(
        name="Cascade",
        origin="US",
        alpha_percent=5.5,
        type="Bittering/Aroma",
        form="Pellet",
        notes="Floral and citrus characteristics",
    )
    db_session.add(hop)
    await db_session.commit()
    await db_session.refresh(hop)

    assert hop.id is not None
    assert hop.name == "Cascade"
    assert hop.alpha_percent == 5.5


@pytest.mark.asyncio
async def test_hop_unique_brewfather_id(db_session):
    """Test that hop brewfather_id must be unique."""
    h1 = Hop(name="Cascade", brewfather_id="default-58d2b845")
    db_session.add(h1)
    await db_session.commit()

    h2 = Hop(name="Different", brewfather_id="default-58d2b845")
    db_session.add(h2)

    with pytest.raises(Exception):
        await db_session.commit()
```

**Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_ingredient_library.py::test_create_hop -v`
Expected: FAIL with "cannot import name 'Hop'"

**Step 3: Write Hop model**

Add to `backend/models.py` after Fermentable class:

```python
class Hop(Base):
    """Master library of hop varieties."""
    __tablename__ = "hops"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Brewfather integration
    brewfather_id: Mapped[Optional[str]] = mapped_column(String(100), unique=True, index=True)

    # Core fields
    name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    origin: Mapped[Optional[str]] = mapped_column(String(50))

    # Hop characteristics
    alpha_percent: Mapped[Optional[float]] = mapped_column()  # AA% (0-100)
    beta_percent: Mapped[Optional[float]] = mapped_column()  # Beta acids %
    type: Mapped[Optional[str]] = mapped_column(String(20))  # Bittering, Aroma, Both
    form: Mapped[Optional[str]] = mapped_column(String(20))  # Pellet, Plug, Leaf

    # Additional properties
    substitutes: Mapped[Optional[str]] = mapped_column(String(200))
    hsi: Mapped[Optional[float]] = mapped_column()  # Hop Storage Index

    # Oil composition (%)
    humulene: Mapped[Optional[float]] = mapped_column()
    caryophyllene: Mapped[Optional[float]] = mapped_column()
    cohumulone: Mapped[Optional[float]] = mapped_column()
    myrcene: Mapped[Optional[float]] = mapped_column()

    # Metadata
    notes: Mapped[Optional[str]] = mapped_column(Text)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        Index('ix_hops_name_origin', 'name', 'origin'),
    )
```

**Step 4: Create and run migration**

Run: `cd backend && alembic revision --autogenerate -m "Add Hop library model"`
Then: `cd backend && alembic upgrade head`

**Step 5: Run test to verify it passes**

Run: `pytest backend/tests/test_ingredient_library.py::test_create_hop -v`
Expected: PASS

**Step 6: Commit**

```bash
git add backend/models.py backend/tests/test_ingredient_library.py backend/alembic/versions/*_add_hop_library_model.py
git commit -m "feat: add Hop library model"
```

---

### Task 3: Create Yeast Library Model

**Files:**
- Modify: `backend/models.py` (add after Hop class)
- Modify: `backend/tests/test_ingredient_library.py`

**Step 1: Write the failing test**

Add to `backend/tests/test_ingredient_library.py`:

```python
from backend.models import Yeast


@pytest.mark.asyncio
async def test_create_yeast(db_session):
    """Test creating a yeast strain."""
    yeast = Yeast(
        name="California Ale",
        lab="White Labs",
        product_id="WLP001",
        type="Ale",
        form="Liquid",
        attenuation_percent=75.0,
        temp_min_c=18.0,
        temp_max_c=22.0,
        flocculation="Medium",
    )
    db_session.add(yeast)
    await db_session.commit()
    await db_session.refresh(yeast)

    assert yeast.id is not None
    assert yeast.name == "California Ale"
    assert yeast.product_id == "WLP001"
```

**Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_ingredient_library.py::test_create_yeast -v`
Expected: FAIL

**Step 3: Write Yeast model**

Add to `backend/models.py` after Hop class:

```python
class Yeast(Base):
    """Master library of yeast strains."""
    __tablename__ = "yeasts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Brewfather integration
    brewfather_id: Mapped[Optional[str]] = mapped_column(String(100), unique=True, index=True)

    # Core fields
    name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    lab: Mapped[Optional[str]] = mapped_column(String(100))
    product_id: Mapped[Optional[str]] = mapped_column(String(50))

    # Yeast characteristics
    type: Mapped[Optional[str]] = mapped_column(String(20))  # Ale, Lager, Wheat, Wine, Champagne
    form: Mapped[Optional[str]] = mapped_column(String(20))  # Liquid, Dry, Slant, Culture

    # Fermentation characteristics
    attenuation_percent: Mapped[Optional[float]] = mapped_column()  # % (0-100)
    temp_min_c: Mapped[Optional[float]] = mapped_column()  # Celsius
    temp_max_c: Mapped[Optional[float]] = mapped_column()  # Celsius
    flocculation: Mapped[Optional[str]] = mapped_column(String(20))  # Low, Medium, High, Very High

    # Additional properties
    alcohol_tolerance: Mapped[Optional[float]] = mapped_column()  # Max ABV %
    best_for: Mapped[Optional[str]] = mapped_column(Text)
    notes: Mapped[Optional[str]] = mapped_column(Text)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        Index('ix_yeasts_lab_product_id', 'lab', 'product_id'),
    )
```

**Step 4: Create and run migration**

Run: `cd backend && alembic revision --autogenerate -m "Add Yeast library model"`
Then: `cd backend && alembic upgrade head`

**Step 5: Run test to verify it passes**

Run: `pytest backend/tests/test_ingredient_library.py::test_create_yeast -v`
Expected: PASS

**Step 6: Commit**

```bash
git add backend/models.py backend/tests/test_ingredient_library.py backend/alembic/versions/*_add_yeast_library_model.py
git commit -m "feat: add Yeast library model"
```

---

### Task 4: Create Misc Library Model

**Files:**
- Modify: `backend/models.py` (add after Yeast class)
- Modify: `backend/tests/test_ingredient_library.py`

**Step 1: Write the failing test**

Add to `backend/tests/test_ingredient_library.py`:

```python
from backend.models import Misc


@pytest.mark.asyncio
async def test_create_misc(db_session):
    """Test creating a misc ingredient."""
    misc = Misc(
        name="Irish Moss",
        type="Fining",
        use_for="Clarity",
        notes="Kettle fining agent",
    )
    db_session.add(misc)
    await db_session.commit()
    await db_session.refresh(misc)

    assert misc.id is not None
    assert misc.name == "Irish Moss"
    assert misc.type == "Fining"
```

**Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_ingredient_library.py::test_create_misc -v`
Expected: FAIL

**Step 3: Write Misc model**

Add to `backend/models.py` after Yeast class:

```python
class Misc(Base):
    """Master library of misc ingredients (spices, finings, water agents, etc)."""
    __tablename__ = "miscs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Brewfather integration
    brewfather_id: Mapped[Optional[str]] = mapped_column(String(100), unique=True, index=True)

    # Core fields
    name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(50), nullable=False)  # Spice, Fining, Water Agent, Herb, Flavor, Other

    # Metadata
    use_for: Mapped[Optional[str]] = mapped_column(Text)
    notes: Mapped[Optional[str]] = mapped_column(Text)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )
```

**Step 4: Create and run migration**

Run: `cd backend && alembic revision --autogenerate -m "Add Misc library model"`
Then: `cd backend && alembic upgrade head`

**Step 5: Run test to verify it passes**

Run: `pytest backend/tests/test_ingredient_library.py::test_create_misc -v`
Expected: PASS

**Step 6: Commit**

```bash
git add backend/models.py backend/tests/test_ingredient_library.py backend/alembic/versions/*_add_misc_library_model.py
git commit -m "feat: add Misc library model"
```

---

## Phase 2: Link Recipe Ingredients to Library

### Task 5: Add Foreign Keys to RecipeFermentable

**Files:**
- Modify: `backend/models.py` (RecipeFermentable class around line 359)
- Create: `backend/tests/test_recipe_ingredient_linking.py`

**Step 1: Write the failing test**

Create `backend/tests/test_recipe_ingredient_linking.py`:

```python
"""Tests for linking recipe ingredients to library."""
import pytest
from sqlalchemy import select

from backend.models import Recipe, RecipeFermentable, Fermentable, Style


@pytest.mark.asyncio
async def test_link_recipe_fermentable_to_library(db_session):
    """Test that recipe fermentable can reference library fermentable."""
    # Create library fermentable
    lib_ferm = Fermentable(
        name="Pale Ale Malt",
        supplier="BestMalz",
        type="Grain",
        yield_percent=82.8,
    )
    db_session.add(lib_ferm)
    await db_session.flush()

    # Create recipe with style
    style = Style(name="American Pale Ale")
    db_session.add(style)
    await db_session.flush()

    recipe = Recipe(name="Test Recipe", style_id=style.id)
    db_session.add(recipe)
    await db_session.flush()

    # Create recipe fermentable linked to library
    recipe_ferm = RecipeFermentable(
        recipe_id=recipe.id,
        fermentable_id=lib_ferm.id,
        amount_kg=5.0,
        # Name and other fields should come from library reference
    )
    db_session.add(recipe_ferm)
    await db_session.commit()

    # Verify relationship
    await db_session.refresh(recipe_ferm)
    assert recipe_ferm.fermentable_id == lib_ferm.id
    assert recipe_ferm.fermentable.name == "Pale Ale Malt"


@pytest.mark.asyncio
async def test_recipe_fermentable_without_library_reference(db_session):
    """Test that recipe fermentable can still work without library reference (legacy support)."""
    style = Style(name="American Pale Ale")
    db_session.add(style)
    await db_session.flush()

    recipe = Recipe(name="Test Recipe", style_id=style.id)
    db_session.add(recipe)
    await db_session.flush()

    # Create recipe fermentable WITHOUT library reference (legacy BeerXML import)
    recipe_ferm = RecipeFermentable(
        recipe_id=recipe.id,
        fermentable_id=None,  # No library link
        name="Custom Malt",
        type="Grain",
        amount_kg=5.0,
    )
    db_session.add(recipe_ferm)
    await db_session.commit()

    # Verify it works
    await db_session.refresh(recipe_ferm)
    assert recipe_ferm.name == "Custom Malt"
    assert recipe_ferm.fermentable_id is None
```

**Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_recipe_ingredient_linking.py::test_link_recipe_fermentable_to_library -v`
Expected: FAIL with "no such column: recipe_fermentables.fermentable_id"

**Step 3: Modify RecipeFermentable model**

In `backend/models.py`, modify the RecipeFermentable class (around line 359):

```python
class RecipeFermentable(Base):
    """Fermentable ingredients (grains, extracts, sugars) in a recipe."""
    __tablename__ = "recipe_fermentables"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False)

    # Link to ingredient library (optional for legacy support)
    fermentable_id: Mapped[Optional[int]] = mapped_column(ForeignKey("fermentables.id", ondelete="SET NULL"))

    # BeerXML fields (kept for legacy imports without library reference)
    # When fermentable_id is set, these can be null and pulled from library
    name: Mapped[Optional[str]] = mapped_column(String(100))
    type: Mapped[Optional[str]] = mapped_column(String(50))

    # Recipe-specific fields (always required)
    amount_kg: Mapped[float] = mapped_column(nullable=False)  # Amount in kilograms
    percentage: Mapped[Optional[float]] = mapped_column()  # % of grain bill

    # Optional overrides (used when fermentable_id is set but you want to override library values)
    yield_percent: Mapped[Optional[float]] = mapped_column()  # % yield (0-100)
    color_lovibond: Mapped[Optional[float]] = mapped_column()  # SRM/Lovibond
    origin: Mapped[Optional[str]] = mapped_column(String(50))
    supplier: Mapped[Optional[str]] = mapped_column(String(100))
    notes: Mapped[Optional[str]] = mapped_column(Text)

    # Advanced BeerXML fields (optional)
    add_after_boil: Mapped[Optional[bool]] = mapped_column(default=False)
    coarse_fine_diff: Mapped[Optional[float]] = mapped_column()
    moisture: Mapped[Optional[float]] = mapped_column()
    diastatic_power: Mapped[Optional[float]] = mapped_column()
    protein: Mapped[Optional[float]] = mapped_column()
    max_in_batch: Mapped[Optional[float]] = mapped_column()
    recommend_mash: Mapped[Optional[bool]] = mapped_column()

    # Relationships
    recipe: Mapped["Recipe"] = relationship(back_populates="fermentables")
    fermentable: Mapped[Optional["Fermentable"]] = relationship()
```

**Step 4: Create and run migration**

Run: `cd backend && alembic revision --autogenerate -m "Add foreign key from RecipeFermentable to Fermentable"`
Then: `cd backend && alembic upgrade head`

**Step 5: Run tests to verify they pass**

Run: `pytest backend/tests/test_recipe_ingredient_linking.py -v`
Expected: PASS (2 tests)

**Step 6: Commit**

```bash
git add backend/models.py backend/tests/test_recipe_ingredient_linking.py backend/alembic/versions/*_add_foreign_key_from_recip*.py
git commit -m "feat: link RecipeFermentable to Fermentable library with legacy support"
```

---

### Task 6: Add Foreign Keys to RecipeHop, RecipeYeast, RecipeMisc

**Files:**
- Modify: `backend/models.py` (RecipeHop, RecipeYeast, RecipeMisc classes)
- Modify: `backend/tests/test_recipe_ingredient_linking.py`

**Step 1: Write the failing tests**

Add to `backend/tests/test_recipe_ingredient_linking.py`:

```python
from backend.models import RecipeHop, Hop, RecipeYeast, Yeast, RecipeMisc, Misc


@pytest.mark.asyncio
async def test_link_recipe_hop_to_library(db_session):
    """Test that recipe hop can reference library hop."""
    lib_hop = Hop(name="Cascade", alpha_percent=5.5)
    db_session.add(lib_hop)
    await db_session.flush()

    style = Style(name="American Pale Ale")
    db_session.add(style)
    await db_session.flush()

    recipe = Recipe(name="Test Recipe", style_id=style.id)
    db_session.add(recipe)
    await db_session.flush()

    recipe_hop = RecipeHop(
        recipe_id=recipe.id,
        hop_id=lib_hop.id,
        amount_kg=0.025,
        use="Boil",
        time_min=60,
    )
    db_session.add(recipe_hop)
    await db_session.commit()

    await db_session.refresh(recipe_hop)
    assert recipe_hop.hop.name == "Cascade"


@pytest.mark.asyncio
async def test_link_recipe_yeast_to_library(db_session):
    """Test that recipe yeast can reference library yeast."""
    lib_yeast = Yeast(name="US-05", lab="Fermentis", product_id="US-05")
    db_session.add(lib_yeast)
    await db_session.flush()

    style = Style(name="American Pale Ale")
    db_session.add(style)
    await db_session.flush()

    recipe = Recipe(name="Test Recipe", style_id=style.id)
    db_session.add(recipe)
    await db_session.flush()

    recipe_yeast = RecipeYeast(
        recipe_id=recipe.id,
        yeast_id=lib_yeast.id,
        amount_l=0.011,
    )
    db_session.add(recipe_yeast)
    await db_session.commit()

    await db_session.refresh(recipe_yeast)
    assert recipe_yeast.yeast.product_id == "US-05"


@pytest.mark.asyncio
async def test_link_recipe_misc_to_library(db_session):
    """Test that recipe misc can reference library misc."""
    lib_misc = Misc(name="Irish Moss", type="Fining")
    db_session.add(lib_misc)
    await db_session.flush()

    style = Style(name="American Pale Ale")
    db_session.add(style)
    await db_session.flush()

    recipe = Recipe(name="Test Recipe", style_id=style.id)
    db_session.add(recipe)
    await db_session.flush()

    recipe_misc = RecipeMisc(
        recipe_id=recipe.id,
        misc_id=lib_misc.id,
        use="Boil",
        time_min=15,
        amount_kg=0.01,
    )
    db_session.add(recipe_misc)
    await db_session.commit()

    await db_session.refresh(recipe_misc)
    assert recipe_misc.misc.name == "Irish Moss"
```

**Step 2: Run tests to verify they fail**

Run: `pytest backend/tests/test_recipe_ingredient_linking.py::test_link_recipe_hop_to_library -v`
Expected: FAIL

**Step 3: Modify RecipeHop model**

In `backend/models.py`, modify RecipeHop (around line 391):

```python
class RecipeHop(Base):
    """Hop additions in a recipe."""
    __tablename__ = "recipe_hops"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False)

    # Link to ingredient library (optional for legacy support)
    hop_id: Mapped[Optional[int]] = mapped_column(ForeignKey("hops.id", ondelete="SET NULL"))

    # BeerXML fields (kept for legacy, can be null when hop_id is set)
    name: Mapped[Optional[str]] = mapped_column(String(100))
    alpha_percent: Mapped[Optional[float]] = mapped_column()

    # Recipe-specific fields (always required)
    amount_kg: Mapped[float] = mapped_column(nullable=False)
    use: Mapped[str] = mapped_column(String(20), nullable=False)
    time_min: Mapped[Optional[float]] = mapped_column()

    # Hop characteristics (optional overrides)
    form: Mapped[Optional[str]] = mapped_column(String(20))
    type: Mapped[Optional[str]] = mapped_column(String(20))
    origin: Mapped[Optional[str]] = mapped_column(String(50))
    substitutes: Mapped[Optional[str]] = mapped_column(String(200))

    # Advanced BeerXML fields
    beta_percent: Mapped[Optional[float]] = mapped_column()
    hsi: Mapped[Optional[float]] = mapped_column()
    humulene: Mapped[Optional[float]] = mapped_column()
    caryophyllene: Mapped[Optional[float]] = mapped_column()
    cohumulone: Mapped[Optional[float]] = mapped_column()
    myrcene: Mapped[Optional[float]] = mapped_column()
    notes: Mapped[Optional[str]] = mapped_column(Text)

    # Relationships
    recipe: Mapped["Recipe"] = relationship(back_populates="hops")
    hop: Mapped[Optional["Hop"]] = relationship()
```

**Step 4: Modify RecipeYeast model**

In `backend/models.py`, modify RecipeYeast (around line 425):

```python
class RecipeYeast(Base):
    """Yeast strains in a recipe."""
    __tablename__ = "recipe_yeasts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False)

    # Link to ingredient library (optional for legacy support)
    yeast_id: Mapped[Optional[int]] = mapped_column(ForeignKey("yeasts.id", ondelete="SET NULL"))

    # BeerXML fields (kept for legacy, can be null when yeast_id is set)
    name: Mapped[Optional[str]] = mapped_column(String(100))
    lab: Mapped[Optional[str]] = mapped_column(String(100))
    product_id: Mapped[Optional[str]] = mapped_column(String(50))
    type: Mapped[Optional[str]] = mapped_column(String(20))
    form: Mapped[Optional[str]] = mapped_column(String(20))

    # Fermentation characteristics (optional overrides)
    attenuation_percent: Mapped[Optional[float]] = mapped_column()
    temp_min_c: Mapped[Optional[float]] = mapped_column()
    temp_max_c: Mapped[Optional[float]] = mapped_column()
    flocculation: Mapped[Optional[str]] = mapped_column(String(20))

    # Pitching (recipe-specific)
    amount_l: Mapped[Optional[float]] = mapped_column()
    amount_kg: Mapped[Optional[float]] = mapped_column()
    add_to_secondary: Mapped[Optional[bool]] = mapped_column(default=False)

    # Advanced fields
    best_for: Mapped[Optional[str]] = mapped_column(Text)
    times_cultured: Mapped[Optional[int]] = mapped_column()
    max_reuse: Mapped[Optional[int]] = mapped_column()
    notes: Mapped[Optional[str]] = mapped_column(Text)

    # Relationships
    recipe: Mapped["Recipe"] = relationship(back_populates="yeasts")
    yeast: Mapped[Optional["Yeast"]] = relationship()
```

**Step 5: Modify RecipeMisc model**

In `backend/models.py`, modify RecipeMisc (around line 460):

```python
class RecipeMisc(Base):
    """Misc ingredients (spices, finings, water agents, etc)."""
    __tablename__ = "recipe_miscs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False)

    # Link to ingredient library (optional for legacy support)
    misc_id: Mapped[Optional[int]] = mapped_column(ForeignKey("miscs.id", ondelete="SET NULL"))

    # BeerXML fields (kept for legacy, can be null when misc_id is set)
    name: Mapped[Optional[str]] = mapped_column(String(100))
    type: Mapped[Optional[str]] = mapped_column(String(50))

    # Recipe-specific fields (always required)
    use: Mapped[str] = mapped_column(String(20), nullable=False)
    time_min: Mapped[Optional[float]] = mapped_column()
    amount_kg: Mapped[Optional[float]] = mapped_column()
    amount_is_weight: Mapped[Optional[bool]] = mapped_column(default=True)

    # Metadata
    use_for: Mapped[Optional[str]] = mapped_column(Text)
    notes: Mapped[Optional[str]] = mapped_column(Text)

    # Relationships
    recipe: Mapped["Recipe"] = relationship(back_populates="miscs")
    misc: Mapped[Optional["Misc"]] = relationship()
```

**Step 6: Create and run migration**

Run: `cd backend && alembic revision --autogenerate -m "Add foreign keys from recipe ingredients to library"`
Then: `cd backend && alembic upgrade head`

**Step 7: Run tests to verify they pass**

Run: `pytest backend/tests/test_recipe_ingredient_linking.py -v`
Expected: PASS (all tests)

**Step 8: Commit**

```bash
git add backend/models.py backend/tests/test_recipe_ingredient_linking.py backend/alembic/versions/*_add_foreign_keys_from_recipe*.py
git commit -m "feat: link RecipeHop, RecipeYeast, RecipeMisc to library with legacy support"
```

---

## Phase 3: Brewfather API Sync Service

### Task 7: Create Brewfather Client

**Files:**
- Create: `backend/services/brewfather_client.py`
- Create: `backend/tests/test_brewfather_client.py`

**Step 1: Write the failing test**

Create `backend/tests/test_brewfather_client.py`:

```python
"""Tests for Brewfather API client."""
import pytest
from unittest.mock import AsyncMock, patch

from backend.services.brewfather_client import BrewfatherClient


@pytest.fixture
def bf_client():
    """Create Brewfather client with test credentials."""
    return BrewfatherClient(
        user_id="test_user",
        api_key="test_key",
        base_url="https://api.brewfather.app/v2"
    )


@pytest.mark.asyncio
@patch("httpx.AsyncClient.get")
async def test_fetch_recipes(mock_get, bf_client):
    """Test fetching recipes from Brewfather API."""
    # Mock API response
    mock_get.return_value = AsyncMock(
        status_code=200,
        json=lambda: [
            {
                "_id": "recipe1",
                "name": "Test Recipe",
                "fermentables": [],
                "hops": [],
                "yeasts": [],
                "miscs": []
            }
        ]
    )

    recipes = await bf_client.fetch_recipes(limit=5)

    assert len(recipes) == 1
    assert recipes[0]["name"] == "Test Recipe"

    # Verify auth header was set correctly
    mock_get.assert_called_once()
    call_kwargs = mock_get.call_args[1]
    assert "Authorization" in call_kwargs["headers"]


@pytest.mark.asyncio
@patch("httpx.AsyncClient.get")
async def test_fetch_fermentables(mock_get, bf_client):
    """Test fetching fermentables inventory."""
    mock_get.return_value = AsyncMock(
        status_code=200,
        json=lambda: []  # Brewfather inventory endpoints return empty if not tracked
    )

    fermentables = await bf_client.fetch_fermentables()

    assert isinstance(fermentables, list)
```

**Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_brewfather_client.py -v`
Expected: FAIL with "cannot import name 'BrewfatherClient'"

**Step 3: Write BrewfatherClient**

Create `backend/services/brewfather_client.py`:

```python
"""Brewfather API client for syncing ingredient data."""
import base64
import logging
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)


class BrewfatherClient:
    """Client for interacting with Brewfather API v2."""

    def __init__(
        self,
        user_id: str,
        api_key: str,
        base_url: str = "https://api.brewfather.app/v2",
    ):
        """Initialize Brewfather client.

        Args:
            user_id: Brewfather user ID
            api_key: Brewfather API key
            base_url: API base URL (default: production v2)
        """
        self.user_id = user_id
        self.api_key = api_key
        self.base_url = base_url

        # Create auth header
        credentials = f"{user_id}:{api_key}"
        encoded = base64.b64encode(credentials.encode()).decode()
        self.headers = {"Authorization": f"Basic {encoded}"}

    async def _get(self, endpoint: str, params: Optional[dict] = None) -> Any:
        """Make GET request to Brewfather API.

        Args:
            endpoint: API endpoint (e.g., "/recipes")
            params: Query parameters

        Returns:
            JSON response data

        Raises:
            httpx.HTTPError: On request failure
        """
        url = f"{self.base_url}{endpoint}"
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=self.headers, params=params or {})
            response.raise_for_status()
            return response.json()

    async def fetch_recipes(
        self, limit: int = 50, complete: bool = True
    ) -> list[dict]:
        """Fetch recipes from Brewfather.

        Args:
            limit: Maximum recipes to fetch (max 50 per request)
            complete: Include all recipe data (True) or just summary (False)

        Returns:
            List of recipe dictionaries
        """
        params = {"limit": min(limit, 50), "complete": str(complete).lower()}
        return await self._get("/recipes", params)

    async def fetch_all_recipes(self, complete: bool = True) -> list[dict]:
        """Fetch all recipes with pagination.

        Args:
            complete: Include all recipe data

        Returns:
            List of all recipe dictionaries
        """
        all_recipes = []
        start_after = None

        while True:
            params = {"limit": 50, "complete": str(complete).lower()}
            if start_after:
                params["start_after"] = start_after

            recipes = await self._get("/recipes", params)
            if not recipes:
                break

            all_recipes.extend(recipes)

            # Check if there are more pages
            if len(recipes) < 50:
                break

            # Use last recipe's _id for next page
            start_after = recipes[-1]["_id"]
            logger.info(f"Fetched {len(all_recipes)} recipes so far...")

        logger.info(f"Fetched total of {len(all_recipes)} recipes")
        return all_recipes

    async def fetch_fermentables(self, complete: bool = True) -> list[dict]:
        """Fetch fermentables inventory.

        Note: Only returns items you've manually added or tracked inventory for.

        Args:
            complete: Include all data

        Returns:
            List of fermentable dictionaries
        """
        params = {"limit": 50, "complete": str(complete).lower()}
        return await self._get("/inventory/fermentables", params)

    async def fetch_hops(self, complete: bool = True) -> list[dict]:
        """Fetch hops inventory."""
        params = {"limit": 50, "complete": str(complete).lower()}
        return await self._get("/inventory/hops", params)

    async def fetch_yeasts(self, complete: bool = True) -> list[dict]:
        """Fetch yeasts inventory."""
        params = {"limit": 50, "complete": str(complete).lower()}
        return await self._get("/inventory/yeasts", params)

    async def fetch_miscs(self, complete: bool = True) -> list[dict]:
        """Fetch misc ingredients inventory."""
        params = {"limit": 50, "complete": str(complete).lower()}
        return await self._get("/inventory/miscs", params)
```

**Step 4: Run test to verify it passes**

Run: `pytest backend/tests/test_brewfather_client.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/services/brewfather_client.py backend/tests/test_brewfather_client.py
git commit -m "feat: add Brewfather API client for ingredient sync"
```

---

### Task 8: Create Ingredient Extractor Service

**Files:**
- Create: `backend/services/ingredient_extractor.py`
- Create: `backend/tests/test_ingredient_extractor.py`

**Step 1: Write the failing test**

Create `backend/tests/test_ingredient_extractor.py`:

```python
"""Tests for ingredient extraction from Brewfather recipes."""
import pytest

from backend.services.ingredient_extractor import IngredientExtractor


def test_extract_unique_fermentables():
    """Test extracting unique fermentables from recipes."""
    recipes = [
        {
            "name": "Recipe 1",
            "fermentables": [
                {
                    "_id": "default-592f3ac",
                    "name": "Pale Ale",
                    "supplier": "BestMalz",
                    "origin": "Germany",
                    "type": "Grain",
                    "potentialPercentage": 82.8,
                    "color": 3.0,
                    "grainCategory": "Base",
                },
            ],
        },
        {
            "name": "Recipe 2",
            "fermentables": [
                {
                    "_id": "default-592f3ac",  # Same ID - should dedupe
                    "name": "Pale Ale",
                    "supplier": "BestMalz",
                    "type": "Grain",
                },
                {
                    "_id": "default-f2ae88f",
                    "name": "Caramunich III",
                    "supplier": "Weyermann",
                    "type": "Grain",
                },
            ],
        },
    ]

    extractor = IngredientExtractor()
    fermentables = extractor.extract_unique_fermentables(recipes)

    # Should have 2 unique fermentables (by _id)
    assert len(fermentables) == 2

    # Check first fermentable has all fields
    pale_ale = next(f for f in fermentables if f["brewfather_id"] == "default-592f3ac")
    assert pale_ale["name"] == "Pale Ale"
    assert pale_ale["supplier"] == "BestMalz"
    assert pale_ale["grain_category"] == "Base"


def test_extract_unique_hops():
    """Test extracting unique hops from recipes."""
    recipes = [
        {
            "hops": [
                {
                    "_id": "default-58d2b845",
                    "name": "Cascade",
                    "origin": "US",
                    "alpha": 5.5,
                    "type": "Pellet",
                    "usage": "Both",
                }
            ]
        }
    ]

    extractor = IngredientExtractor()
    hops = extractor.extract_unique_hops(recipes)

    assert len(hops) == 1
    assert hops[0]["name"] == "Cascade"
    assert hops[0]["alpha_percent"] == 5.5
```

**Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_ingredient_extractor.py -v`
Expected: FAIL

**Step 3: Write IngredientExtractor**

Create `backend/services/ingredient_extractor.py`:

```python
"""Extract unique ingredients from Brewfather recipes."""
import logging
from typing import Any

logger = logging.getLogger(__name__)


class IngredientExtractor:
    """Extract and deduplicate ingredients from Brewfather recipe data."""

    def extract_unique_fermentables(self, recipes: list[dict]) -> list[dict]:
        """Extract unique fermentables from recipes.

        Args:
            recipes: List of Brewfather recipe dictionaries

        Returns:
            List of unique fermentable dictionaries, keyed by brewfather_id
        """
        unique = {}

        for recipe in recipes:
            for ferm in recipe.get("fermentables", []):
                bf_id = ferm.get("_id")
                if not bf_id or bf_id in unique:
                    continue

                # Map Brewfather JSON to our schema
                unique[bf_id] = {
                    "brewfather_id": bf_id,
                    "name": ferm.get("name"),
                    "supplier": ferm.get("supplier"),
                    "origin": ferm.get("origin"),
                    "type": ferm.get("type"),
                    "yield_percent": ferm.get("potentialPercentage"),
                    "color_lovibond": ferm.get("color"),
                    "grain_category": ferm.get("grainCategory"),
                    "potential_percentage": ferm.get("potentialPercentage"),
                    "notes": ferm.get("notes"),
                    # Advanced fields
                    "coarse_fine_diff": ferm.get("coarseFineDiff"),
                    "moisture": ferm.get("moisture"),
                    "diastatic_power": ferm.get("diastaticPower"),
                    "protein": ferm.get("protein"),
                    "max_in_batch": ferm.get("maxInBatch"),
                    "recommend_mash": ferm.get("recommendMash"),
                }

        logger.info(f"Extracted {len(unique)} unique fermentables")
        return list(unique.values())

    def extract_unique_hops(self, recipes: list[dict]) -> list[dict]:
        """Extract unique hops from recipes."""
        unique = {}

        for recipe in recipes:
            for hop in recipe.get("hops", []):
                bf_id = hop.get("_id")
                if not bf_id or bf_id in unique:
                    continue

                unique[bf_id] = {
                    "brewfather_id": bf_id,
                    "name": hop.get("name"),
                    "origin": hop.get("origin"),
                    "alpha_percent": hop.get("alpha"),
                    "beta_percent": hop.get("beta"),
                    "type": hop.get("usage"),  # Brewfather uses "usage" field
                    "form": hop.get("type"),   # Brewfather "type" is our "form"
                    "substitutes": hop.get("substitutes"),
                    "hsi": hop.get("hsi"),
                    "humulene": hop.get("humulene"),
                    "caryophyllene": hop.get("caryophyllene"),
                    "cohumulone": hop.get("cohumulone"),
                    "myrcene": hop.get("myrcene"),
                    "notes": hop.get("notes"),
                }

        logger.info(f"Extracted {len(unique)} unique hops")
        return list(unique.values())

    def extract_unique_yeasts(self, recipes: list[dict]) -> list[dict]:
        """Extract unique yeasts from recipes."""
        unique = {}

        for recipe in recipes:
            for yeast in recipe.get("yeasts", []):
                bf_id = yeast.get("_id")
                if not bf_id or bf_id in unique:
                    continue

                unique[bf_id] = {
                    "brewfather_id": bf_id,
                    "name": yeast.get("name"),
                    "lab": yeast.get("laboratory"),
                    "product_id": yeast.get("productId"),
                    "type": yeast.get("type"),
                    "form": yeast.get("form"),
                    "attenuation_percent": yeast.get("attenuation"),
                    "temp_min_c": yeast.get("minTemp"),
                    "temp_max_c": yeast.get("maxTemp"),
                    "flocculation": yeast.get("flocculation"),
                    "alcohol_tolerance": yeast.get("maxAbv"),
                    "best_for": yeast.get("bestFor"),
                    "notes": yeast.get("description"),
                }

        logger.info(f"Extracted {len(unique)} unique yeasts")
        return list(unique.values())

    def extract_unique_miscs(self, recipes: list[dict]) -> list[dict]:
        """Extract unique misc ingredients from recipes."""
        unique = {}

        for recipe in recipes:
            for misc in recipe.get("miscs", []):
                bf_id = misc.get("_id")
                if not bf_id or bf_id in unique:
                    continue

                unique[bf_id] = {
                    "brewfather_id": bf_id,
                    "name": misc.get("name"),
                    "type": misc.get("type"),
                    "use_for": misc.get("use"),
                    "notes": misc.get("notes"),
                }

        logger.info(f"Extracted {len(unique)} unique miscs")
        return list(unique.values())
```

**Step 4: Run test to verify it passes**

Run: `pytest backend/tests/test_ingredient_extractor.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/services/ingredient_extractor.py backend/tests/test_ingredient_extractor.py
git commit -m "feat: add ingredient extractor for deduplicating Brewfather data"
```

---

### Task 9: Create Ingredient Sync Service

**Files:**
- Create: `backend/services/ingredient_sync.py`
- Create: `backend/tests/test_ingredient_sync.py`

**Step 1: Write the failing test**

Create `backend/tests/test_ingredient_sync.py`:

```python
"""Tests for ingredient sync service."""
import pytest
from unittest.mock import AsyncMock, patch

from backend.models import Fermentable, Hop, Yeast, Misc
from backend.services.ingredient_sync import IngredientSyncService


@pytest.mark.asyncio
@patch("backend.services.ingredient_sync.BrewfatherClient")
async def test_sync_ingredients_from_recipes(mock_client_class, db_session):
    """Test syncing ingredients from Brewfather recipes."""
    # Mock Brewfather client
    mock_client = AsyncMock()
    mock_client.fetch_all_recipes.return_value = [
        {
            "fermentables": [
                {
                    "_id": "bf-ferm-1",
                    "name": "Pale Malt",
                    "type": "Grain",
                    "supplier": "Crisp",
                }
            ],
            "hops": [
                {
                    "_id": "bf-hop-1",
                    "name": "Cascade",
                    "alpha": 5.5,
                }
            ],
            "yeasts": [],
            "miscs": [],
        }
    ]
    mock_client_class.return_value = mock_client

    # Run sync
    sync_service = IngredientSyncService(
        user_id="test_user",
        api_key="test_key",
        db_session=db_session,
    )
    stats = await sync_service.sync_from_recipes()

    # Verify ingredients were created
    assert stats["fermentables_created"] == 1
    assert stats["hops_created"] == 1

    # Verify in database
    fermentable = (await db_session.execute(
        select(Fermentable).where(Fermentable.brewfather_id == "bf-ferm-1")
    )).scalar_one()
    assert fermentable.name == "Pale Malt"

    hop = (await db_session.execute(
        select(Hop).where(Hop.brewfather_id == "bf-hop-1")
    )).scalar_one()
    assert hop.name == "Cascade"


@pytest.mark.asyncio
async def test_sync_skips_duplicates(db_session):
    """Test that sync doesn't create duplicates."""
    # Create existing fermentable
    existing = Fermentable(
        brewfather_id="bf-ferm-1",
        name="Existing",
        type="Grain",
    )
    db_session.add(existing)
    await db_session.commit()

    # Mock client returning same brewfather_id
    with patch("backend.services.ingredient_sync.BrewfatherClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.fetch_all_recipes.return_value = [
            {
                "fermentables": [
                    {
                        "_id": "bf-ferm-1",
                        "name": "Updated Name",
                        "type": "Grain",
                    }
                ],
                "hops": [],
                "yeasts": [],
                "miscs": [],
            }
        ]
        mock_client_class.return_value = mock_client

        sync_service = IngredientSyncService(
            user_id="test_user",
            api_key="test_key",
            db_session=db_session,
        )
        stats = await sync_service.sync_from_recipes()

        # Should skip, not create
        assert stats["fermentables_created"] == 0
        assert stats["fermentables_skipped"] == 1
```

**Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_ingredient_sync.py -v`
Expected: FAIL

**Step 3: Write IngredientSyncService**

Create `backend/services/ingredient_sync.py`:

```python
"""Service for syncing ingredients from Brewfather to local database."""
import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Fermentable, Hop, Yeast, Misc
from backend.services.brewfather_client import BrewfatherClient
from backend.services.ingredient_extractor import IngredientExtractor

logger = logging.getLogger(__name__)


class IngredientSyncService:
    """Sync ingredient library from Brewfather recipes."""

    def __init__(
        self,
        user_id: str,
        api_key: str,
        db_session: AsyncSession,
        base_url: str = "https://api.brewfather.app/v2",
    ):
        """Initialize sync service.

        Args:
            user_id: Brewfather user ID
            api_key: Brewfather API key
            db_session: Database session
            base_url: API base URL
        """
        self.client = BrewfatherClient(user_id, api_key, base_url)
        self.extractor = IngredientExtractor()
        self.db = db_session

    async def sync_from_recipes(self) -> dict:
        """Sync ingredients by extracting from all Brewfather recipes.

        Returns:
            Statistics dictionary with counts of created/skipped items
        """
        logger.info("Fetching all recipes from Brewfather...")
        recipes = await self.client.fetch_all_recipes(complete=True)

        logger.info("Extracting unique ingredients...")
        fermentables = self.extractor.extract_unique_fermentables(recipes)
        hops = self.extractor.extract_unique_hops(recipes)
        yeasts = self.extractor.extract_unique_yeasts(recipes)
        miscs = self.extractor.extract_unique_miscs(recipes)

        stats = {
            "fermentables_created": 0,
            "fermentables_skipped": 0,
            "hops_created": 0,
            "hops_skipped": 0,
            "yeasts_created": 0,
            "yeasts_skipped": 0,
            "miscs_created": 0,
            "miscs_skipped": 0,
        }

        # Sync fermentables
        for ferm_data in fermentables:
            if await self._fermentable_exists(ferm_data["brewfather_id"]):
                stats["fermentables_skipped"] += 1
                continue

            fermentable = Fermentable(**ferm_data)
            self.db.add(fermentable)
            stats["fermentables_created"] += 1

        # Sync hops
        for hop_data in hops:
            if await self._hop_exists(hop_data["brewfather_id"]):
                stats["hops_skipped"] += 1
                continue

            hop = Hop(**hop_data)
            self.db.add(hop)
            stats["hops_created"] += 1

        # Sync yeasts
        for yeast_data in yeasts:
            if await self._yeast_exists(yeast_data["brewfather_id"]):
                stats["yeasts_skipped"] += 1
                continue

            yeast = Yeast(**yeast_data)
            self.db.add(yeast)
            stats["yeasts_created"] += 1

        # Sync miscs
        for misc_data in miscs:
            if await self._misc_exists(misc_data["brewfather_id"]):
                stats["miscs_skipped"] += 1
                continue

            misc = Misc(**misc_data)
            self.db.add(misc)
            stats["miscs_created"] += 1

        await self.db.commit()
        logger.info(f"Sync complete: {stats}")
        return stats

    async def _fermentable_exists(self, brewfather_id: Optional[str]) -> bool:
        """Check if fermentable with brewfather_id exists."""
        if not brewfather_id:
            return False
        result = await self.db.execute(
            select(Fermentable).where(Fermentable.brewfather_id == brewfather_id)
        )
        return result.scalar_one_or_none() is not None

    async def _hop_exists(self, brewfather_id: Optional[str]) -> bool:
        """Check if hop with brewfather_id exists."""
        if not brewfather_id:
            return False
        result = await self.db.execute(
            select(Hop).where(Hop.brewfather_id == brewfather_id)
        )
        return result.scalar_one_or_none() is not None

    async def _yeast_exists(self, brewfather_id: Optional[str]) -> bool:
        """Check if yeast with brewfather_id exists."""
        if not brewfather_id:
            return False
        result = await self.db.execute(
            select(Yeast).where(Yeast.brewfather_id == brewfather_id)
        )
        return result.scalar_one_or_none() is not None

    async def _misc_exists(self, brewfather_id: Optional[str]) -> bool:
        """Check if misc with brewfather_id exists."""
        if not brewfather_id:
            return False
        result = await self.db.execute(
            select(Misc).where(Misc.brewfather_id == brewfather_id)
        )
        return result.scalar_one_or_none() is not None
```

**Step 4: Run test to verify it passes**

Run: `pytest backend/tests/test_ingredient_sync.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/services/ingredient_sync.py backend/tests/test_ingredient_sync.py
git commit -m "feat: add ingredient sync service for Brewfather integration"
```

---

## Phase 4: REST API Endpoints

### Task 10: Create Ingredient Library API Router

**Files:**
- Create: `backend/routers/ingredients.py`
- Create: `backend/tests/test_ingredients_api.py`
- Modify: `backend/main.py` (register router)

**Step 1: Write the failing test**

Create `backend/tests/test_ingredients_api.py`:

```python
"""Tests for ingredient library API endpoints."""
import pytest
from httpx import AsyncClient

from backend.models import Fermentable, Hop


@pytest.mark.asyncio
async def test_list_fermentables(client: AsyncClient, db_session):
    """Test listing fermentables."""
    # Create test data
    ferm1 = Fermentable(name="Pale Malt", type="Grain", yield_percent=82.0)
    ferm2 = Fermentable(name="Vienna Malt", type="Grain", yield_percent=78.0)
    db_session.add_all([ferm1, ferm2])
    await db_session.commit()

    # Request
    response = await client.get("/api/ingredients/fermentables")
    assert response.status_code == 200

    data = response.json()
    assert len(data) == 2
    assert data[0]["name"] in ["Pale Malt", "Vienna Malt"]


@pytest.mark.asyncio
async def test_get_fermentable(client: AsyncClient, db_session):
    """Test getting a specific fermentable."""
    ferm = Fermentable(
        name="Pale Malt",
        type="Grain",
        supplier="Crisp",
        yield_percent=82.0,
    )
    db_session.add(ferm)
    await db_session.commit()

    response = await client.get(f"/api/ingredients/fermentables/{ferm.id}")
    assert response.status_code == 200

    data = response.json()
    assert data["name"] == "Pale Malt"
    assert data["supplier"] == "Crisp"


@pytest.mark.asyncio
async def test_create_fermentable(client: AsyncClient):
    """Test creating a fermentable."""
    payload = {
        "name": "Crystal 40",
        "type": "Grain",
        "supplier": "Great Western",
        "yield_percent": 75.0,
        "color_lovibond": 40.0,
    }

    response = await client.post("/api/ingredients/fermentables", json=payload)
    assert response.status_code == 201

    data = response.json()
    assert data["name"] == "Crystal 40"
    assert data["id"] is not None


@pytest.mark.asyncio
async def test_search_fermentables(client: AsyncClient, db_session):
    """Test searching fermentables by name."""
    ferm1 = Fermentable(name="Pale Ale Malt", type="Grain")
    ferm2 = Fermentable(name="Pale Wheat Malt", type="Grain")
    ferm3 = Fermentable(name="Munich Malt", type="Grain")
    db_session.add_all([ferm1, ferm2, ferm3])
    await db_session.commit()

    response = await client.get("/api/ingredients/fermentables?search=pale")
    assert response.status_code == 200

    data = response.json()
    assert len(data) == 2  # Only "Pale" matches
    names = [f["name"] for f in data]
    assert "Munich Malt" not in names
```

**Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_ingredients_api.py::test_list_fermentables -v`
Expected: FAIL with 404 (route not found)

**Step 3: Create ingredients router**

Create `backend/routers/ingredients.py`:

```python
"""Ingredient library API endpoints."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import (
    Fermentable,
    Hop,
    Yeast,
    Misc,
)

router = APIRouter(prefix="/api/ingredients", tags=["ingredients"])


# Fermentables

@router.get("/fermentables")
async def list_fermentables(
    search: Optional[str] = Query(None),
    type: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List fermentables with optional filtering."""
    query = select(Fermentable)

    if search:
        query = query.where(
            or_(
                Fermentable.name.ilike(f"%{search}%"),
                Fermentable.supplier.ilike(f"%{search}%"),
            )
        )

    if type:
        query = query.where(Fermentable.type == type)

    query = query.order_by(Fermentable.name).offset(offset).limit(limit)

    result = await db.execute(query)
    return result.scalars().all()


@router.get("/fermentables/{fermentable_id}")
async def get_fermentable(
    fermentable_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get a specific fermentable by ID."""
    fermentable = await db.get(Fermentable, fermentable_id)
    if not fermentable:
        raise HTTPException(status_code=404, detail="Fermentable not found")
    return fermentable


@router.post("/fermentables", status_code=201)
async def create_fermentable(
    fermentable: dict,
    db: AsyncSession = Depends(get_db),
):
    """Create a new fermentable."""
    db_fermentable = Fermentable(**fermentable)
    db.add(db_fermentable)
    await db.commit()
    await db.refresh(db_fermentable)
    return db_fermentable


@router.put("/fermentables/{fermentable_id}")
async def update_fermentable(
    fermentable_id: int,
    updates: dict,
    db: AsyncSession = Depends(get_db),
):
    """Update a fermentable."""
    fermentable = await db.get(Fermentable, fermentable_id)
    if not fermentable:
        raise HTTPException(status_code=404, detail="Fermentable not found")

    for key, value in updates.items():
        if hasattr(fermentable, key):
            setattr(fermentable, key, value)

    await db.commit()
    await db.refresh(fermentable)
    return fermentable


@router.delete("/fermentables/{fermentable_id}")
async def delete_fermentable(
    fermentable_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Delete a fermentable."""
    fermentable = await db.get(Fermentable, fermentable_id)
    if not fermentable:
        raise HTTPException(status_code=404, detail="Fermentable not found")

    await db.delete(fermentable)
    await db.commit()
    return {"status": "deleted"}


# Hops (similar pattern)

@router.get("/hops")
async def list_hops(
    search: Optional[str] = Query(None),
    origin: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List hops with optional filtering."""
    query = select(Hop)

    if search:
        query = query.where(Hop.name.ilike(f"%{search}%"))

    if origin:
        query = query.where(Hop.origin == origin)

    query = query.order_by(Hop.name).offset(offset).limit(limit)

    result = await db.execute(query)
    return result.scalars().all()


@router.get("/hops/{hop_id}")
async def get_hop(hop_id: int, db: AsyncSession = Depends(get_db)):
    """Get a specific hop by ID."""
    hop = await db.get(Hop, hop_id)
    if not hop:
        raise HTTPException(status_code=404, detail="Hop not found")
    return hop


@router.post("/hops", status_code=201)
async def create_hop(hop: dict, db: AsyncSession = Depends(get_db)):
    """Create a new hop."""
    db_hop = Hop(**hop)
    db.add(db_hop)
    await db.commit()
    await db.refresh(db_hop)
    return db_hop


# Yeasts

@router.get("/yeasts")
async def list_yeasts(
    search: Optional[str] = Query(None),
    lab: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List yeasts with optional filtering."""
    query = select(Yeast)

    if search:
        query = query.where(
            or_(
                Yeast.name.ilike(f"%{search}%"),
                Yeast.product_id.ilike(f"%{search}%"),
            )
        )

    if lab:
        query = query.where(Yeast.lab == lab)

    query = query.order_by(Yeast.name).offset(offset).limit(limit)

    result = await db.execute(query)
    return result.scalars().all()


@router.get("/yeasts/{yeast_id}")
async def get_yeast(yeast_id: int, db: AsyncSession = Depends(get_db)):
    """Get a specific yeast by ID."""
    yeast = await db.get(Yeast, yeast_id)
    if not yeast:
        raise HTTPException(status_code=404, detail="Yeast not found")
    return yeast


@router.post("/yeasts", status_code=201)
async def create_yeast(yeast: dict, db: AsyncSession = Depends(get_db)):
    """Create a new yeast."""
    db_yeast = Yeast(**yeast)
    db.add(db_yeast)
    await db.commit()
    await db.refresh(db_yeast)
    return db_yeast


# Miscs

@router.get("/miscs")
async def list_miscs(
    search: Optional[str] = Query(None),
    type: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List misc ingredients with optional filtering."""
    query = select(Misc)

    if search:
        query = query.where(Misc.name.ilike(f"%{search}%"))

    if type:
        query = query.where(Misc.type == type)

    query = query.order_by(Misc.name).offset(offset).limit(limit)

    result = await db.execute(query)
    return result.scalars().all()


@router.get("/miscs/{misc_id}")
async def get_misc(misc_id: int, db: AsyncSession = Depends(get_db)):
    """Get a specific misc by ID."""
    misc = await db.get(Misc, misc_id)
    if not misc:
        raise HTTPException(status_code=404, detail="Misc ingredient not found")
    return misc


@router.post("/miscs", status_code=201)
async def create_misc(misc: dict, db: AsyncSession = Depends(get_db)):
    """Create a new misc ingredient."""
    db_misc = Misc(**misc)
    db.add(db_misc)
    await db.commit()
    await db.refresh(db_misc)
    return db_misc
```

**Step 4: Register router in main.py**

In `backend/main.py`, add after line 19:

```python
from .routers import alerts, ambient, batches, config, control, devices, ha, ingest, ingredients, recipes, system, tilts
```

And after the lifespan context manager, add:

```python
app.include_router(ingredients.router)
```

**Step 5: Run test to verify it passes**

Run: `pytest backend/tests/test_ingredients_api.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add backend/routers/ingredients.py backend/tests/test_ingredients_api.py backend/main.py
git commit -m "feat: add ingredient library REST API endpoints"
```

---

## Phase 5: Sync Command & Integration

### Task 11: Create CLI Command for Brewfather Sync

**Files:**
- Create: `backend/cli/sync_brewfather.py`
- Create: `backend/tests/test_sync_command.py`

**Step 1: Write the failing test**

Create `backend/tests/test_sync_command.py`:

```python
"""Tests for Brewfather sync CLI command."""
import pytest
from unittest.mock import AsyncMock, patch

from backend.cli.sync_brewfather import sync_ingredients


@pytest.mark.asyncio
@patch("backend.cli.sync_brewfather.IngredientSyncService")
@patch("backend.cli.sync_brewfather.async_session_factory")
async def test_sync_command(mock_session_factory, mock_sync_service_class):
    """Test sync command executes successfully."""
    # Mock database session
    mock_session = AsyncMock()
    mock_session_factory.return_value.__aenter__.return_value = mock_session

    # Mock sync service
    mock_sync_service = AsyncMock()
    mock_sync_service.sync_from_recipes.return_value = {
        "fermentables_created": 10,
        "hops_created": 5,
        "yeasts_created": 3,
        "miscs_created": 2,
    }
    mock_sync_service_class.return_value = mock_sync_service

    # Run command
    await sync_ingredients(user_id="test_user", api_key="test_key")

    # Verify sync was called
    mock_sync_service.sync_from_recipes.assert_called_once()
```

**Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_sync_command.py -v`
Expected: FAIL

**Step 3: Create sync command**

Create `backend/cli/sync_brewfather.py`:

```python
#!/usr/bin/env python3
"""CLI command to sync ingredients from Brewfather."""
import asyncio
import logging
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.database import async_session_factory
from backend.services.ingredient_sync import IngredientSyncService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def sync_ingredients(user_id: str, api_key: str):
    """Sync ingredients from Brewfather.

    Args:
        user_id: Brewfather user ID
        api_key: Brewfather API key
    """
    logger.info("Starting Brewfather ingredient sync...")

    async with async_session_factory() as session:
        sync_service = IngredientSyncService(
            user_id=user_id,
            api_key=api_key,
            db_session=session,
        )

        stats = await sync_service.sync_from_recipes()

        logger.info("Sync complete!")
        logger.info(f"Fermentables: {stats['fermentables_created']} created, {stats['fermentables_skipped']} skipped")
        logger.info(f"Hops: {stats['hops_created']} created, {stats['hops_skipped']} skipped")
        logger.info(f"Yeasts: {stats['yeasts_created']} created, {stats['yeasts_skipped']} skipped")
        logger.info(f"Miscs: {stats['miscs_created']} created, {stats['miscs_skipped']} skipped")


def main():
    """CLI entry point."""
    # Read credentials from environment
    user_id = os.getenv("BREWFATHER_USER_ID")
    api_key = os.getenv("BREWFATHER_API_KEY")

    if not user_id or not api_key:
        logger.error("Missing BREWFATHER_USER_ID or BREWFATHER_API_KEY environment variables")
        logger.error("Set them in .env file or export them before running")
        sys.exit(1)

    asyncio.run(sync_ingredients(user_id, api_key))


if __name__ == "__main__":
    main()
```

**Step 4: Run test to verify it passes**

Run: `pytest backend/tests/test_sync_command.py -v`
Expected: PASS

**Step 5: Make script executable and test manually**

Run: `chmod +x backend/cli/sync_brewfather.py`
Then: `python3 backend/cli/sync_brewfather.py`
Expected: Syncs ingredients from Brewfather using .env credentials

**Step 6: Commit**

```bash
git add backend/cli/sync_brewfather.py backend/tests/test_sync_command.py
git commit -m "feat: add CLI command for syncing Brewfather ingredients"
```

---

## Phase 6: Documentation & Wrap-up

### Task 12: Add README Documentation

**Files:**
- Create: `docs/ingredients-database.md`
- Modify: `README.md` (add link to new docs)

**Step 1: Create documentation**

Create `docs/ingredients-database.md`:

```markdown
# Ingredients Database & Recipe Builder

This feature enables creating, editing, and managing brewing recipes using a comprehensive ingredient library.

## Features

- **Ingredient Library**: Master database of fermentables, hops, yeasts, and misc ingredients
- **Brewfather Integration**: Sync ingredients from your Brewfather account
- **Recipe Editing**: Modify imported BeerXML recipes
- **Recipe Builder**: Create recipes from scratch using library ingredients
- **Search & Filter**: Find ingredients by name, type, supplier, origin

## Architecture

### Database Schema

The system uses two sets of tables:

1. **Ingredient Library** (master data):
   - `fermentables` - grains, extracts, sugars
   - `hops` - hop varieties
   - `yeasts` - yeast strains
   - `miscs` - water agents, finings, spices

2. **Recipe Ingredients** (recipe-specific):
   - `recipe_fermentables` - links recipes to fermentables with amounts
   - `recipe_hops` - links recipes to hops with additions
   - `recipe_yeasts` - links recipes to yeasts with pitching info
   - `recipe_miscs` - links recipes to misc with usage

Each recipe ingredient table has:
- Foreign key to library table (optional for legacy BeerXML imports)
- Recipe-specific fields (amounts, timing, usage)
- Optional overrides for library values

### Brewfather Integration

The system syncs ingredients from Brewfather by:

1. Fetching all recipes from Brewfather API
2. Extracting unique ingredients (deduplicated by `brewfather_id`)
3. Populating library tables
4. Preserving `brewfather_id` for future syncs

## Usage

### Sync Ingredients from Brewfather

```bash
# Set credentials in .env
BREWFATHER_USER_ID=your_user_id
BREWFATHER_API_KEY=your_api_key

# Run sync
python3 backend/cli/sync_brewfather.py
```

### API Endpoints

**List Fermentables:**
```http
GET /api/ingredients/fermentables?search=pale&type=Grain&limit=50
```

**Get Fermentable:**
```http
GET /api/ingredients/fermentables/{id}
```

**Create Fermentable:**
```http
POST /api/ingredients/fermentables
Content-Type: application/json

{
  "name": "Pale Ale Malt",
  "type": "Grain",
  "supplier": "Crisp",
  "yield_percent": 82.0,
  "color_lovibond": 3.0
}
```

Similar endpoints exist for `/hops`, `/yeasts`, and `/miscs`.

### Creating Recipes with Library Ingredients

When creating a recipe, reference library ingredients:

```http
POST /api/recipes
Content-Type: application/json

{
  "name": "My Pale Ale",
  "style_id": 1,
  "fermentables": [
    {
      "fermentable_id": 5,  // Reference library item
      "amount_kg": 5.0,
      "percentage": 85.0
    }
  ],
  "hops": [
    {
      "hop_id": 12,  // Reference library item
      "amount_kg": 0.025,
      "use": "Boil",
      "time_min": 60
    }
  ]
}
```

## Migration from BeerXML

Legacy BeerXML imports work unchanged - they populate recipe ingredients without library references. To link them to library:

1. Run Brewfather sync to populate library
2. Update recipe ingredients to reference library items by matching on name/supplier

## Future Enhancements

- Inventory tracking integration
- Custom ingredient creation via UI
- Recipe scaling calculator
- Substitution suggestions
- Batch ingredient consumption tracking
```

**Step 2: Update main README**

Add to `README.md` after the Features section:

```markdown
### Recipe Management

- **BeerXML Import**: Import recipes from BeerXML files
- **Ingredients Library**: Master database of brewing ingredients synced from Brewfather
- **Recipe Builder**: Create and edit recipes using library ingredients
- See [Ingredients Database Documentation](docs/ingredients-database.md) for details
```

**Step 3: Commit**

```bash
git add docs/ingredients-database.md README.md
git commit -m "docs: add ingredients database documentation"
```

---

## Testing & Verification

### Task 13: Run Full Test Suite

**Step 1: Run all tests**

Run: `pytest backend/tests/ -v --cov=backend --cov-report=term-missing`
Expected: All tests PASS with >80% coverage

**Step 2: Fix any failing tests**

If tests fail, debug and fix them before proceeding.

**Step 3: Commit**

```bash
git add .
git commit -m "test: verify full test suite passes"
```

---

### Task 14: Manual End-to-End Test

**Step 1: Reset database**

Run: `cd backend && alembic downgrade base && alembic upgrade head`

**Step 2: Sync ingredients from Brewfather**

Run: `python3 backend/cli/sync_brewfather.py`
Expected: Ingredients synced successfully

**Step 3: Verify via API**

Run: `curl http://localhost:8000/api/ingredients/fermentables | jq`
Expected: Returns list of fermentables from Brewfather

**Step 4: Create a recipe using library ingredients**

Use API or UI to create a recipe referencing library ingredients.

**Step 5: Verify recipe shows ingredient details**

Fetch recipe and verify ingredient data pulls from library.

**Step 6: Document any issues**

Create GitHub issues for any bugs found.

---

## Completion

Plan complete! This implementation:

✅ Creates ingredient library tables with Brewfather integration
✅ Links recipe ingredients to library while preserving legacy support
✅ Provides Brewfather API client and sync service
✅ Exposes REST API endpoints for CRUD operations
✅ Includes CLI command for syncing
✅ Maintains backward compatibility with BeerXML imports
✅ Follows TDD with comprehensive test coverage
✅ Includes documentation

---

**Total estimated tasks:** 14 main tasks, ~60-80 individual steps
**Estimated implementation time:** 6-8 hours for experienced developer
**Technologies:** FastAPI, SQLAlchemy 2.0, Alembic, Pydantic, httpx, pytest
