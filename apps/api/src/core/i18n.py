"""
Internationalization (i18n) utilities using gettext.

Provides translation functions for API error messages, validation errors,
and user-facing text. LLM prompts are NOT translated (LLMs understand all languages).

Supported languages: fr, en, es, de, it, zh-CN

A sentence written without an explicit language is written in the DECLARED one
(ADR-323): the language of the current request, turn or job, declared where the
person becomes known (``declare_language`` / ``language_scope``) and read by
``resolve_language``. No parameter carries a language as its default — a literal
default writes that language to everybody who is not passed explicitly.
"""

import gettext
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from functools import lru_cache
from pathlib import Path

import structlog

from src.core.config import settings
from src.core.constants import LANGUAGE_TO_LOCALE
from src.core.i18n_types import LANGUAGE_NAMES, Language, canonical_language

logger = structlog.get_logger(__name__)

# The languages this instance offers (settings, canonical): a filter on what a
# request may declare, never a fallback — the fallback is DEFAULT_LANGUAGE.
SUPPORTED_LANGUAGES: list[Language] = settings.supported_languages  # type: ignore[assignment]

# Locale directory path (relative to project root)
LOCALE_DIR = Path(__file__).parent.parent.parent / "locales"


def normalize_language(language: str | None) -> Language:
    """Normalize a language code to the canonical backend format.

    Single chokepoint for language-code normalization (audit wave 2, zh):
    the frontend spells Chinese ``zh`` (URLs, locale files) while the backend
    canonical code is ``zh-CN`` (``User.language``, ``SUPPORTED_LANGUAGES``,
    i18n table keys). Every consumer keying a table by language must call
    this function first — never key a table on a raw incoming locale.

    This is the reading of a GIVEN language — a person's stored preference, a
    payload's field. A language ABSENT from the current context is resolved by
    :func:`resolve_language`, which prefers the declared one.

    Args:
        language: Raw locale (e.g., "zh", "zh-CN", "zh_CN", "fr-FR", "en_US"),
            or None/empty.

    Returns:
        Canonical Language code; the instance's configured default language
        for an empty or unsupported one.
    """
    return canonical_language(language) or settings.default_language


# The language declared for the current request, turn or job. Set where the
# person becomes known — the Accept-Language of a request, the authenticated
# account's own language, the account an out-of-turn run serves — and read by
# ``resolve_language`` wherever a sentence is written without an explicit one.
_declared_language: ContextVar[Language | None] = ContextVar("declared_language", default=None)


def resolve_language(language: str | None = None) -> Language:
    """Return the language a sentence is written in.

    The caller's explicit language wins (normalised); otherwise the language
    declared for the current request, turn or job; otherwise the instance's
    configured ``DEFAULT_LANGUAGE``. A function that takes an optional language
    writes in ``resolve_language(language)``. A code bound for a PROVIDER (a
    Wikipedia edition, a Places request) keeps an explicit value verbatim and
    resolves only its absence — ``language or resolve_language()`` — since the
    provider may speak a code of its own (``zh-TW`` is not ``zh-CN``).

    Args:
        language: An explicit language code, or None/empty to use the declared one.

    Returns:
        The canonical language code to write in.
    """
    if language:
        return normalize_language(language)
    return _declared_language.get() or settings.default_language


def declare_language(language: str | None) -> None:
    """Declare the language of the rest of the current task.

    For a request, a turn or a job whose task ends with it: set once, where the
    person becomes known, and dropped with the task — nothing to restore. A block
    that must restore the previous value uses :func:`language_scope`. An empty
    language declares nothing.

    Args:
        language: The person's language code, or None when unknown.
    """
    if language:
        _declared_language.set(normalize_language(language))


@contextmanager
def language_scope(language: str | None) -> Iterator[None]:
    """Declare a language for the duration of a block, then restore the previous one.

    Args:
        language: The language to declare, or None/empty to keep the current one.

    Yields:
        None.
    """
    if not language:
        yield
        return
    token = _declared_language.set(normalize_language(language))
    try:
        yield
    finally:
        _declared_language.reset(token)


def get_language_name(language: str) -> str:
    """Name a language for a model, from any spelling of its code.

    The one door between a stored or incoming locale and the word a prompt
    carries: ``"zh"``, ``"zh_CN"`` and ``"zh-CN"`` all read « Simplified Chinese »,
    ``"fr-FR"`` reads « French ». A raw code in a prompt is a coin toss on how the
    model interprets it (prompt audit 2026-09-12, lot 3).

    Args:
        language: Raw locale (e.g., "zh", "zh-CN", "fr-FR", "en_US").

    Returns:
        The human-readable name of the normalised language; an unsupported code
        names the configured default language, like every other consumer.
    """
    return LANGUAGE_NAMES[normalize_language(language)]


def get_locale_for_language(language: str | None) -> str:
    """Map a raw language code to a valid BCP 47 display locale.

    Replaces the buggy ``f"{lang}-{lang.upper()}"`` derivation, which
    produced nonexistent locales such as "en-EN" or "zh-ZH" (audit wave 3,
    N-129). Normalizes first, so any incoming spelling ("zh", "en_US",
    "fr-FR") resolves to its canonical display locale.

    Args:
        language: Raw language/locale code, or None for the declared language.

    Returns:
        BCP 47 locale (e.g., "en-US", "zh-CN", "fr-FR").
    """
    # Direct indexing on purpose: resolve_language returns a canonical
    # supported code and the boot-time assert in constants guarantees the
    # mapping is complete — a KeyError here means broken config, not a
    # situation to paper over with a silent fallback.
    return LANGUAGE_TO_LOCALE[resolve_language(language)]


@lru_cache(maxsize=10)
def get_translator(language: Language) -> gettext.NullTranslations:
    """
    Get cached gettext translator for language.

    Falls back to the instance's default language if the requested catalog is
    missing — a broken deployment, since the six are guarded to exist.

    Args:
        language: Canonical target language code (one of the six supported)

    Returns:
        NullTranslations instance for the language

    Example:
        >>> translator = get_translator("en")
        >>> translator.gettext("Preferences updated")
        "Preferences updated"
    """
    try:
        return gettext.translation(
            "messages",
            localedir=str(LOCALE_DIR),
            languages=[language],
            fallback=False,
        )
    except FileNotFoundError:
        logger.warning(
            "translation_not_found_using_fallback",
            requested_language=language,
            fallback_language=settings.default_language,
        )
        return gettext.translation(
            "messages",
            localedir=str(LOCALE_DIR),
            languages=[settings.default_language],
            fallback=True,
        )


def _(text: str, language: str | None = None) -> str:
    """
    Translate text to target language using gettext.

    Main translation function for API messages. Use this for all user-facing
    error messages, validation errors, and status messages. Every msgid a call
    names must be translated in the six catalogs (``apps/api/locales``), which
    hold nothing else — guarded by ``test_gettext_catalog_guard.py``.

    Args:
        text: English text to translate (source language)
        language: Any spelling of a language code (normalised); the declared
            language when absent

    Returns:
        Translated text in target language

    Example:
        >>> _("Preferences updated", "en")
        "Preferences updated"
        >>> _("Preferences updated", "fr")
        "Préférences mises à jour"
    """
    translator = get_translator(resolve_language(language))
    return translator.gettext(text)


def _header_weight(params: list[str]) -> float | None:
    """The ``q`` weight among an Accept-Language entry's parameters.

    Args:
        params: The entry's parameters, after its language tag.

    Returns:
        The weight (1 when the entry states none), or None for a malformed one.
    """
    for param in params:
        name, _eq, value = param.partition("=")
        if name.strip().lower() == "q":
            try:
                weight = float(value)
            except ValueError:
                return None
            # RFC 9110: a qvalue lies in [0, 1]; ``nan``, ``inf`` or ``2`` is malformed.
            return weight if 0.0 <= weight <= 1.0 else None
    return 1.0


def language_from_header(accept_language: str | None) -> Language | None:
    """Return the supported language an Accept-Language header prefers.

    Entries rank by their ``q`` weight, ties keeping the order the client wrote
    them; an entry weighted ``q=0`` is a language the client REFUSES and is never
    chosen, and a malformed weight drops its entry. Each tag is canonicalised by
    the single chokepoint, so ``zh``, ``zh-TW`` and ``zh-CN`` all name Chinese.

    Args:
        accept_language: Accept-Language header value (e.g., "fr-FR,fr;q=0.9,en;q=0.8").

    Returns:
        The canonical code of the preferred supported entry, or None when the
        header names none — a request that says nothing declares nothing.
    """
    ranked: list[tuple[float, int, Language]] = []
    for position, entry in enumerate((accept_language or "").split(",")):
        tag, *params = entry.split(";")
        weight = _header_weight(params)
        canonical = canonical_language(tag)
        if weight is None or weight <= 0 or canonical is None:
            continue
        if canonical in SUPPORTED_LANGUAGES:
            ranked.append((-weight, position, canonical))
    return min(ranked)[2] if ranked else None
