import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional

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


class FermentationAlert(Base):
    """Fermentation alerts tracked over time with first detection and resolution."""
    __tablename__ = "fermentation_alerts"
    __table_args__ = (
        Index("ix_alert_batch_active", "batch_id", "cleared_at"),
        Index("ix_alert_type_batch", "alert_type", "batch_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("batches.id"), nullable=False, index=True)
    device_id: Mapped[Optional[str]] = mapped_column(String(100), ForeignKey("devices.id"))

    # Alert classification
    alert_type: Mapped[str] = mapped_column(String(30), nullable=False)  # stall, temperature_high, temperature_low, anomaly
    severity: Mapped[str] = mapped_column(String(20), default="warning")  # info, warning, critical

    # Alert message and context
    message: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[Optional[str]] = mapped_column(Text)  # JSON with additional data (sg_rate, temp, etc.)

    # Reading that triggered the alert
    trigger_reading_id: Mapped[Optional[int]] = mapped_column(ForeignKey("readings.id"))

    # Lifecycle timestamps
    first_detected_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc), nullable=False)
    cleared_at: Mapped[Optional[datetime]] = mapped_column()  # null = still active

    # Relationships
    batch: Mapped["Batch"] = relationship(back_populates="alerts")
    trigger_reading: Mapped[Optional["Reading"]] = relationship()


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
    comments: Mapped[Optional[str]] = mapped_column(Text)  # Contains aliases like "NEIPA"
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))

    # Relationships
    recipes: Mapped[list["Recipe"]] = relationship(back_populates="style")


class YeastStrain(Base):
    """Yeast strain reference database.

    Seeded from JSON file on startup, with support for custom user strains.
    """
    __tablename__ = "yeast_strains"
    __table_args__ = (
        Index("ix_yeast_strains_producer_product", "producer", "product_id"),
        Index("ix_yeast_strains_type", "type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Core identification
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    producer: Mapped[Optional[str]] = mapped_column(String(100))  # Lab name (Fermentis, White Labs, etc.)
    product_id: Mapped[Optional[str]] = mapped_column(String(50))  # e.g., "US-05", "WLP001"

    # Classification
    type: Mapped[Optional[str]] = mapped_column(String(20))  # ale, lager, wine, wild, hybrid
    form: Mapped[Optional[str]] = mapped_column(String(20))  # dry, liquid, slant

    # Fermentation characteristics
    attenuation_low: Mapped[Optional[float]] = mapped_column()  # % (e.g., 73.0)
    attenuation_high: Mapped[Optional[float]] = mapped_column()  # % (e.g., 77.0)
    temp_low: Mapped[Optional[float]] = mapped_column()  # Celsius
    temp_high: Mapped[Optional[float]] = mapped_column()  # Celsius
    alcohol_tolerance: Mapped[Optional[str]] = mapped_column(String(20))  # low, medium, high, very_high
    flocculation: Mapped[Optional[str]] = mapped_column(String(20))  # low, medium, high, very_high

    # Metadata
    description: Mapped[Optional[str]] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(50), default="custom")  # brewunited, beermaverick, custom
    is_custom: Mapped[bool] = mapped_column(default=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class HopVariety(Base):
    """Hop variety reference database.

    Seeded from JSON file on startup, with support for custom user varieties.
    """
    __tablename__ = "hop_varieties"
    __table_args__ = (
        Index("ix_hop_varieties_name", "name"),
        Index("ix_hop_varieties_origin", "origin"),
        Index("ix_hop_varieties_purpose", "purpose"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Core identification
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    origin: Mapped[Optional[str]] = mapped_column(String(100))  # Country/region

    # Alpha/Beta acids
    alpha_acid_low: Mapped[Optional[float]] = mapped_column()  # % (e.g., 5.5)
    alpha_acid_high: Mapped[Optional[float]] = mapped_column()  # % (e.g., 8.5)
    beta_acid_low: Mapped[Optional[float]] = mapped_column()
    beta_acid_high: Mapped[Optional[float]] = mapped_column()

    # Classification
    purpose: Mapped[Optional[str]] = mapped_column(String(20))  # bittering, aroma, dual

    # Characteristics
    aroma_profile: Mapped[Optional[str]] = mapped_column(Text)  # Citrus, pine, floral, etc.
    substitutes: Mapped[Optional[str]] = mapped_column(Text)  # Comma-separated similar hops

    # Metadata
    description: Mapped[Optional[str]] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(50), default="custom")
    is_custom: Mapped[bool] = mapped_column(default=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class Fermentable(Base):
    """Fermentable reference database (grains, sugars, extracts, adjuncts).

    Seeded from JSON file on startup, with support for custom user entries.
    """
    __tablename__ = "fermentables"
    __table_args__ = (
        Index("ix_fermentables_name", "name"),
        Index("ix_fermentables_type", "type"),
        Index("ix_fermentables_origin", "origin"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Core identification
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    type: Mapped[Optional[str]] = mapped_column(String(30))  # base, specialty, adjunct, sugar, extract, fruit, other
    origin: Mapped[Optional[str]] = mapped_column(String(100))  # Country/region
    maltster: Mapped[Optional[str]] = mapped_column(String(100))  # Manufacturer (e.g., Weyermann, Briess)

    # Brewing characteristics
    color_srm: Mapped[Optional[float]] = mapped_column()  # Color in SRM/Lovibond
    potential_sg: Mapped[Optional[float]] = mapped_column()  # Extract potential (e.g., 1.037)
    max_in_batch_percent: Mapped[Optional[float]] = mapped_column()  # Max recommended % in grain bill
    diastatic_power: Mapped[Optional[float]] = mapped_column()  # Lintner (enzymatic power for base malts)

    # Characteristics
    flavor_profile: Mapped[Optional[str]] = mapped_column(Text)  # Biscuit, caramel, roasty, etc.
    substitutes: Mapped[Optional[str]] = mapped_column(Text)  # Comma-separated similar grains

    # Metadata
    description: Mapped[Optional[str]] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(50), default="custom")
    is_custom: Mapped[bool] = mapped_column(default=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


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
    yeast_strain_id: Mapped[Optional[int]] = mapped_column(ForeignKey("yeast_strains.id"))

    # Batch identification
    batch_number: Mapped[Optional[int]] = mapped_column()
    name: Mapped[Optional[str]] = mapped_column(String(200))  # Optional override

    # Status tracking - full lifecycle: planning → brewing → fermenting → conditioning → completed
    status: Mapped[str] = mapped_column(String(20), default="planning")

    # Timeline - legacy fields (kept for compatibility)
    brew_date: Mapped[Optional[datetime]] = mapped_column()
    start_time: Mapped[Optional[datetime]] = mapped_column()  # Fermentation start
    end_time: Mapped[Optional[datetime]] = mapped_column()  # Fermentation end

    # Phase timestamps - track when each phase started
    brewing_started_at: Mapped[Optional[datetime]] = mapped_column()
    fermenting_started_at: Mapped[Optional[datetime]] = mapped_column()
    conditioning_started_at: Mapped[Optional[datetime]] = mapped_column()
    completed_at: Mapped[Optional[datetime]] = mapped_column()

    # Measured values
    measured_og: Mapped[Optional[float]] = mapped_column()
    measured_fg: Mapped[Optional[float]] = mapped_column()
    measured_abv: Mapped[Optional[float]] = mapped_column()
    measured_attenuation: Mapped[Optional[float]] = mapped_column()

    # Brew day observations
    actual_mash_temp: Mapped[Optional[float]] = mapped_column()  # Celsius
    actual_mash_ph: Mapped[Optional[float]] = mapped_column()
    strike_water_volume: Mapped[Optional[float]] = mapped_column()  # Liters
    pre_boil_gravity: Mapped[Optional[float]] = mapped_column()  # SG
    pre_boil_volume: Mapped[Optional[float]] = mapped_column()  # Liters
    post_boil_volume: Mapped[Optional[float]] = mapped_column()  # Liters
    actual_efficiency: Mapped[Optional[float]] = mapped_column()  # Percentage
    brew_day_notes: Mapped[Optional[str]] = mapped_column(Text)

    # Packaging info
    packaged_at: Mapped[Optional[datetime]] = mapped_column()
    packaging_type: Mapped[Optional[str]] = mapped_column(String(20))  # bottles, keg, cans
    packaging_volume: Mapped[Optional[float]] = mapped_column()  # Liters packaged
    carbonation_method: Mapped[Optional[str]] = mapped_column(String(30))  # forced, bottle_conditioned, keg_conditioned
    priming_sugar_type: Mapped[Optional[str]] = mapped_column(String(50))  # e.g., "table sugar", "corn sugar"
    priming_sugar_amount: Mapped[Optional[float]] = mapped_column()  # Grams
    packaging_notes: Mapped[Optional[str]] = mapped_column(Text)

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

    # Reading control - pause storage during manual gravity checks
    readings_paused: Mapped[bool] = mapped_column(default=False)

    # Brew day timer state (persisted for multi-device sync)
    timer_phase: Mapped[Optional[str]] = mapped_column(String(20))  # idle, mash, boil, complete
    timer_started_at: Mapped[Optional[datetime]] = mapped_column()  # When current phase started
    timer_duration_seconds: Mapped[Optional[int]] = mapped_column()  # Total duration for phase
    timer_paused_at: Mapped[Optional[datetime]] = mapped_column()  # When paused (null if running)

    # Relationships
    recipe: Mapped[Optional["Recipe"]] = relationship(back_populates="batches")
    device: Mapped[Optional["Device"]] = relationship()
    yeast_strain: Mapped[Optional["YeastStrain"]] = relationship()
    readings: Mapped[list["Reading"]] = relationship(
        back_populates="batch",
        cascade="all, delete-orphan"
    )
    alerts: Mapped[list["FermentationAlert"]] = relationship(
        back_populates="batch",
        cascade="all, delete-orphan"
    )
    tasting_notes: Mapped[list["TastingNote"]] = relationship(
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

    @property
    def time_min(self) -> Optional[float]:
        """Extract time from timing JSON for backward compatibility.

        Returns duration value from timing.duration object.

        Note: BeerXML quirk - Dry Hop times are in DAYS, not minutes.
        This property returns the raw value without conversion to preserve
        backward compatibility with BeerXML semantics.
        """
        if not self.timing:
            return None

        duration = self.timing.get('duration')
        if not duration:
            return None

        value = duration.get('value')
        if value is None:
            return None

        # Return raw value - BeerXML stores Dry Hop in days, boil hops in minutes
        return float(value)

    @property
    def type(self) -> Optional[str]:
        """Extract type from format_extensions for backward compatibility."""
        if not self.format_extensions:
            return None
        return self.format_extensions.get('type')

    @property
    def beta_percent(self) -> Optional[float]:
        """Alias for beta_acid_percent for backward compatibility."""
        return self.beta_acid_percent

    @property
    def hsi(self) -> Optional[float]:
        """Extract HSI from format_extensions for backward compatibility."""
        if not self.format_extensions:
            return None
        return self.format_extensions.get('hsi')

    @property
    def humulene(self) -> Optional[float]:
        """Extract humulene from format_extensions for backward compatibility."""
        if not self.format_extensions:
            return None
        return self.format_extensions.get('humulene')

    @property
    def caryophyllene(self) -> Optional[float]:
        """Extract caryophyllene from format_extensions for backward compatibility."""
        if not self.format_extensions:
            return None
        return self.format_extensions.get('caryophyllene')

    @property
    def cohumulone(self) -> Optional[float]:
        """Extract cohumulone from format_extensions for backward compatibility."""
        if not self.format_extensions:
            return None
        return self.format_extensions.get('cohumulone')

    @property
    def myrcene(self) -> Optional[float]:
        """Extract myrcene from format_extensions for backward compatibility."""
        if not self.format_extensions:
            return None
        return self.format_extensions.get('myrcene')

    @property
    def substitutes(self) -> Optional[str]:
        """Extract substitutes from format_extensions for backward compatibility."""
        if not self.format_extensions:
            return None
        return self.format_extensions.get('substitutes')

    @property
    def notes(self) -> Optional[str]:
        """Extract notes from format_extensions for backward compatibility."""
        if not self.format_extensions:
            return None
        return self.format_extensions.get('notes')


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

    @property
    def lab(self) -> Optional[str]:
        """Alias for producer for backward compatibility."""
        return self.producer

    @property
    def attenuation_percent(self) -> Optional[float]:
        """Alias for attenuation_min_percent for backward compatibility."""
        return self.attenuation_min_percent

    @property
    def flocculation(self) -> Optional[str]:
        """Extract flocculation from format_extensions for backward compatibility."""
        if not self.format_extensions:
            return None
        return self.format_extensions.get('flocculation')

    @property
    def amount_kg(self) -> Optional[float]:
        """Convert amount to kg for backward compatibility.

        Amount is stored as grams (for dry yeast), convert back to kg.
        """
        if not self.amount or not self.amount_unit:
            return None
        if self.amount_unit == 'g':
            return self.amount / 1000.0
        return None  # Only for dry yeast

    @property
    def amount_l(self) -> Optional[float]:
        """Return amount in liters for backward compatibility.

        Note: The importer stores amount_l directly as-is with unit='ml',
        without converting liters to milliliters. This property returns
        the value as stored (which is actually in liters, not ml).
        """
        if not self.amount or not self.amount_unit:
            return None
        if self.amount_unit == 'ml':
            return self.amount  # Already in liters (importer bug/quirk)
        return None  # Only for liquid yeast

    @property
    def add_to_secondary(self) -> Optional[bool]:
        """Extract add_to_secondary from format_extensions for backward compatibility."""
        if not self.format_extensions:
            return None
        return self.format_extensions.get('add_to_secondary')

    @property
    def best_for(self) -> Optional[str]:
        """Extract best_for from format_extensions for backward compatibility."""
        if not self.format_extensions:
            return None
        return self.format_extensions.get('best_for')

    @property
    def times_cultured(self) -> Optional[int]:
        """Extract times_cultured from format_extensions for backward compatibility."""
        if not self.format_extensions:
            return None
        return self.format_extensions.get('times_cultured')

    @property
    def max_reuse(self) -> Optional[int]:
        """Extract max_reuse from format_extensions for backward compatibility."""
        if not self.format_extensions:
            return None
        return self.format_extensions.get('max_reuse')

    @property
    def notes(self) -> Optional[str]:
        """Extract notes from format_extensions for backward compatibility."""
        if not self.format_extensions:
            return None
        return self.format_extensions.get('notes')


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


class TastingNote(Base):
    """Tasting notes for a batch - can have multiple over time as beer conditions."""
    __tablename__ = "tasting_notes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("batches.id", ondelete="CASCADE"), nullable=False)

    # When tasted
    tasted_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))

    # Appearance (1-5 scale)
    appearance_score: Mapped[Optional[int]] = mapped_column()  # 1-5
    appearance_notes: Mapped[Optional[str]] = mapped_column(Text)

    # Aroma (1-5 scale)
    aroma_score: Mapped[Optional[int]] = mapped_column()  # 1-5
    aroma_notes: Mapped[Optional[str]] = mapped_column(Text)

    # Flavor (1-5 scale)
    flavor_score: Mapped[Optional[int]] = mapped_column()  # 1-5
    flavor_notes: Mapped[Optional[str]] = mapped_column(Text)

    # Mouthfeel (1-5 scale)
    mouthfeel_score: Mapped[Optional[int]] = mapped_column()  # 1-5
    mouthfeel_notes: Mapped[Optional[str]] = mapped_column(Text)

    # Overall impression
    overall_score: Mapped[Optional[int]] = mapped_column()  # 1-5
    overall_notes: Mapped[Optional[str]] = mapped_column(Text)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationship
    batch: Mapped["Batch"] = relationship(back_populates="tasting_notes")


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

    # Battery (GravityMon/iSpindel)
    battery_percent: Optional[int] = None

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


class FermentationAlertResponse(BaseModel):
    """Pydantic response model for fermentation alerts."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    batch_id: int
    device_id: Optional[str] = None
    alert_type: str
    severity: str
    message: str
    context: Optional[str] = None  # JSON string with additional data
    trigger_reading_id: Optional[int] = None
    first_detected_at: datetime
    last_seen_at: datetime
    cleared_at: Optional[datetime] = None

    @field_serializer('first_detected_at', 'last_seen_at', 'cleared_at')
    def serialize_dt(self, dt: Optional[datetime]) -> Optional[str]:
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
    # AI Assistant settings
    ai_enabled: Optional[bool] = None
    ai_provider: Optional[str] = None  # local, openai, anthropic, google, groq, deepseek
    ai_model: Optional[str] = None  # Model name (e.g., gpt-4o, claude-3-5-sonnet)
    ai_api_key: Optional[str] = None  # API key (encrypted at rest)
    ai_base_url: Optional[str] = None  # For Ollama: http://localhost:11434
    ai_temperature: Optional[float] = None
    ai_max_tokens: Optional[int] = None
    # MQTT settings for Home Assistant
    mqtt_enabled: Optional[bool] = None
    mqtt_host: Optional[str] = None
    mqtt_port: Optional[int] = None
    mqtt_username: Optional[str] = None
    mqtt_password: Optional[str] = None
    mqtt_topic_prefix: Optional[str] = None

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

    @field_validator("ai_provider")
    @classmethod
    def validate_ai_provider(cls, v: Optional[str]) -> Optional[str]:
        valid_providers = ("local", "openai", "anthropic", "google", "groq", "deepseek", "huggingface", "openrouter")
        if v is not None and v not in valid_providers:
            raise ValueError(f"ai_provider must be one of: {', '.join(valid_providers)}")
        return v

    @field_validator("ai_temperature")
    @classmethod
    def validate_ai_temperature(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and (v < 0 or v > 2):
            raise ValueError("ai_temperature must be between 0 and 2")
        return v

    @field_validator("ai_max_tokens")
    @classmethod
    def validate_ai_max_tokens(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and (v < 100 or v > 8000):
            raise ValueError("ai_max_tokens must be between 100 and 8000")
        return v

    @field_validator("mqtt_port")
    @classmethod
    def validate_mqtt_port(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and (v < 1 or v > 65535):
            raise ValueError("mqtt_port must be between 1 and 65535")
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
    # AI Assistant settings
    ai_enabled: bool = False
    ai_provider: str = "local"
    ai_model: str = ""
    ai_api_key: str = ""  # Masked in responses, stored encrypted
    ai_base_url: str = ""
    ai_temperature: float = 0.7
    ai_max_tokens: int = 2000
    # MQTT settings for Home Assistant
    mqtt_enabled: bool = False
    mqtt_host: str = ""
    mqtt_port: int = 1883
    mqtt_username: str = ""
    mqtt_password: str = ""
    mqtt_topic_prefix: str = "brewsignal"


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


# Yeast Strain Pydantic Schemas
class YeastStrainCreate(BaseModel):
    """Schema for creating a custom yeast strain."""
    name: str
    producer: Optional[str] = None
    product_id: Optional[str] = None
    type: Optional[str] = None  # ale, lager, wine, wild, hybrid
    form: Optional[str] = None  # dry, liquid, slant
    attenuation_low: Optional[float] = None
    attenuation_high: Optional[float] = None
    temp_low: Optional[float] = None  # Celsius
    temp_high: Optional[float] = None  # Celsius
    alcohol_tolerance: Optional[str] = None  # low, medium, high, very_high
    flocculation: Optional[str] = None  # low, medium, high, very_high
    description: Optional[str] = None

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: Optional[str]) -> Optional[str]:
        if v and v not in ("ale", "lager", "wine", "wild", "hybrid"):
            raise ValueError("type must be ale, lager, wine, wild, or hybrid")
        return v

    @field_validator("form")
    @classmethod
    def validate_form(cls, v: Optional[str]) -> Optional[str]:
        if v and v not in ("dry", "liquid", "slant"):
            raise ValueError("form must be dry, liquid, or slant")
        return v

    @field_validator("flocculation")
    @classmethod
    def validate_flocculation(cls, v: Optional[str]) -> Optional[str]:
        if v and v not in ("low", "medium", "high", "very_high"):
            raise ValueError("flocculation must be low, medium, high, or very_high")
        return v


class YeastStrainResponse(BaseModel):
    """Schema for yeast strain API responses."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    producer: Optional[str] = None
    product_id: Optional[str] = None
    type: Optional[str] = None
    form: Optional[str] = None
    attenuation_low: Optional[float] = None
    attenuation_high: Optional[float] = None
    temp_low: Optional[float] = None
    temp_high: Optional[float] = None
    alcohol_tolerance: Optional[str] = None
    flocculation: Optional[str] = None
    description: Optional[str] = None
    source: str
    is_custom: bool
    created_at: datetime
    updated_at: datetime

    @field_serializer('created_at', 'updated_at')
    def serialize_dt(self, dt: datetime) -> str:
        return serialize_datetime_to_utc(dt)


class HopVarietyCreate(BaseModel):
    """Schema for creating a custom hop variety."""
    name: str
    origin: Optional[str] = None
    alpha_acid_low: Optional[float] = None
    alpha_acid_high: Optional[float] = None
    beta_acid_low: Optional[float] = None
    beta_acid_high: Optional[float] = None
    purpose: Optional[str] = None  # bittering, aroma, dual
    aroma_profile: Optional[str] = None
    substitutes: Optional[str] = None
    description: Optional[str] = None

    @field_validator("purpose")
    @classmethod
    def validate_purpose(cls, v: Optional[str]) -> Optional[str]:
        if v and v not in ("bittering", "aroma", "dual"):
            raise ValueError("purpose must be bittering, aroma, or dual")
        return v


class HopVarietyResponse(BaseModel):
    """Schema for hop variety API responses."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    origin: Optional[str] = None
    alpha_acid_low: Optional[float] = None
    alpha_acid_high: Optional[float] = None
    beta_acid_low: Optional[float] = None
    beta_acid_high: Optional[float] = None
    purpose: Optional[str] = None
    aroma_profile: Optional[str] = None
    substitutes: Optional[str] = None
    description: Optional[str] = None
    source: str
    is_custom: bool
    created_at: datetime
    updated_at: datetime

    @field_serializer('created_at', 'updated_at')
    def serialize_dt(self, dt: datetime) -> str:
        return serialize_datetime_to_utc(dt)


class FermentableCreate(BaseModel):
    """Schema for creating a custom fermentable."""
    name: str
    type: Optional[str] = None  # base, specialty, adjunct, sugar, extract, fruit, other
    origin: Optional[str] = None
    maltster: Optional[str] = None
    color_srm: Optional[float] = None
    potential_sg: Optional[float] = None
    max_in_batch_percent: Optional[float] = None
    diastatic_power: Optional[float] = None
    flavor_profile: Optional[str] = None
    substitutes: Optional[str] = None
    description: Optional[str] = None

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: Optional[str]) -> Optional[str]:
        valid_types = ("base", "specialty", "adjunct", "sugar", "extract", "fruit", "other")
        if v and v not in valid_types:
            raise ValueError(f"type must be one of: {', '.join(valid_types)}")
        return v


class FermentableResponse(BaseModel):
    """Schema for fermentable API responses."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    type: Optional[str] = None
    origin: Optional[str] = None
    maltster: Optional[str] = None
    color_srm: Optional[float] = None
    potential_sg: Optional[float] = None
    max_in_batch_percent: Optional[float] = None
    diastatic_power: Optional[float] = None
    flavor_profile: Optional[str] = None
    substitutes: Optional[str] = None
    description: Optional[str] = None
    source: str
    is_custom: bool
    created_at: datetime
    updated_at: datetime

    @field_serializer('created_at', 'updated_at')
    def serialize_dt(self, dt: datetime) -> str:
        return serialize_datetime_to_utc(dt)


class RecipeCreate(BaseModel):
    name: str
    author: Optional[str] = None
    style_id: Optional[str] = None
    type: Optional[str] = None
    og: Optional[float] = None
    fg: Optional[float] = None
    abv: Optional[float] = None
    ibu: Optional[float] = None
    color_srm: Optional[float] = None
    batch_size_liters: Optional[float] = None
    boil_time_minutes: Optional[int] = None
    efficiency_percent: Optional[float] = None
    carbonation_vols: Optional[float] = None
    yeast_name: Optional[str] = None
    yeast_lab: Optional[str] = None
    yeast_product_id: Optional[str] = None
    yeast_temp_min: Optional[float] = None
    yeast_temp_max: Optional[float] = None
    yeast_attenuation: Optional[float] = None
    notes: Optional[str] = None
    format_extensions: Optional[Dict[str, Any]] = None


class RecipeUpdate(BaseModel):
    name: Optional[str] = None
    author: Optional[str] = None
    style_id: Optional[str] = None
    type: Optional[str] = None
    og: Optional[float] = None
    fg: Optional[float] = None
    abv: Optional[float] = None
    ibu: Optional[float] = None
    color_srm: Optional[float] = None
    batch_size_liters: Optional[float] = None
    boil_time_minutes: Optional[int] = None
    efficiency_percent: Optional[float] = None
    carbonation_vols: Optional[float] = None
    yeast_name: Optional[str] = None
    yeast_lab: Optional[str] = None
    yeast_product_id: Optional[str] = None
    yeast_temp_min: Optional[float] = None
    yeast_temp_max: Optional[float] = None
    yeast_attenuation: Optional[float] = None
    notes: Optional[str] = None
    format_extensions: Optional[Dict[str, Any]] = None


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
    boil_time_minutes: Optional[int] = None
    efficiency_percent: Optional[float] = None
    mash_temp: Optional[float] = None
    pre_boil_og: Optional[float] = None
    notes: Optional[str] = None
    # Yeast info (stored on recipe for quick access)
    yeast_name: Optional[str] = None
    yeast_lab: Optional[str] = None
    yeast_product_id: Optional[str] = None
    yeast_temp_min: Optional[float] = None
    yeast_temp_max: Optional[float] = None
    yeast_attenuation: Optional[float] = None
    format_extensions: Optional[Dict[str, Any]] = None
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
    yeast_strain_id: Optional[int] = None  # Override recipe yeast with specific strain
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
        valid = ["planning", "brewing", "fermenting", "conditioning", "completed", "archived"]
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
    yeast_strain_id: Optional[int] = None  # Override recipe yeast with specific strain
    brew_date: Optional[datetime] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    measured_og: Optional[float] = None
    measured_fg: Optional[float] = None
    # Brew day observations
    actual_mash_temp: Optional[float] = None
    actual_mash_ph: Optional[float] = None
    strike_water_volume: Optional[float] = None
    pre_boil_gravity: Optional[float] = None
    pre_boil_volume: Optional[float] = None
    post_boil_volume: Optional[float] = None
    actual_efficiency: Optional[float] = None
    brew_day_notes: Optional[str] = None
    # Packaging info
    packaged_at: Optional[datetime] = None
    packaging_type: Optional[str] = None
    packaging_volume: Optional[float] = None
    carbonation_method: Optional[str] = None
    priming_sugar_type: Optional[str] = None
    priming_sugar_amount: Optional[float] = None
    packaging_notes: Optional[str] = None
    notes: Optional[str] = None
    # Temperature control
    heater_entity_id: Optional[str] = None
    cooler_entity_id: Optional[str] = None
    temp_target: Optional[float] = None
    temp_hysteresis: Optional[float] = None
    # Reading control
    readings_paused: Optional[bool] = None
    # Timer control
    timer_phase: Optional[str] = None
    timer_started_at: Optional[datetime] = None
    timer_duration_seconds: Optional[int] = None
    timer_paused_at: Optional[datetime] = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        valid = ["planning", "brewing", "fermenting", "conditioning", "completed", "archived"]
        if v not in valid:
            raise ValueError(f"status must be one of: {', '.join(valid)}")
        return v

    @field_validator("timer_phase")
    @classmethod
    def validate_timer_phase(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        valid = ["idle", "mash", "boil", "complete"]
        if v not in valid:
            raise ValueError(f"timer_phase must be one of: {', '.join(valid)}")
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
    yeast_strain_id: Optional[int] = None
    batch_number: Optional[int] = None
    name: Optional[str] = None
    status: str
    brew_date: Optional[datetime] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    # Phase timestamps
    brewing_started_at: Optional[datetime] = None
    fermenting_started_at: Optional[datetime] = None
    conditioning_started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    measured_og: Optional[float] = None
    measured_fg: Optional[float] = None
    measured_abv: Optional[float] = None
    measured_attenuation: Optional[float] = None
    # Brew day observations
    actual_mash_temp: Optional[float] = None
    actual_mash_ph: Optional[float] = None
    strike_water_volume: Optional[float] = None
    pre_boil_gravity: Optional[float] = None
    pre_boil_volume: Optional[float] = None
    post_boil_volume: Optional[float] = None
    actual_efficiency: Optional[float] = None
    brew_day_notes: Optional[str] = None
    # Packaging info
    packaged_at: Optional[datetime] = None
    packaging_type: Optional[str] = None
    packaging_volume: Optional[float] = None
    carbonation_method: Optional[str] = None
    priming_sugar_type: Optional[str] = None
    priming_sugar_amount: Optional[float] = None
    packaging_notes: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime
    deleted_at: Optional[datetime] = None
    recipe: Optional[RecipeResponse] = None
    yeast_strain: Optional[YeastStrainResponse] = None
    tasting_notes: list["TastingNoteResponse"] = []
    # Temperature control
    heater_entity_id: Optional[str] = None
    cooler_entity_id: Optional[str] = None
    temp_target: Optional[float] = None
    temp_hysteresis: Optional[float] = None
    # Reading control
    readings_paused: bool = False
    # Timer state
    timer_phase: Optional[str] = None
    timer_started_at: Optional[datetime] = None
    timer_duration_seconds: Optional[int] = None
    timer_paused_at: Optional[datetime] = None

    @field_serializer('brew_date', 'start_time', 'end_time', 'brewing_started_at', 'fermenting_started_at', 'conditioning_started_at', 'completed_at', 'created_at', 'deleted_at', 'packaged_at', 'timer_started_at', 'timer_paused_at')
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


# =============================================================================
# Tasting Note Models
# =============================================================================

class TastingNoteCreate(BaseModel):
    """Create a new tasting note for a batch."""
    batch_id: int
    tasted_at: Optional[datetime] = None
    appearance_score: Optional[int] = None
    appearance_notes: Optional[str] = None
    aroma_score: Optional[int] = None
    aroma_notes: Optional[str] = None
    flavor_score: Optional[int] = None
    flavor_notes: Optional[str] = None
    mouthfeel_score: Optional[int] = None
    mouthfeel_notes: Optional[str] = None
    overall_score: Optional[int] = None
    overall_notes: Optional[str] = None

    @field_validator("appearance_score", "aroma_score", "flavor_score", "mouthfeel_score", "overall_score")
    @classmethod
    def validate_score(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and (v < 1 or v > 5):
            raise ValueError("Score must be between 1 and 5")
        return v


class TastingNoteUpdate(BaseModel):
    """Update an existing tasting note."""
    tasted_at: Optional[datetime] = None
    appearance_score: Optional[int] = None
    appearance_notes: Optional[str] = None
    aroma_score: Optional[int] = None
    aroma_notes: Optional[str] = None
    flavor_score: Optional[int] = None
    flavor_notes: Optional[str] = None
    mouthfeel_score: Optional[int] = None
    mouthfeel_notes: Optional[str] = None
    overall_score: Optional[int] = None
    overall_notes: Optional[str] = None

    @field_validator("appearance_score", "aroma_score", "flavor_score", "mouthfeel_score", "overall_score")
    @classmethod
    def validate_score(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and (v < 1 or v > 5):
            raise ValueError("Score must be between 1 and 5")
        return v


class TastingNoteResponse(BaseModel):
    """Response schema for a tasting note."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    batch_id: int
    tasted_at: datetime
    appearance_score: Optional[int] = None
    appearance_notes: Optional[str] = None
    aroma_score: Optional[int] = None
    aroma_notes: Optional[str] = None
    flavor_score: Optional[int] = None
    flavor_notes: Optional[str] = None
    mouthfeel_score: Optional[int] = None
    mouthfeel_notes: Optional[str] = None
    overall_score: Optional[int] = None
    overall_notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    @field_serializer('tasted_at', 'created_at', 'updated_at')
    def serialize_dt(self, dt: Optional[datetime]) -> Optional[str]:
        return serialize_datetime_to_utc(dt)


# =============================================================================
# AG-UI Models - Conversation threads and messages for AI assistant
# =============================================================================

class AgUiThread(Base):
    """AG-UI conversation thread."""
    __tablename__ = "ag_ui_threads"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    title: Mapped[Optional[str]] = mapped_column(String(200))
    title_locked: Mapped[bool] = mapped_column(default=False)  # Prevents auto-summarization
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    messages: Mapped[list["AgUiMessage"]] = relationship(
        back_populates="thread",
        cascade="all, delete-orphan",
        order_by="AgUiMessage.created_at"
    )


class AgUiMessage(Base):
    """AG-UI message within a thread."""
    __tablename__ = "ag_ui_messages"
    __table_args__ = (
        Index("ix_ag_ui_messages_thread_created", "thread_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    thread_id: Mapped[str] = mapped_column(String(100), ForeignKey("ag_ui_threads.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(20))  # user, assistant, tool
    content: Mapped[str] = mapped_column(Text)
    tool_calls: Mapped[Optional[str]] = mapped_column(Text)  # JSON array of tool calls
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))

    # Relationships
    thread: Mapped["AgUiThread"] = relationship(back_populates="messages")

    @property
    def tool_calls_data(self) -> Optional[list[dict[str, Any]]]:
        """Get tool calls as list of dicts."""
        if self.tool_calls:
            return json.loads(self.tool_calls)
        return None

    @tool_calls_data.setter
    def tool_calls_data(self, value: Optional[list[dict[str, Any]]]) -> None:
        """Set tool calls from list of dicts."""
        if value is not None:
            self.tool_calls = json.dumps(value)
        else:
            self.tool_calls = None


# AG-UI Pydantic Schemas

# =============================================================================
# Inventory Models - Equipment, Hops, and Yeast tracking
# =============================================================================

class Equipment(Base):
    """Brewing equipment (kettles, fermenters, etc.)."""
    __tablename__ = "equipment"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)  # kettle, fermenter, pump, chiller, etc.
    brand: Mapped[Optional[str]] = mapped_column(String(100))
    model: Mapped[Optional[str]] = mapped_column(String(100))
    capacity_liters: Mapped[Optional[float]] = mapped_column()  # Volume capacity
    capacity_kg: Mapped[Optional[float]] = mapped_column()  # Weight capacity (for grain mills, etc.)
    is_active: Mapped[bool] = mapped_column(default=True)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )


class HopInventory(Base):
    """Hops in inventory."""
    __tablename__ = "hop_inventory"
    __table_args__ = (
        Index("ix_hop_inventory_variety", "variety"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    variety: Mapped[str] = mapped_column(String(100), nullable=False)  # e.g., "Citra", "Cascade"
    amount_grams: Mapped[float] = mapped_column(nullable=False)  # Current amount in grams
    alpha_acid_percent: Mapped[Optional[float]] = mapped_column()  # AA% (0-100)
    crop_year: Mapped[Optional[int]] = mapped_column()  # Year harvested
    form: Mapped[str] = mapped_column(String(20), default="pellet")  # pellet, leaf, plug
    storage_location: Mapped[Optional[str]] = mapped_column(String(100))  # e.g., "Freezer A"
    purchase_date: Mapped[Optional[datetime]] = mapped_column()
    supplier: Mapped[Optional[str]] = mapped_column(String(100))
    lot_number: Mapped[Optional[str]] = mapped_column(String(50))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )


class YeastInventory(Base):
    """Yeast strains in inventory."""
    __tablename__ = "yeast_inventory"
    __table_args__ = (
        Index("ix_yeast_inventory_strain", "yeast_strain_id"),
        Index("ix_yeast_inventory_expiry", "expiry_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # Link to yeast strain database or custom name
    yeast_strain_id: Mapped[Optional[int]] = mapped_column(ForeignKey("yeast_strains.id"))
    custom_name: Mapped[Optional[str]] = mapped_column(String(200))  # For unlisted strains

    quantity: Mapped[int] = mapped_column(nullable=False, default=1)  # Number of packages/vials/jars
    form: Mapped[str] = mapped_column(String(20), nullable=False)  # dry, liquid, slant, harvested
    manufacture_date: Mapped[Optional[datetime]] = mapped_column()
    expiry_date: Mapped[Optional[datetime]] = mapped_column()

    # For harvested yeast
    generation: Mapped[Optional[int]] = mapped_column()  # Generation number (1 = first harvest)
    source_batch_id: Mapped[Optional[int]] = mapped_column(ForeignKey("batches.id"))

    storage_location: Mapped[Optional[str]] = mapped_column(String(100))  # e.g., "Fridge A"
    supplier: Mapped[Optional[str]] = mapped_column(String(100))
    lot_number: Mapped[Optional[str]] = mapped_column(String(50))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    yeast_strain: Mapped[Optional["YeastStrain"]] = relationship()
    source_batch: Mapped[Optional["Batch"]] = relationship()


# AG-UI Pydantic Schemas

class AgUiMessageResponse(BaseModel):
    """AG-UI message response."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    thread_id: str
    role: str
    content: str
    tool_calls: Optional[list[dict[str, Any]]] = None
    created_at: datetime

    @field_serializer('created_at')
    def serialize_dt(self, dt: datetime) -> str:
        return serialize_datetime_to_utc(dt) or ""

    @field_validator('tool_calls', mode='before')
    @classmethod
    def parse_tool_calls(cls, v: Any) -> Optional[list[dict[str, Any]]]:
        if v is None:
            return None
        if isinstance(v, str):
            return json.loads(v)
        return v


class AgUiThreadResponse(BaseModel):
    """AG-UI thread response."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    messages: list[AgUiMessageResponse] = []
    message_count: int = 0

    @field_serializer('created_at', 'updated_at')
    def serialize_dt(self, dt: datetime) -> str:
        return serialize_datetime_to_utc(dt) or ""


class AgUiThreadListItem(BaseModel):
    """AG-UI thread list item (without messages)."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    message_count: int = 0

    @field_serializer('created_at', 'updated_at')
    def serialize_dt(self, dt: datetime) -> str:
        return serialize_datetime_to_utc(dt) or ""


# =============================================================================
# Inventory Pydantic Schemas
# =============================================================================

# Equipment schemas
class EquipmentCreate(BaseModel):
    """Schema for creating equipment."""
    name: str
    type: str  # kettle, fermenter, pump, chiller, etc.
    brand: Optional[str] = None
    model: Optional[str] = None
    capacity_liters: Optional[float] = None
    capacity_kg: Optional[float] = None
    is_active: bool = True
    notes: Optional[str] = None

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        valid_types = ("kettle", "fermenter", "pump", "chiller", "mill", "mash_tun", "lauter_tun", "hot_liquor_tank", "bottling", "kegging", "all_in_one", "other")
        if v not in valid_types:
            raise ValueError(f"type must be one of: {', '.join(valid_types)}")
        return v


class EquipmentUpdate(BaseModel):
    """Schema for updating equipment."""
    name: Optional[str] = None
    type: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    capacity_liters: Optional[float] = None
    capacity_kg: Optional[float] = None
    is_active: Optional[bool] = None
    notes: Optional[str] = None

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        valid_types = ("kettle", "fermenter", "pump", "chiller", "mill", "mash_tun", "lauter_tun", "hot_liquor_tank", "bottling", "kegging", "all_in_one", "other")
        if v not in valid_types:
            raise ValueError(f"type must be one of: {', '.join(valid_types)}")
        return v


class EquipmentResponse(BaseModel):
    """Schema for equipment API responses."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    type: str
    brand: Optional[str] = None
    model: Optional[str] = None
    capacity_liters: Optional[float] = None
    capacity_kg: Optional[float] = None
    is_active: bool
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    @field_serializer('created_at', 'updated_at')
    def serialize_dt(self, dt: datetime) -> str:
        return serialize_datetime_to_utc(dt) or ""


# Hop Inventory schemas
class HopInventoryCreate(BaseModel):
    """Schema for creating hop inventory."""
    variety: str
    amount_grams: float
    alpha_acid_percent: Optional[float] = None
    crop_year: Optional[int] = None
    form: str = "pellet"
    storage_location: Optional[str] = None
    purchase_date: Optional[datetime] = None
    supplier: Optional[str] = None
    lot_number: Optional[str] = None
    notes: Optional[str] = None

    @field_validator("form")
    @classmethod
    def validate_form(cls, v: str) -> str:
        valid_forms = ("pellet", "leaf", "plug")
        if v not in valid_forms:
            raise ValueError(f"form must be one of: {', '.join(valid_forms)}")
        return v

    @field_validator("amount_grams")
    @classmethod
    def validate_amount(cls, v: float) -> float:
        if v < 0:
            raise ValueError("amount_grams must be >= 0")
        return v

    @field_validator("alpha_acid_percent")
    @classmethod
    def validate_alpha(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and (v < 0 or v > 100):
            raise ValueError("alpha_acid_percent must be between 0 and 100")
        return v


class HopInventoryUpdate(BaseModel):
    """Schema for updating hop inventory."""
    variety: Optional[str] = None
    amount_grams: Optional[float] = None
    alpha_acid_percent: Optional[float] = None
    crop_year: Optional[int] = None
    form: Optional[str] = None
    storage_location: Optional[str] = None
    purchase_date: Optional[datetime] = None
    supplier: Optional[str] = None
    lot_number: Optional[str] = None
    notes: Optional[str] = None

    @field_validator("form")
    @classmethod
    def validate_form(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        valid_forms = ("pellet", "leaf", "plug")
        if v not in valid_forms:
            raise ValueError(f"form must be one of: {', '.join(valid_forms)}")
        return v

    @field_validator("amount_grams")
    @classmethod
    def validate_amount(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and v < 0:
            raise ValueError("amount_grams must be >= 0")
        return v


class HopInventoryAdjust(BaseModel):
    """Schema for adjusting hop amount."""
    delta_grams: float  # Positive to add, negative to subtract

    @field_validator("delta_grams")
    @classmethod
    def validate_delta(cls, v: float) -> float:
        if v == 0:
            raise ValueError("delta_grams must not be 0")
        return v


class HopInventoryResponse(BaseModel):
    """Schema for hop inventory API responses."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    variety: str
    amount_grams: float
    alpha_acid_percent: Optional[float] = None
    crop_year: Optional[int] = None
    form: str
    storage_location: Optional[str] = None
    purchase_date: Optional[datetime] = None
    supplier: Optional[str] = None
    lot_number: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    @field_serializer('created_at', 'updated_at', 'purchase_date')
    def serialize_dt(self, dt: Optional[datetime]) -> Optional[str]:
        return serialize_datetime_to_utc(dt)


# Yeast Inventory schemas
class YeastInventoryCreate(BaseModel):
    """Schema for creating yeast inventory."""
    yeast_strain_id: Optional[int] = None  # Either this or custom_name required
    custom_name: Optional[str] = None
    quantity: int = 1
    form: str  # dry, liquid, slant, harvested
    manufacture_date: Optional[datetime] = None
    expiry_date: Optional[datetime] = None
    generation: Optional[int] = None  # For harvested yeast
    source_batch_id: Optional[int] = None  # For harvested yeast
    storage_location: Optional[str] = None
    supplier: Optional[str] = None
    lot_number: Optional[str] = None
    notes: Optional[str] = None

    @field_validator("form")
    @classmethod
    def validate_form(cls, v: str) -> str:
        valid_forms = ("dry", "liquid", "slant", "harvested")
        if v not in valid_forms:
            raise ValueError(f"form must be one of: {', '.join(valid_forms)}")
        return v

    @field_validator("quantity")
    @classmethod
    def validate_quantity(cls, v: int) -> int:
        if v < 0:
            raise ValueError("quantity must be >= 0")
        return v


class YeastInventoryUpdate(BaseModel):
    """Schema for updating yeast inventory."""
    yeast_strain_id: Optional[int] = None
    custom_name: Optional[str] = None
    quantity: Optional[int] = None
    form: Optional[str] = None
    manufacture_date: Optional[datetime] = None
    expiry_date: Optional[datetime] = None
    generation: Optional[int] = None
    source_batch_id: Optional[int] = None
    storage_location: Optional[str] = None
    supplier: Optional[str] = None
    lot_number: Optional[str] = None
    notes: Optional[str] = None

    @field_validator("form")
    @classmethod
    def validate_form(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        valid_forms = ("dry", "liquid", "slant", "harvested")
        if v not in valid_forms:
            raise ValueError(f"form must be one of: {', '.join(valid_forms)}")
        return v


class YeastInventoryUse(BaseModel):
    """Schema for using yeast (decrementing quantity)."""
    quantity: int = 1  # How many to use

    @field_validator("quantity")
    @classmethod
    def validate_quantity(cls, v: int) -> int:
        if v < 1:
            raise ValueError("quantity must be >= 1")
        return v


class YeastInventoryHarvest(BaseModel):
    """Schema for harvesting yeast from a batch."""
    source_batch_id: int
    quantity: int = 1
    notes: Optional[str] = None


class YeastInventoryResponse(BaseModel):
    """Schema for yeast inventory API responses."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    yeast_strain_id: Optional[int] = None
    custom_name: Optional[str] = None
    quantity: int
    form: str
    manufacture_date: Optional[datetime] = None
    expiry_date: Optional[datetime] = None
    generation: Optional[int] = None
    source_batch_id: Optional[int] = None
    storage_location: Optional[str] = None
    supplier: Optional[str] = None
    lot_number: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    # Nested relationships
    yeast_strain: Optional[YeastStrainResponse] = None

    @field_serializer('created_at', 'updated_at', 'manufacture_date', 'expiry_date')
    def serialize_dt(self, dt: Optional[datetime]) -> Optional[str]:
        return serialize_datetime_to_utc(dt)
