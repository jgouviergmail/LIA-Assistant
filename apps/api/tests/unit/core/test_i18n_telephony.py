"""Parity + accessor tests for the central telephony i18n module."""

from __future__ import annotations

import pytest

from src.core import i18n_telephony as it

_LANGS = {"fr", "en", "de", "es", "it", "zh"}


@pytest.mark.unit
def test_all_tables_cover_the_six_languages() -> None:
    assert set(it.DISCLOSURE_FIRST_MESSAGE) == _LANGS
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
    # zh-CN normalizes to zh.
    assert it.get_return_phrases("zh-CN") == it.RETURN_PHRASES["zh"]
    assert it.get_tool_phrases("fr-FR") == it.TOOL_PHRASES["fr"]
    assert it.get_availability_phrases("fr")["all_free"].startswith("Aucun")
    # Unknown / empty language → English fallback.
    assert it.get_return_phrases("ja") == it.RETURN_PHRASES["en"]
    assert it.get_disclosure_first_message(None) == it.DISCLOSURE_FIRST_MESSAGE["en"]


@pytest.mark.unit
def test_disclosure_and_tool_phrases_keep_dynamic_markers() -> None:
    # The agent disclosure must keep the ElevenLabs dynamic-variable markers.
    for msg in it.DISCLOSURE_FIRST_MESSAGE.values():
        assert "{{user_name}}" in msg and "{{objective}}" in msg
    # The tool clarification phrases keep their {name}/{candidates} placeholders.
    for phrases in it.TOOL_PHRASES.values():
        assert "{name}" in phrases["not_found"]
        assert "{name}" in phrases["ambiguous"] and "{candidates}" in phrases["ambiguous"]
