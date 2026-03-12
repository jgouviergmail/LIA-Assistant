"""
Core validation utilities.
Centralized validators for common data types.
"""

import re
from zoneinfo import ZoneInfo, available_timezones

# Email validation regex - checks basic format:
# - At least one char before @
# - At least one char between @ and last dot
# - At least one char after last dot (TLD)
# Intentionally not overly strict to avoid rejecting valid edge cases
EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def validate_email(email: str) -> bool:
    """
    Validate email address format.

    Checks basic structure: local@domain.tld
    - Must contain exactly one @
    - Must have a domain with at least one dot (TLD required)
    - No whitespace allowed

    Args:
        email: Email address to validate

    Returns:
        True if valid format, False otherwise

    Example:
        >>> validate_email("user@example.com")
        True
        >>> validate_email("user@example")  # Missing TLD
        False
        >>> validate_email("user@hotmail")  # Missing TLD
        False
        >>> validate_email("invalid")
        False
    """
    if not email or not isinstance(email, str):
        return False
    return bool(EMAIL_REGEX.match(email.strip()))


def validate_timezone(timezone: str) -> bool:
    """
    Validate IANA timezone string.

    Args:
        timezone: IANA timezone name (e.g., "Europe/Paris")

    Returns:
        True if valid, False otherwise

    Example:
        >>> validate_timezone("Europe/Paris")
        True
        >>> validate_timezone("Invalid/Zone")
        False
    """
    try:
        # Check if in available timezones
        if timezone not in available_timezones():
            return False

        # Try to create ZoneInfo instance
        ZoneInfo(timezone)
        return True
    except Exception:
        return False


def get_common_timezones() -> dict[str, list[str]]:
    """
    Get list of common timezones grouped by region.

    Returns:
        Dict with regions as keys and timezone lists as values

    Example:
        >>> get_common_timezones()
        {
          "Europe": ["Europe/Paris", "Europe/London", ...],
          "America": ["America/New_York", "America/Los_Angeles", ...],
          ...
        }
    """
    # Pre-selection of the most common timezones
    common = [
        # Europe
        "Europe/Paris",
        "Europe/London",
        "Europe/Berlin",
        "Europe/Madrid",
        "Europe/Rome",
        "Europe/Amsterdam",
        "Europe/Brussels",
        "Europe/Vienna",
        "Europe/Zurich",
        "Europe/Stockholm",
        "Europe/Oslo",
        "Europe/Copenhagen",
        "Europe/Helsinki",
        "Europe/Prague",
        "Europe/Warsaw",
        "Europe/Athens",
        "Europe/Bucharest",
        "Europe/Budapest",
        "Europe/Sofia",
        "Europe/Dublin",
        "Europe/Lisbon",
        "Europe/Moscow",
        "Europe/Istanbul",
        # Americas
        "America/New_York",
        "America/Chicago",
        "America/Denver",
        "America/Los_Angeles",
        "America/Anchorage",
        "America/Phoenix",
        "America/Toronto",
        "America/Vancouver",
        "America/Montreal",
        "America/Mexico_City",
        "America/Sao_Paulo",
        "America/Buenos_Aires",
        "America/Santiago",
        "America/Lima",
        "America/Bogota",
        "America/Caracas",
        # Asia
        "Asia/Dubai",
        "Asia/Kolkata",
        "Asia/Bangkok",
        "Asia/Singapore",
        "Asia/Hong_Kong",
        "Asia/Shanghai",
        "Asia/Tokyo",
        "Asia/Seoul",
        "Asia/Jakarta",
        "Asia/Manila",
        "Asia/Karachi",
        "Asia/Tehran",
        # Pacific
        "Pacific/Auckland",
        "Pacific/Fiji",
        "Pacific/Honolulu",
        "Australia/Sydney",
        "Australia/Melbourne",
        "Australia/Brisbane",
        "Australia/Perth",
        # Africa
        "Africa/Cairo",
        "Africa/Johannesburg",
        "Africa/Lagos",
        "Africa/Nairobi",
        # Atlantic
        "Atlantic/Reykjavik",
        "Atlantic/Azores",
    ]

    # Group by region
    grouped: dict[str, list[str]] = {}
    for tz in sorted(common):
        region = tz.split("/")[0]
        if region not in grouped:
            grouped[region] = []
        grouped[region].append(tz)

    return grouped
