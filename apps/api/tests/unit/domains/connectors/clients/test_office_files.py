"""What an Office file holds, read from real files (ADR-369, lot 11).

These files are built by the libraries that read them, never by a double: a mock of openpyxl would
prove nothing about what a workbook gives back. A file a third party wrote is hostile until proven
otherwise, so the budget and the refusals are tested on what would otherwise reach the parser.
"""

from __future__ import annotations

from datetime import date, datetime
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from docx import Document
from docx.oxml import OxmlElement
from openpyxl import Workbook
from pptx import Presentation

from src.core.constants import OFFICE_ARCHIVE_MAX_UNPACKED_BYTES, SHEETS_READ_MAX_COLUMNS
from src.domains.connectors.clients.office_files import (
    OfficeContentRefusedError,
    OfficeRefusal,
    SheetReading,
    _cell_text,
    append_word_text,
    read_rows,
    read_sheets,
    read_slides_text,
    read_word_text,
    read_workbook,
)

pytestmark = pytest.mark.unit


def _workbook(*sheets: tuple[str, list[list[object]]]) -> bytes:
    book = Workbook()
    book.remove(book.active)
    for title, rows in sheets:
        sheet = book.create_sheet(title)
        for row in rows:
            sheet.append(row)
    buffer = BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def _word(build: object) -> bytes:
    document = Document()
    build(document)  # type: ignore[operator]
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _archive(**parts: bytes) -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
        for name, content in parts.items():
            archive.writestr(name, content)
    return buffer.getvalue()


class TestAWorkbook:
    def test_its_sheets_are_named_with_what_the_file_declares(self) -> None:
        data = _workbook(("Dépenses", [["Poste", "Montant"], ["Loyer", 1200]]), ("Vide", []))

        sheets = read_sheets(data)

        assert [sheet["properties"]["title"] for sheet in sheets] == ["Dépenses", "Vide"]
        assert sheets[0]["properties"]["gridProperties"] == {"rowCount": 2, "columnCount": 2}

    def test_a_size_the_file_does_not_declare_is_no_zero(self) -> None:
        """A sheet part may carry no ``dimension``: « 0 rows » would be a false count."""
        buffer = BytesIO()
        with ZipFile(BytesIO(_workbook(("Feuille", [["a"]]))), "r") as source:
            with ZipFile(buffer, "w") as target:
                for item in source.infolist():
                    content = source.read(item.filename)
                    if item.filename == "xl/worksheets/sheet1.xml":
                        start = content.index(b"<dimension")
                        content = content[:start] + content[content.index(b"/>", start) + 2 :]
                    target.writestr(item.filename, content)

        assert "gridProperties" not in read_sheets(buffer.getvalue())[0]["properties"]

    def test_its_rows_read_as_displayed_text(self) -> None:
        data = _workbook(
            (
                "Feuille",
                [
                    ["Texte", 12, 12.5, 1200.0, True],
                    [date(2026, 11, 5), datetime(2026, 11, 5, 9, 30), None, "fin"],
                ],
            )
        )

        assert read_rows(data, "Feuille", 10) == [
            ["Texte", "12", "12.5", "1200", "TRUE"],
            ["2026-11-05", "2026-11-05 09:30:00", "", "fin"],
        ]

    def test_a_whole_number_stored_with_its_decimals_reads_without_them(self) -> None:
        """The parser hands 1200.0 back from a file that wrote it so: a person reads 1200."""
        assert _cell_text(1200.0) == "1200"
        assert _cell_text(1200.5) == "1200.5"

    def test_a_row_ends_on_its_last_value_and_the_sheet_on_its_last_row(self) -> None:
        data = _workbook(("Feuille", [["a", None, None], [None, None], ["b"], [None], [None]]))

        assert read_rows(data, "Feuille", 10) == [["a"], [], ["b"]]

    def test_the_read_stops_at_the_page(self) -> None:
        data = _workbook(("Feuille", [[f"r{index}"] for index in range(50)]))

        assert read_rows(data, "Feuille", 3) == [["r0"], ["r1"], ["r2"]]

    def test_the_sheet_named_is_the_one_read(self) -> None:
        data = _workbook(("A", [["premier"]]), ("B", [["second"]]))

        assert read_rows(data, "B", 5) == [["second"]]

    def test_a_row_is_read_as_far_as_a_google_sheet_is(self) -> None:
        wide = ["x"] * (SHEETS_READ_MAX_COLUMNS + 10)

        (row,) = read_rows(_workbook(("Feuille", [wide])), "Feuille", 5)

        assert len(row) == SHEETS_READ_MAX_COLUMNS

    def test_a_sheet_the_file_does_not_hold_is_refused(self) -> None:
        with pytest.raises(OfficeContentRefusedError) as refused:
            read_rows(_workbook(("A", [["x"]])), "B", 5)

        assert refused.value.refusal is OfficeRefusal.UNREADABLE


class TestAWorkbookRead:
    def test_each_sheet_comes_with_its_name_and_its_rows(self) -> None:
        data = _workbook(("Budget", [["a", 1]]), ("Team", [["b"], ["c"]]))

        assert read_workbook(data, sheets=5, rows=5, columns=5, cell_chars=50) == (
            [
                SheetReading("Budget", [["a", "1"]], False),
                SheetReading("Team", [["b"], ["c"]], False),
            ],
            False,
        )

    def test_a_sheet_past_its_rows_says_it_was_cut(self) -> None:
        data = _workbook(("Long", [["a"], ["b"], ["c"]]))

        sheets, _ = read_workbook(data, sheets=5, rows=2, columns=5, cell_chars=50)

        assert sheets == [SheetReading("Long", [["a"], ["b"]], True)]

    def test_a_sheet_of_exactly_its_rows_is_whole(self) -> None:
        data = _workbook(("Fits", [["a"], ["b"]]))

        sheets, _ = read_workbook(data, sheets=5, rows=2, columns=5, cell_chars=50)

        assert sheets == [SheetReading("Fits", [["a"], ["b"]], False)]

    def test_a_sheet_past_its_columns_says_it_was_cut(self) -> None:
        data = _workbook(("Wide", [["a", "b", "c"]]))

        sheets, _ = read_workbook(data, sheets=5, rows=5, columns=2, cell_chars=50)

        assert sheets == [SheetReading("Wide", [["a", "b"]], True)]

    def test_a_sheet_of_exactly_its_columns_is_whole(self) -> None:
        data = _workbook(("Fits", [["a", "b"]]))

        sheets, _ = read_workbook(data, sheets=5, rows=5, columns=2, cell_chars=50)

        assert sheets == [SheetReading("Fits", [["a", "b"]], False)]

    def test_sheets_past_the_bound_are_said(self) -> None:
        data = _workbook(("One", [["a"]]), ("Two", [["b"]]), ("Three", [["c"]]))

        sheets, more = read_workbook(data, sheets=2, rows=5, columns=5, cell_chars=50)

        assert [sheet.name for sheet in sheets] == ["One", "Two"]
        assert more is True

    def test_a_long_cell_stops_at_its_bound_and_says_so(self) -> None:
        data = _workbook(("Long", [["x" * 20]]))

        sheets, _ = read_workbook(data, sheets=5, rows=5, columns=5, cell_chars=8)

        assert sheets == [SheetReading("Long", [["x" * 8]], True)]

    def test_an_empty_sheet_is_a_sheet_with_no_rows(self) -> None:
        data = _workbook(("Empty", []))

        sheets, _ = read_workbook(data, sheets=5, rows=5, columns=5, cell_chars=50)

        assert sheets == [SheetReading("Empty", [], False)]

    def test_a_file_that_is_no_workbook_is_one_refusal(self) -> None:
        with pytest.raises(OfficeContentRefusedError) as refused:
            read_workbook(b"no archive", sheets=5, rows=5, columns=5, cell_chars=50)

        assert refused.value.refusal is OfficeRefusal.UNREADABLE


def _deck() -> bytes:
    deck = Presentation()
    first = deck.slides.add_slide(deck.slide_layouts[1])
    first.shapes.title.text = "Plan"
    first.placeholders[1].text = "Three points"
    first.notes_slide.notes_text_frame.text = "Said aloud"
    second = deck.slides.add_slide(deck.slide_layouts[5])
    second.shapes.title.text = "Figures"
    table = second.shapes.add_table(1, 2, 0, 0, 3000000, 500000).table
    table.cell(0, 0).text = "Sales"
    table.cell(0, 1).text = "12"
    written = BytesIO()
    deck.save(written)
    return written.getvalue()


class TestASlideDeck:
    def test_its_slides_read_in_order_tables_and_notes_included(self) -> None:
        text = read_slides_text(_deck())

        assert text.index("Plan") < text.index("Three points") < text.index("Figures")
        assert "Sales | 12" in text
        assert "Said aloud" in text

    def test_two_slides_stand_apart(self) -> None:
        assert "\n\nFigures" in read_slides_text(_deck())

    def test_a_file_that_is_no_deck_is_one_refusal(self) -> None:
        with pytest.raises(OfficeContentRefusedError) as refused:
            read_slides_text(b"no archive")

        assert refused.value.refusal is OfficeRefusal.UNREADABLE


class TestAWordDocument:
    def test_it_reads_in_the_documents_order(self) -> None:
        def build(document: Document) -> None:  # type: ignore[valid-type]
            document.add_heading("Compte rendu", level=1)
            document.add_paragraph("Présents :")
            table = document.add_table(rows=2, cols=2)
            table.cell(0, 0).text = "Nom"
            table.cell(0, 1).text = "Rôle"
            table.cell(1, 0).text = "Ana"
            table.cell(1, 1).text = "Cheffe"
            document.add_heading("Suite", level=2)
            document.add_paragraph("Un point", style="List Bullet")
            document.add_paragraph("   ")

        assert read_word_text(_word(build)).split("\n") == [
            "# Compte rendu",
            "Présents :",
            "Nom | Rôle",
            "Ana | Cheffe",
            "## Suite",
            "- Un point",
        ]

    def test_a_content_control_reads_like_what_it_holds(self) -> None:
        """A template's fields sit in one: skipping them would drop the words a person typed."""

        def build(document: Document) -> None:  # type: ignore[valid-type]
            field = document.add_paragraph("Dans un champ")._p
            control, content = OxmlElement("w:sdt"), OxmlElement("w:sdtContent")
            field.addprevious(control)
            control.append(content)
            content.append(field)
            document.add_paragraph("Après")

        assert read_word_text(_word(build)).split("\n") == ["Dans un champ", "Après"]

    def test_a_merged_cell_reads_once(self) -> None:
        def build(document: Document) -> None:  # type: ignore[valid-type]
            table = document.add_table(rows=1, cols=3)
            table.cell(0, 0).merge(table.cell(0, 1)).text = "Fusion"
            table.cell(0, 2).text = "Seule"

        assert read_word_text(_word(build)) == "Fusion | Seule"

    def test_text_is_added_after_what_it_holds_one_line_a_paragraph(self) -> None:
        def build(document: Document) -> None:  # type: ignore[valid-type]
            document.add_heading("Notes", level=1)
            document.add_paragraph("Existant")

        written = append_word_text(_word(build), "Ligne une\nLigne deux")

        assert read_word_text(written).split("\n") == [
            "# Notes",
            "Existant",
            "Ligne une",
            "Ligne deux",
        ]
        assert len(Document(BytesIO(written)).paragraphs) == 4

    def test_what_it_held_keeps_its_shape(self) -> None:
        def build(document: Document) -> None:  # type: ignore[valid-type]
            document.add_paragraph("Gras").runs[0].bold = True

        written = append_word_text(_word(build), "Ajout")

        assert Document(BytesIO(written)).paragraphs[0].runs[0].bold is True


class TestAFileNobodyVouchedFor:
    @pytest.mark.parametrize(
        "read",
        [
            read_sheets,
            lambda data: read_rows(data, "Feuille", 5),
            read_word_text,
            lambda data: append_word_text(data, "x"),
        ],
    )
    def test_bytes_that_are_no_archive_are_refused(self, read: object) -> None:
        with pytest.raises(OfficeContentRefusedError) as refused:
            read(b"\xd0\xcf\x11\xe0 a protected or an old format")  # type: ignore[operator]

        assert refused.value.refusal is OfficeRefusal.UNREADABLE

    @pytest.mark.parametrize("read", [read_sheets, read_word_text])
    def test_an_archive_that_holds_no_such_file_is_refused(self, read: object) -> None:
        with pytest.raises(OfficeContentRefusedError) as refused:
            read(_archive(**{"notes.txt": b"nothing"}))  # type: ignore[operator]

        assert refused.value.refusal is OfficeRefusal.UNREADABLE

    @pytest.mark.parametrize("read", [read_sheets, read_word_text])
    def test_an_archive_past_its_budget_never_reaches_the_parser(self, read: object) -> None:
        bomb = _archive(**{"word/document.xml": b"0" * (OFFICE_ARCHIVE_MAX_UNPACKED_BYTES + 1)})

        with pytest.raises(OfficeContentRefusedError) as refused:
            read(bomb)  # type: ignore[operator]

        assert refused.value.refusal is OfficeRefusal.TOO_LARGE
