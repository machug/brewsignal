import json
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, field_validator, field_serializer
from sqlalchemy import ForeignKey, Index, JSON, String, Text, UniqueConstraint, false
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def serialize_datetime_to_utc(dt: Optional[datetime]) -> Optional[str]:
    """Serialize datetime to ISO format with 'Z' suffix to indicate UTC.

    This ensures JavaScript Date() correctly interprets timestamps as UTC rather
    than local time, preventing timezone display bugs.

    Handles three cases defensively:
    - None: Returns None (for optional fields)
    - Naive datetime: Assumes UTC (database stores all times in UTC)
    - Timezone-aware non-UTC: Converts to UTC (defensive, should not occur in practice)
    """
    if dt is None:
        return None
    # Ensure datetime is in UTC
    if dt.tzinfo is None:
        # Naive datetime - assume UTC since database stores everything in UTC
        dt = dt.replace(tzinfo=timezone.utc)
    elif dt.tzinfo != timezone.utc:
        # Non-UTC timezone - convert to UTC (defensive, should not happen)
        dt = dt.astimezone(timezone.utc)
    # Format as ISO with 'Z' suffix per RFC 3339
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


# SQLAlchemy Models
class Device(Base):
    """Universal hydrometer device registry."""
    __tablename__ = "devices"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    device_type: Mapped[str] = mapped_column(String(20), nullable=False, default="tilt")
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    display_name: Mapped[Optional[str]] = mapped_column(String(100))

    # Current assignment
    beer_name: Mapped[Optional[str]] = mapped_column(String(100))
    original_gravity: Mapped[Optional[float]] = mapped_column()

    # Stored units (all temperatures stored in Celsius, all gravity in SG)
    # NOTE: Tilt devices broadcast in Fahrenheit but are converted to Celsius on ingestion
    native_gravity_unit: Mapped[str] = mapped_column(String(10), default="sg")
    native_temp_unit: Mapped[str] = mapped_column(String(5), default="c")

    # Calibration - stored as JSON string, use properties for access
    calibration_type: Mapped[str] = mapped_column(String(20), default="none")
    _calibration_data: Mapped[Optional[str]] = mapped_column("calibration_data", Text)

    @property
    def calibration_data(self) -> Optional[dict[str, Any]]:
        """Get calibration data as dict."""
        if self._calibration_data:
            return json.loads(self._calibration_data)
        return None

    @calibration_data.setter
    def calibration_data(self, value: Optional[dict[str, Any]]) -> None:
        """Set calibration data from dict."""
        if value is not None:
            self._calibration_data = json.dumps(value)
        else:
            self._calibration_data = None

    # Security
    auth_token: Mapped[Optional[str]] = mapped_column(String(100))

    # Status
    last_seen: Mapped[Optional[datetime]] = mapped_column()
    battery_voltage: Mapped[Optional[float]] = mapped_column()
    firmware_version: Mapped[Optional[str]] = mapped_column(String(50))

    # Legacy compatibility (Tilt-specific)
    color: Mapped[Optional[str]] = mapped_column(String(20))
    mac: Mapped[Optional[str]] = mapped_column(String(17))

    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
    paired: Mapped[bool] = mapped_column(default=False, server_default=false(), index=True)
    paired_at: Mapped[Optional[datetime]] = mapped_column()

    # Relationships
    readings: Mapped[list["Reading"]] = relationship(back_populates="device", cascade="all, delete-orphan")
    calibration_points: Mapped[list["CalibrationPoint"]] = relationship(back_populates="device", cascade="all, delete-orphan")

class Reading(Base):
    """Hydrometer reading (from any device type)."""
    __tablename__ = "readings"
    __table_args__ = (
        Index("ix_readings_device_timestamp", "device_id", "timestamp"),
        Index("ix_readings_batch_timestamp", "batch_id", "timestamp"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # Universal device FK - for all device types including Tilt
    device_id: Mapped[Optional[str]] = mapped_column(String(100), ForeignKey("devices.id"), nullable=True, index=True)
    # Batch FK - for tracking readings per batch
    batch_id: Mapped[Optional[int]] = mapped_column(ForeignKey("batches.id"), nullable=True, index=True)
    device_type: Mapped[str] = mapped_column(String(20), default="tilt")
    timestamp: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc), index=True)

    # Gravity readings
    sg_raw: Mapped[Optional[float]] = mapped_column()
    sg_calibrated: Mapped[Optional[float]] = mapped_column()

    # Temperature readings
    temp_raw: Mapped[Optional[float]] = mapped_column()
    temp_calibrated: Mapped[Optional[float]] = mapped_column()

    # Signal/battery
    rssi: Mapped[Optional[int]] = mapped_column()
    battery_voltage: Mapped[Optional[float]] = mapped_column()
    battery_percent: Mapped[Optional[int]] = mapped_column()

    # iSpindel-specific
    angle: Mapped[Optional[float]] = mapped_column()

    # Processing metadata
    source_protocol: Mapped[str] = mapped_column(String(20), default="ble")
    status: Mapped[str] = mapped_column(String(20), default="valid")
    is_pre_filtered: Mapped[bool] = mapped_column(default=False)

    # ML outputs - Kalman filtered values (Celsius)
    sg_filtered: Mapped[Optional[float]] = mapped_column()
    temp_filtered: Mapped[Optional[float]] = mapped_column()

    # ML outputs - Confidence and rates
    confidence: Mapped[Optional[float]] = mapped_column()  # 0.0-1.0
    sg_rate: Mapped[Optional[float]] = mapped_column()     # d(SG)/dt in points/hour
    temp_rate: Mapped[Optional[float]] = mapped_column()   # d(temp)/dt in °C/hour

    # ML outputs - Anomaly detection
    is_anomaly: Mapped[Optional[bool]] = mapped_column(default=False)
    anomaly_score: Mapped[Optional[float]] = mapped_column()  # 0.0-1.0
    anomaly_reasons: Mapped[Optional[str]] = mapped_column(Text)  # JSON array

    # Relationships
    device: Mapped[Optional["Device"]] = relationship(back_populates="readings")
    batch: Mapped[Optional["Batch"]] = relationship(back_populates="readings")


class CalibrationPoint(Base):
    """Calibration point for device (was: tilt)."""
    __tablename__ = "calibration_points"
    __table_args__ = (
        UniqueConstraint("device_id", "type", "raw_value", name="uq_calibration_point"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(String(100), ForeignKey("devices.id"), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(10), nullable=False)  # 'sg' or 'temp'
    raw_value: Mapped[float] = mapped_column(nullable=False)
    actual_value: Mapped[float] = mapped_column(nullable=False)

    device: Mapped["Device"] = relationship(back_populates="calibration_points")


class AmbientReading(Base):
    """Ambient temperature/humidity readings from Home Assistant sensors."""
    __tablename__ = "ambient_readings"
    __table_args__ = (
        Index("ix_ambient_timestamp", "timestamp"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc), index=True)
    temperature: Mapped[Optional[float]] = mapped_column()
    humidity: Mapped[Optional[float]] = mapped_column()
    entity_id: Mapped[Optional[str]] = mapped_column(String(100))


class ChamberReading(Base):
    """Chamber temperature/humidity readings from Home Assistant sensors."""
    __tablename__ = "chamber_readings"
    __table_args__ = (
        Index("ix_chamber_timestamp", "timestamp"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc), index=True)
    temperature: Mapped[Optional[float]] = mapped_column()  # Celsius
    humidity: Mapped[Optional[float]] = mapped_column()
    entity_id: Mapped[Optional[str]] = mapped_column(String(100))


class ControlEvent(Base):
    """Temperature control events (heater on/off, cooler on/off)."""
    __tablename__ = "control_events"
    __table_args__ = (
        Index("ix_control_timestamp", "timestamp"),
        Index("ix_control_batch_timestamp", "batch_id", "timestamp"),  # Composite index for batch queries
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc), index=True)
    device_id: Mapped[Optional[str]] = mapped_column(String(100), ForeignKey("devices.id"))
    batch_id: Mapped[Optional[int]] = mapped_column(ForeignKey("batches.id"))
    action: Mapped[str] = mapped_column(String(20))  # heat_on, heat_off, cool_on, cool_off
    wort_temp: Mapped[Optional[float]] = mapped_column()  # Temperature in Celsius
    ambient_temp: Mapped[Optional[float]] = mapped_column()  # Temperature in Celsius
    target_temp: Mapped[Optional[float]] = mapped_column()  # Temperature in Celsius


class Config(Base):
    __tablename__ = "config"

    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    value: Mapped[Optional[str]] = mapped_column(Text)  # JSON encoded


class Style(Base):
    """BJCP Style Guidelines reference data."""
    __tablename__ = "styles"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)  # e.g., "bjcp-2021-18b"
    guide: Mapped[str] = mapped_column(String(50), nullable=False)  # "BJCP 2021"
    category_number: Mapped[str] = mapped_column(String(10), nullable=False)  # "18"
    style_letter: Mapped[Optional[str]] = mapped_column(String(5))  # "B"
    name: Mapped[str] = mapped_column(String(100), nullable=False)  # "American Pale Ale"
    category: Mapped[str] = mapped_column(String(100), nullable=False)  # "Pale American Ale"
    type: Mapped[Optional[str]] = mapped_column(String(20))  # "Ale", "Lager", etc.
    og_min: Mapped[Optional[float]] = mapped_column()
    og_max: Mapped[Optional[float]] = mapped_column()
    fg_min: Mapped[Optional[float]] = mapped_column()
    fg_max: Mapped[Optional[float]] = mapped_column()
    ibu_min: Mapped[Optional[float]] = mapped_column()
    ibu_max: Mapped[Optional[float]] = mapped_column()
    srm_min: Mapped[Optional[float]] = mapped_column()
    srm_max: Mapped[Optional[float]] = mapped_column()
    abv_min: Mapped[Optional[float]] = mapped_column()
    abv_max: Mapped[Optional[float]] = mapped_column()
    description: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))

    # Relationships
    recipes: Mapped[list["Recipe"]] = relationship(back_populates="style")


class Recipe(Base):
    """Recipes following BeerJSON 1.0 schema (with BeerXML backward compatibility)."""
    __tablename__ = "recipes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # BeerJSON core fields
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    type: Mapped[Optional[str]] = mapped_column(String(50))  # "All Grain", "Extract", etc.
    author: Mapped[Optional[str]] = mapped_column(String(100))

    # Recipe vitals
    batch_size_liters: Mapped[Optional[float]] = mapped_column()
    boil_time_minutes: Mapped[Optional[int]] = mapped_column()
    efficiency_percent: Mapped[Optional[float]] = mapped_column()  # Brewhouse efficiency (0-100)

    # Gravity targets (renamed from *_target)
    og: Mapped[Optional[float]] = mapped_column()
    fg: Mapped[Optional[float]] = mapped_column()
    abv: Mapped[Optional[float]] = mapped_column()
    ibu: Mapped[Optional[float]] = mapped_column()
    color_srm: Mapped[Optional[float]] = mapped_column()  # renamed from srm_target
    carbonation_vols: Mapped[Optional[float]] = mapped_column()  # CO2 volumes

    # Style reference
    style_id: Mapped[Optional[str]] = mapped_column(ForeignKey("styles.id"))

    # BeerJSON version tracking
    beerjson_version: Mapped[str] = mapped_column(String(10), default="1.0")

    # Format-specific extensions (JSON)
    format_extensions: Mapped[Optional[dict]] = mapped_column(JSON)

    # Yeast info (extracted from BeerXML, preserved for backward compatibility)
    yeast_name: Mapped[Optional[str]] = mapped_column(String(100))
    yeast_lab: Mapped[Optional[str]] = mapped_column(String(100))
    yeast_product_id: Mapped[Optional[str]] = mapped_column(String(50))
    yeast_temp_min: Mapped[Optional[float]] = mapped_column()  # Celsius
    yeast_temp_max: Mapped[Optional[float]] = mapped_column()  # Celsius
    yeast_attenuation: Mapped[Optional[float]] = mapped_column()  # Percent

    # Expanded BeerXML fields (preserved for backward compatibility)
    brewer: Mapped[Optional[str]] = mapped_column(String(100))
    asst_brewer: Mapped[Optional[str]] = mapped_column(String(100))

    # Boil
    boil_size_l: Mapped[Optional[float]] = mapped_column()  # Pre-boil volume (liters)

    # Fermentation stages
    primary_age_days: Mapped[Optional[int]] = mapped_column()
    primary_temp_c: Mapped[Optional[float]] = mapped_column()
    secondary_age_days: Mapped[Optional[int]] = mapped_column()
    secondary_temp_c: Mapped[Optional[float]] = mapped_column()
    tertiary_age_days: Mapped[Optional[int]] = mapped_column()
    tertiary_temp_c: Mapped[Optional[float]] = mapped_column()

    # Aging
    age_days: Mapped[Optional[int]] = mapped_column()
    age_temp_c: Mapped[Optional[float]] = mapped_column()

    # Carbonation details
    forced_carbonation: Mapped[Optional[bool]] = mapped_column()
    priming_sugar_name: Mapped[Optional[str]] = mapped_column(String(50))
    priming_sugar_amount_kg: Mapped[Optional[float]] = mapped_column()

    # Tasting
    taste_notes: Mapped[Optional[str]] = mapped_column(Text)
    taste_rating: Mapped[Optional[float]] = mapped_column()  # BJCP scale (0-50)

    # Dates
    date: Mapped[Optional[str]] = mapped_column(String(50))  # Brew date from BeerXML

    # Notes and legacy
    notes: Mapped[Optional[str]] = mapped_column(Text)
    beerxml_content: Mapped[Optional[str]] = mapped_column(Text)  # Raw BeerXML for future re-parsing

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    style: Mapped[Optional["Style"]] = relationship(back_populates="recipes")
    batches: Mapped[list["Batch"]] = relationship(back_populates="recipe")
    fermentables: Mapped[list["RecipeFermentable"]] = relationship(back_populates="recipe", cascade="all, delete-orphan")
    hops: Mapped[list["RecipeHop"]] = relationship(back_populates="recipe", cascade="all, delete-orphan")
    cultures: Mapped[list["RecipeCulture"]] = relationship(back_populates="recipe", cascade="all, delete-orphan")
    miscs: Mapped[list["RecipeMisc"]] = relationship(back_populates="recipe", cascade="all, delete-orphan")
    water_profiles: Mapped[list["RecipeWaterProfile"]] = relationship(back_populates="recipe", cascade="all, delete-orphan")
    water_adjustments: Mapped[list["RecipeWaterAdjustment"]] = relationship(back_populates="recipe", cascade="all, delete-orphan")
    mash_steps: Mapped[list["RecipeMashStep"]] = relationship(back_populates="recipe", cascade="all, delete-orphan")
    fermentation_steps: Mapped[list["RecipeFermentationStep"]] = relationship(back_populates="recipe", cascade="all, delete-orphan")


class Batch(Base):
    """Instances of brewing a recipe on a device."""
    __tablename__ = "batches"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    recipe_id: Mapped[Optional[int]] = mapped_column(ForeignKey("recipes.id"))
    device_id: Mapped[Optional[str]] = mapped_column(ForeignKey("devices.id"))

    # Batch identification
    batch_number: Mapped[Optional[int]] = mapped_column()
    name: Mapped[Optional[str]] = mapped_column(String(200))  # Optional override

    # Status tracking
    status: Mapped[str] = mapped_column(String(20), default="planning")  # planning, fermenting, conditioning, completed, archived

    # Timeline
    brew_date: Mapped[Optional[datetime]] = mapped_column()
    start_time: Mapped[Optional[datetime]] = mapped_column()  # Fermentation start
    end_time: Mapped[Optional[datetime]] = mapped_column()  # Fermentation end

    # Measured values
    measured_og: Mapped[Optional[float]] = mapped_column()
    measured_fg: Mapped[Optional[float]] = mapped_column()
    measured_abv: Mapped[Optional[float]] = mapped_column()
    measured_attenuation: Mapped[Optional[float]] = mapped_column()

    # Temperature control - per-batch heater assignment
    heater_entity_id: Mapped[Optional[str]] = mapped_column(String(100))
    cooler_entity_id: Mapped[Optional[str]] = mapped_column(String(100))
    temp_target: Mapped[Optional[float]] = mapped_column()  # Override target temp for this batch
    temp_hysteresis: Mapped[Optional[float]] = mapped_column()  # Override hysteresis for this batch

    # Notes
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Soft delete timestamp
    deleted_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)

    # Relationships
    recipe: Mapped[Optional["Recipe"]] = relationship(back_populates="batches")
    device: Mapped[Optional["Device"]] = relationship()
    readings: Mapped[list["Reading"]] = relationship(
        back_populates="batch",
        cascade="all, delete-orphan"
    )

    @property
    def is_deleted(self) -> bool:
        """Check if batch is soft-deleted."""
        return self.deleted_at is not None


class RecipeFermentable(Base):
    """Fermentable ingredients (grains, extracts, sugars) in a recipe."""
    __tablename__ = "recipe_fermentables"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False)

    # BeerJSON core fields
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    type: Mapped[Optional[str]] = mapped_column(String(50))  # base, adjunct, sugar, grain, non-malt adjunct
    grain_group: Mapped[Optional[str]] = mapped_column(String(50))  # base, caramel, roasted, etc.
    amount_kg: Mapped[float] = mapped_column(nullable=False)  # Amount in kilograms
    percentage: Mapped[Optional[float]] = mapped_column()  # % of grain bill (0-100)
    yield_percent: Mapped[Optional[float]] = mapped_column()  # % yield (0-100)
    color_srm: Mapped[Optional[float]] = mapped_column()  # SRM color (renamed from color_lovibond)

    # Additional metadata
    origin: Mapped[Optional[str]] = mapped_column(String(50))
    supplier: Mapped[Optional[str]] = mapped_column(String(100))
    notes: Mapped[Optional[str]] = mapped_column(Text)

    # BeerJSON timing
    timing: Mapped[Optional[dict]] = mapped_column(JSON)

    # Format-specific extensions (preserves BeerXML/Brewfather data)
    format_extensions: Mapped[Optional[dict]] = mapped_column(JSON)

    # Advanced BeerXML fields (optional)
    add_after_boil: Mapped[Optional[bool]] = mapped_column(default=False)
    coarse_fine_diff: Mapped[Optional[float]] = mapped_column()  # %
    moisture: Mapped[Optional[float]] = mapped_column()  # %
    diastatic_power: Mapped[Optional[float]] = mapped_column()  # Lintner
    protein: Mapped[Optional[float]] = mapped_column()  # %
    max_in_batch: Mapped[Optional[float]] = mapped_column()  # %
    recommend_mash: Mapped[Optional[bool]] = mapped_column()

    # Relationship
    recipe: Mapped["Recipe"] = relationship(back_populates="fermentables")

    @property
    def color_lovibond(self) -> Optional[float]:
        """Alias for color_srm for backward compatibility."""
        return self.color_srm


class RecipeHop(Base):
    """Hop additions in a recipe."""
    __tablename__ = "recipe_hops"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False)

    # BeerJSON core fields
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    origin: Mapped[Optional[str]] = mapped_column(String(50))
    form: Mapped[Optional[str]] = mapped_column(String(20))  # pellet, leaf, plug, powder, extract
    alpha_acid_percent: Mapped[float] = mapped_column(nullable=False)  # AA% (0-100), renamed from alpha_percent
    beta_acid_percent: Mapped[Optional[float]] = mapped_column()  # Beta acids %, renamed from beta_percent
    amount_grams: Mapped[float] = mapped_column(nullable=False)  # Amount in grams (renamed from amount_kg)

    # BeerJSON timing (replaces use/time_min)
    timing: Mapped[Optional[dict]] = mapped_column(JSON)

    # Format-specific extensions (preserves BeerXML/Brewfather data)
    format_extensions: Mapped[Optional[dict]] = mapped_column(JSON)

    # Relationship
    recipe: Mapped["Recipe"] = relationship(back_populates="hops")

    @property
    def alpha_percent(self) -> float:
        """Alias for alpha_acid_percent for backward compatibility."""
        return self.alpha_acid_percent

    @property
    def amount_kg(self) -> float:
        """Alias for amount_grams (converted to kg) for backward compatibility."""
        return self.amount_grams / 1000.0

    @property
    def use(self) -> Optional[str]:
        """Extract use field from timing JSON for backward compatibility.

        Maps BeerJSON timing.use to BeerXML use values:
        - add_to_boil -> Boil
        - add_to_mash -> Mash
        - add_to_fermentation -> Dry Hop
        - add_to_package -> Bottling
        """
        if not self.timing:
            return None

        timing_use = self.timing.get('use')
        if not timing_use:
            return None

        # Map BeerJSON timing use to BeerXML use
        use_mapping = {
            'add_to_boil': 'Boil',
            'add_to_mash': 'Mash',
            'add_to_fermentation': 'Dry Hop',
            'add_to_package': 'Bottling'
        }

        return use_mapping.get(timing_use, 'Boil')


class RecipeCulture(Base):
    """Culture/yeast strains in a recipe (BeerJSON terminology)."""
    __tablename__ = "recipe_cultures"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False)

    # BeerJSON core fields
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    type: Mapped[Optional[str]] = mapped_column(String(20))  # ale, lager, wine, champagne, other
    form: Mapped[Optional[str]] = mapped_column(String(20))  # liquid, dry, slant, culture
    producer: Mapped[Optional[str]] = mapped_column(String(100))  # renamed from lab
    product_id: Mapped[Optional[str]] = mapped_column(String(50))

    # Temperature range (Celsius)
    temp_min_c: Mapped[Optional[float]] = mapped_column()
    temp_max_c: Mapped[Optional[float]] = mapped_column()

    # Attenuation range
    attenuation_min_percent: Mapped[Optional[float]] = mapped_column()  # % (0-100)
    attenuation_max_percent: Mapped[Optional[float]] = mapped_column()  # % (0-100)

    # Amount with unit
    amount: Mapped[Optional[float]] = mapped_column()
    amount_unit: Mapped[Optional[str]] = mapped_column(String(10))  # pkg, ml, g, etc.

    # BeerJSON timing
    timing: Mapped[Optional[dict]] = mapped_column(JSON)

    # Format-specific extensions (preserves BeerXML/Brewfather data)
    format_extensions: Mapped[Optional[dict]] = mapped_column(JSON)

    # Relationship
    recipe: Mapped["Recipe"] = relationship(back_populates="cultures")


class RecipeMisc(Base):
    """Misc ingredients (spices, finings, water agents, etc)."""
    __tablename__ = "recipe_miscs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False)

    # BeerJSON core fields
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)  # spice, fining, water agent, herb, flavor, other
    use: Mapped[str] = mapped_column(String(20), nullable=False)  # boil, mash, primary, secondary, bottling
    time_min: Mapped[Optional[float]] = mapped_column()  # Minutes (legacy BeerXML)
    amount_kg: Mapped[Optional[float]] = mapped_column()  # Amount (check amount_unit)
    amount_is_weight: Mapped[Optional[bool]] = mapped_column(default=True)  # Legacy BeerXML
    amount_unit: Mapped[Optional[str]] = mapped_column(String(10))  # g, kg, ml, l, tsp, tbsp, etc.
    use_for: Mapped[Optional[str]] = mapped_column(Text)
    notes: Mapped[Optional[str]] = mapped_column(Text)

    # BeerJSON timing
    timing: Mapped[Optional[dict]] = mapped_column(JSON)

    # Format-specific extensions (preserves BeerXML/Brewfather data)
    format_extensions: Mapped[Optional[dict]] = mapped_column(JSON)

    recipe: Mapped["Recipe"] = relationship(back_populates="miscs")


class RecipeWaterProfile(Base):
    """Water chemistry profiles for a recipe (source, target, or sparge water)."""
    __tablename__ = "recipe_water_profiles"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False)

    # Profile metadata
    profile_type: Mapped[str] = mapped_column(String(20), nullable=False)  # source, target, sparge
    name: Mapped[Optional[str]] = mapped_column(String(100))

    # Ion concentrations (ppm)
    calcium_ppm: Mapped[Optional[float]] = mapped_column()
    magnesium_ppm: Mapped[Optional[float]] = mapped_column()
    sodium_ppm: Mapped[Optional[float]] = mapped_column()
    chloride_ppm: Mapped[Optional[float]] = mapped_column()
    sulfate_ppm: Mapped[Optional[float]] = mapped_column()
    bicarbonate_ppm: Mapped[Optional[float]] = mapped_column()

    # Water characteristics
    ph: Mapped[Optional[float]] = mapped_column()
    alkalinity: Mapped[Optional[float]] = mapped_column()

    # Format-specific extensions
    format_extensions: Mapped[Optional[dict]] = mapped_column(JSON)

    # Relationship
    recipe: Mapped["Recipe"] = relationship(back_populates="water_profiles")


class RecipeWaterAdjustment(Base):
    """Water treatment additions (salts and acids) for a recipe."""
    __tablename__ = "recipe_water_adjustments"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False)

    # Stage metadata
    stage: Mapped[str] = mapped_column(String(20), nullable=False)  # mash, sparge, total
    volume_liters: Mapped[Optional[float]] = mapped_column()

    # Salt additions (grams)
    calcium_sulfate_g: Mapped[Optional[float]] = mapped_column()  # Gypsum (CaSO4)
    calcium_chloride_g: Mapped[Optional[float]] = mapped_column()  # CaCl2
    magnesium_sulfate_g: Mapped[Optional[float]] = mapped_column()  # Epsom salt (MgSO4)
    sodium_bicarbonate_g: Mapped[Optional[float]] = mapped_column()  # Baking soda (NaHCO3)
    calcium_carbonate_g: Mapped[Optional[float]] = mapped_column()  # Chalk (CaCO3)
    calcium_hydroxide_g: Mapped[Optional[float]] = mapped_column()  # Slaked lime (Ca(OH)2)
    magnesium_chloride_g: Mapped[Optional[float]] = mapped_column()  # MgCl2
    sodium_chloride_g: Mapped[Optional[float]] = mapped_column()  # Table salt (NaCl)

    # Acid additions
    acid_type: Mapped[Optional[str]] = mapped_column(String(20))  # lactic, phosphoric, citric, etc.
    acid_ml: Mapped[Optional[float]] = mapped_column()
    acid_concentration_percent: Mapped[Optional[float]] = mapped_column()

    # Format-specific extensions
    format_extensions: Mapped[Optional[dict]] = mapped_column(JSON)

    # Relationship
    recipe: Mapped["Recipe"] = relationship(back_populates="water_adjustments")


class RecipeMashStep(Base):
    """Mash schedule steps for a recipe."""
    __tablename__ = "recipe_mash_steps"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False)

    # Step metadata
    step_number: Mapped[int] = mapped_column(nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False)  # infusion, temperature, decoction

    # Step parameters (temperatures in Celsius)
    temp_c: Mapped[float] = mapped_column(nullable=False)
    time_minutes: Mapped[int] = mapped_column(nullable=False)

    # Infusion step parameters
    infusion_amount_liters: Mapped[Optional[float]] = mapped_column()
    infusion_temp_c: Mapped[Optional[float]] = mapped_column()

    # Ramp parameters
    ramp_time_minutes: Mapped[Optional[int]] = mapped_column()

    # Format-specific extensions
    format_extensions: Mapped[Optional[dict]] = mapped_column(JSON)

    # Relationship
    recipe: Mapped["Recipe"] = relationship(back_populates="mash_steps")


class RecipeFermentationStep(Base):
    """Fermentation schedule steps for a recipe."""
    __tablename__ = "recipe_fermentation_steps"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False)

    # Step metadata
    step_number: Mapped[int] = mapped_column(nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False)  # primary, secondary, conditioning

    # Step parameters (temperature in Celsius)
    temp_c: Mapped[float] = mapped_column(nullable=False)
    time_days: Mapped[int] = mapped_column(nullable=False)

    # Format-specific extensions
    format_extensions: Mapped[Optional[dict]] = mapped_column(JSON)

    # Relationship
    recipe: Mapped["Recipe"] = relationship(back_populates="fermentation_steps")


# Pydantic Schemas
class TiltReading(BaseModel):
    id: str
    color: str
    sg: float
    sg_raw: float
    temp: float
    temp_raw: float
    rssi: int
    last_seen: datetime
    beer_name: str
    paired: bool

    @field_serializer('last_seen')
    def serialize_dt(self, dt: datetime) -> str:
        return serialize_datetime_to_utc(dt)


class ReadingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    timestamp: datetime
    sg_raw: Optional[float]
    sg_calibrated: Optional[float]
    temp_raw: Optional[float]
    temp_calibrated: Optional[float]
    rssi: Optional[int]
    status: Optional[str] = None  # 'valid', 'invalid', 'uncalibrated', 'incomplete'

    # ML outputs
    sg_filtered: Optional[float] = None
    temp_filtered: Optional[float] = None
    confidence: Optional[float] = None
    sg_rate: Optional[float] = None
    temp_rate: Optional[float] = None
    is_anomaly: Optional[bool] = None
    anomaly_score: Optional[float] = None
    anomaly_reasons: Optional[str] = None

    @field_serializer('timestamp')
    def serialize_dt(self, dt: datetime) -> str:
        return serialize_datetime_to_utc(dt)


class AmbientReadingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    timestamp: datetime
    temperature: Optional[float]
    humidity: Optional[float]

    @field_serializer('timestamp')
    def serialize_dt(self, dt: datetime) -> str:
        return serialize_datetime_to_utc(dt)


class ChamberReadingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    timestamp: datetime
    temperature: Optional[float]
    humidity: Optional[float]

    @field_serializer('timestamp')
    def serialize_dt(self, dt: datetime) -> str:
        return serialize_datetime_to_utc(dt)


class ControlEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    timestamp: datetime
    device_id: Optional[str]
    batch_id: Optional[int]
    action: str
    wort_temp: Optional[float]  # Temperature in Celsius
    ambient_temp: Optional[float]  # Temperature in Celsius
    target_temp: Optional[float]  # Temperature in Celsius

    @field_serializer('timestamp')
    def serialize_dt(self, dt: datetime) -> str:
        return serialize_datetime_to_utc(dt)


class CalibrationPointCreate(BaseModel):
    type: str  # 'sg' or 'temp'
    raw_value: float
    actual_value: float


class CalibrationPointResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: str
    raw_value: float
    actual_value: float


class ConfigUpdate(BaseModel):
    temp_units: Optional[str] = None  # "F" or "C"
    sg_units: Optional[str] = None  # "sg", "plato", "brix"
    local_logging_enabled: Optional[bool] = None
    local_interval_minutes: Optional[int] = None
    min_rssi: Optional[int] = None
    smoothing_enabled: Optional[bool] = None
    smoothing_samples: Optional[int] = None
    id_by_mac: Optional[bool] = None
    # Home Assistant settings
    ha_enabled: Optional[bool] = None
    ha_url: Optional[str] = None
    ha_token: Optional[str] = None
    ha_ambient_temp_entity_id: Optional[str] = None
    ha_ambient_humidity_entity_id: Optional[str] = None
    # Chamber settings
    ha_chamber_temp_entity_id: Optional[str] = None
    ha_chamber_humidity_entity_id: Optional[str] = None
    # Temperature control
    temp_control_enabled: Optional[bool] = None
    temp_target: Optional[float] = None
    temp_hysteresis: Optional[float] = None
    ha_heater_entity_id: Optional[str] = None
    # Weather
    ha_weather_entity_id: Optional[str] = None
    # Alerts
    weather_alerts_enabled: Optional[bool] = None
    alert_temp_threshold: Optional[float] = None

    @field_validator("temp_units")
    @classmethod
    def validate_temp_units(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in ("F", "C"):
            raise ValueError("temp_units must be 'F' or 'C'")
        return v

    @field_validator("sg_units")
    @classmethod
    def validate_sg_units(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in ("sg", "plato", "brix"):
            raise ValueError("sg_units must be 'sg', 'plato', or 'brix'")
        return v

    @field_validator("local_interval_minutes")
    @classmethod
    def validate_interval(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and (v < 1 or v > 60):
            raise ValueError("local_interval_minutes must be between 1 and 60")
        return v

    @field_validator("min_rssi")
    @classmethod
    def validate_rssi(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and (v < -100 or v > 0):
            raise ValueError("min_rssi must be between -100 and 0")
        return v

    @field_validator("smoothing_samples")
    @classmethod
    def validate_samples(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and (v < 1 or v > 20):
            raise ValueError("smoothing_samples must be between 1 and 20")
        return v

    @field_validator("ha_url")
    @classmethod
    def validate_ha_url(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v and not v.startswith(("http://", "https://")):
            raise ValueError("ha_url must start with http:// or https://")
        return v.rstrip("/") if v else v

    @field_validator("temp_target")
    @classmethod
    def validate_temp_target(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and (v < 0 or v > 100):
            raise ValueError("temp_target must be between 0-100°C (32-212°F)")
        return v

    @field_validator("temp_hysteresis")
    @classmethod
    def validate_temp_hysteresis(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and (v < 0.05 or v > 5.5):
            raise ValueError("temp_hysteresis must be between 0.05-5.5°C (0.1-10°F)")
        return v

    @field_validator("alert_temp_threshold")
    @classmethod
    def validate_alert_temp_threshold(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and (v < 0.5 or v > 11):
            raise ValueError("alert_temp_threshold must be between 0.5-11°C (1-20°F)")
        return v


class ConfigResponse(BaseModel):
    temp_units: str = "C"
    sg_units: str = "sg"
    local_logging_enabled: bool = True
    local_interval_minutes: int = 15
    min_rssi: int = -100
    smoothing_enabled: bool = False
    smoothing_samples: int = 5
    id_by_mac: bool = False
    # Home Assistant settings
    ha_enabled: bool = False
    ha_url: str = ""
    ha_token: str = ""
    ha_ambient_temp_entity_id: str = ""
    ha_ambient_humidity_entity_id: str = ""
    # Chamber settings
    ha_chamber_temp_entity_id: str = ""
    ha_chamber_humidity_entity_id: str = ""
    # Temperature control
    temp_control_enabled: bool = False
    temp_target: float = 68.0
    temp_hysteresis: float = 1.0
    ha_heater_entity_id: str = ""
    # Weather
    ha_weather_entity_id: str = ""
    # Alerts
    weather_alerts_enabled: bool = False
    alert_temp_threshold: float = 5.0


# Recipe & Batch Pydantic Schemas
class StyleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    guide: str
    category_number: str
    style_letter: Optional[str] = None
    name: str
    category: str
    type: Optional[str] = None
    og_min: Optional[float] = None
    og_max: Optional[float] = None
    fg_min: Optional[float] = None
    fg_max: Optional[float] = None
    ibu_min: Optional[float] = None
    ibu_max: Optional[float] = None
    srm_min: Optional[float] = None
    srm_max: Optional[float] = None
    abv_min: Optional[float] = None
    abv_max: Optional[float] = None
    description: Optional[str] = None


class RecipeCreate(BaseModel):
    name: str
    author: Optional[str] = None
    style_id: Optional[str] = None
    type: Optional[str] = None
    og: Optional[float] = None
    fg: Optional[float] = None
    yeast_name: Optional[str] = None
    yeast_temp_min: Optional[float] = None
    yeast_temp_max: Optional[float] = None
    yeast_attenuation: Optional[float] = None
    ibu: Optional[float] = None
    abv: Optional[float] = None
    batch_size_liters: Optional[float] = None
    notes: Optional[str] = None


class RecipeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    author: Optional[str] = None
    style_id: Optional[str] = None
    type: Optional[str] = None
    og: Optional[float] = None
    fg: Optional[float] = None
    yeast_name: Optional[str] = None
    yeast_lab: Optional[str] = None
    yeast_product_id: Optional[str] = None
    yeast_temp_min: Optional[float] = None
    yeast_temp_max: Optional[float] = None
    yeast_attenuation: Optional[float] = None
    ibu: Optional[float] = None
    color_srm: Optional[float] = None
    abv: Optional[float] = None
    batch_size_liters: Optional[float] = None
    notes: Optional[str] = None
    created_at: datetime
    style: Optional[StyleResponse] = None

    @field_serializer('created_at')
    def serialize_dt(self, dt: datetime) -> str:
        return serialize_datetime_to_utc(dt)


class FermentableResponse(BaseModel):
    """Pydantic response model for fermentable ingredients."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    type: Optional[str] = None
    amount_kg: Optional[float] = None
    yield_percent: Optional[float] = None
    color_srm: Optional[float] = None  # Renamed from color_lovibond
    origin: Optional[str] = None
    supplier: Optional[str] = None


class HopResponse(BaseModel):
    """Pydantic response model for hop additions."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    origin: Optional[str] = None
    form: Optional[str] = None
    alpha_acid_percent: Optional[float] = None
    beta_acid_percent: Optional[float] = None
    amount_grams: Optional[float] = None
    timing: Optional[dict] = None  # BeerJSON timing object
    format_extensions: Optional[dict] = None  # BeerXML metadata (type, substitutes, oils, notes)


class CultureResponse(BaseModel):
    """Pydantic response model for culture (yeast/bacteria) strains."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    producer: Optional[str] = None  # Renamed from lab
    product_id: Optional[str] = None
    type: Optional[str] = None
    form: Optional[str] = None
    attenuation_min_percent: Optional[float] = None  # BeerJSON uses min/max range
    attenuation_max_percent: Optional[float] = None
    temp_min_c: Optional[float] = None
    temp_max_c: Optional[float] = None
    amount: Optional[float] = None
    amount_unit: Optional[str] = None
    timing: Optional[dict] = None  # BeerJSON timing object
    format_extensions: Optional[dict] = None  # BeerXML metadata (flocculation, best_for, etc.)


# Backward compatibility alias
YeastResponse = CultureResponse


class MiscResponse(BaseModel):
    """Pydantic response model for misc ingredients."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    type: Optional[str] = None
    use: Optional[str] = None
    time_min: Optional[float] = None
    amount_kg: Optional[float] = None
    amount_is_weight: Optional[bool] = None


class RecipeDetailResponse(BaseModel):
    """Full recipe with all ingredients."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    author: Optional[str] = None
    style_id: Optional[str] = None
    type: Optional[str] = None
    og: Optional[float] = None
    fg: Optional[float] = None
    ibu: Optional[float] = None
    color_srm: Optional[float] = None
    abv: Optional[float] = None
    batch_size_liters: Optional[float] = None
    notes: Optional[str] = None
    created_at: datetime
    style: Optional[StyleResponse] = None

    # Ingredient lists
    fermentables: list[FermentableResponse] = []
    hops: list[HopResponse] = []
    cultures: list[CultureResponse] = []
    miscs: list[MiscResponse] = []

    @field_serializer('created_at')
    def serialize_dt(self, dt: datetime) -> str:
        return serialize_datetime_to_utc(dt)


class BatchCreate(BaseModel):
    recipe_id: Optional[int] = None
    device_id: Optional[str] = None
    name: Optional[str] = None
    status: str = "planning"
    brew_date: Optional[datetime] = None
    measured_og: Optional[float] = None
    notes: Optional[str] = None
    # Temperature control
    heater_entity_id: Optional[str] = None
    cooler_entity_id: Optional[str] = None
    temp_target: Optional[float] = None
    temp_hysteresis: Optional[float] = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        valid = ["planning", "fermenting", "conditioning", "completed", "archived"]
        if v not in valid:
            raise ValueError(f"status must be one of: {', '.join(valid)}")
        return v

    @field_validator("heater_entity_id", "cooler_entity_id")
    @classmethod
    def validate_entity(cls, v: Optional[str]) -> Optional[str]:
        if v and not v.startswith(("switch.", "input_boolean.")):
            raise ValueError("entity_id must be a valid HA entity (e.g., switch.heater_1 or input_boolean.heater_1)")
        return v

    @field_validator("temp_target")
    @classmethod
    def validate_temp_target(cls, v: Optional[float]) -> Optional[float]:
        if v is not None:
            if v < 0.0 or v > 100.0:  # Celsius range (32-212°F)
                raise ValueError("temp_target must be between 0-100°C (32-212°F)")
        return v

    @field_validator("temp_hysteresis")
    @classmethod
    def validate_temp_hysteresis(cls, v: Optional[float]) -> Optional[float]:
        if v is not None:
            if v < 0.05 or v > 5.5:  # Celsius deltas (0.1-10°F)
                raise ValueError("temp_hysteresis must be between 0.05-5.5°C (0.1-10°F)")
        return v


class BatchUpdate(BaseModel):
    recipe_id: Optional[int] = None
    name: Optional[str] = None
    status: Optional[str] = None
    device_id: Optional[str] = None
    brew_date: Optional[datetime] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    measured_og: Optional[float] = None
    measured_fg: Optional[float] = None
    notes: Optional[str] = None
    # Temperature control
    heater_entity_id: Optional[str] = None
    cooler_entity_id: Optional[str] = None
    temp_target: Optional[float] = None
    temp_hysteresis: Optional[float] = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        valid = ["planning", "fermenting", "conditioning", "completed", "archived"]
        if v not in valid:
            raise ValueError(f"status must be one of: {', '.join(valid)}")
        return v

    @field_validator("heater_entity_id", "cooler_entity_id")
    @classmethod
    def validate_entity(cls, v: Optional[str]) -> Optional[str]:
        if v and not v.startswith(("switch.", "input_boolean.")):
            raise ValueError("entity_id must be a valid HA entity (e.g., switch.heater_1 or input_boolean.heater_1)")
        return v

    @field_validator("temp_target")
    @classmethod
    def validate_temp_target(cls, v: Optional[float]) -> Optional[float]:
        if v is not None:
            if v < 0.0 or v > 100.0:  # Celsius range (32-212°F)
                raise ValueError("temp_target must be between 0-100°C (32-212°F)")
        return v

    @field_validator("temp_hysteresis")
    @classmethod
    def validate_temp_hysteresis(cls, v: Optional[float]) -> Optional[float]:
        if v is not None:
            if v < 0.05 or v > 5.5:  # Celsius deltas (0.1-10°F)
                raise ValueError("temp_hysteresis must be between 0.05-5.5°C (0.1-10°F)")
        return v


class BatchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    recipe_id: Optional[int] = None
    device_id: Optional[str] = None
    batch_number: Optional[int] = None
    name: Optional[str] = None
    status: str
    brew_date: Optional[datetime] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    measured_og: Optional[float] = None
    measured_fg: Optional[float] = None
    measured_abv: Optional[float] = None
    measured_attenuation: Optional[float] = None
    notes: Optional[str] = None
    created_at: datetime
    deleted_at: Optional[datetime] = None
    recipe: Optional[RecipeResponse] = None
    # Temperature control
    heater_entity_id: Optional[str] = None
    cooler_entity_id: Optional[str] = None
    temp_target: Optional[float] = None
    temp_hysteresis: Optional[float] = None

    @field_serializer('brew_date', 'start_time', 'end_time', 'created_at', 'deleted_at')
    def serialize_dt(self, dt: Optional[datetime]) -> Optional[str]:
        return serialize_datetime_to_utc(dt)


class BatchProgressResponse(BaseModel):
    """Fermentation progress response."""
    batch_id: int
    recipe_name: Optional[str] = None
    status: str
    targets: dict  # og, fg, attenuation, abv
    measured: dict  # og, current_sg, attenuation, abv
    progress: dict  # percent_complete, sg_remaining, estimated_days_remaining
    temperature: dict  # current, yeast_min, yeast_max, status


class BatchPredictionsResponse(BaseModel):
    """ML predictions response for a batch."""
    model_config = ConfigDict(from_attributes=True)

    available: bool
    predicted_fg: Optional[float] = None
    predicted_og: Optional[float] = None
    estimated_completion: Optional[str] = None
    hours_to_completion: Optional[float] = None
    model_type: Optional[str] = None
    r_squared: Optional[float] = None
    num_readings: int = 0
    error: Optional[str] = None
    reason: Optional[str] = None
