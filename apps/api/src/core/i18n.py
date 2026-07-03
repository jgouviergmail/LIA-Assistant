"""
Internationalization (i18n) utilities using gettext.

Provides translation functions for API error messages, validation errors,
and user-facing text. LLM prompts are NOT translated (LLMs understand all languages).

Supported languages: fr, en, es, de, it, zh-CN
"""

import gettext
from functools import lru_cache
from pathlib import Path

import structlog

from src.core.config import settings
from src.core.constants import LANGUAGE_TO_LOCALE
from src.core.i18n_types import Language

logger = structlog.get_logger(__name__)

# Language configuration from settings (with auto-detection as primary strategy)
# These act as fallbacks when Accept-Language header is missing or invalid
# NOTE: These override the defaults in i18n_types.py with runtime config
SUPPORTED_LANGUAGES: list[Language] = settings.supported_languages  # type: ignore[assignment]
DEFAULT_LANGUAGE: Language = settings.default_language  # type: ignore[assignment]

# Locale directory path (relative to project root)
LOCALE_DIR = Path(__file__).parent.parent.parent / "locales"


def normalize_language(language: str) -> Language:
    """Normalize a language code to the canonical backend format.

    Single chokepoint for language-code normalization (audit wave 2, zh):
    the frontend spells Chinese ``zh`` (URLs, locale files) while the backend
    canonical code is ``zh-CN`` (``User.language``, ``SUPPORTED_LANGUAGES``,
    i18n table keys). Every consumer keying a table by language must call
    this function first — never key a table on a raw incoming locale.

    Args:
        language: Raw locale (e.g., "zh", "zh-CN", "zh_CN", "fr-FR", "en_US").

    Returns:
        Canonical Language code; falls back to the configured default
        language (settings-driven).
    """
    lang_lower = language.lower().replace("_", "-")

    # Handle Chinese variants (zh, zh-CN, zh-TW, ... → canonical zh-CN)
    if lang_lower.startswith("zh"):
        return "zh-CN"

    # Extract base language code
    base_lang = lang_lower.split("-")[0]

    if base_lang in ("fr", "en", "es", "de", "it"):
        return base_lang  # type: ignore[return-value]

    # Unsupported: fall back to the configured default language
    return DEFAULT_LANGUAGE


def get_locale_for_language(language: str | None) -> str:
    """Map a raw language code to a valid BCP 47 display locale.

    Replaces the buggy ``f"{lang}-{lang.upper()}"`` derivation, which
    produced nonexistent locales such as "en-EN" or "zh-ZH" (audit wave 3,
    N-129). Normalizes first, so any incoming spelling ("zh", "en_US",
    "fr-FR") resolves to its canonical display locale.

    Args:
        language: Raw language/locale code, or None for the default language.

    Returns:
        BCP 47 locale (e.g., "en-US", "zh-CN", "fr-FR").
    """
    # Direct indexing on purpose: normalize_language returns a canonical
    # supported code and the boot-time assert in constants guarantees the
    # mapping is complete — a KeyError here means broken config, not a
    # situation to paper over with a silent fallback.
    return LANGUAGE_TO_LOCALE[normalize_language(language or DEFAULT_LANGUAGE)]


@lru_cache(maxsize=10)
def get_translator(language: Language) -> gettext.NullTranslations:
    """
    Get cached gettext translator for language.

    Falls back to default language (fr) if requested language not available.

    Args:
        language: Target language code (fr/en/es/de/it)

    Returns:
        NullTranslations instance for the language

    Example:
        >>> translator = get_translator("en")
        >>> translator.gettext("User not found")
        "User not found"
    """
    try:
        return gettext.translation(
            "messages",
            localedir=str(LOCALE_DIR),
            languages=[language],
            fallback=False,
        )
    except FileNotFoundError:
        # Fallback to default language
        logger.warning(
            "translation_not_found_using_fallback",
            requested_language=language,
            fallback_language=DEFAULT_LANGUAGE,
        )
        return gettext.translation(
            "messages",
            localedir=str(LOCALE_DIR),
            languages=[DEFAULT_LANGUAGE],
            fallback=True,
        )


def _(text: str, language: Language = DEFAULT_LANGUAGE) -> str:
    """
    Translate text to target language using gettext.

    Main translation function for API messages. Use this for all user-facing
    error messages, validation errors, and status messages.

    Args:
        text: English text to translate (source language)
        language: Target language code (default: fr)

    Returns:
        Translated text in target language

    Example:
        >>> _("User not found", "en")
        "User not found"
        >>> _("User not found", "fr")
        "Utilisateur introuvable"
    """
    translator = get_translator(language)
    return translator.gettext(text)


def _n(
    singular: str,
    plural: str,
    n: int,
    language: Language = DEFAULT_LANGUAGE,
) -> str:
    """
    Translate with pluralization support.

    Handles singular/plural forms correctly for each language.

    Args:
        singular: Singular form (English)
        plural: Plural form (English)
        n: Count to determine singular/plural
        language: Target language code (default: fr)

    Returns:
        Translated text with correct plural form

    Example:
        >>> _n("1 message", "{n} messages", 1, "en")
        "1 message"
        >>> _n("1 message", "{n} messages", 5, "en")
        "5 messages"
        >>> _n("1 message", "{n} messages", 5, "fr")
        "5 messages"
    """
    translator = get_translator(language)
    return translator.ngettext(singular, plural, n)


def get_language_from_header(accept_language: str | None) -> Language:
    """
    Parse Accept-Language header and return best match.

    Implements language negotiation based on browser preferences.
    Falls back to DEFAULT_LANGUAGE if no match found.

    Args:
        accept_language: Accept-Language header value (e.g., "fr-FR,fr;q=0.9,en;q=0.8")

    Returns:
        Best matching supported language code

    Example:
        >>> get_language_from_header("fr-FR,fr;q=0.9,en;q=0.8")
        "fr"
        >>> get_language_from_header("en-US,en;q=0.9")
        "en"
        >>> get_language_from_header("ja-JP")
        "fr"  # Fallback to default
    """
    if not accept_language:
        return DEFAULT_LANGUAGE

    # Parse: "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7,zh-CN;q=0.6"
    for lang_code in accept_language.split(","):
        # Extract language code (before semicolon)
        lang = lang_code.split(";")[0].strip()

        # Try exact match first (for zh-CN)
        if lang in SUPPORTED_LANGUAGES:
            return lang

        # Try with only first 2 chars (for en-US -> en)
        lang_short = lang[:2].lower()
        if lang_short in SUPPORTED_LANGUAGES:
            return lang_short

    return DEFAULT_LANGUAGE
