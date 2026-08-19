"""Unit tests for the pricing workbook's translations.

The workbook is the administrator's working surface: its column headings, its
notice and its diagnostics are read, not merely displayed. They therefore go
through the backend i18n tables like every other user-visible string, in the
six supported languages — and Chinese is keyed on the backend canonical
``zh-CN``, never the frontend's ``zh``.
"""

from __future__ import annotations

import pytest

from src.core.i18n_pricing_sheet import (
    SHEET_LABEL_KEYS,
    build_sheet_labels,
    build_sheet_notice,
)
from src.domains.llm.pricing_sheet import MODELS_SHEET, SLOTS_SHEET
from src.domains.llm.pricing_sheet_rows import EXPORT_LABEL_KEYS

LANGUAGES = ("fr", "en", "es", "de", "it", "zh-CN")


@pytest.mark.unit
class TestCoverage:
    @pytest.mark.parametrize("language", LANGUAGES)
    def test_every_column_of_every_sheet_is_translated(self, language: str) -> None:
        labels = build_sheet_labels(language)
        for sheet in (MODELS_SHEET, SLOTS_SHEET):
            for column in sheet.columns:
                assert labels.get(column.label_key), f"{language}: {column.key}"

    @pytest.mark.parametrize("language", LANGUAGES)
    def test_every_derived_column_string_is_translated(self, language: str) -> None:
        """The status and summary texts are written into cells, not into logs."""
        labels = build_sheet_labels(language)
        for key in EXPORT_LABEL_KEYS:
            assert labels.get(key), f"{language}: {key}"

    @pytest.mark.parametrize("language", LANGUAGES)
    def test_structural_strings_are_translated(self, language: str) -> None:
        labels = build_sheet_labels(language)
        for key in ("sheet.notice", "sheet.referentials", "sheet.metadata"):
            assert labels.get(key), f"{language}: {key}"

    @pytest.mark.parametrize("language", LANGUAGES)
    def test_the_yes_no_words_are_translated(self, language: str) -> None:
        labels = build_sheet_labels(language)
        assert labels["boolean.true"] and labels["boolean.false"]
        assert labels["boolean.true"] != labels["boolean.false"]

    def test_the_published_key_list_matches_what_is_produced(self) -> None:
        assert set(SHEET_LABEL_KEYS) == set(build_sheet_labels("en"))


@pytest.mark.unit
class TestLanguageResolution:
    def test_chinese_is_keyed_on_the_backend_canonical_code(self) -> None:
        """The frontend spells it ``zh``; the tables are keyed ``zh-CN``."""
        assert build_sheet_labels("zh") == build_sheet_labels("zh-CN")

    def test_a_regional_variant_resolves_to_its_language(self) -> None:
        assert build_sheet_labels("fr-FR") == build_sheet_labels("fr")

    def test_an_unknown_language_falls_back_rather_than_failing(self) -> None:
        labels = build_sheet_labels("kl-GL")
        assert labels["boolean.true"]

    def test_translations_actually_differ_between_languages(self) -> None:
        """A table that silently returns English everywhere would pass every
        coverage check above and still ship an untranslated workbook."""
        french = build_sheet_labels("fr")
        english = build_sheet_labels("en")
        differing = [key for key in french if french[key] != english.get(key)]
        assert len(differing) > 20, "the two languages are suspiciously identical"


@pytest.mark.unit
class TestNotice:
    @pytest.mark.parametrize("language", LANGUAGES)
    def test_the_notice_is_translated_and_substantial(self, language: str) -> None:
        lines = build_sheet_notice(language)
        assert len(lines) >= 6
        assert all(isinstance(line, str) for line in lines)

    @pytest.mark.parametrize("language", LANGUAGES)
    def test_the_notice_states_the_rules_that_protect_the_administrator(
        self, language: str
    ) -> None:
        """Three rules an administrator cannot guess from the file itself."""
        joined = " ".join(build_sheet_notice(language)).lower()
        assert "is_active" in joined
        assert "row_fingerprint" not in joined, "an internal column must not be advertised"
        assert len(joined) > 200

    def test_the_notice_differs_between_languages(self) -> None:
        assert build_sheet_notice("fr") != build_sheet_notice("en")
