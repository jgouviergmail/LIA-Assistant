"""Parity + accessor tests for the bookmarks knowledge-space i18n module.

The auto-created « Kept answers » space and the rendered document header are
written by the BACKEND in the person's language, so every string here must
exist in the six languages, keyed by the backend-canonical code (``zh-CN``).
"""

from __future__ import annotations

import pytest

from src.core import i18n_bookmarks as ib
from src.core.i18n import normalize_language

pytestmark = pytest.mark.unit

_LANGS = {"en", "fr", "de", "es", "it", "zh-CN"}


def test_every_table_covers_the_six_languages() -> None:
    for table in (ib.SPACE_NAME, ib.SPACE_DESCRIPTION, ib.DOCUMENT_LABELS):
        assert set(table) == _LANGS


def test_document_labels_have_identical_keys_in_every_language() -> None:
    reference = set(ib.DOCUMENT_LABELS["en"])
    assert reference == {"name", "title", "request", "no_request", "answered_on"}
    for lang, entry in ib.DOCUMENT_LABELS.items():
        assert set(entry) == reference, f"{lang} drifts from en"


def test_the_title_keeps_its_date_marker_everywhere() -> None:
    for lang, entry in ib.DOCUMENT_LABELS.items():
        assert "{date}" in entry["title"], lang


def test_accessors_normalise_the_raw_locale_through_the_single_chokepoint() -> None:
    # The frontend spells Chinese ``zh``; the backend table is keyed ``zh-CN``.
    assert ib.get_space_name("zh") == ib.SPACE_NAME["zh-CN"]
    assert ib.get_space_description("fr-FR") == ib.SPACE_DESCRIPTION["fr"]
    # An unknown or missing locale falls back to what the chokepoint decides
    # (the configured default language), never to a choice of this module.
    assert ib.get_document_labels("ja") == ib.DOCUMENT_LABELS[normalize_language("ja")]
    assert ib.get_space_name(None) == ib.SPACE_NAME[normalize_language("")]


def test_no_value_is_empty() -> None:
    for table in (ib.SPACE_NAME, ib.SPACE_DESCRIPTION):
        assert all(value.strip() for value in table.values())
    for entry in ib.DOCUMENT_LABELS.values():
        assert all(value.strip() for value in entry.values())
