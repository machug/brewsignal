from pathlib import Path
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncAttrs, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

DATA_DIR = Path(__file__).parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)

DATABASE_URL = f"sqlite+aiosqlite:///{DATA_DIR}/fermentation.db"

engine = create_async_engine(DATABASE_URL, echo=False)
async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


class Base(AsyncAttrs, DeclarativeBase):
    pass


def _migrate_add_batch_id_to_readings(conn):
    """Add batch_id column to readings table if not present."""
    from sqlalchemy import inspect, text
    inspector = inspect(conn)

    if "readings" not in inspector.get_table_names():
        return  # Fresh install, create_all will handle it

    columns = [c["name"] for c in inspector.get_columns("readings")]
    if "batch_id" not in columns:
        conn.execute(text("ALTER TABLE readings ADD COLUMN batch_id INTEGER REFERENCES batches(id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_readings_batch_id ON readings(batch_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_readings_batch_timestamp ON readings(batch_id, timestamp)"))
        print("Migration: Added batch_id column to readings table")


def _migrate_add_ml_columns(conn):
    """Add ML output columns to readings table."""
    from sqlalchemy import inspect, text
    import logging
    inspector = inspect(conn)

    if "readings" not in inspector.get_table_names():
        return  # Fresh install, create_all will handle it

    columns = [c["name"] for c in inspector.get_columns("readings")]

    if "sg_filtered" in columns:
        logging.info("ML columns already exist, skipping migration")
        return

    logging.info("Adding ML output columns to readings table")

    # Add ML columns
    conn.execute(text("""
        ALTER TABLE readings ADD COLUMN sg_filtered REAL
    """))
    conn.execute(text("""
        ALTER TABLE readings ADD COLUMN temp_filtered REAL
    """))
    conn.execute(text("""
        ALTER TABLE readings ADD COLUMN confidence REAL
    """))
    conn.execute(text("""
        ALTER TABLE readings ADD COLUMN sg_rate REAL
    """))
    conn.execute(text("""
        ALTER TABLE readings ADD COLUMN temp_rate REAL
    """))
    conn.execute(text("""
        ALTER TABLE readings ADD COLUMN is_anomaly INTEGER DEFAULT 0
    """))
    conn.execute(text("""
        ALTER TABLE readings ADD COLUMN anomaly_score REAL
    """))
    conn.execute(text("""
        ALTER TABLE readings ADD COLUMN anomaly_reasons TEXT
    """))

    logging.info("ML columns added successfully")


async def _migrate_temps_fahrenheit_to_celsius(engine):
    """Convert all temperature data from Fahrenheit to Celsius.

    Uses explicit migration tracking via config table to prevent double-migration.
    """
    from sqlalchemy import text
    import logging

    async with engine.begin() as conn:
        # Check if config table exists
        result = await conn.execute(text(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='config'"
        ))
        if not result.fetchone():
            logging.info("Config table doesn't exist yet, skipping temperature migration")
            return

        # Check if migration already completed via explicit flag
        result = await conn.execute(text(
            "SELECT value FROM config WHERE key = 'temp_migration_v1_complete'"
        ))
        if result.fetchone():
            logging.info("Temperature migration already completed (tracked via config)")
            return

        # Check if readings table exists using SQLite-specific query
        result = await conn.execute(text(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='readings'"
        ))
        if not result.fetchone():
            logging.info("Readings table doesn't exist yet, skipping temperature migration")
            return

        # Check if migration already applied by sampling a reading (legacy heuristic)
        result = await conn.execute(text(
            "SELECT temp_raw FROM readings WHERE temp_raw IS NOT NULL LIMIT 1"
        ))
        row = result.fetchone()

        if not row:
            logging.info("No readings with temperature data, skipping migration")
            # Mark as complete even if no data to prevent future attempts
            await conn.execute(text(
                "INSERT OR REPLACE INTO config (key, value) VALUES ('temp_migration_v1_complete', 'true')"
            ))
            return

        if row[0] < 50:  # Already in Celsius (fermentation temps are 0-40°C)
            logging.info("Temperatures already in Celsius (heuristic check)")
            # Mark as complete to prevent future heuristic checks
            await conn.execute(text(
                "INSERT OR REPLACE INTO config (key, value) VALUES ('temp_migration_v1_complete', 'true')"
            ))
            return

        logging.info("Converting temperatures from Fahrenheit to Celsius")

        # Convert readings table
        await conn.execute(text("""
            UPDATE readings
            SET
                temp_raw = (temp_raw - 32) * 5.0 / 9.0,
                temp_calibrated = (temp_calibrated - 32) * 5.0 / 9.0
            WHERE temp_raw IS NOT NULL OR temp_calibrated IS NOT NULL
        """))

        # Convert calibration points (only if table exists)
        result = await conn.execute(text(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='calibration_points'"
        ))
        if result.fetchone():
            await conn.execute(text("""
                UPDATE calibration_points
                SET
                    raw_value = (raw_value - 32) * 5.0 / 9.0,
                    actual_value = (actual_value - 32) * 5.0 / 9.0
                WHERE type = 'temp'
            """))

        # Convert batch temperature fields (only if table exists)
        result = await conn.execute(text(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='batches'"
        ))
        if result.fetchone():
            # Check if any batch has temperature values that need conversion
            # Detect Fahrenheit: temp_target >= 50 OR temp_hysteresis > 10
            # (50°F = 10°C is the boundary - lagers can ferment at 50°F)
            # (Hysteresis >10 must be Fahrenheit since typical values are 0.5-5°C / 1-9°F)
            result = await conn.execute(text("""
                SELECT COUNT(*) FROM batches
                WHERE (temp_target IS NOT NULL AND temp_target >= 50)
                   OR (temp_hysteresis IS NOT NULL AND temp_hysteresis > 10)
            """))
            count = result.scalar()

            if count > 0:
                logging.info(f"Converting {count} batch temperature fields from Fahrenheit to Celsius")
                # Convert temp_target (absolute temperature): (F - 32) * 5/9
                # Convert temp_hysteresis (temperature delta): F * 5/9 (no -32 offset)
                await conn.execute(text("""
                    UPDATE batches
                    SET
                        temp_target = CASE
                            WHEN temp_target IS NOT NULL AND temp_target >= 50
                            THEN (temp_target - 32) * 5.0 / 9.0
                            ELSE temp_target
                        END,
                        temp_hysteresis = CASE
                            WHEN temp_hysteresis IS NOT NULL AND temp_hysteresis > 10
                            THEN temp_hysteresis * 5.0 / 9.0
                            ELSE temp_hysteresis
                        END
                    WHERE (temp_target IS NOT NULL AND temp_target >= 50)
                       OR (temp_hysteresis IS NOT NULL AND temp_hysteresis > 10)
                """))

        # NOTE: ambient_readings table is NOT converted - Home Assistant already sends Celsius

        # Mark migration as complete
        await conn.execute(text(
            "INSERT OR REPLACE INTO config (key, value) VALUES ('temp_migration_v1_complete', 'true')"
        ))

        logging.info("Temperature conversion complete and tracked in config")


async def _migrate_populate_recipe_cultures(engine):
    """Populate recipe_cultures from recipe yeast fields for BeerJSON compliance.

    This ensures all recipes have their yeast info in the cultures table,
    not just stored in legacy fields on the Recipe model.
    """
    import logging
    from sqlalchemy import text

    async with engine.begin() as conn:
        # Check if migration already ran
        result = await conn.execute(text(
            "SELECT value FROM config WHERE key = 'recipe_cultures_migration_complete'"
        ))
        row = result.fetchone()
        if row and row[0] == 'true':
            return  # Already migrated

        # Find recipes with yeast info but no cultures
        result = await conn.execute(text("""
            SELECT r.id, r.yeast_name, r.yeast_lab, r.yeast_product_id,
                   r.yeast_temp_min, r.yeast_temp_max, r.yeast_attenuation
            FROM recipes r
            LEFT JOIN recipe_cultures c ON r.id = c.recipe_id
            WHERE r.yeast_name IS NOT NULL
              AND c.id IS NULL
        """))
        recipes = result.fetchall()

        if recipes:
            logging.info(f"Migrating {len(recipes)} recipes to have cultures")
            for recipe in recipes:
                await conn.execute(text("""
                    INSERT INTO recipe_cultures (
                        recipe_id, name, producer, product_id,
                        temp_min_c, temp_max_c,
                        attenuation_min_percent, attenuation_max_percent
                    ) VALUES (
                        :recipe_id, :name, :producer, :product_id,
                        :temp_min, :temp_max,
                        :attenuation, :attenuation
                    )
                """), {
                    "recipe_id": recipe[0],
                    "name": recipe[1],
                    "producer": recipe[2],
                    "product_id": recipe[3],
                    "temp_min": recipe[4],
                    "temp_max": recipe[5],
                    "attenuation": recipe[6],
                })

            logging.info(f"Created {len(recipes)} recipe_cultures records")

        # Mark migration as complete
        await conn.execute(text(
            "INSERT OR REPLACE INTO config (key, value) VALUES ('recipe_cultures_migration_complete', 'true')"
        ))


async def init_db():
    """Initialize database with migrations.

    Order matters:
    1. Run migrations first (for existing DBs with data)
    2. Then create_all (for new tables/columns in fresh DBs)
    3. Then data migrations (copy tilts to devices)

    IMPORTANT: This function is not thread-safe. Run with a single worker
    during startup to avoid migration race conditions. After initial startup,
    multiple workers can safely access the database for read/write operations.
    """
    async with engine.begin() as conn:
        # Step 1: Schema migrations for existing DBs
        await conn.run_sync(_migrate_add_original_gravity)
        await conn.run_sync(_migrate_create_devices_table)
        await conn.run_sync(_migrate_add_reading_columns)
        await conn.run_sync(_migrate_readings_nullable_tilt_id)
        await conn.run_sync(_migrate_add_ml_columns)

        # BeerJSON support migration (must run before create_all)
        from backend.migrations.add_beerjson_support import migrate_add_beerjson_support
        await migrate_add_beerjson_support(conn)

        # Step 2: Create any missing tables (includes new Style, Recipe, Batch, ChamberReading tables)
        await conn.run_sync(Base.metadata.create_all)

        # Step 3: Migrations that depend on new tables existing
        await conn.run_sync(_migrate_create_recipe_fermentables_table)  # Create recipe_fermentables table
        await conn.run_sync(_migrate_create_recipe_hops_table)  # Create recipe_hops table
        await conn.run_sync(_migrate_create_recipe_yeasts_table)  # Create recipe_yeasts table
        await conn.run_sync(_migrate_create_recipe_miscs_table)  # Create recipe_miscs table
        await conn.run_sync(_migrate_add_recipe_expanded_fields)  # Add expanded BeerXML fields to recipes

        # Enhance ingredient tables with BeerJSON timing support
        from backend.migrations.enhance_ingredient_tables import migrate_enhance_ingredient_tables
        await migrate_enhance_ingredient_tables(conn)

        # Create water chemistry and procedure tables
        from backend.migrations.create_water_and_procedure_tables import migrate_create_water_and_procedure_tables
        await migrate_create_water_and_procedure_tables(conn)

        await conn.run_sync(_migrate_add_batch_id_to_readings)  # Add this line (after batches table exists)
        await conn.run_sync(_migrate_add_batch_heater_columns)  # Add heater control columns to batches
        await conn.run_sync(_migrate_add_batch_id_to_control_events)  # Add batch_id to control_events
        await conn.run_sync(_migrate_add_paired_to_tilts_and_devices)  # Add paired field
        await conn.run_sync(_migrate_add_deleted_at)  # Add soft delete support to batches
        await conn.run_sync(_migrate_add_deleted_at_index)  # Add index on deleted_at column
        await conn.run_sync(_migrate_create_yeast_strains_table)  # Create yeast strain reference table
        await conn.run_sync(_migrate_add_yeast_strain_to_batches)  # Add yeast override to batches
        await conn.run_sync(_migrate_add_batch_phase_timestamps)  # Add phase lifecycle timestamps
        await conn.run_sync(_migrate_add_brew_day_observations)  # Add brew day observation columns
        await conn.run_sync(_migrate_add_packaging_columns)  # Add packaging info columns
        await conn.run_sync(_migrate_create_tasting_notes_table)  # Create tasting notes table
        await conn.run_sync(_migrate_add_batch_timer_columns)  # Add brew day timer state columns

        # Add readings_paused column to batches
        from backend.migrations.add_readings_paused import migrate_add_readings_paused
        await migrate_add_readings_paused(conn)

    # Convert temperatures F→C (runs outside conn.begin() context since it has its own)
    await _migrate_temps_fahrenheit_to_celsius(engine)

    async with engine.begin() as conn:
        # Step 4: Data migrations
        await conn.run_sync(_migrate_tilts_to_devices)
        await conn.run_sync(_migrate_mark_outliers_invalid)  # Mark historical outliers
        await conn.run_sync(_migrate_fix_temp_outlier_detection)  # Fix F→C temp check bug
        await conn.run_sync(_migrate_tilts_to_devices_final)  # Final migration: drop tilts table
        await conn.run_sync(_migrate_control_events_tilt_id_to_device_id)  # Migrate control_events to use device_id

    # Add cooler support (runs outside conn.begin() context since it has its own)
    await _migrate_add_cooler_entity()

    # Populate recipe_cultures from recipe yeast fields (BeerJSON compliance)
    await _migrate_populate_recipe_cultures(engine)

    # Migrate yeast_strains table for alcohol_tolerance type change (REAL -> TEXT)
    # Must run separately and then call create_all() again to recreate the table
    reseed_styles = False
    async with engine.begin() as conn:
        await conn.run_sync(_migrate_yeast_strains_alcohol_tolerance)
        # Add comments column to styles for alias searching (NEIPA -> Hazy IPA)
        reseed_styles = await conn.run_sync(_migrate_add_style_comments_column)
        # Add title_locked column to ag_ui_threads
        await conn.run_sync(_migrate_add_ag_ui_thread_title_locked)
        # Recreate the table with correct schema
        await conn.run_sync(Base.metadata.create_all)

    # Seed yeast strains from JSON file
    from .services.yeast_seeder import seed_yeast_strains
    async with async_session_factory() as session:
        result = await seed_yeast_strains(session)
        if result.get("action") == "seeded":
            print(f"Seeded {result.get('count', 0)} yeast strains")

    # Seed hop varieties from JSON file
    from .services.hop_seeder import seed_hop_varieties
    async with async_session_factory() as session:
        result = await seed_hop_varieties(session)
        if result.get("action") == "seeded":
            print(f"Seeded {result.get('count', 0)} hop varieties")

    # Seed fermentables from JSON file
    from .services.fermentable_seeder import seed_fermentables
    async with async_session_factory() as session:
        result = await seed_fermentables(session)
        if result.get("action") == "seeded":
            print(f"Seeded {result.get('count', 0)} fermentables")

    # Seed BJCP styles from JSON file (force re-seed if comments column was just added)
    from .services.style_seeder import seed_styles
    async with async_session_factory() as session:
        result = await seed_styles(session, force=reseed_styles)
        if result.get("action") == "seeded":
            print(f"Seeded {result.get('count', 0)} BJCP styles")


def _migrate_add_original_gravity(conn):
    """Add original_gravity column to tilts table if not present."""
    from sqlalchemy import inspect, text
    inspector = inspect(conn)

    # Check if tilts table exists
    if "tilts" not in inspector.get_table_names():
        return  # Fresh install, create_all will handle it

    columns = [c["name"] for c in inspector.get_columns("tilts")]
    if "original_gravity" not in columns:
        conn.execute(text("ALTER TABLE tilts ADD COLUMN original_gravity REAL"))
        print("Migration: Added original_gravity column to tilts table")


def _migrate_create_devices_table(conn):
    """Create devices table if it doesn't exist (without SQLAlchemy metadata)."""
    from sqlalchemy import inspect, text
    inspector = inspect(conn)

    if "devices" in inspector.get_table_names():
        return  # Table exists, will check data migration separately

    # Create devices table manually (not via create_all)
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS devices (
            id TEXT PRIMARY KEY,
            device_type TEXT NOT NULL DEFAULT 'tilt',
            name TEXT NOT NULL,
            display_name TEXT,
            beer_name TEXT,
            original_gravity REAL,
            native_gravity_unit TEXT DEFAULT 'sg',
            native_temp_unit TEXT DEFAULT 'f',
            calibration_type TEXT DEFAULT 'none',
            calibration_data TEXT,
            auth_token TEXT,
            last_seen TIMESTAMP,
            battery_voltage REAL,
            firmware_version TEXT,
            color TEXT,
            mac TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """))
    print("Migration: Created devices table")


def _migrate_tilts_to_devices(conn):
    """Migrate existing tilts to devices table, preserving calibration offsets."""
    from sqlalchemy import text
    import json

    # Check if tilts table exists and has data
    try:
        result = conn.execute(text("SELECT COUNT(*) FROM tilts"))
        tilt_count = result.scalar()
    except Exception:
        # tilts table doesn't exist (fresh install)
        return

    if tilt_count == 0:
        return  # No tilts to migrate

    # Check if these tilts are already in devices
    result = conn.execute(text("""
        SELECT COUNT(*) FROM devices d
        WHERE EXISTS (SELECT 1 FROM tilts t WHERE t.id = d.id)
    """))
    migrated_count = result.scalar()

    if migrated_count >= tilt_count:
        print(f"Migration: Tilts already migrated ({migrated_count} devices)")
        return

    # Get tilts that need migration
    tilts_to_migrate = conn.execute(text("""
        SELECT id, color, mac, beer_name, original_gravity, last_seen
        FROM tilts
        WHERE id NOT IN (SELECT id FROM devices)
    """)).fetchall()

    # Check if calibration_points table exists
    try:
        has_calibration = conn.execute(text(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='calibration_points'"
        )).scalar() is not None
    except Exception:
        has_calibration = False

    for tilt in tilts_to_migrate:
        tilt_id = tilt[0]
        color = tilt[1]
        mac = tilt[2]
        beer_name = tilt[3]
        original_gravity = tilt[4]
        last_seen = tilt[5]

        # Calculate calibration offsets from CalibrationPoint table
        sg_offset = 0.0
        temp_offset = 0.0
        calibration_type = "none"

        if has_calibration:
            # Get SG calibration points for this tilt
            sg_points = conn.execute(text("""
                SELECT raw_value, actual_value FROM calibration_points
                WHERE tilt_id = :tilt_id AND type = 'sg'
                ORDER BY raw_value
            """), {"tilt_id": tilt_id}).fetchall()

            # Get temp calibration points for this tilt
            temp_points = conn.execute(text("""
                SELECT raw_value, actual_value FROM calibration_points
                WHERE tilt_id = :tilt_id AND type = 'temp'
                ORDER BY raw_value
            """), {"tilt_id": tilt_id}).fetchall()

            # Determine calibration type based on number of points
            # Use linear interpolation if 2+ points exist for either SG or temp
            has_multi_point = (len(sg_points) >= 2 or len(temp_points) >= 2)

            if has_multi_point:
                calibration_type = "linear"
            elif sg_points or temp_points:
                # Single point: calculate offset
                calibration_type = "offset"
                if sg_points:
                    sg_offset = sg_points[0][1] - sg_points[0][0]
                if temp_points:
                    temp_offset = temp_points[0][1] - temp_points[0][0]

        calibration_data = json.dumps({
            "sg_offset": round(sg_offset, 4),
            "temp_offset": round(temp_offset, 2),
            # Store full calibration points for linear interpolation
            "sg_points": [[p[0], p[1]] for p in sg_points] if has_calibration and sg_points else [],
            "temp_points": [[p[0], p[1]] for p in temp_points] if has_calibration and temp_points else [],
        })

        conn.execute(text("""
            INSERT INTO devices (
                id, device_type, name, color, mac, beer_name,
                original_gravity, calibration_type, calibration_data,
                last_seen, created_at
            ) VALUES (
                :id, 'tilt', :name, :color, :mac, :beer_name,
                :original_gravity, :calibration_type, :calibration_data,
                :last_seen, CURRENT_TIMESTAMP
            )
        """), {
            "id": tilt_id,
            "name": color or tilt_id,
            "color": color,
            "mac": mac,
            "beer_name": beer_name,
            "original_gravity": original_gravity,
            "calibration_type": calibration_type,
            "calibration_data": calibration_data,
            "last_seen": last_seen,
        })

    print(f"Migration: Migrated {len(tilts_to_migrate)} tilts to devices table (with calibration data)")


def _migrate_add_reading_columns(conn):
    """Add new columns to readings table for multi-hydrometer support."""
    from sqlalchemy import inspect, text
    inspector = inspect(conn)

    # Check if readings table exists
    if "readings" not in inspector.get_table_names():
        return  # Fresh install, create_all will handle it

    columns = [c["name"] for c in inspector.get_columns("readings")]

    new_columns = [
        ("device_id", "TEXT REFERENCES devices(id)"),
        ("device_type", "TEXT DEFAULT 'tilt'"),
        ("angle", "REAL"),
        ("battery_voltage", "REAL"),
        ("battery_percent", "INTEGER"),
        ("source_protocol", "TEXT DEFAULT 'ble'"),
        ("status", "TEXT DEFAULT 'valid'"),
        ("is_pre_filtered", "INTEGER DEFAULT 0"),
    ]

    for col_name, col_def in new_columns:
        if col_name not in columns:
            try:
                conn.execute(text(f"ALTER TABLE readings ADD COLUMN {col_name} {col_def}"))
                print(f"Migration: Added {col_name} column to readings table")
            except Exception as e:
                # Column might already exist in some edge cases
                print(f"Migration: Skipping {col_name} - {e}")

    # Create indexes if they don't exist
    try:
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_readings_device_id ON readings(device_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_readings_status ON readings(status)"))
    except Exception:
        pass  # Indexes might already exist


def _migrate_readings_nullable_tilt_id(conn):
    """Make tilt_id nullable in readings table for non-Tilt devices.

    SQLite doesn't support ALTER COLUMN, so we need to recreate the table.
    This migration checks if tilt_id is NOT NULL and recreates the table
    with tilt_id as nullable.
    """
    from sqlalchemy import inspect, text
    inspector = inspect(conn)

    if "readings" not in inspector.get_table_names():
        return  # Fresh install, create_all will handle it

    # Check if tilt_id is currently NOT NULL by looking at table info
    result = conn.execute(text("PRAGMA table_info(readings)"))
    columns_info = result.fetchall()

    # Find tilt_id column and check if it's NOT NULL (notnull=1)
    tilt_id_info = None
    for col in columns_info:
        if col[1] == "tilt_id":  # col[1] is column name
            tilt_id_info = col
            break

    if tilt_id_info is None:
        return  # No tilt_id column, nothing to migrate

    # col[3] is notnull flag (1 = NOT NULL, 0 = nullable)
    if tilt_id_info[3] == 0:
        print("Migration: tilt_id already nullable, skipping")
        return  # Already nullable

    print("Migration: Recreating readings table with nullable tilt_id...")

    # Step 1: Create new table with correct schema
    conn.execute(text("""
        CREATE TABLE readings_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tilt_id VARCHAR(50) REFERENCES tilts(id),
            device_id VARCHAR(100) REFERENCES devices(id),
            device_type VARCHAR(20) DEFAULT 'tilt',
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            sg_raw REAL,
            sg_calibrated REAL,
            temp_raw REAL,
            temp_calibrated REAL,
            rssi INTEGER,
            battery_voltage REAL,
            battery_percent INTEGER,
            angle REAL,
            source_protocol VARCHAR(20) DEFAULT 'ble',
            status VARCHAR(20) DEFAULT 'valid',
            is_pre_filtered INTEGER DEFAULT 0
        )
    """))

    # Step 2: Copy data from old table
    conn.execute(text("""
        INSERT INTO readings_new (
            id, tilt_id, device_id, device_type, timestamp,
            sg_raw, sg_calibrated, temp_raw, temp_calibrated, rssi,
            battery_voltage, battery_percent, angle,
            source_protocol, status, is_pre_filtered
        )
        SELECT
            id, tilt_id, device_id, device_type, timestamp,
            sg_raw, sg_calibrated, temp_raw, temp_calibrated, rssi,
            battery_voltage, battery_percent, angle,
            source_protocol, status, is_pre_filtered
        FROM readings
    """))

    # Step 3: Drop old table
    conn.execute(text("DROP TABLE readings"))

    # Step 4: Rename new table
    conn.execute(text("ALTER TABLE readings_new RENAME TO readings"))

    # Step 5: Recreate indexes
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_readings_tilt_timestamp ON readings(tilt_id, timestamp)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_readings_device_timestamp ON readings(device_id, timestamp)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_readings_timestamp ON readings(timestamp)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_readings_tilt_id ON readings(tilt_id)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_readings_device_id ON readings(device_id)"))

    print("Migration: Readings table recreated with nullable tilt_id")


def _migrate_add_batch_heater_columns(conn):
    """Add heater control columns to batches table if not present."""
    from sqlalchemy import inspect, text
    inspector = inspect(conn)

    if "batches" not in inspector.get_table_names():
        return  # Fresh install, create_all will handle it

    columns = [c["name"] for c in inspector.get_columns("batches")]

    new_columns = [
        ("heater_entity_id", "VARCHAR(100)"),
        ("temp_target", "REAL"),
        ("temp_hysteresis", "REAL"),
    ]

    for col_name, col_def in new_columns:
        if col_name not in columns:
            try:
                conn.execute(text(f"ALTER TABLE batches ADD COLUMN {col_name} {col_def}"))
                print(f"Migration: Added {col_name} column to batches table")
            except Exception as e:
                print(f"Migration: Skipping {col_name} - {e}")

    # Add composite index for efficient querying of fermenting batches with heaters
    indexes = [idx["name"] for idx in inspector.get_indexes("batches")]
    if "ix_batch_fermenting_heater" not in indexes:
        try:
            conn.execute(text(
                "CREATE INDEX ix_batch_fermenting_heater ON batches (status, heater_entity_id)"
            ))
            print("Migration: Added ix_batch_fermenting_heater index to batches table")
        except Exception as e:
            print(f"Migration: Skipping index creation - {e}")

    # Add partial unique index to prevent heater conflicts at database level
    if "idx_fermenting_heater_unique" not in indexes:
        try:
            conn.execute(text(
                "CREATE UNIQUE INDEX idx_fermenting_heater_unique "
                "ON batches (heater_entity_id) "
                "WHERE status = 'fermenting' AND heater_entity_id IS NOT NULL"
            ))
            print("Migration: Added unique constraint for fermenting batch heaters")
        except Exception as e:
            print(f"Migration: Skipping unique heater index creation - {e}")

    # Add partial unique index to prevent device conflicts at database level
    if "idx_fermenting_device_unique" not in indexes:
        try:
            conn.execute(text(
                "CREATE UNIQUE INDEX idx_fermenting_device_unique "
                "ON batches (device_id) "
                "WHERE status = 'fermenting' AND device_id IS NOT NULL"
            ))
            print("Migration: Added unique constraint for fermenting batch devices")
        except Exception as e:
            print(f"Migration: Skipping unique device index creation - {e}")


async def _migrate_add_cooler_entity():
    """Add cooler_entity_id column to batches table."""
    from sqlalchemy import text
    async with engine.begin() as conn:
        # Check if batches table exists
        result = await conn.execute(text(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='batches'"
        ))
        if not result.fetchone():
            return  # Fresh install, create_all will handle it

        # Check if column exists
        result = await conn.execute(text("PRAGMA table_info(batches)"))
        columns = {row[1] for row in result}

        if "cooler_entity_id" not in columns:
            await conn.execute(text(
                "ALTER TABLE batches ADD COLUMN cooler_entity_id VARCHAR(100)"
            ))
            print("Migration: Added cooler_entity_id column to batches table")


def _migrate_add_batch_id_to_control_events(conn):
    """Add batch_id column to control_events table if not present."""
    from sqlalchemy import inspect, text
    inspector = inspect(conn)

    if "control_events" not in inspector.get_table_names():
        return  # Fresh install, create_all will handle it

    columns = [c["name"] for c in inspector.get_columns("control_events")]

    if "batch_id" not in columns:
        try:
            conn.execute(text("ALTER TABLE control_events ADD COLUMN batch_id INTEGER"))
            print("Migration: Added batch_id column to control_events table")
        except Exception as e:
            print(f"Migration: Skipping batch_id column - {e}")


def _migrate_add_paired_to_tilts_and_devices(conn):
    """Add paired boolean field and paired_at timestamp to tilts and devices tables."""
    from sqlalchemy import inspect, text
    inspector = inspect(conn)

    # Migrate tilts table
    if "tilts" in inspector.get_table_names():
        columns = [c["name"] for c in inspector.get_columns("tilts")]
        if "paired" not in columns:
            conn.execute(text("ALTER TABLE tilts ADD COLUMN paired INTEGER DEFAULT 0"))
            print("Migration: Added paired column to tilts table")
        if "paired_at" not in columns:
            conn.execute(text("ALTER TABLE tilts ADD COLUMN paired_at TIMESTAMP"))
            print("Migration: Added paired_at column to tilts table")

        # Create index on paired field
        indexes = [idx["name"] for idx in inspector.get_indexes("tilts")]
        if "ix_tilts_paired" not in indexes:
            conn.execute(text("CREATE INDEX ix_tilts_paired ON tilts (paired)"))
            print("Migration: Added index on tilts.paired")

    # Migrate devices table
    if "devices" in inspector.get_table_names():
        columns = [c["name"] for c in inspector.get_columns("devices")]
        if "paired" not in columns:
            conn.execute(text("ALTER TABLE devices ADD COLUMN paired INTEGER DEFAULT 0"))
            print("Migration: Added paired column to devices table")
        if "paired_at" not in columns:
            conn.execute(text("ALTER TABLE devices ADD COLUMN paired_at TIMESTAMP"))
            print("Migration: Added paired_at column to devices table")

        # Create index on paired field
        indexes = [idx["name"] for idx in inspector.get_indexes("devices")]
        if "ix_devices_paired" not in indexes:
            conn.execute(text("CREATE INDEX ix_devices_paired ON devices (paired)"))
            print("Migration: Added index on devices.paired")


def _migrate_create_recipe_fermentables_table(conn):
    """Create recipe_fermentables table if it doesn't exist."""
    from sqlalchemy import inspect, text
    inspector = inspect(conn)

    if "recipe_fermentables" in inspector.get_table_names():
        return  # Table exists

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS recipe_fermentables (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recipe_id INTEGER NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
            name VARCHAR(100) NOT NULL,
            type VARCHAR(50),
            amount_kg REAL,
            yield_percent REAL,
            color_lovibond REAL,
            origin VARCHAR(50),
            supplier VARCHAR(100),
            notes TEXT,
            add_after_boil INTEGER DEFAULT 0,
            coarse_fine_diff REAL,
            moisture REAL,
            diastatic_power REAL,
            protein REAL,
            max_in_batch REAL,
            recommend_mash INTEGER
        )
    """))

    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_fermentables_recipe ON recipe_fermentables(recipe_id)"))
    print("Migration: Created recipe_fermentables table")


def _migrate_create_recipe_hops_table(conn):
    """Create recipe_hops table if it doesn't exist."""
    from sqlalchemy import inspect, text
    inspector = inspect(conn)

    if "recipe_hops" in inspector.get_table_names():
        return

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS recipe_hops (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recipe_id INTEGER NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
            name VARCHAR(100) NOT NULL,
            alpha_percent REAL,
            amount_kg REAL NOT NULL,
            use VARCHAR(20) NOT NULL,
            time_min REAL,
            form VARCHAR(20),
            type VARCHAR(20),
            origin VARCHAR(50),
            substitutes VARCHAR(200),
            beta_percent REAL,
            hsi REAL,
            humulene REAL,
            caryophyllene REAL,
            cohumulone REAL,
            myrcene REAL,
            notes TEXT
        )
    """))

    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_hops_recipe ON recipe_hops(recipe_id)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_hops_use ON recipe_hops(use)"))  # For dry hop queries
    print("Migration: Created recipe_hops table")


def _migrate_create_recipe_yeasts_table(conn):
    """Create recipe_yeasts table if it doesn't exist."""
    from sqlalchemy import inspect, text
    inspector = inspect(conn)

    if "recipe_yeasts" in inspector.get_table_names():
        return

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS recipe_yeasts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recipe_id INTEGER NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
            name VARCHAR(100) NOT NULL,
            lab VARCHAR(100),
            product_id VARCHAR(50),
            type VARCHAR(20),
            form VARCHAR(20),
            attenuation_percent REAL,
            temp_min_c REAL,
            temp_max_c REAL,
            flocculation VARCHAR(20),
            amount_l REAL,
            amount_kg REAL,
            add_to_secondary INTEGER DEFAULT 0,
            best_for TEXT,
            times_cultured INTEGER,
            max_reuse INTEGER,
            notes TEXT
        )
    """))

    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_yeasts_recipe ON recipe_yeasts(recipe_id)"))
    print("Migration: Created recipe_yeasts table")


def _migrate_create_recipe_miscs_table(conn):
    """Create recipe_miscs table if it doesn't exist."""
    from sqlalchemy import inspect, text
    inspector = inspect(conn)

    if "recipe_miscs" in inspector.get_table_names():
        return

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS recipe_miscs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recipe_id INTEGER NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
            name VARCHAR(100) NOT NULL,
            type VARCHAR(50) NOT NULL,
            use VARCHAR(20) NOT NULL,
            time_min REAL,
            amount_kg REAL,
            amount_is_weight INTEGER DEFAULT 1,
            use_for TEXT,
            notes TEXT
        )
    """))

    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_miscs_recipe ON recipe_miscs(recipe_id)"))
    print("Migration: Created recipe_miscs table")


def _migrate_add_recipe_expanded_fields(conn):
    """Add expanded BeerXML fields to recipes table."""
    from sqlalchemy import inspect, text
    inspector = inspect(conn)

    if "recipes" not in inspector.get_table_names():
        return

    columns = [c["name"] for c in inspector.get_columns("recipes")]

    new_columns = [
        ("brewer", "VARCHAR(100)"),
        ("asst_brewer", "VARCHAR(100)"),
        ("boil_size_l", "REAL"),
        ("boil_time_min", "INTEGER"),
        ("efficiency_percent", "REAL"),
        ("primary_age_days", "INTEGER"),
        ("primary_temp_c", "REAL"),
        ("secondary_age_days", "INTEGER"),
        ("secondary_temp_c", "REAL"),
        ("tertiary_age_days", "INTEGER"),
        ("tertiary_temp_c", "REAL"),
        ("age_days", "INTEGER"),
        ("age_temp_c", "REAL"),
        ("carbonation_vols", "REAL"),
        ("forced_carbonation", "INTEGER"),
        ("priming_sugar_name", "VARCHAR(50)"),
        ("priming_sugar_amount_kg", "REAL"),
        ("taste_notes", "TEXT"),
        ("taste_rating", "REAL"),
        ("date", "VARCHAR(50)"),
    ]

    for col_name, col_def in new_columns:
        if col_name not in columns:
            conn.execute(text(f"ALTER TABLE recipes ADD COLUMN {col_name} {col_def}"))

    print("Migration: Added expanded BeerXML fields to recipes table")


def _migrate_mark_outliers_invalid(conn):
    """Mark historical outlier readings as invalid.

    This migration finds existing readings with physically impossible values
    and marks them as invalid so they're filtered from charts.

    Valid ranges:
    - SG: 0.500-1.200 (beer is typically 1.000-1.120)
    - Temp: 0-100°C (freezing to boiling)
    """
    from sqlalchemy import inspect, text
    inspector = inspect(conn)

    if "readings" not in inspector.get_table_names():
        return

    columns = [c["name"] for c in inspector.get_columns("readings")]
    if "status" not in columns:
        return  # Status column doesn't exist yet, skip

    # Mark SG outliers
    result = conn.execute(text("""
        UPDATE readings
        SET status = 'invalid'
        WHERE status = 'valid'
        AND (sg_calibrated < 0.500 OR sg_calibrated > 1.200)
    """))
    sg_count = result.rowcount

    # Mark temperature outliers (Celsius range: 0-100°C)
    result = conn.execute(text("""
        UPDATE readings
        SET status = 'invalid'
        WHERE status = 'valid'
        AND (temp_calibrated < 0.0 OR temp_calibrated > 100.0)
    """))
    temp_count = result.rowcount

    total = sg_count + temp_count
    if total > 0:
        print(f"Migration: Marked {total} outlier readings as invalid ({sg_count} SG, {temp_count} temp)")


def _migrate_fix_temp_outlier_detection(conn):
    """Fix readings incorrectly marked invalid by Fahrenheit temp check.

    After the F→C migration, the outlier detection was still using Fahrenheit
    ranges (32-212°F) against Celsius data, incorrectly marking valid readings
    as invalid. This migration restores readings that have valid Celsius temps
    (0-100°C) and valid SG (0.5-1.2).
    """
    from sqlalchemy import inspect, text
    inspector = inspect(conn)

    if "readings" not in inspector.get_table_names():
        return

    columns = [c["name"] for c in inspector.get_columns("readings")]
    if "status" not in columns:
        return

    # Fix readings that are invalid but have valid Celsius temps and valid SG
    result = conn.execute(text("""
        UPDATE readings
        SET status = 'valid'
        WHERE status = 'invalid'
        AND temp_calibrated >= 0.0 AND temp_calibrated <= 100.0
        AND sg_calibrated >= 0.500 AND sg_calibrated <= 1.200
    """))
    fixed_count = result.rowcount

    if fixed_count > 0:
        print(f"Migration: Fixed {fixed_count} readings incorrectly marked invalid by F→C temp check")


def _migrate_add_deleted_at(conn):
    """Add deleted_at column to batches table and migrate archived status."""
    from sqlalchemy import inspect, text
    inspector = inspect(conn)

    if "batches" not in inspector.get_table_names():
        return  # Fresh install, create_all will handle it

    columns = [c["name"] for c in inspector.get_columns("batches")]

    if "deleted_at" not in columns:
        print("Migration: Adding deleted_at column to batches table")
        conn.execute(text("ALTER TABLE batches ADD COLUMN deleted_at TIMESTAMP"))

        # Migrate any 'archived' status to 'completed'
        result = conn.execute(
            text("UPDATE batches SET status = 'completed' WHERE status = 'archived'")
        )
        updated = result.rowcount
        if updated > 0:
            print(f"Migration: Migrated {updated} batches from 'archived' to 'completed' status")

        print("Migration: deleted_at column added successfully")
    else:
        print("Migration: deleted_at column already exists, skipping")


def _migrate_add_deleted_at_index(conn):
    """Add index on deleted_at column for better query performance."""
    from sqlalchemy import inspect, text
    inspector = inspect(conn)

    if "batches" not in inspector.get_table_names():
        return  # Fresh install, create_all will handle it

    # Check if index already exists
    indexes = inspector.get_indexes("batches")
    index_names = [idx["name"] for idx in indexes]

    if "ix_batches_deleted_at" not in index_names:
        print("Migration: Adding index on deleted_at column")
        conn.execute(text("CREATE INDEX ix_batches_deleted_at ON batches (deleted_at)"))
        print("Migration: deleted_at index added successfully")
    else:
        print("Migration: deleted_at index already exists, skipping")


def _migrate_tilts_to_devices_final(conn):
    """Final migration: Consolidate Tilt table into Device table.

    This migration:
    1. Copies all Tilt records to Device table (if not already there)
    2. Updates foreign keys: tilt_id -> device_id in readings and calibration_points
    3. Drops the legacy tilts table

    Idempotent: Can run multiple times safely.

    Error handling: This function is called within engine.begin() transaction context,
    so any exception will automatically trigger a rollback, leaving the database
    in its pre-migration state.
    """
    from sqlalchemy import inspect, text
    import logging
    logger = logging.getLogger(__name__)

    inspector = inspect(conn)

    # Check if tilts table exists
    if "tilts" not in inspector.get_table_names():
        print("Migration: tilts table already migrated")
        return

    print("Migration: Starting Tilt -> Device consolidation")

    try:

        # Step 1: Migrate Tilt data to Device table
        # Uses INSERT OR IGNORE to handle devices that already exist (from PR #73)
        result = conn.execute(text("""
            INSERT OR IGNORE INTO devices (
                id, device_type, name, display_name, beer_name, original_gravity,
                native_gravity_unit, native_temp_unit, calibration_type, calibration_data,
                mac, color, last_seen, paired, paired_at, created_at
            )
            SELECT
                id,
                'tilt' as device_type,
                color as name,
                NULL as display_name,
                beer_name,
                original_gravity,
                'sg' as native_gravity_unit,
                'c' as native_temp_unit,
                'linear' as calibration_type,
                '{"sg_offset": 0.0, "temp_offset": 0.0, "sg_points": [], "temp_points": []}' as calibration_data,
                mac,
                color,
                last_seen,
                paired,
                paired_at,
                CURRENT_TIMESTAMP as created_at
            FROM tilts
        """))
        migrated_count = result.rowcount
        print(f"Migration: Copied {migrated_count} Tilt records to Device table")

        # Step 2: Update foreign keys in readings table
        # Check if column needs renaming or migrating
        readings_columns = [c["name"] for c in inspector.get_columns("readings")]
        if "tilt_id" in readings_columns:
            if "device_id" in readings_columns:
                # Both columns exist - copy tilt_id to device_id where device_id is NULL
                print("Migration: Copying tilt_id to device_id in readings table")
                conn.execute(text("""
                    UPDATE readings
                    SET device_id = tilt_id
                    WHERE device_id IS NULL AND tilt_id IS NOT NULL
                """))
                # Now drop the tilt_id column by recreating the table
                print("Migration: Dropping tilt_id column from readings table")
                # Get all columns except tilt_id
                all_columns = [c["name"] for c in inspector.get_columns("readings")]
                columns_to_keep = [c for c in all_columns if c != "tilt_id"]
                columns_str = ", ".join(columns_to_keep)

                # Recreate table without tilt_id - match exact column order from original table
                conn.execute(text("""
                    CREATE TABLE readings_new (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        device_id VARCHAR(100),
                        batch_id INTEGER,
                        device_type VARCHAR(20) DEFAULT 'tilt',
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                        sg_raw FLOAT,
                        sg_calibrated FLOAT,
                        temp_raw FLOAT,
                        temp_calibrated FLOAT,
                        rssi INTEGER,
                        battery_voltage FLOAT,
                        battery_percent INTEGER,
                        angle FLOAT,
                        source_protocol VARCHAR(20) DEFAULT 'ble',
                        status VARCHAR(20) DEFAULT 'valid',
                        is_pre_filtered INTEGER DEFAULT 0,
                        sg_filtered FLOAT,
                        temp_filtered FLOAT,
                        confidence FLOAT,
                        sg_rate FLOAT,
                        temp_rate FLOAT,
                        is_anomaly INTEGER DEFAULT 0,
                        anomaly_score FLOAT,
                        anomaly_reasons TEXT,
                        FOREIGN KEY(device_id) REFERENCES devices(id),
                        FOREIGN KEY(batch_id) REFERENCES batches(id)
                    )
                """))
                # Use explicit column list in same order
                conn.execute(text(f"INSERT INTO readings_new ({columns_str}) SELECT {columns_str} FROM readings"))
                conn.execute(text("DROP TABLE readings"))
                conn.execute(text("ALTER TABLE readings_new RENAME TO readings"))
                # Recreate indexes
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_readings_device_id ON readings(device_id)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_readings_timestamp ON readings(timestamp)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_readings_batch_id ON readings(batch_id)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_readings_batch_timestamp ON readings(batch_id, timestamp)"))
                print("Migration: Dropped tilt_id column from readings table")
            else:
                # Only tilt_id exists - rename it to device_id
                version_result = conn.execute(text("SELECT sqlite_version()"))
                sqlite_version = version_result.scalar()
                major, minor, _ = sqlite_version.split('.')

                if int(major) >= 3 and int(minor) >= 25:
                    # SQLite 3.25+ supports ALTER TABLE RENAME COLUMN
                    conn.execute(text("ALTER TABLE readings RENAME COLUMN tilt_id TO device_id"))
                    print("Migration: Renamed readings.tilt_id to device_id")
                else:
                    # Older SQLite: recreate table
                    print("Migration: Recreating readings table with device_id column")
                    conn.execute(text("""
                        CREATE TABLE readings_new (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            device_id VARCHAR(100),
                            batch_id INTEGER,
                            device_type VARCHAR(20) DEFAULT 'tilt',
                            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                            sg_raw FLOAT,
                            sg_calibrated FLOAT,
                            temp_raw FLOAT,
                            temp_calibrated FLOAT,
                            rssi INTEGER,
                            battery_voltage FLOAT,
                            battery_percent INTEGER,
                            angle FLOAT,
                            source_protocol VARCHAR(20) DEFAULT 'ble',
                            status VARCHAR(20) DEFAULT 'valid',
                            is_pre_filtered INTEGER DEFAULT 0,
                            sg_filtered FLOAT,
                            temp_filtered FLOAT,
                            confidence FLOAT,
                            sg_rate FLOAT,
                            temp_rate FLOAT,
                            is_anomaly INTEGER DEFAULT 0,
                            anomaly_score FLOAT,
                            anomaly_reasons TEXT,
                            FOREIGN KEY(device_id) REFERENCES devices(id),
                            FOREIGN KEY(batch_id) REFERENCES batches(id)
                        )
                    """))
                    conn.execute(text("INSERT INTO readings_new SELECT * FROM readings"))
                    conn.execute(text("DROP TABLE readings"))
                    conn.execute(text("ALTER TABLE readings_new RENAME TO readings"))
                    # Recreate indexes
                    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_readings_device_id ON readings(device_id)"))
                    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_readings_timestamp ON readings(timestamp)"))
                    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_readings_batch_id ON readings(batch_id)"))
                    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_readings_batch_timestamp ON readings(batch_id, timestamp)"))
                    print("Migration: Recreated readings table with device_id")

        # Step 3: Update foreign keys in calibration_points table
        calibration_columns = [c["name"] for c in inspector.get_columns("calibration_points")]
        if "tilt_id" in calibration_columns:
            if "device_id" in calibration_columns:
                # Both columns exist - copy tilt_id to device_id where device_id is NULL
                print("Migration: Copying tilt_id to device_id in calibration_points table")
                conn.execute(text("""
                    UPDATE calibration_points
                    SET device_id = tilt_id
                    WHERE device_id IS NULL AND tilt_id IS NOT NULL
                """))
                # Now drop the tilt_id column by recreating the table
                print("Migration: Dropping tilt_id column from calibration_points table")
                # Get all columns except tilt_id
                all_columns = [c["name"] for c in inspector.get_columns("calibration_points")]
                columns_to_keep = [c for c in all_columns if c != "tilt_id"]
                columns_str = ", ".join(columns_to_keep)

                # Recreate table without tilt_id
                conn.execute(text("""
                    CREATE TABLE calibration_points_new (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        device_id VARCHAR(100) NOT NULL,
                        type VARCHAR(20) NOT NULL,
                        raw_value FLOAT NOT NULL,
                        actual_value FLOAT NOT NULL,
                        created_at DATETIME NOT NULL,
                        FOREIGN KEY(device_id) REFERENCES devices(id) ON DELETE CASCADE
                    )
                """))
                conn.execute(text(f"INSERT INTO calibration_points_new SELECT {columns_str} FROM calibration_points"))
                conn.execute(text("DROP TABLE calibration_points"))
                conn.execute(text("ALTER TABLE calibration_points_new RENAME TO calibration_points"))
                # Recreate indexes
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_calibration_points_device_id ON calibration_points(device_id)"))
                print("Migration: Dropped tilt_id column from calibration_points table")
            else:
                # Only tilt_id exists - rename it to device_id
                version_result = conn.execute(text("SELECT sqlite_version()"))
                sqlite_version = version_result.scalar()
                major, minor, _ = sqlite_version.split('.')

                if int(major) >= 3 and int(minor) >= 25:
                    conn.execute(text("ALTER TABLE calibration_points RENAME COLUMN tilt_id TO device_id"))
                    # Drop old index and create new one with correct name
                    conn.execute(text("DROP INDEX IF EXISTS ix_calibration_points_tilt_id"))
                    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_calibration_points_device_id ON calibration_points(device_id)"))
                    print("Migration: Renamed calibration_points.tilt_id to device_id")
                else:
                    print("Migration: Recreating calibration_points table with device_id column")
                    conn.execute(text("""
                        CREATE TABLE calibration_points_new (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            device_id VARCHAR(100) NOT NULL,
                            type VARCHAR(20) NOT NULL,
                            raw_value FLOAT NOT NULL,
                            actual_value FLOAT NOT NULL,
                            created_at DATETIME NOT NULL,
                            FOREIGN KEY(device_id) REFERENCES devices(id) ON DELETE CASCADE
                        )
                    """))
                    conn.execute(text("INSERT INTO calibration_points_new SELECT * FROM calibration_points"))
                    conn.execute(text("DROP TABLE calibration_points"))
                    conn.execute(text("ALTER TABLE calibration_points_new RENAME TO calibration_points"))
                    # Recreate indexes
                    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_calibration_points_device_id ON calibration_points(device_id)"))
                    print("Migration: Recreated calibration_points table with device_id")

        # Step 4: Drop tilts table
        conn.execute(text("DROP TABLE tilts"))
        print("Migration: Dropped tilts table - migration complete!")

    except Exception as e:
        # Log the error - transaction will automatically rollback
        logger.error(f"Migration failed during Tilt->Device consolidation: {e}")
        logger.error("Transaction will be rolled back. Database remains in pre-migration state.")
        raise  # Re-raise to trigger rollback


def _migrate_control_events_tilt_id_to_device_id(conn):
    """Rename tilt_id column to device_id in control_events table."""
    from sqlalchemy import inspect, text
    inspector = inspect(conn)

    if "control_events" not in inspector.get_table_names():
        return  # Fresh install, create_all will handle it

    columns = [c["name"] for c in inspector.get_columns("control_events")]

    if "tilt_id" not in columns:
        return  # Already migrated or fresh install

    print("Migration: Renaming control_events.tilt_id to device_id")

    # Check SQLite version for RENAME COLUMN support
    version_result = conn.execute(text("SELECT sqlite_version()"))
    sqlite_version = version_result.scalar()
    major, minor, _ = sqlite_version.split('.')

    if int(major) >= 3 and int(minor) >= 25:
        # SQLite 3.25+ supports ALTER TABLE RENAME COLUMN
        conn.execute(text("ALTER TABLE control_events RENAME COLUMN tilt_id TO device_id"))
        print("Migration: Renamed control_events.tilt_id to device_id")
    else:
        # Older SQLite - recreate table
        print("Migration: Recreating control_events table with device_id column")
        conn.execute(text("""
            CREATE TABLE control_events_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                device_id VARCHAR(100),
                batch_id INTEGER,
                action VARCHAR(20),
                wort_temp FLOAT,
                ambient_temp FLOAT,
                target_temp FLOAT,
                FOREIGN KEY(device_id) REFERENCES devices(id),
                FOREIGN KEY(batch_id) REFERENCES batches(id)
            )
        """))
        conn.execute(text("""
            INSERT INTO control_events_new (id, timestamp, device_id, batch_id, action, wort_temp, ambient_temp, target_temp)
            SELECT id, timestamp, tilt_id, batch_id, action, wort_temp, ambient_temp, target_temp FROM control_events
        """))
        conn.execute(text("DROP TABLE control_events"))
        conn.execute(text("ALTER TABLE control_events_new RENAME TO control_events"))
        # Recreate index
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_control_timestamp ON control_events(timestamp)"))
        print("Migration: Recreated control_events table with device_id")


def _migrate_create_yeast_strains_table(conn):
    """Create yeast_strains table if it doesn't exist."""
    from sqlalchemy import inspect, text
    inspector = inspect(conn)

    if "yeast_strains" in inspector.get_table_names():
        return  # Table exists

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS yeast_strains (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name VARCHAR(200) NOT NULL,
            producer VARCHAR(100),
            product_id VARCHAR(50),
            type VARCHAR(20),
            form VARCHAR(20),
            attenuation_low REAL,
            attenuation_high REAL,
            temp_low REAL,
            temp_high REAL,
            alcohol_tolerance REAL,
            flocculation VARCHAR(20),
            description TEXT,
            source VARCHAR(50) DEFAULT 'custom',
            is_custom INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_yeast_strains_producer_product ON yeast_strains(producer, product_id)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_yeast_strains_type ON yeast_strains(type)"))
    print("Migration: Created yeast_strains table")


def _migrate_add_yeast_strain_to_batches(conn):
    """Add yeast_strain_id column to batches table."""
    from sqlalchemy import inspect, text
    inspector = inspect(conn)

    if "batches" not in inspector.get_table_names():
        return  # Fresh install, create_all will handle it

    columns = [c["name"] for c in inspector.get_columns("batches")]
    if "yeast_strain_id" not in columns:
        conn.execute(text("ALTER TABLE batches ADD COLUMN yeast_strain_id INTEGER REFERENCES yeast_strains(id)"))
        print("Migration: Added yeast_strain_id column to batches table")


def _migrate_yeast_strains_alcohol_tolerance(conn):
    """Migrate alcohol_tolerance column from REAL to TEXT.

    SQLite doesn't support ALTER COLUMN, so we drop and recreate the table.
    All data will be re-seeded from the JSON file anyway.
    """
    from sqlalchemy import inspect, text
    inspector = inspect(conn)

    if "yeast_strains" not in inspector.get_table_names():
        return  # Fresh install, create_all will handle it

    # Check if alcohol_tolerance column type needs migration
    columns = {c["name"]: c for c in inspector.get_columns("yeast_strains")}
    if "alcohol_tolerance" not in columns:
        return  # Column doesn't exist, create_all will handle it

    # Check the column type - if it's REAL, we need to migrate
    col_type = str(columns["alcohol_tolerance"]["type"]).upper()
    if "REAL" in col_type or "FLOAT" in col_type or "NUMERIC" in col_type:
        # Clear yeast_strain_id references on batches before dropping
        # (IDs will change after re-seeding, so old references would be wrong)
        if "batches" in inspector.get_table_names():
            batch_cols = [c["name"] for c in inspector.get_columns("batches")]
            if "yeast_strain_id" in batch_cols:
                conn.execute(text("UPDATE batches SET yeast_strain_id = NULL"))
                print("Migration: Cleared yeast_strain_id references on batches")

        # Drop the table - it will be recreated by create_all() with correct schema
        # and then re-seeded from the JSON file
        conn.execute(text("DROP TABLE yeast_strains"))
        print("Migration: Dropped yeast_strains table for schema update (alcohol_tolerance REAL -> TEXT)")


def _migrate_add_style_comments_column(conn):
    """Add comments column to styles table for alias searching (e.g., NEIPA -> Hazy IPA)."""
    from sqlalchemy import inspect, text
    inspector = inspect(conn)

    if "styles" not in inspector.get_table_names():
        return  # Fresh install, create_all will handle it

    columns = [c["name"] for c in inspector.get_columns("styles")]
    if "comments" not in columns:
        conn.execute(text("ALTER TABLE styles ADD COLUMN comments TEXT"))
        print("Migration: Added comments column to styles table")
        # Return True to signal that styles need re-seeding
        return True
    return False


def _migrate_add_ag_ui_thread_title_locked(conn):
    """Add title_locked column to ag_ui_threads table to prevent auto-summarization overwrites."""
    from sqlalchemy import inspect, text
    inspector = inspect(conn)

    if "ag_ui_threads" not in inspector.get_table_names():
        return  # Fresh install, create_all will handle it

    columns = [c["name"] for c in inspector.get_columns("ag_ui_threads")]
    if "title_locked" not in columns:
        conn.execute(text("ALTER TABLE ag_ui_threads ADD COLUMN title_locked INTEGER DEFAULT 0"))
        print("Migration: Added title_locked column to ag_ui_threads table")


def _migrate_add_batch_phase_timestamps(conn):
    """Add phase timestamp columns to batches table for lifecycle tracking.

    These columns track when each phase of the brewing lifecycle started:
    - brewing_started_at: When brew day began
    - fermenting_started_at: When fermentation started (distinct from legacy start_time)
    - conditioning_started_at: When conditioning/aging began
    - completed_at: When the batch was marked complete
    """
    from sqlalchemy import inspect, text
    inspector = inspect(conn)

    if "batches" not in inspector.get_table_names():
        return  # Fresh install, create_all will handle it

    columns = [c["name"] for c in inspector.get_columns("batches")]

    new_columns = [
        ("brewing_started_at", "TIMESTAMP"),
        ("fermenting_started_at", "TIMESTAMP"),
        ("conditioning_started_at", "TIMESTAMP"),
        ("completed_at", "TIMESTAMP"),
    ]

    added = []
    for col_name, col_def in new_columns:
        if col_name not in columns:
            try:
                conn.execute(text(f"ALTER TABLE batches ADD COLUMN {col_name} {col_def}"))
                added.append(col_name)
            except Exception as e:
                print(f"Migration: Skipping {col_name} - {e}")

    if added:
        print(f"Migration: Added batch phase columns: {', '.join(added)}")


def _migrate_add_brew_day_observations(conn):
    """Add brew day observation columns to batches table.

    These columns track actual measurements during brew day:
    - actual_mash_temp: Actual mash temperature achieved (Celsius)
    - actual_mash_ph: Mash pH reading
    - strike_water_volume: Strike water volume (Liters)
    - pre_boil_gravity: Gravity before boil (SG)
    - pre_boil_volume: Volume before boil (Liters)
    - post_boil_volume: Volume after boil (Liters)
    - actual_efficiency: Calculated brewhouse efficiency (%)
    - brew_day_notes: Specific brew day notes
    """
    from sqlalchemy import inspect, text
    inspector = inspect(conn)

    if "batches" not in inspector.get_table_names():
        return  # Fresh install, create_all will handle it

    columns = [c["name"] for c in inspector.get_columns("batches")]

    new_columns = [
        ("actual_mash_temp", "REAL"),
        ("actual_mash_ph", "REAL"),
        ("strike_water_volume", "REAL"),
        ("pre_boil_gravity", "REAL"),
        ("pre_boil_volume", "REAL"),
        ("post_boil_volume", "REAL"),
        ("actual_efficiency", "REAL"),
        ("brew_day_notes", "TEXT"),
    ]

    added = []
    for col_name, col_def in new_columns:
        if col_name not in columns:
            try:
                conn.execute(text(f"ALTER TABLE batches ADD COLUMN {col_name} {col_def}"))
                added.append(col_name)
            except Exception as e:
                print(f"Migration: Skipping {col_name} - {e}")

    if added:
        print(f"Migration: Added brew day observation columns: {', '.join(added)}")


def _migrate_add_packaging_columns(conn):
    """Add packaging info columns to batches table.

    These columns track packaging details for completed batches:
    - packaged_at: When the batch was packaged
    - packaging_type: Type of packaging (bottles, keg, cans)
    - packaging_volume: Total volume packaged (Liters)
    - carbonation_method: How carbonation is achieved
    - priming_sugar_type: Type of priming sugar used
    - priming_sugar_amount: Amount of priming sugar (grams)
    - packaging_notes: Additional packaging notes
    """
    from sqlalchemy import inspect, text
    inspector = inspect(conn)

    if "batches" not in inspector.get_table_names():
        return  # Fresh install, create_all will handle it

    columns = [c["name"] for c in inspector.get_columns("batches")]

    new_columns = [
        ("packaged_at", "TIMESTAMP"),
        ("packaging_type", "VARCHAR(20)"),
        ("packaging_volume", "REAL"),
        ("carbonation_method", "VARCHAR(30)"),
        ("priming_sugar_type", "VARCHAR(50)"),
        ("priming_sugar_amount", "REAL"),
        ("packaging_notes", "TEXT"),
    ]

    added = []
    for col_name, col_def in new_columns:
        if col_name not in columns:
            try:
                conn.execute(text(f"ALTER TABLE batches ADD COLUMN {col_name} {col_def}"))
                added.append(col_name)
            except Exception as e:
                print(f"Migration: Skipping {col_name} - {e}")

    if added:
        print(f"Migration: Added packaging columns: {', '.join(added)}")


def _migrate_create_tasting_notes_table(conn):
    """Create tasting_notes table for storing multiple tasting entries per batch."""
    from sqlalchemy import inspect, text
    inspector = inspect(conn)

    if "tasting_notes" in inspector.get_table_names():
        return  # Table already exists

    conn.execute(text("""
        CREATE TABLE tasting_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id INTEGER NOT NULL REFERENCES batches(id) ON DELETE CASCADE,
            tasted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            appearance_score INTEGER,
            appearance_notes TEXT,
            aroma_score INTEGER,
            aroma_notes TEXT,
            flavor_score INTEGER,
            flavor_notes TEXT,
            mouthfeel_score INTEGER,
            mouthfeel_notes TEXT,
            overall_score INTEGER,
            overall_notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """))
    print("Migration: Created tasting_notes table")


def _migrate_add_batch_timer_columns(conn):
    """Add brew day timer state columns to batches table.

    These columns persist timer state for multi-device sync:
    - timer_phase: Current timer phase (idle, mash, boil, complete)
    - timer_started_at: When the current timer was started
    - timer_duration_seconds: Total duration for the current phase
    - timer_paused_at: When the timer was paused (null if running)
    """
    from sqlalchemy import inspect, text
    inspector = inspect(conn)

    if "batches" not in inspector.get_table_names():
        return  # Fresh install, create_all will handle it

    columns = [c["name"] for c in inspector.get_columns("batches")]

    new_columns = [
        ("timer_phase", "VARCHAR(20)"),
        ("timer_started_at", "TIMESTAMP"),
        ("timer_duration_seconds", "INTEGER"),
        ("timer_paused_at", "TIMESTAMP"),
    ]

    added = []
    for col_name, col_type in new_columns:
        if col_name not in columns:
            try:
                conn.execute(text(f"ALTER TABLE batches ADD COLUMN {col_name} {col_type}"))
                added.append(col_name)
            except Exception as e:
                print(f"Migration: Skipping {col_name} - {e}")

    if added:
        print(f"Migration: Added batch timer columns: {', '.join(added)}")


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        yield session
