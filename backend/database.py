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
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Migration: add original_gravity column if it doesn't exist
        await conn.run_sync(_migrate_add_original_gravity)


def _migrate_add_original_gravity(conn):
    """Add original_gravity column to tilts table if not present."""
    from sqlalchemy import inspect, text
    inspector = inspect(conn)
    columns = [c["name"] for c in inspector.get_columns("tilts")]
    if "original_gravity" not in columns:
        conn.execute(text("ALTER TABLE tilts ADD COLUMN original_gravity REAL"))
        print("Migration: Added original_gravity column to tilts table")


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        yield session
