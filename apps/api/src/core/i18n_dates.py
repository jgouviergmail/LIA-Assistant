"""
Internationalized date names for formatting.

Provides centralized day and month name translations.
Used by formatters to display dates in user's locale.

Supported languages: fr, en, es, de, it, zh-CN
"""

from src.core.i18n import DEFAULT_LANGUAGE
from src.core.i18n_types import Language

# Day names indexed by weekday (0=Monday, 6=Sunday)
DAY_NAMES: dict[Language, list[str]] = {
    "fr": ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"],
    "en": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
    "es": ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"],
    "de": ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"],
    "it": ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"],
    "zh-CN": ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"],
}

# Month names indexed by month (0=January, 11=December)
MONTH_NAMES: dict[Language, list[str]] = {
    "fr": [
        "janvier",
        "février",
        "mars",
        "avril",
        "mai",
        "juin",
        "juillet",
        "août",
        "septembre",
        "octobre",
        "novembre",
        "décembre",
    ],
    "en": [
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    ],
    "es": [
        "enero",
        "febrero",
        "marzo",
        "abril",
        "mayo",
        "junio",
        "julio",
        "agosto",
        "septiembre",
        "octubre",
        "noviembre",
        "diciembre",
    ],
    "de": [
        "Januar",
        "Februar",
        "März",
        "April",
        "Mai",
        "Juni",
        "Juli",
        "August",
        "September",
        "Oktober",
        "November",
        "Dezember",
    ],
    "it": [
        "gennaio",
        "febbraio",
        "marzo",
        "aprile",
        "maggio",
        "giugno",
        "luglio",
        "agosto",
        "settembre",
        "ottobre",
        "novembre",
        "dicembre",
    ],
    "zh-CN": [
        "1月",
        "2月",
        "3月",
        "4月",
        "5月",
        "6月",
        "7月",
        "8月",
        "9月",
        "10月",
        "11月",
        "12月",
    ],
}

# Time connectors for datetime formatting
TIME_CONNECTORS: dict[Language, str] = {
    "fr": "à",
    "en": "at",
    "es": "a las",
    "de": "um",
    "it": "alle",
    "zh-CN": "",
}


def get_day_name(weekday: int, locale: str = "fr") -> str:
    """
    Get localized day name.

    Args:
        weekday: Day of week (0=Monday, 6=Sunday)
        locale: Locale string (e.g., "fr", "en", "fr-FR")

    Returns:
        Localized day name

    Example:
        >>> get_day_name(0, "fr")
        "lundi"
        >>> get_day_name(0, "en")
        "Monday"
    """
    lang = _extract_language(locale)
    return DAY_NAMES.get(lang, DAY_NAMES[DEFAULT_LANGUAGE])[weekday]


def get_month_name(month: int, locale: str = "fr") -> str:
    """
    Get localized month name.

    Args:
        month: Month number (1=January, 12=December)
        locale: Locale string (e.g., "fr", "en", "fr-FR")

    Returns:
        Localized month name

    Example:
        >>> get_month_name(11, "fr")
        "novembre"
        >>> get_month_name(11, "en")
        "November"
    """
    lang = _extract_language(locale)
    return MONTH_NAMES.get(lang, MONTH_NAMES[DEFAULT_LANGUAGE])[month - 1]


def get_time_connector(locale: str = "fr") -> str:
    """
    Get time connector word for datetime formatting.

    Args:
        locale: Locale string

    Returns:
        Connector word (e.g., "à" for French, "at" for English)
    """
    lang = _extract_language(locale)
    return TIME_CONNECTORS.get(lang, TIME_CONNECTORS[DEFAULT_LANGUAGE])


def format_date(day: int, month: int, year: int | None, locale: str = "fr") -> str:
    """
    Format a date with localized month name.

    Args:
        day: Day of month (1-31)
        month: Month number (1-12)
        year: Year (optional)
        locale: Locale string

    Returns:
        Formatted date string (e.g., "03 novembre 1975")

    Example:
        >>> format_date(3, 11, 1975, "fr")
        "03 novembre 1975"
        >>> format_date(3, 11, None, "fr")
        "03 novembre"
    """
    lang = _extract_language(locale)
    month_name = get_month_name(month, lang)
    day_str = f"{day:02d}"

    if lang == "zh-CN":
        if year:
            return f"{year}年{month}月{day}日"
        return f"{month}月{day}日"
    else:
        if year:
            return f"{day_str} {month_name} {year}"
        return f"{day_str} {month_name}"


def _extract_language(locale: str | None) -> Language:
    """
    Extract language code from locale string.

    Args:
        locale: Locale string (e.g., "fr-FR", "en", "zh-CN")

    Returns:
        Language code

    Example:
        >>> _extract_language("fr-FR")
        "fr"
        >>> _extract_language("zh-CN")
        "zh-CN"
    """
    if not locale:
        return DEFAULT_LANGUAGE

    # Special case for zh-CN (keep as-is)
    if locale.lower() == "zh-cn":
        return "zh-CN"

    # Extract first part (e.g., "fr-FR" -> "fr")
    lang = locale.split("-")[0].lower() if "-" in locale else locale.lower()

    # Validate it's a supported language
    if lang in DAY_NAMES:
        return lang

    return DEFAULT_LANGUAGE
