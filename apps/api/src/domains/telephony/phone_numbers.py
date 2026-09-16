"""What a phone number is, decided once for the whole telephony domain.

Two readers need the same rules: the third-party call tool (is this callee a
number or a name? does the address book carry this line?) and the identity
service (is the number the person declared a dialable E.164 line?). They used
to be private helpers of the tool; a second copy in the identity service would
have let a national number be accepted by one and refused by the other.

No domain import: the only dependency is the deployment's country code.
"""

from __future__ import annotations

import re

from src.core.config import get_settings

#: A callee looks like a phone number when it is a '+'-prefixed / digit run with
#: only phone punctuation — a contact name never matches this.
_PHONE_RE = re.compile(r"^\+?\d[\d\s().\-]{6,}$")

#: E.164: a '+', a non-zero first digit, 7 to 15 digits in total.
_E164_RE = re.compile(r"^\+[1-9]\d{6,14}$")

#: A national number keeps enough digits to identify a line on its own; below
#: that, a suffix match would be a coincidence.
_MIN_SIGNIFICANT_DIGITS = 8

#: Longest country calling code (3 digits) plus the leading '+'.
_MAX_COUNTRY_PREFIX = 4


def looks_like_phone(value: str) -> bool:
    """Whether a raw callee is already a dialable number (skip name resolution).

    Args:
        value: What the planner passed as the callee.

    Returns:
        True for a digit run with phone punctuation only.
    """
    return bool(_PHONE_RE.match(value.strip()))


def normalize_phone(value: str) -> str:
    """Collapse a raw number to a compact E.164-ish form (keep a leading '+').

    When ``TELEPHONY_DEFAULT_COUNTRY_CODE`` is configured, a national number
    (single leading 0, e.g. ``0682511639``) is converted to E.164 by replacing
    the trunk 0 (``+33682511639``). ``00``-prefixed international numbers and
    numbers already carrying ``+`` are left untouched.

    Args:
        value: The raw number, with any display punctuation.

    Returns:
        Digits only, with the leading '+' when there was one or one was added.
    """
    stripped = value.strip()
    if stripped.startswith("+"):
        return f"+{re.sub(r'[^0-9]', '', stripped)}"
    digits = re.sub(r"[^0-9]", "", stripped)
    country_code = get_settings().telephony_default_country_code
    if country_code and len(digits) >= 6 and digits.startswith("0") and not digits.startswith("00"):
        return f"{country_code}{digits[1:]}"
    return digits


def to_e164(value: str) -> str | None:
    """The E.164 form of a number the person typed, or None when it has none.

    The identity service stores this or nothing: a number that cannot be
    dialled as typed is not an identity, and a national number under no
    configured country code cannot be promoted without guessing a country.

    Args:
        value: The raw number, with any display punctuation.

    Returns:
        ``+<digits>`` when the normalised number is E.164, else None.
    """
    normalized = normalize_phone(value)
    return normalized if _E164_RE.match(normalized) else None


def same_line(a: str, b: str) -> bool:
    """Whether two raw numbers designate the same line.

    Equality after normalization is the nominal case. The national/E.164 pair
    is handled ONLY when one side could not be promoted — i.e. when no
    ``TELEPHONY_DEFAULT_COUNTRY_CODE`` is configured: the international form
    must then END with the whole national number minus its trunk zero, and
    differ by a country prefix at most. A loose suffix comparison would merge
    two lines in different countries.

    Args:
        a: One raw number.
        b: The other raw number.

    Returns:
        True when both name one line.
    """
    na, nb = normalize_phone(a), normalize_phone(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    if na.startswith("+") == nb.startswith("+"):
        return False
    intl, local = (na, nb) if na.startswith("+") else (nb, na)
    significant = local.lstrip("0")
    if len(significant) < _MIN_SIGNIFICANT_DIGITS or not intl.endswith(significant):
        return False
    return len(intl) - len(significant) <= _MAX_COUNTRY_PREFIX


def number_search_variants(number: str) -> list[str]:
    """The spellings to search a number under, most canonical first.

    Providers index the string AS STORED: a contact saved ``06 12 34 56 78`` is
    invisible to a ``+33612345678`` search. Without the national variant the
    reverse lookup would miss the most common case and fail silently.

    Args:
        number: The raw number.

    Returns:
        Deduplicated spellings, the normalised form first.
    """
    normalized = normalize_phone(number)
    variants = [normalized]
    country_code = get_settings().telephony_default_country_code
    if normalized.startswith("+") and country_code and normalized.startswith(country_code):
        variants.append("0" + normalized[len(country_code) :])
    if not normalized.startswith("+") and normalized.startswith("0"):
        variants.append(normalized.lstrip("0"))
    return list(dict.fromkeys(variant for variant in variants if variant))


__all__ = [
    "looks_like_phone",
    "normalize_phone",
    "number_search_variants",
    "same_line",
    "to_e164",
]
