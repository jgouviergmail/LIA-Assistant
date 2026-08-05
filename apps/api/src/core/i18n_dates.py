"""
Internationalized date names for formatting.

Provides centralized day and month name translations.
Used by formatters to display dates in user's locale.

Supported languages: fr, en, es, de, it, zh-CN
"""

from src.core.i18n import DEFAULT_LANGUAGE, normalize_language
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

# Short day names indexed by weekday (0=Monday, 6=Sunday).
#
# Declared, never derived: truncating the full name is wrong in German (the
# usual forms are Mo/Di/Mi, not Mon/Die/Mit) and meaningless in Chinese. An
# abbreviation is linguistic data.
DAY_NAMES_SHORT: dict[Language, list[str]] = {
    "fr": ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"],
    "en": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
    "es": ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"],
    "de": ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"],
    "it": ["Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom"],
    "zh-CN": ["周一", "周二", "周三", "周四", "周五", "周六", "周日"],
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


def get_day_name_short(weekday: int, locale: str = "fr") -> str:
    """
    Get the localized SHORT day name.

    Args:
        weekday: Day of week (0=Monday, 6=Sunday)
        locale: Locale string (e.g., "fr", "en", "fr-FR")

    Returns:
        Localized abbreviation

    Example:
        >>> get_day_name_short(2, "de")
        "Mi"
        >>> get_day_name_short(2, "fr")
        "Mer"
    """
    lang = _extract_language(locale)
    return DAY_NAMES_SHORT.get(lang, DAY_NAMES_SHORT[DEFAULT_LANGUAGE])[weekday]


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

    # Single chokepoint: the frontend spells Chinese "zh" while every table
    # here is keyed on the backend canonical "zh-CN". Splitting on "-" locally
    # left "zh" untouched, missed DAY_NAMES/MONTH_NAMES and silently served
    # FRENCH day names to a Chinese user.
    return normalize_language(locale)


def format_half_hour_label(hour: float) -> str:
    """``9.4`` → ``"09:30"``: round a fractional hour to the nearest half hour.

    Single authority for the learned-habits surfaces (suggestion text,
    heartbeat offers) — the same rounding used to exist in two copies, which
    is one drift away from a suggestion and its offer disagreeing on the
    same learned hour. Lives beside the other date/time wordings this
    feature renders with (``get_day_name``).

    Args:
        hour: Fractional hour in [0, 24).

    Returns:
        Zero-padded ``HH:MM`` label, wrapping past midnight.
    """
    total_minutes = int(round(hour * 60 / 30.0) * 30) % (24 * 60)
    return f"{total_minutes // 60:02d}:{total_minutes % 60:02d}"
