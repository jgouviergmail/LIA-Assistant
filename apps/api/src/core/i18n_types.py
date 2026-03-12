"""
Shared types for internationalization (i18n).

Centralized type definitions to eliminate duplication across i18n modules.

Phase 5A: DRY consolidation - single source of truth for i18n types.
"""

from typing import Literal

# Type-safe language codes for all i18n modules
# Supports: French, English, Spanish, German, Italian, Chinese (Simplified)
Language = Literal["fr", "en", "es", "de", "it", "zh-CN"]

# Alias for consistency with different naming conventions in codebase
SupportedLanguage = Language

# Default language (fallback when user language is unavailable)
# Can be overridden by settings at runtime
DEFAULT_LANGUAGE: Language = "fr"

# Note: SUPPORTED_LANGUAGES is defined in core/constants.py (source of truth)
# Use: from src.core.constants import SUPPORTED_LANGUAGES

# Human-readable language names for LLM prompts
# Typed as dict[str, str] to allow flexible key lookup (e.g., from DB values)
LANGUAGE_NAMES: dict[str, str] = {
    "fr": "French",
    "en": "English",
    "es": "Spanish",
    "de": "German",
    "it": "Italian",
    "zh-CN": "Simplified Chinese",
}


def get_language_name(language_code: str) -> str:
    """
    Convert a language code to a human-readable name for LLM prompts.

    This ensures LLMs understand language directives clearly.
    E.g., "zh-CN" → "Simplified Chinese", "fr" → "French"

    Args:
        language_code: ISO language code (e.g., "fr", "en", "zh-CN")

    Returns:
        Human-readable language name, or the code itself if not found
    """
    return LANGUAGE_NAMES.get(language_code, language_code)


__all__ = [
    "Language",
    "SupportedLanguage",
    "DEFAULT_LANGUAGE",
    "LANGUAGE_NAMES",
    "get_language_name",
]
