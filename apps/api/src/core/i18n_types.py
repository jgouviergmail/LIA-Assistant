"""
Shared types for internationalization (i18n).

Centralized type definitions to eliminate duplication across i18n modules.

Phase 5A: DRY consolidation - single source of truth for i18n types.
"""

from typing import Literal, get_args

# A LEAF: this module imports nothing from ``src``. Every i18n module reads it,
# and ``core.constants`` derives ``SUPPORTED_LANGUAGES`` from it — an import back
# made the whole family depend on which of the two a process loaded first.

# THE declaration of the supported languages: ``SUPPORTED_LANGUAGES`` and the
# base codes below derive from it, and every table naming them is checked against
# it. Supports: French, English, Spanish, German, Italian, Chinese (Simplified).
Language = Literal["fr", "en", "es", "de", "it", "zh-CN"]

# Alias for consistency with different naming conventions in codebase
SupportedLanguage = Language

# The instance's default language is a SETTING (``DEFAULT_LANGUAGE``), read
# through ``core.i18n``; no module may hold a copy of its own (ADR-323).

# Base code of every supported language written without a region, derived from
# the Literal so a key cannot name one language and its value another. Chinese is
# the one language whose canonical code carries one, so it is matched on its
# prefix instead (``zh``, ``zh_CN``, ``zh-tw`` → ``zh-CN``).
_BASE_CODES: dict[str, Language] = {code: code for code in get_args(Language) if "-" not in code}


def canonical_language(code: str | None) -> Language | None:
    """Return the canonical code a raw spelling names, or None when it names none.

    The settings-free core of ``core.i18n.normalize_language``: the configuration
    validates the instance's default language with it, before any setting exists
    to fall back on.

    Args:
        code: A raw language or locale code (``"zh"``, ``"fr-FR"``, ``"en_US"``).

    Returns:
        The canonical supported code, or None for an empty or unsupported one —
        and for anything that is not a string: a test double's attribute is
        truthy and its ``startswith`` answers truthy, so it used to read as
        Chinese.
    """
    if not isinstance(code, str) or not code.strip():
        return None
    locale = code.strip().lower().replace("_", "-")
    if locale.startswith("zh"):
        return "zh-CN"
    return _BASE_CODES.get(locale.split("-")[0])


# Human-readable language names for LLM prompts. Name a language through
# ``core.i18n.get_language_name`` (it normalises the code first); never key this
# table on a raw locale.
# Typed as dict[str, str] to allow flexible key lookup (e.g., from DB values)
LANGUAGE_NAMES: dict[str, str] = {
    "fr": "French",
    "en": "English",
    "es": "Spanish",
    "de": "German",
    "it": "Italian",
    "zh-CN": "Simplified Chinese",
}


def _assert_one_vocabulary() -> None:
    """The tables naming the supported languages name the ``Language`` literal's.

    The base codes with the one regional code (derived, so checked by
    construction) and the names a model is told. ``SUPPORTED_LANGUAGES`` is
    derived from the literal in ``core.constants``. A language added to the
    literal and not to a table would be missing from it in silence — every
    table keyed on one of them reads the others' codes. A ``RuntimeError``,
    never an ``assert``: ``python -O`` strips an assert.

    Raises:
        RuntimeError: A declaration disagrees with the ``Language`` literal.
    """
    literal = set(get_args(Language))
    declarations: dict[str, set[str]] = {
        "_BASE_CODES + zh-CN": {*_BASE_CODES.values(), "zh-CN"},
        "LANGUAGE_NAMES": set(LANGUAGE_NAMES),
    }
    disagreeing = {
        name: sorted(codes ^ literal) for name, codes in declarations.items() if codes != literal
    }
    if disagreeing:
        raise RuntimeError(f"The supported languages disagree with Language: {disagreeing}")


_assert_one_vocabulary()


__all__ = [
    "Language",
    "SupportedLanguage",
    "LANGUAGE_NAMES",
    "canonical_language",
]
