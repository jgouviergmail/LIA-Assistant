"""
Internationalization (i18n) utilities using gettext.

Provides translation functions for API error messages, validation errors,
and user-facing text. LLM prompts are NOT translated (LLMs understand all languages).

Supported languages: fr, en, es, de, it
"""

import gettext
from functools import lru_cache
from pathlib import Path

import structlog

from src.core.config import settings
from src.core.i18n_types import Language

logger = structlog.get_logger(__name__)

# Language configuration from settings (with auto-detection as primary strategy)
# These act as fallbacks when Accept-Language header is missing or invalid
# NOTE: These override the defaults in i18n_types.py with runtime config
SUPPORTED_LANGUAGES: list[Language] = settings.supported_languages  # type: ignore[assignment]
DEFAULT_LANGUAGE: Language = settings.default_language  # type: ignore[assignment]

# Locale directory path (relative to project root)
LOCALE_DIR = Path(__file__).parent.parent.parent / "locales"


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
            return lang  # type: ignore[return-value]

        # Try with only first 2 chars (for en-US -> en)
        lang_short = lang[:2].lower()
        if lang_short in SUPPORTED_LANGUAGES:
            return lang_short  # type: ignore[return-value]

    return DEFAULT_LANGUAGE
