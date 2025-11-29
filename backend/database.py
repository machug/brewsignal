from pathlib import Path
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncAttrs, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

DATA_DIR = Path(__file__).parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)

DATABASE_URL = f"sqlite+aiosqlite:///{DATA_DIR}/tiltui.db"

engine = create_async_engine(DATABASE_URL, echo=False)
async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


class Base(AsyncAttrs, DeclarativeBase):
    pass


async def init_db():
    """Initialize database with migrations.

    Order matters:
    1. Run migrations first (for existing DBs with data)
    2. Then create_all (for new tables/columns in fresh DBs)
    3. Then data migrations (copy tilts to devices)
    """
    async with engine.begin() as conn:
        # Step 1: Schema migrations for existing DBs
        await conn.run_sync(_migrate_add_original_gravity)
        await conn.run_sync(_migrate_create_devices_table)
        await conn.run_sync(_migrate_add_reading_columns)

        # Step 2: Create any missing tables (fresh install or new models)
        # NOTE: Device model should be imported AFTER migrations for existing DBs
        await conn.run_sync(Base.metadata.create_all)

        # Step 3: Data migrations (requires both tables to exist)
        await conn.run_sync(_migrate_tilts_to_devices)


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
    """Migrate existing tilts to devices table if not already done."""
    from sqlalchemy import text

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

    # Migrate tilts that aren't in devices yet
    # Build calibration_data as JSON string manually (portable, no json_object)
    conn.execute(text("""
        INSERT OR IGNORE INTO devices (
            id, device_type, name, color, mac, beer_name,
            original_gravity, calibration_type, calibration_data,
            last_seen, created_at
        )
        SELECT
            id,
            'tilt',
            COALESCE(color, id),
            color,
            mac,
            beer_name,
            original_gravity,
            'offset',
            '{"sg_offset": 0, "temp_offset": 0}',
            last_seen,
            CURRENT_TIMESTAMP
        FROM tilts
        WHERE id NOT IN (SELECT id FROM devices)
    """))
    print(f"Migration: Migrated {tilt_count - migrated_count} tilts to devices table")


def _migrate_add_reading_columns(conn):
    """Add new columns to readings table for multi-hydrometer support."""
    from sqlalchemy import inspect, text
    inspector = inspect(conn)

    # Check if readings table exists
    if "readings" not in inspector.get_table_names():
        return  # Fresh install, create_all will handle it

    columns = [c["name"] for c in inspector.get_columns("readings")]

    new_columns = [
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


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        yield session
