"""How a typed value reads in the reader's language (ADR-274 amendment).

Word, PDF, slides and Markdown show TEXT, so the renderer writes the reader's
conventions; Excel shows a NUMBER through a format code, and the reader's own
system draws the separators. Both are pinned here, value by value.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pytest

from src.core.i18n_types import LANGUAGE_NAMES
from src.domains.document_generation.numbers import CONVENTIONS, display, excel_format

pytestmark = [pytest.mark.unit]

NNBSP, NBSP = " ", " "


class TestTheReaderReadsTheirOwnConventions:
    @pytest.mark.parametrize(
        ("language", "expected"),
        [
            ("fr", f"1{NNBSP}234,50{NBSP}€"),
            ("de", f"1.234,50{NBSP}€"),
            ("es", f"1.234,50{NBSP}€"),
            ("it", f"1.234,50{NBSP}€"),
            ("en", "€1,234.50"),
            ("zh-CN", "€1,234.50"),
        ],
    )
    def test_an_amount(self, language: str, expected: str) -> None:
        assert display(Decimal("1234.5"), "amount", "EUR", 2, language) == expected

    def test_a_negative_amount_keeps_its_sign_before_everything(self) -> None:
        assert display(Decimal("-1234.5"), "amount", "USD", 2, "en") == "-$1,234.50"
        assert display(Decimal("-1234.5"), "amount", "EUR", 2, "fr") == f"-1{NNBSP}234,50{NBSP}€"

    def test_an_alphabetic_currency_is_spaced_from_the_number(self) -> None:
        assert display(Decimal("12"), "amount", "CHF", 2, "en") == f"CHF{NBSP}12.00"

    def test_an_unknown_currency_code_reads_as_itself(self) -> None:
        assert display(Decimal("12"), "amount", "XYZ", 0, "fr") == f"12{NBSP}XYZ"

    def test_an_amount_without_unit_is_a_grouped_number(self) -> None:
        assert display(Decimal("1234567"), "amount", "", 0, "en") == "1,234,567"

    @pytest.mark.parametrize(
        ("language", "expected"),
        [("fr", f"12,5{NNBSP}%"), ("de", f"12,5{NBSP}%"), ("en", "12.5%"), ("zh-CN", "12.5%")],
    )
    def test_a_percentage(self, language: str, expected: str) -> None:
        assert display(Decimal("0.125"), "percent", "", 1, language) == expected

    def test_a_quantity_carries_its_unit(self) -> None:
        assert display(Decimal("1234.5"), "quantity", "kg", 1, "fr") == f"1{NNBSP}234,5{NBSP}kg"

    def test_a_year_and_a_code_are_never_grouped(self) -> None:
        assert display(Decimal("2026"), "year", "", 0, "en") == "2026"
        assert display("01000", "code", "", 0, "fr") == "01000"

    @pytest.mark.parametrize(
        ("language", "expected"),
        [("fr", "01/09/2026"), ("de", "01.09.2026"), ("en", "2026-09-01"), ("zh-CN", "2026-09-01")],
    )
    def test_a_date(self, language: str, expected: str) -> None:
        assert display(date(2026, 9, 1), "date", "", 0, language) == expected

    def test_a_datetime(self) -> None:
        assert display(datetime(2026, 9, 1, 14, 5), "datetime", "", 0, "fr") == "01/09/2026 14:05"

    def test_rounding_is_half_away_from_zero_like_the_workbook(self) -> None:
        assert display(Decimal("2.345"), "amount", "", 2, "en") == "2.35"
        assert display(Decimal("-2.345"), "amount", "", 2, "en") == "-2.35"

    @pytest.mark.parametrize(
        ("value", "kind", "decimals", "expected"),
        [
            ("-0.005", "amount", 2, "-0.01"),
            ("-0.5", "quantity", 0, "-1"),
            ("-0.0005", "percent", 1, "-0.1%"),
        ],
    )
    def test_a_negative_value_rounded_away_from_zero_keeps_its_sign(
        self, value: str, kind: str, decimals: int, expected: str
    ) -> None:
        """The sign follows the rounding of the number it stands before: Excel
        shows -0.01 for -0.005, never a positive 0.01."""
        assert display(Decimal(value), kind, "", decimals, "en") == expected

    def test_a_negative_value_rounded_to_zero_reads_no_minus(self) -> None:
        assert display(Decimal("-0.004"), "amount", "", 2, "en") == "0.00"

    def test_a_number_longer_than_a_decimal_context_is_written_whole(self) -> None:
        """6^40 has 32 digits: rounding it must not depend on the 28 a context keeps."""
        assert display(Decimal(6**40), "amount", "", 2, "en") == f"{6**40:,}.00"
        assert display(Decimal(-(10**300)), "quantity", "", 0, "en") == f"-{10**300:,}"

    def test_nothing_reads_as_nothing(self) -> None:
        assert display(None, "amount", "EUR", 2, "fr") == ""

    def test_every_language_has_its_conventions(self) -> None:
        assert set(CONVENTIONS) == set(LANGUAGE_NAMES)


class TestExcelDrawsTheSeparatorsItself:
    def test_an_amount_format_puts_the_currency_on_the_reader_side(self) -> None:
        assert excel_format("amount", "EUR", 2, "fr") == '#,##0.00" €";[Red]-#,##0.00" €"'
        assert excel_format("amount", "USD", 0, "en") == '"$"#,##0;[Red]-"$"#,##0'

    def test_a_quantity_a_percentage_a_year_a_code(self) -> None:
        assert excel_format("quantity", "kg", 1, "en") == '#,##0.0" kg"'
        assert excel_format("percent", "", 1, "en") == "0.0%"
        assert excel_format("year", "", 0, "en") == "0"
        assert excel_format("code", "", 0, "en") == "@"

    def test_dates_follow_the_reader(self) -> None:
        assert excel_format("date", "", 0, "fr") == "dd/mm/yyyy"
        assert excel_format("datetime", "", 0, "de") == "dd.mm.yyyy hh:mm"
        assert excel_format("date", "", 0, "en") == "yyyy-mm-dd"

    def test_a_quote_in_a_unit_cannot_break_the_format(self) -> None:
        """A quote would close the literal and turn the rest into format syntax."""
        assert excel_format("quantity", 'k"g', 0, "en") == '#,##0" kg"'
