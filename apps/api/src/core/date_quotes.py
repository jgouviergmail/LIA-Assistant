"""Parse literal localized calendar dates without a tool or model dependency."""

import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# Month name mappings for localized date parsing (FR, EN, DE, ES, IT)
_MONTH_NAMES: dict[str, int] = {
    # French
    "janvier": 1,
    "février": 2,
    "fevrier": 2,
    "mars": 3,
    "avril": 4,
    "mai": 5,
    "juin": 6,
    "juillet": 7,
    "août": 8,
    "aout": 8,
    "septembre": 9,
    "octobre": 10,
    "novembre": 11,
    "décembre": 12,
    "decembre": 12,
    # English
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
    # German
    "januar": 1,
    "februar": 2,
    "märz": 3,
    "marz": 3,
    "juni": 6,
    "juli": 7,
    "oktober": 10,
    "dezember": 12,
    # Spanish
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
    # Italian
    "gennaio": 1,
    "febbraio": 2,
    "aprile": 4,
    "maggio": 5,
    "giugno": 6,
    "luglio": 7,
    "settembre": 9,
    "ottobre": 10,
    "dicembre": 12,
}

# Pattern: optional day-of-week, then DD month YYYY (e.g., "jeudi 09 avril 2026", "9 avril 2026")
_LOCALIZED_DATE_PATTERN = re.compile(r"(?:\w+\s+)?(\d{1,2})\s+(\w+)\s+(\d{4})", re.IGNORECASE)
_ISO_DATE_PATTERN = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_ISO_TIMESTAMP_PATTERN = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}[Tt ][0-9]{2}:[0-9]{2}"
    r"(?::[0-9]{2}(?:\.[0-9]{1,6})?)?"
    r"(?:[Zz]|[+-](?:0[0-9]|1[0-9]|2[0-3]):[0-5][0-9])?"
)


def parse_localized_date(ref: str) -> date | None:
    """Parse a date written in words, like 'jeudi 09 avril 2026' or '9 April 2026'.

    Supports French, English, German, Spanish, and Italian month names, day first.

    Args:
        ref: Date string to parse.

    Returns:
        Parsed date or None if not recognized.
    """
    match = _LOCALIZED_DATE_PATTERN.match(ref.strip())
    if not match:
        return None

    day_str, month_str, year_str = match.groups()
    month = _MONTH_NAMES.get(month_str.lower())
    if month is None:
        return None

    try:
        return date(int(year_str), month, int(day_str))
    except ValueError:
        return None


def date_from_quote(
    quote: str,
    reference_date: date | None = None,
    *,
    reference_timezone: str | None = None,
) -> date | None:
    """Read one exact date expression against the server-recorded request context.

    Civil dates retain their day. A timestamp uses the request timezone rather
    than its textual ISO date prefix; no model-supplied timezone is inferred.
    """
    expression = quote.strip()
    if _ISO_TIMESTAMP_PATTERN.fullmatch(expression):
        return _timestamp_quote_date(expression, reference_timezone)
    localized = (
        parse_localized_date(expression) if _LOCALIZED_DATE_PATTERN.fullmatch(expression) else None
    )
    if localized is not None:
        return localized
    if not _ISO_DATE_PATTERN.fullmatch(expression):
        return _relative_date_from_quote(expression, reference_date)
    try:
        return date.fromisoformat(expression)
    except ValueError:
        return None


def _timestamp_quote_date(expression: str, reference_timezone: str | None) -> date | None:
    """Offset-aware instants convert; an unqualified time belongs to its request zone."""
    if reference_timezone is None:
        return None
    normalized = expression.replace("t", "T")
    if normalized.endswith("Z") or normalized.endswith("z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        instant = datetime.fromisoformat(normalized)
        timezone = ZoneInfo(reference_timezone)
    except ValueError, ZoneInfoNotFoundError:
        return None
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone)
    return instant.astimezone(timezone).date()


def _relative_date_from_quote(quote: str, reference_date: date | None) -> date | None:
    if reference_date is None:
        return None
    expression = " ".join(quote.casefold().split())
    offsets = {
        "today": 0,
        "aujourd'hui": 0,
        "heute": 0,
        "hoy": 0,
        "oggi": 0,
        "今天": 0,
        "tomorrow": 1,
        "demain": 1,
        "morgen": 1,
        "mañana": 1,
        "domani": 1,
        "明天": 1,
        "day after tomorrow": 2,
        "après-demain": 2,
        "übermorgen": 2,
        "pasado mañana": 2,
        "dopodomani": 2,
        "后天": 2,
    }
    offset = offsets.get(expression)
    return reference_date + timedelta(days=offset) if offset is not None else None
