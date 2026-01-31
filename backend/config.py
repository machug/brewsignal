"""
BrewSignal Configuration

Supports two deployment modes:
- local: Single-user RPi deployment with SQLite, optional auth
- cloud: Multi-tenant SaaS with PostgreSQL + Supabase Auth

Feature flags control which capabilities are enabled. Each deployment mode
has sensible defaults, with optional per-flag overrides via environment variables.
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


# Default feature flags for each deployment mode
DEPLOYMENT_PRESETS = {
    "local": {
        "scanner": True,       # BLE Tilt scanning
        "ha": True,            # Home Assistant integration
        "mqtt": True,          # MQTT publishing
        "control": True,       # Temperature controller
        "pollers": True,       # Ambient/chamber polling
        "cleanup": True,       # Reading cleanup service
        "gateway": False,      # Gateway WebSocket for ESP32
        "cloud_sync": False,   # Premium cloud sync
        "require_auth": False, # Anonymous access allowed
        "serve_frontend": True, # Serve static SvelteKit build
    },
    "cloud": {
        "scanner": False,
        "ha": False,
        "mqtt": False,
        "control": False,
        "pollers": False,
        "cleanup": False,      # Disabled until TZ fix
        "gateway": True,
        "cloud_sync": True,
        "require_auth": True,  # JWT required
        "serve_frontend": False, # Vercel serves frontend
    },
}


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

    # Feature flag overrides (None = use preset default)
    scanner_enabled: Optional[bool] = None
    ha_enabled: Optional[bool] = None
    mqtt_enabled: Optional[bool] = None
    control_enabled: Optional[bool] = None
    pollers_enabled: Optional[bool] = None
    cleanup_enabled: Optional[bool] = None
    gateway_enabled: Optional[bool] = None
    cloud_sync_enabled: Optional[bool] = None
    require_auth_enabled: Optional[bool] = None
    serve_frontend_enabled: Optional[bool] = None

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

    def is_enabled(self, feature: str) -> bool:
        """Check if a feature is enabled.

        First checks for an explicit override via environment variable,
        then falls back to the deployment preset default.

        Args:
            feature: Feature name (e.g., "scanner", "mqtt", "require_auth")

        Returns:
            True if the feature is enabled, False otherwise.
        """
        # Check for explicit override
        override = getattr(self, f"{feature}_enabled", None)
        if override is not None:
            return override
        # Fall back to preset default
        preset = DEPLOYMENT_PRESETS.get(self.deployment_mode.value, {})
        return preset.get(feature, False)

    @property
    def require_auth(self) -> bool:
        """Check if authentication is required."""
        return self.is_enabled("require_auth")

    def get_database_url(self) -> str:
        """Get the database URL, with defaults based on deployment mode."""
        if self.database_url:
            # SSL for PostgreSQL is handled via connect_args in database.py
            return self.database_url

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
