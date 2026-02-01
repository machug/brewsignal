"""Pytest configuration for backend tests."""

import asyncio
import os
import sys
from pathlib import Path
from typing import AsyncGenerator, Generator

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

# Force LOCAL deployment mode for tests BEFORE importing backend modules
# This ensures require_auth returns dummy "local" user instead of requiring JWT
os.environ["DEPLOYMENT_MODE"] = "local"

# Ensure backend package is importable
backend_path = Path(__file__).parent.parent.parent
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

from backend.database import Base  # noqa: E402
from backend.main import app  # noqa: E402

# Clear cached settings to ensure our env var override takes effect
from backend.auth import get_settings
get_settings.cache_clear()


# Test database URL (in-memory SQLite)
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """Create an event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def test_db() -> AsyncGenerator[AsyncSession, None]:
    """Create a test database session."""
    # Create async engine for testing
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)

    # Run migrations to set up schema (same as production)
    # We need to temporarily swap the engine so migrations run on test DB
    import backend.database as db_module
    original_engine = db_module.engine
    db_module.engine = engine

    try:
        # This runs all migrations in the correct order
        await db_module.init_db()
    finally:
        # Restore original engine
        db_module.engine = original_engine

    # Create session factory
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    # Provide session
    async with async_session() as session:
        yield session

    # Drop all tables after test
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture
async def client(test_db: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Create an async HTTP client for testing."""
    from backend.database import get_db

    # Override the get_db dependency to use test database
    async def override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = override_get_db

    # Create async client
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as ac:
        yield ac

    # Clean up
    app.dependency_overrides.clear()
