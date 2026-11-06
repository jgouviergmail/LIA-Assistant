"""What a document reads as, whatever its type says (ADR-369, lot 14).

OneDrive declares ``application/octet-stream`` for a Markdown file, a CSV and a log (measured on a
real drive, 2026-11-05) and a mail says what its sender's client thought: a type that says nothing
readable falls back on the name, and a type that does say wins over it.
"""

from __future__ import annotations

import pytest

from src.core.document_types import (
    CSV_TYPE,
    PDF_TYPE,
    SLIDES_TYPE,
    WORD_TYPE,
    WORKBOOK_TYPE,
    is_text_type,
    plain_type,
    reading_type,
)

pytestmark = pytest.mark.unit


class TestADeclaredType:
    @pytest.mark.parametrize(
        ("declared", "plain"),
        [
            ("text/plain", "text/plain"),
            ("TEXT/PLAIN; charset=utf-8", "text/plain"),
            ("  application/PDF ; name=a.pdf", "application/pdf"),
            ("", ""),
        ],
    )
    def test_it_is_read_without_its_parameters(self, declared: str, plain: str) -> None:
        assert plain_type(declared) == plain


class TestWhatADocumentReadsAs:
    @pytest.mark.parametrize(
        ("declared", "name", "expected"),
        [
            ("text/plain", "notes.txt", "text/plain"),
            ("text/plain; charset=utf-8", "notes", "text/plain"),
            ("application/json", "data.json", "application/json"),
            ("text/html", "page.html", "text/html"),
            (WORD_TYPE, "report", WORD_TYPE),
            (PDF_TYPE, "report", PDF_TYPE),
        ],
    )
    def test_a_type_that_says_is_taken_at_its_word(
        self, declared: str, name: str, expected: str
    ) -> None:
        assert reading_type(declared, name) == expected

    @pytest.mark.parametrize(
        ("declared", "name", "expected"),
        [
            ("application/octet-stream", "notes.md", "text/markdown"),
            ("application/octet-stream", "NOTES.MD", "text/markdown"),
            ("application/octet-stream", "export.csv", CSV_TYPE),
            ("application/octet-stream", "export.tsv", CSV_TYPE),
            ("application/octet-stream", "server.log", "text/plain"),
            ("application/vnd.ms-excel", "export.csv", CSV_TYPE),
            ("", "report.docx", WORD_TYPE),
            ("application/octet-stream", "budget.xlsx", WORKBOOK_TYPE),
            ("application/octet-stream", "talk.pptx", SLIDES_TYPE),
            ("application/octet-stream", "scan.pdf", PDF_TYPE),
        ],
    )
    def test_a_type_that_says_nothing_leaves_it_to_the_name(
        self, declared: str, name: str, expected: str
    ) -> None:
        assert reading_type(declared, name) == expected

    def test_a_type_that_says_wins_over_the_name(self) -> None:
        assert reading_type(PDF_TYPE, "notes.md") == PDF_TYPE

    @pytest.mark.parametrize(
        ("declared", "name"),
        [
            ("application/octet-stream", "setup.exe"),
            ("application/zip", "archive.zip"),
            ("image/png", "photo.png"),
            ("", ""),
            ("", "no-extension"),
        ],
    )
    def test_nothing_is_claimed_of_what_neither_names(self, declared: str, name: str) -> None:
        assert reading_type(declared, name) is None


class TestWhatIsText:
    @pytest.mark.parametrize(
        "kind", ["text/plain", "text/markdown", CSV_TYPE, "text/html", "application/json"]
    )
    def test_what_a_person_can_type_is_text(self, kind: str) -> None:
        assert is_text_type(kind) is True

    @pytest.mark.parametrize("kind", [PDF_TYPE, WORD_TYPE, WORKBOOK_TYPE, SLIDES_TYPE, None])
    def test_a_format_of_its_own_is_not(self, kind: str | None) -> None:
        assert is_text_type(kind) is False
