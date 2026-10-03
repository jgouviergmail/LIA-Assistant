"""Presence-aware access to provider measurements (zero is a real value)."""

from collections.abc import Mapping
from math import isfinite


def first_present(data: Mapping[str, object], *keys: str) -> object:
    """Return the first supplied value, preserving numeric zero."""
    for key in keys:
        value = data.get(key)
        if value is not None and value != "" and not isinstance(value, bool):
            if isinstance(value, float) and not isfinite(value):
                continue
            return value
    return ""


def scalar_text(value: object) -> str:
    """Display a scalar measurement, never a missing/null value or a raw tree."""
    if isinstance(value, float) and not isfinite(value):
        return ""
    if not isinstance(value, str | int | float) or isinstance(value, bool):
        return ""
    try:
        return str(value)
    except ValueError:
        # Python rejects pathologically large untrusted integer text.
        return ""


def list_values(value: object) -> list[object]:
    """Only a supplied JSON list is a collection; do not iterate a raw scalar."""
    return value if isinstance(value, list) else []


def rating_value(value: object) -> float | None:
    """A finite provider score, without converting an invalid value into a fact."""
    if not isinstance(value, str | int | float) or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except ValueError, OverflowError:
        return None
    return number if isfinite(number) and 0 <= number <= 5 else None


def nonnegative_integer(value: object) -> int | None:
    """Accept a supplied count without coercing booleans, trees or fractions."""
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def nonnegative_number(value: object) -> float | None:
    """Read a finite measurement, including the numeric legacy string form."""
    if not isinstance(value, str | int | float) or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except ValueError, OverflowError:
        return None
    return number if isfinite(number) and number >= 0 else None
