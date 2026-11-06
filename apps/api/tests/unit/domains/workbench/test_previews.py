"""What can be read of a document, for the mail and the files (ADR-369, lot 14).

The peek a generated document shows stops at 24 paragraphs and 7 rows: a person consulting a file
reads it, its cut said. A PDF and a Word file are served whole, for the page's viewers; the files
here are built by the libraries that read them. What is served never runs here: an HTML file is
its words, a table is rows of words.
"""

from __future__ import annotations

import codecs
import csv
import json
from io import BytesIO
from typing import Any
from unittest.mock import patch

import pytest
from docx import Document
from openpyxl import Workbook

from src.core.constants import (
    WORKBENCH_READING_MAX_COLUMNS,
    WORKBENCH_READING_MAX_ROWS,
    WORKBENCH_READING_MAX_SHEETS,
    WORKBENCH_READING_TEXT_MAX_BYTES,
)
from src.core.document_types import PDF_TYPE, SLIDES_TYPE, WORD_TYPE, WORKBOOK_TYPE
from src.core.exceptions import BaseAPIException
from src.domains.attachments.preview import DocumentPreview
from src.domains.connectors.clients import office_files
from src.domains.workbench import previews
from src.domains.workbench.errors import NOT_SUPPORTED_BY_PROVIDER

pytestmark = pytest.mark.unit

PNG = b"\x89PNG\r\n\x1a\nimage"
SHEETS_TYPE = "application/json"


def _word(*paragraphs: str) -> bytes:
    document = Document()
    for paragraph in paragraphs:
        document.add_paragraph(paragraph)
    written = BytesIO()
    document.save(written)
    return written.getvalue()


def _workbook(*sheets: tuple[str, list[list[object]]]) -> bytes:
    book = Workbook()
    book.remove(book.active)
    for name, rows in sheets:
        sheet = book.create_sheet(name)
        for row in rows:
            sheet.append(row)
    written = BytesIO()
    book.save(written)
    return written.getvalue()


def _sheets_of(shown: DocumentPreview) -> list[dict[str, Any]]:
    assert shown.media_type == SHEETS_TYPE
    sheets: list[dict[str, Any]] = json.loads(shown.content)["sheets"]
    return sheets


async def _refused(data: bytes, mime_type: str, name: str = "") -> Any:
    with pytest.raises(BaseAPIException) as refused:
        await previews.shown_document(data, mime_type, name)
    return refused.value.detail["code"]


class TestAWordDocument:
    async def test_it_is_served_as_itself_for_the_page_to_lay_out(self) -> None:
        data = _word("Paragraph")

        shown = await previews.shown_document(data, WORD_TYPE, "report.docx")

        assert shown == DocumentPreview(data, WORD_TYPE)

    async def test_a_file_that_is_no_archive_is_refused(self) -> None:
        assert await _refused(b"no archive", WORD_TYPE) == NOT_SUPPORTED_BY_PROVIDER

    async def test_an_archive_past_its_budget_never_reaches_the_page(self) -> None:
        with patch.object(office_files, "OFFICE_ARCHIVE_MAX_UNPACKED_BYTES", 10):
            assert await _refused(_word("Paragraph"), WORD_TYPE) == NOT_SUPPORTED_BY_PROVIDER


class TestASlideDeck:
    async def test_it_reads_as_its_words(self) -> None:
        with patch.object(previews, "read_slides_text", return_value="# Slide 1"):
            shown = await previews.shown_document(b"zip", SLIDES_TYPE, "deck.pptx")

        assert shown == DocumentPreview(b"# Slide 1", "text/plain")

    async def test_past_its_bound_it_is_cut_and_says_so(self) -> None:
        long_words = "word " * WORKBENCH_READING_TEXT_MAX_BYTES

        with patch.object(previews, "read_slides_text", return_value=long_words):
            shown = await previews.shown_document(b"zip", SLIDES_TYPE, "deck.pptx")

        assert shown.truncated is True
        assert len(shown.content) <= WORKBENCH_READING_TEXT_MAX_BYTES

    async def test_a_cut_keeps_a_character_whole(self) -> None:
        # An odd start: the bound then falls in the middle of a two-byte letter.
        text = "a" + "é" * WORKBENCH_READING_TEXT_MAX_BYTES

        with patch.object(previews, "read_slides_text", return_value=text):
            shown = await previews.shown_document(b"zip", SLIDES_TYPE, "deck.pptx")

        assert shown.truncated is True
        assert "�" not in shown.content.decode()

    async def test_a_file_no_parser_can_read_is_refused(self) -> None:
        assert await _refused(b"no archive", SLIDES_TYPE) == NOT_SUPPORTED_BY_PROVIDER


class TestATable:
    async def test_a_workbook_answers_each_sheet_with_its_name_and_rows(self) -> None:
        data = _workbook(("Budget", [["Item", "Cost"], ["Rent", 700]]), ("Team", [["Ana"]]))

        shown = await previews.shown_document(data, WORKBOOK_TYPE, "budget.xlsx")

        assert _sheets_of(shown) == [
            {"name": "Budget", "rows": [["Item", "Cost"], ["Rent", "700"]], "cut": False},
            {"name": "Team", "rows": [["Ana"]], "cut": False},
        ]
        assert shown.truncated is False

    async def test_a_workbook_with_no_sheet_to_read_shows_nothing(self) -> None:
        with patch.object(previews, "read_workbook", return_value=([], False)):
            assert await _refused(b"zip", WORKBOOK_TYPE) == NOT_SUPPORTED_BY_PROVIDER

    async def test_its_bounds_are_those_published(self) -> None:
        rows: list[list[object]] = [
            [f"{row}:{column}" for column in range(WORKBENCH_READING_MAX_COLUMNS + 2)]
            for row in range(WORKBENCH_READING_MAX_ROWS + 2)
        ]

        shown = await previews.shown_document(_workbook(("Wide", rows)), WORKBOOK_TYPE, "wide.xlsx")

        sheet = _sheets_of(shown)[0]
        assert len(sheet["rows"]) == WORKBENCH_READING_MAX_ROWS
        assert len(sheet["rows"][0]) == WORKBENCH_READING_MAX_COLUMNS
        assert sheet["cut"] is True
        assert shown.truncated is True

    async def test_sheets_past_the_bound_say_the_reading_was_cut(self) -> None:
        sheets = [(f"S{index}", [["a"]]) for index in range(WORKBENCH_READING_MAX_SHEETS + 1)]

        shown = await previews.shown_document(_workbook(*sheets), WORKBOOK_TYPE, "many.xlsx")

        assert len(_sheets_of(shown)) == WORKBENCH_READING_MAX_SHEETS
        assert shown.truncated is True

    @pytest.mark.parametrize(
        ("text", "rows"),
        [
            (b"a,b\n1,2\n", [["a", "b"], ["1", "2"]]),
            (b"a;b\n1;2\n", [["a", "b"], ["1", "2"]]),
            (b"a\tb\n1\t2\n", [["a", "b"], ["1", "2"]]),
            (b'"a,b";c\n', [["a,b", "c"]]),
            ("prénom,âge\n".encode(), [["prénom", "âge"]]),
        ],
    )
    async def test_a_csv_is_a_table_whatever_separates_it(
        self, text: bytes, rows: list[list[str]]
    ) -> None:
        shown = await previews.shown_document(text, "text/csv", "export.csv")

        assert _sheets_of(shown) == [{"name": "", "rows": rows, "cut": False}]

    @pytest.mark.parametrize("line_end", [b"\r", b"\r\n", b"\n"])
    async def test_a_csv_of_any_line_end_is_a_table(self, line_end: bytes) -> None:
        text = line_end.join([b"a,b", b"c,d", b""])

        shown = await previews.shown_document(text, "text/csv", "export.csv")

        assert _sheets_of(shown)[0]["rows"] == [["a", "b"], ["c", "d"]]

    async def test_a_csv_no_reader_can_take_stays_its_words(self) -> None:
        with patch.object(previews.csv, "reader", side_effect=csv.Error("no")):
            shown = await previews.shown_document(b"a,b\n", "text/csv", "export.csv")

        assert shown == DocumentPreview(b"a,b\n", "text/plain", False)

    async def test_a_windows_csv_keeps_its_accents(self) -> None:
        text = "prénom;âge\n".encode("cp1252")

        shown = await previews.shown_document(text, "text/csv", "export.csv")

        assert _sheets_of(shown)[0]["rows"] == [["prénom", "âge"]]

    async def test_a_csv_that_declares_nothing_is_a_table_by_its_name(self) -> None:
        shown = await previews.shown_document(b"a;b\n", "application/octet-stream", "export.csv")

        assert _sheets_of(shown)[0]["rows"] == [["a", "b"]]

    async def test_a_csv_past_its_rows_is_cut_and_says_so(self) -> None:
        text = "\n".join(f"{index},x" for index in range(WORKBENCH_READING_MAX_ROWS + 5)).encode()

        shown = await previews.shown_document(text, "text/csv", "long.csv")

        assert len(_sheets_of(shown)[0]["rows"]) == WORKBENCH_READING_MAX_ROWS
        assert shown.truncated is True

    async def test_a_line_the_byte_bound_broke_is_left_out(self) -> None:
        line = ",".join(["x" * 24] * 40) + "\n"
        lines = WORKBENCH_READING_TEXT_MAX_BYTES // len(line) + 2

        shown = await previews.shown_document((line * lines).encode(), "text/csv", "long.csv")

        rows = _sheets_of(shown)[0]["rows"]
        assert {len(row) for row in rows} == {WORKBENCH_READING_MAX_COLUMNS}

    async def test_a_csv_cut_at_its_bytes_says_so_and_drops_its_broken_line(self) -> None:
        text = ("a,b\n" * (WORKBENCH_READING_TEXT_MAX_BYTES // 4 + 1)).encode() + b"last,line"

        shown = await previews.shown_document(text, "text/csv", "long.csv")

        assert shown.truncated is True
        assert ["last", "line"] not in _sheets_of(shown)[0]["rows"]


class TestTheLettersOfAText:
    async def test_a_windows_text_keeps_its_accents(self) -> None:
        shown = await previews.shown_document("déjà vu".encode("cp1252"), "text/plain", "a.txt")

        assert shown.content.decode() == "déjà vu"

    @pytest.mark.parametrize("encoding", ["utf-16", "utf-16-le", "utf-16-be"])
    async def test_a_text_windows_marked_as_utf16_is_read_as_it_says(self, encoding: str) -> None:
        mark = {"utf-16-le": codecs.BOM_UTF16_LE, "utf-16-be": codecs.BOM_UTF16_BE}.get(
            encoding, b""
        )

        shown = await previews.shown_document(
            mark + "déjà vu".encode(encoding), "text/plain", "a.txt"
        )

        assert shown.content.decode() == "déjà vu"

    async def test_utf8_is_read_as_utf8(self) -> None:
        shown = await previews.shown_document("déjà vu".encode(), "text/plain", "a.txt")

        assert shown.content.decode() == "déjà vu"

    async def test_a_letter_the_bound_cuts_never_turns_the_whole_text_into_another(self) -> None:
        # An odd start: the bound then falls in the middle of a two-byte letter.
        text = ("a" + "é" * WORKBENCH_READING_TEXT_MAX_BYTES).encode()

        shown = await previews.shown_document(text, "text/plain", "a.txt")

        assert set(shown.content.decode()) == {"a", "é"}
        assert shown.truncated is True

    async def test_a_text_under_the_bound_is_whole(self) -> None:
        text = b"a" * WORKBENCH_READING_TEXT_MAX_BYTES

        shown = await previews.shown_document(text, "text/plain", "a.txt")

        assert shown == DocumentPreview(text, "text/plain", False)

    async def test_a_mark_is_no_letter(self) -> None:
        shown = await previews.shown_document(b"\xef\xbb\xbfhello", "text/plain", "a.txt")

        assert shown.content == b"hello"

    async def test_a_utf16_letter_the_bound_cuts_is_left_out_whole(self) -> None:
        # Four bytes a letter, after a two-byte mark: the bound falls inside one.
        text = codecs.BOM_UTF16_LE + ("😀" * WORKBENCH_READING_TEXT_MAX_BYTES).encode("utf-16-le")

        shown = await previews.shown_document(text, "text/plain", "a.txt")

        assert set(shown.content.decode()) == {"😀"}

    async def test_a_utf16_text_keeps_its_letters_past_the_bound(self) -> None:
        text = codecs.BOM_UTF16_LE + ("é" * WORKBENCH_READING_TEXT_MAX_BYTES).encode("utf-16-le")

        shown = await previews.shown_document(text, "text/plain", "a.txt")

        assert set(shown.content.decode()) == {"é"}
        assert shown.truncated is True


class TestAnythingElse:
    @pytest.mark.parametrize(
        ("mime_type", "name"),
        [
            ("text/html", "page.html"),
            ("application/json", "data.json"),
            ("application/octet-stream", "server.log"),
        ],
    )
    async def test_a_text_is_its_words_never_a_page(self, mime_type: str, name: str) -> None:
        words = b"<script>alert(1)</script>"

        shown = await previews.shown_document(words, mime_type, name)

        assert shown == DocumentPreview(words, "text/plain", False)

    async def test_a_markdown_says_it_is_one_for_the_page_to_lay_it_out(self) -> None:
        shown = await previews.shown_document(b"# Title", "application/octet-stream", "notes.md")

        assert shown == DocumentPreview(b"# Title", "text/markdown", False)

    async def test_a_pdf_is_served_whole(self) -> None:
        shown = await previews.shown_document(b"%PDF", "application/octet-stream", "a.pdf")

        assert shown == DocumentPreview(b"%PDF", PDF_TYPE)

    async def test_an_image_is_itself(self) -> None:
        shown = await previews.shown_document(PNG, "image/png; name=a.png", "a.png")

        assert shown == DocumentPreview(PNG, "image/png")

    @pytest.mark.parametrize(
        "mime_type", ["image/png evil", "image/svg+xml", "image/heic", "image/tiff"]
    )
    async def test_an_image_no_page_can_draw_is_refused(self, mime_type: str) -> None:
        assert await _refused(PNG, mime_type, "a") == NOT_SUPPORTED_BY_PROVIDER

    @pytest.mark.parametrize(
        ("mime_type", "name"), [("application/octet-stream", "a.exe"), ("", ""), ("audio/mpeg", "")]
    )
    async def test_what_nothing_can_show_is_refused(self, mime_type: str, name: str) -> None:
        assert await _refused(b"x", mime_type, name) == NOT_SUPPORTED_BY_PROVIDER


class TestWhatThePageIsTold:
    @pytest.mark.parametrize(
        ("mime_type", "name", "offered"),
        [
            ("image/jpeg", "a.jpg", True),
            ("application/pdf", "a.pdf", True),
            ("application/octet-stream", "notes.md", True),
            ("text/plain", "a", True),
            (WORD_TYPE, "a", True),
            ("application/octet-stream", "a.exe", False),
            ("image/svg+xml", "a.svg", False),
            ("image/heic", "a.heic", False),
            ("audio/mpeg", "a.mp3", False),
            ("", "", False),
        ],
    )
    def test_it_is_offered_what_can_be_shown(
        self, mime_type: str, name: str, offered: bool
    ) -> None:
        assert previews.can_be_shown(mime_type, name) is offered
