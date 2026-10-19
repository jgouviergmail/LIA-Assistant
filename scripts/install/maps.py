"""Optional browser Maps credentials: closed names and env-safe values."""

from __future__ import annotations

import re
from collections.abc import Mapping

MAPS_ENV_KEYS = ("GOOGLE_MAPS_BROWSER_API_KEY", "GOOGLE_MAPS_MAP_ID")


def valid_maps_value(value: str) -> bool:
    """A bounded single-line identifier, not a claim that Google accepts it."""
    return re.fullmatch(r"[A-Za-z0-9_-]{1,512}", value) is not None


def valid_map_id(value: str) -> bool:
    """Production installers never emit the vendor's development demo ID."""
    return valid_maps_value(value) and value.upper() != "DEMO_MAP_ID"


def validate_maps_settings(values: Mapping[str, str]) -> dict[str, str]:
    """Accept an omitted integration or a complete, injection-safe pair."""
    if not values:
        return {}
    if set(values) != set(MAPS_ENV_KEYS):
        raise ValueError("incomplete_maps_configuration")
    key, map_id = (values[name] for name in MAPS_ENV_KEYS)
    if not key and not map_id:
        return {}
    if not key or not map_id:
        raise ValueError("incomplete_maps_configuration")
    if not valid_maps_value(key) or not valid_map_id(map_id):
        raise ValueError("invalid_maps_configuration")
    return dict(values)
