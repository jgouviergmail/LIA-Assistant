"""Tables: typing by column unanimity, legal headers and names, chunks (ADR-274)."""

from datetime import date, datetime

import pytest

from src.domains.document_generation.schemas import TableSheet
from src.domains.document_generation.tables import (
    ColumnKind,
    chunk_rows,
    excel_table_name,
    infer_column_types,
    is_excel_legal_name,
    normalize_sheet,
    sanitize_headers,
    typed_value,
)

pytestmark = [pytest.mark.unit]


def _kinds(*columns: list[str]) -> list[ColumnKind]:
    rows = [list(row) for row in zip(*columns, strict=True)]
    headers = [f"h{index}" for index in range(len(columns))]
    return [column.kind for column in infer_column_types(headers, rows)]


class TestTypingIsByUnanimity:
    def test_a_column_whose_cells_all_agree_is_typed(self) -> None:
        assert _kinds(["1", "2", ""], ["1.5", "2.25", "3.0"], ["12%", "3.5 %", "0%"]) == [
            ColumnKind.INT,
            ColumnKind.DECIMAL,
            ColumnKind.PERCENT,
        ]
        assert _kinds(
            ["2026-09-08", "2026-01-01"], ["2026-09-08 14:30", "2026-09-08T09:00:00"]
        ) == [
            ColumnKind.DATE,
            ColumnKind.DATETIME,
        ]

    def test_one_stray_value_keeps_the_whole_column_text(self) -> None:
        """The rule that protects data: a column is never half-converted."""
        assert (
            _kinds(["1", "x"], ["2026-13-45", "2026-01-01"], ["1", "2026-01-01"])
            == [ColumnKind.TEXT] * 3
        )

    def test_integers_and_decimals_are_one_numeric_rule(self) -> None:
        """Prices whose round values lost their '.00' are still prices."""
        column = infer_column_types(["h"], [["1.5"], ["2"], ["3.25"]])[0]
        assert column.kind is ColumnKind.DECIMAL

    def test_codes_years_and_phones_land_where_the_data_demands(self) -> None:
        assert _kinds(["67000", "01000"])[0] is ColumnKind.TEXT  # a leading zero protects it
        assert _kinds(["2026", "2027"])[0] is ColumnKind.INT  # a year is an integer
        assert _kinds(["+33 6 12 34 56 78"])[0] is ColumnKind.TEXT
        assert _kinds(["=1+1", "2"])[0] is ColumnKind.TEXT
        assert _kinds([""])[0] is ColumnKind.TEXT  # nothing agreed on nothing

    def test_decimals_follow_the_widest_cell_and_formats_are_derived(self) -> None:
        column = infer_column_types(["h"], [["1.5"], ["2.125"], ["3.0"]])[0]
        assert column.decimals == 3 and column.number_format == "0.000"
        percent = infer_column_types(["h"], [["12%"], ["3.5%"]])[0]
        assert percent.number_format == "0.0%"
        assert infer_column_types(["h"], [["1"], ["2"]])[0].number_format == "0"
        assert infer_column_types(["h"], [["x"]])[0].number_format == "@"

    def test_more_decimals_than_a_reader_can_use_are_capped(self) -> None:
        column = infer_column_types(["h"], [["1.1234567"]])[0]
        assert column.kind is ColumnKind.TEXT  # beyond the 6-digit pattern: not a number we type

    def test_alignment_follows_the_type(self) -> None:
        assert infer_column_types(["h"], [["1"]])[0].numeric
        assert not infer_column_types(["h"], [["2026-01-01"]])[0].numeric


class TestTypedValues:
    def test_each_kind_converts(self) -> None:
        integer = infer_column_types(["h"], [["7"]])[0]
        assert typed_value("7", integer) == 7
        assert typed_value("", integer) is None
        assert typed_value("12.5%", infer_column_types(["h"], [["12.5%"]])[0]) == pytest.approx(
            0.125
        )
        assert typed_value("2026-09-08", infer_column_types(["h"], [["2026-09-08"]])[0]) == date(
            2026, 9, 8
        )
        assert typed_value(
            "2026-09-08 14:30", infer_column_types(["h"], [["2026-09-08 14:30"]])[0]
        ) == datetime(2026, 9, 8, 14, 30)

    def test_text_stays_neutralized(self) -> None:
        """The OWASP rule of ADR-226 survives the typing (probe 2026-08-17)."""
        text = infer_column_types(["h"], [["=1+1"]])[0]
        assert typed_value("=1+1", text) == "'=1+1"
        assert typed_value("-5.2", infer_column_types(["h"], [["-5.2"]])[0]) == -5.2


class TestHeadersAndRows:
    def test_headers_become_unique_and_non_empty(self) -> None:
        """Excel refuses the workbook otherwise — measured 2026-09-08."""
        assert sanitize_headers(["a", "A", "", "  b  ", "a"], "en") == [
            "a",
            "A (2)",
            "Column 3",
            "b",
            "a (3)",
        ]

    def test_generated_headers_speak_the_readers_language(self) -> None:
        assert sanitize_headers([""], "fr") == ["Colonne 1"]

    def test_ragged_rows_are_widened_never_truncated(self) -> None:
        sheet = normalize_sheet(
            TableSheet(name="s", headers=["a", "b"], rows=[["1"], ["1", "2", "3"], ["", " "]]),
            "en",
        )
        assert sheet is not None
        assert sheet.headers == ["a", "b", "Column 3"]
        assert sheet.rows == [["1", "", ""], ["1", "2", "3"]]  # the blank row is dropped

    def test_missing_headers_are_generated_and_an_empty_table_is_dropped(self) -> None:
        widened = normalize_sheet(TableSheet(name="s", headers=[], rows=[["x", "y"]]), "en")
        assert widened is not None and widened.headers == ["Column 1", "Column 2"]
        assert normalize_sheet(TableSheet(name="s", headers=[], rows=[]), "en") is None

    def test_a_header_only_table_survives(self) -> None:
        """A sheet with columns and no data is a legitimate template."""
        sheet = normalize_sheet(TableSheet(name="s", headers=["a"], rows=[]), "en")
        assert sheet is not None and sheet.rows == []


class TestExcelNamesAndChunks:
    def test_names_are_generated_and_legal(self) -> None:
        assert excel_table_name(1) == "Table1"
        assert is_excel_legal_name(excel_table_name(12))
        assert is_excel_legal_name("_x")

    @pytest.mark.parametrize("bad", ["Q1 2026", "1abc", "A1", "R1C1", "r1c1", "", "Ventes-2026"])
    def test_names_excel_would_refuse(self, bad: str) -> None:
        assert not is_excel_legal_name(bad)

    def test_chunks_keep_order_and_never_loop(self) -> None:
        assert chunk_rows([[str(i)] for i in range(5)], 2) == [
            [["0"], ["1"]],
            [["2"], ["3"]],
            [["4"]],
        ]
        assert chunk_rows([], 3) == []
        assert chunk_rows([["a"]], 0) == [[["a"]]]  # a zero size must not spin forever
