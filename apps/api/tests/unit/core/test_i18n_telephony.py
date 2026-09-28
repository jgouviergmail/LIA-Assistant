"""Parity + accessor tests for the central telephony i18n module."""

from __future__ import annotations

import pytest

from src.core import i18n_telephony as it
from src.core.config import settings
from src.core.i18n import language_scope

_LANGS = {"fr", "en", "de", "es", "it", "zh-CN"}


@pytest.mark.unit
def test_all_tables_cover_the_six_languages() -> None:
    assert set(it.GREETING_FIRST_MESSAGE) == _LANGS
    assert set(it.AVAILABILITY_PHRASES) == _LANGS
    assert set(it.TOOL_PHRASES) == _LANGS
    assert set(it.RETURN_PHRASES) == _LANGS


@pytest.mark.unit
@pytest.mark.parametrize(
    "table",
    [it.AVAILABILITY_PHRASES, it.TOOL_PHRASES, it.RETURN_PHRASES],
)
def test_nested_tables_have_identical_sub_keys(table: dict) -> None:
    reference = set(table["en"])
    for lang, entry in table.items():
        assert set(entry) == reference, f"{lang} sub-keys drift from en"


@pytest.mark.unit
def test_accessors_normalize_and_fall_back() -> None:
    # Every spelling of Chinese reaches the canonical zh-CN entry.
    assert it.get_return_phrases("zh") == it.RETURN_PHRASES["zh-CN"]
    assert it.get_tool_phrases("fr-FR") == it.TOOL_PHRASES["fr"]
    assert it.get_availability_phrases("fr")["all_free"].startswith("Aucun")
    # An unsupported code reads as the instance default (ADR-323)...
    assert it.get_return_phrases("ja") == it.RETURN_PHRASES[settings.default_language]
    # ...and an absent one as the declared language.
    with language_scope("de"):
        assert it.get_return_phrases(None) == it.RETURN_PHRASES["de"]


@pytest.mark.unit
def test_tool_phrases_keep_dynamic_markers() -> None:
    # The tool clarification phrases keep their {name}/{candidates} placeholders.
    for phrases in it.TOOL_PHRASES.values():
        assert "{name}" in phrases["not_found"]
        assert "{name}" in phrases["ambiguous"] and "{candidates}" in phrases["ambiguous"]


@pytest.mark.unit
def test_greeting_keeps_user_name_marker_and_stays_short() -> None:
    """Identity-only instant greeting: {{user_name}} marker, no objective marker."""
    for lang, msg in it.GREETING_FIRST_MESSAGE.items():
        assert "{{user_name}}" in msg, lang
        assert "{{objective}}" not in msg, lang  # objective comes from the LLM turn
    assert it.get_greeting_first_message("fr-FR") == it.GREETING_FIRST_MESSAGE["fr"]
    with language_scope("it"):
        assert it.get_greeting_first_message(None) == it.GREETING_FIRST_MESSAGE["it"]
