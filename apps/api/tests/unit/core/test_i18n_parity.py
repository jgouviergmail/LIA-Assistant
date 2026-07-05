"""Backend i18n parity guard — every language-keyed table covers all 6 languages.

The pre-commit hook enforces locale key parity for the FRONTEND only. This test
is the backend equivalent (ADR-085 model): it recursively scans the ``core.i18n_*``
modules for dicts keyed by language code and asserts each carries all supported
languages. A missing translation (e.g. a table with fr/en/es/de/it but no
``zh-CN``) fails the test, so a non-French user can never hit an untranslated key.
"""

from __future__ import annotations

import importlib

import pytest

from src.core.i18n import SUPPORTED_LANGUAGES

pytestmark = [pytest.mark.unit]

_SUPPORTED: frozenset[str] = frozenset(SUPPORTED_LANGUAGES)

# Tokens recognized as language codes when deciding whether a dict is keyed by
# language. Includes non-canonical Chinese spellings so a table that mistakenly
# uses "zh" instead of the canonical "zh-CN" is still detected (and flagged for
# missing "zh-CN").
_LANG_LIKE: frozenset[str] = _SUPPORTED | {"zh", "zh-cn", "zh-tw"}

# The i18n modules that hold user-facing translation tables.
_I18N_MODULES: tuple[str, ...] = (
    "i18n_hitl",
    "i18n_drafts",
    "i18n_api_messages",
    "i18n_v3",
    "i18n_dates",
    "i18n_patterns",
)

# Modules excluded from the *within-language key parity* check. i18n_patterns
# holds keyword/ordinal maps whose inner keys ARE the language's own words
# (French "cette", German "diese", …) — different keys per language is correct
# there, so key parity legitimately does not apply. The all-languages-present
# check still covers them.
_KEY_PARITY_EXCLUDED_MODULES: frozenset[str] = frozenset({"i18n_patterns"})


def _is_language_keyed(d: dict) -> bool:
    """Heuristic: is this dict keyed by language code (vs. keyed by an id)?

    A dict is language-keyed when it has ≥2 string keys, at least 60% of which
    look like language codes, and at least one is a supported language.
    """
    keys = [k for k in d if isinstance(k, str)]
    if len(keys) < 2:
        return False
    langish = sum(1 for k in keys if k in _LANG_LIKE)
    return langish >= 2 and langish >= len(keys) * 0.6 and bool(set(keys) & (_SUPPORTED | {"zh"}))


def _collect_gaps(obj: object, path: str, gaps: list[tuple[str, list[str]]]) -> None:
    """Recurse into ``obj``; record every language-keyed dict missing a language."""
    if not isinstance(obj, dict):
        return
    if _is_language_keyed(obj):
        missing = _SUPPORTED - set(obj.keys())
        if missing:
            gaps.append((path, sorted(missing)))
        return
    for key, value in obj.items():
        _collect_gaps(value, f"{path}[{key!r}]", gaps)


def _all_language_gaps() -> list[tuple[str, list[str]]]:
    gaps: list[tuple[str, list[str]]] = []
    for modname in _I18N_MODULES:
        module = importlib.import_module(f"src.core.{modname}")
        for name in dir(module):
            if name.startswith("__"):
                continue
            value = getattr(module, name)
            if isinstance(value, dict):
                _collect_gaps(value, f"{modname}.{name}", gaps)
    return gaps


def test_supported_languages_are_the_expected_six() -> None:
    """Guards the assumption this parity test is built on."""
    assert _SUPPORTED == {"fr", "en", "es", "de", "it", "zh-CN"}


def test_backend_i18n_tables_cover_all_supported_languages() -> None:
    """Every language-keyed i18n table declares all six supported languages."""
    gaps = _all_language_gaps()
    assert not gaps, "Backend i18n tables missing languages:\n" + "\n".join(
        f"  {path} → missing {missing}" for path, missing in gaps
    )


def _collect_key_parity_gaps(obj: object, path: str, gaps: list[tuple[str, list[str]]]) -> None:
    """For a language-keyed dict whose per-language values are dicts (shape
    ``dict[lang, dict[key, ...]]``), record any language whose key set differs
    from the union of keys across languages."""
    if not isinstance(obj, dict):
        return
    if _is_language_keyed(obj):
        sub = {
            lang: value
            for lang, value in obj.items()
            if lang in _SUPPORTED and isinstance(value, dict)
        }
        if len(sub) >= 2:
            union = set().union(*(set(v) for v in sub.values()))
            for lang, value in sub.items():
                missing = sorted(union - set(value))
                if missing:
                    gaps.append((f"{path}[{lang!r}]", missing))
        return
    for key, value in obj.items():
        _collect_key_parity_gaps(value, f"{path}[{key!r}]", gaps)


def test_backend_i18n_translation_tables_have_key_parity() -> None:
    """Translation tables keyed ``dict[lang, dict[key, ...]]`` must expose the
    same inner keys in every language (keyword/pattern maps are excluded)."""
    gaps: list[tuple[str, list[str]]] = []
    for modname in _I18N_MODULES:
        if modname in _KEY_PARITY_EXCLUDED_MODULES:
            continue
        module = importlib.import_module(f"src.core.{modname}")
        for name in dir(module):
            if name.startswith("__"):
                continue
            value = getattr(module, name)
            if isinstance(value, dict):
                _collect_key_parity_gaps(value, f"{modname}.{name}", gaps)
    assert not gaps, "Backend i18n tables with inconsistent keys across languages:\n" + "\n".join(
        f"  {path} → missing keys {missing}" for path, missing in gaps
    )
