"""
BrewSignal Configuration

Supports two deployment modes:
- local: Single-user RPi deployment with SQLite, no auth
- cloud: Multi-tenant SaaS with PostgreSQL + Supabase Auth
"""

import os
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings


class DeploymentMode(str, Enum):
    LOCAL = "local"
    CLOUD = "cloud"


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Deployment mode
    deployment_mode: DeploymentMode = DeploymentMode.LOCAL

    # Database
    # For local: defaults to SQLite in data/fermentation.db
    # For cloud: should be postgresql+asyncpg://...
    database_url: Optional[str] = None

    # Authentication (only used in cloud mode)
    auth_enabled: bool = False
    supabase_url: Optional[str] = None
    supabase_anon_key: Optional[str] = None
    supabase_service_role_key: Optional[str] = None

    # Multi-tenancy (only used in cloud mode)
    multi_tenant: bool = False

    # External APIs
    brewfather_user_id: Optional[str] = None
    brewfather_api_key: Optional[str] = None
    brewfather_api_endpoint: str = "https://api.brewfather.app/v2/"
    anthropic_api_key: Optional[str] = None

    # Scanner settings
    scanner_mock: bool = False
    scanner_relay_host: Optional[str] = None

    # Server settings
    host: str = "0.0.0.0"
    port: int = 8080

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"  # Ignore extra env vars

    @property
    def is_cloud(self) -> bool:
        """Check if running in cloud mode."""
        return self.deployment_mode == DeploymentMode.CLOUD

    @property
    def is_local(self) -> bool:
        """Check if running in local mode."""
        return self.deployment_mode == DeploymentMode.LOCAL

    def get_database_url(self) -> str:
        """Get the database URL, with defaults based on deployment mode."""
        if self.database_url:
            url = self.database_url
            # Ensure SSL is set for PostgreSQL (required by Supabase)
            # asyncpg uses 'ssl' parameter, not 'sslmode'
            if url.startswith("postgresql") and "ssl=" not in url and "sslmode=" not in url:
                separator = "&" if "?" in url else "?"
                url = f"{url}{separator}ssl=require"
            return url

        # Default to SQLite for local mode
        if self.is_local:
            data_dir = Path(__file__).parent.parent / "data"
            data_dir.mkdir(exist_ok=True)
            return f"sqlite+aiosqlite:///{data_dir}/fermentation.db"

        # Cloud mode requires explicit DATABASE_URL
        raise ValueError(
            "DATABASE_URL must be set for cloud deployment. "
            "Expected format: postgresql+asyncpg://user:pass@host:port/dbname"
        )

    def get_sync_database_url(self) -> str:
        """Get synchronous database URL for migrations."""
        url = self.get_database_url()
        # Convert async drivers to sync equivalents
        return url.replace("+aiosqlite", "").replace("+asyncpg", "+psycopg2")


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# Convenience accessors
settings = get_settings()
