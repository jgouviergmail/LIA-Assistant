"""Renderer-generated labels exist in the six languages with the same keys (ADR-274).

The model writes the document in the reader's language; the renderer adds a
handful of words of its own — the table of contents heading, the page footer,
a table label, a generated column name — and those must exist in the six
languages too, or a French report grows an English footer.
"""

import re

import pytest

from src.core.i18n_documents import (
    DOCUMENT_LABELS,
    SUPPORTED_DOCUMENT_LABEL_LANGUAGES,
    document_label,
)

pytestmark = [pytest.mark.unit]
_PLACEHOLDER = re.compile(r"\{(\w+)\}")


class TestTheLabelsAreComplete:
    def test_six_languages_with_identical_key_sets(self) -> None:
        assert set(DOCUMENT_LABELS) == set(SUPPORTED_DOCUMENT_LABEL_LANGUAGES)
        assert set(DOCUMENT_LABELS) == {"fr", "en", "de", "es", "it", "zh-CN"}
        reference = set(DOCUMENT_LABELS["en"])
        for language, table in DOCUMENT_LABELS.items():
            assert set(table) == reference, language

    def test_identical_placeholders_everywhere(self) -> None:
        """A missing placeholder would drop the page number, not just reword it."""
        reference = DOCUMENT_LABELS["en"]
        for language, table in DOCUMENT_LABELS.items():
            for key, template in table.items():
                assert set(_PLACEHOLDER.findall(template)) == set(
                    _PLACEHOLDER.findall(reference[key])
                ), (language, key)

    def test_no_empty_or_untranslated_value(self) -> None:
        for language, table in DOCUMENT_LABELS.items():
            for key, template in table.items():
                assert template.strip(), (language, key)


class TestTheLabelsRender:
    def test_placeholders_are_filled_and_the_locale_is_normalised(self) -> None:
        assert document_label("fr-FR", "documents.page_of", page=2, total=5) == "Page 2 / 5"
        assert document_label("zh", "documents.toc_heading") == "目录"
        assert document_label("de", "documents.column_label", n=2) == "Spalte 2"

    def test_an_unknown_locale_follows_the_single_chokepoint(self) -> None:
        """``normalize_language`` decides — an unknown code lands on the deployment's
        default language, exactly as everywhere else in the backend, never on a
        second opinion of this module's own."""
        from src.core.config import settings
        from src.core.i18n import normalize_language

        expected = DOCUMENT_LABELS[normalize_language(settings.default_language)][
            "documents.table_label"
        ].format(n=3)
        assert document_label("xx", "documents.table_label", n=3) == expected

    def test_an_unknown_key_never_raises(self) -> None:
        """A renderer must not die on a label: the English wording is the floor."""
        assert document_label("fr", "documents.toc_heading") == "Sommaire"
        for language in DOCUMENT_LABELS:
            assert document_label(language, "documents.page_of", page=1, total=1)
