"""Shared application state.

This module holds global state that needs to be accessed from multiple
parts of the application without creating circular dependencies.

Latest readings are persisted to disk so they survive service restarts.
This is important for devices like GravityMon that only send data every
5 minutes - without persistence, users would have to wait after every
restart to see readings.
"""

import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# In-memory cache of latest readings per device
# Format: {device_id: {reading_payload_dict}}
latest_readings: dict[str, dict] = {}

# Path to the persistent cache file
_CACHE_FILE: Optional[Path] = None


def _get_cache_path() -> Path:
    """Get the path to the readings cache file."""
    global _CACHE_FILE
    if _CACHE_FILE is None:
        # Use the same data directory as the database
        data_dir = Path(__file__).parent.parent / "data"
        data_dir.mkdir(exist_ok=True)
        _CACHE_FILE = data_dir / "latest_readings.json"
    return _CACHE_FILE


def load_readings_cache() -> None:
    """Load latest readings from persistent cache on startup."""
    global latest_readings
    cache_path = _get_cache_path()

    if not cache_path.exists():
        logger.debug("No readings cache file found, starting fresh")
        return

    try:
        with open(cache_path, "r") as f:
            cached = json.load(f)

        if isinstance(cached, dict):
            latest_readings.update(cached)
            logger.info(f"Loaded {len(cached)} cached readings from {cache_path}")
    except (json.JSONDecodeError, IOError) as e:
        logger.warning(f"Failed to load readings cache: {e}")


def save_readings_cache() -> None:
    """Save latest readings to persistent cache."""
    cache_path = _get_cache_path()

    try:
        with open(cache_path, "w") as f:
            json.dump(latest_readings, f)
    except IOError as e:
        logger.warning(f"Failed to save readings cache: {e}")


def update_reading(device_id: str, reading: dict) -> None:
    """Update a device's latest reading and persist to cache.

    Args:
        device_id: The device identifier
        reading: The reading payload dict
    """
    latest_readings[device_id] = reading
    # Persist after each update - this is fast enough for the low frequency
    # of readings (every few seconds for Tilt BLE, every 5 min for GravityMon)
    save_readings_cache()


def get_reading(device_id: str) -> Optional[dict]:
    """Get the latest reading for a device.

    Args:
        device_id: The device identifier

    Returns:
        The reading dict or None if not found
    """
    return latest_readings.get(device_id)


def get_all_readings() -> dict[str, dict]:
    """Get all latest readings.

    Returns:
        Dict of device_id -> reading payload
    """
    return latest_readings.copy()
