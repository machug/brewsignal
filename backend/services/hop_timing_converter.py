"""Hop timing conversion utilities for BeerJSON migration.

This module provides utilities to convert legacy hop timing data (use/time fields)
to BeerJSON timing objects. Extracted from migrations for testability.
"""
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


def convert_hop_timing_safe(use: Optional[str], time: Optional[float]) -> Optional[Dict[str, Any]]:
    """Convert old hop use/time to BeerJSON timing object.

    Only creates timing if use is valid. Returns None for invalid data.

    Args:
        use: Legacy hop use value (e.g., "Boil", "Dry Hop", "Mash", etc.)
        time: Time value in minutes (or NULL)

    Returns:
        Dict (not JSON string) for SQLAlchemy JSON column, or None if invalid

    Examples:
        >>> convert_hop_timing_safe("Boil", 60)
        {'use': 'add_to_boil', 'continuous': False, 'duration': {'value': 60, 'unit': 'min'}}

        >>> convert_hop_timing_safe("Dry Hop", 1440)  # 1 day in minutes
        {'use': 'add_to_fermentation', 'continuous': False, 'duration': {'value': 1, 'unit': 'day'}, 'phase': 'primary'}

        >>> convert_hop_timing_safe("Unknown", 60)
        None

        >>> convert_hop_timing_safe(None, 60)
        None

        >>> convert_hop_timing_safe("", 60)
        None
    """
    if not use or use == '':
        return None

    use_mapping = {
        "Boil": "add_to_boil",
        "Dry Hop": "add_to_fermentation",
        "Mash": "add_to_mash",
        "First Wort": "add_to_boil",
        "Aroma": "add_to_boil"
    }

    # Unknown use value - preserve NULL
    if use not in use_mapping:
        logger.warning(f"Unknown hop use '{use}', preserving NULL timing")
        return None

    timing = {
        "use": use_mapping[use],
        "continuous": False
    }

    # Add duration if time is valid
    # Note: Only Boil, Aroma, and Dry Hop get duration values
    # - First Wort: Added at start of boil, duration is implied by boil time
    # - Mash: Added during mash, duration is implied by mash schedule
    if time is not None and time > 0:
        if use in ["Boil", "Aroma"]:
            timing["duration"] = {"value": time, "unit": "min"}
        elif use == "Dry Hop":
            # Convert minutes to days (BeerXML quirk)
            # Use round() instead of int() to handle fractional days properly
            days = round(time / 1440)

            # Sanity check: Cap at 365 days (BeerXML files sometimes have nonsensical values)
            if days > 365:
                logger.warning(f"Dry hop duration {days} days exceeds maximum (365), capping value")
                days = 365

            timing["duration"] = {"value": days, "unit": "day"}
            timing["phase"] = "primary"

    return timing  # Return dict, not json.dumps()
