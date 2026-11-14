"""A report's band of key figures: rows as even as a slide's, one size per row (ADR-274)."""

import pytest

from src.domains.document_generation import typography
from src.domains.document_generation.fit import (
    AVG_CHAR_WIDTH_EM,
    SANS_CHAR_WIDTH_EM,
    text_width_em,
)
from src.domains.document_generation.renderers.page_figures import plan_band
from src.domains.document_generation.schemas import KeyFigure

pytestmark = [pytest.mark.unit]

#: An A4 text column at Word's margins.
_WIDTH_PT = 453.0


def _figures(*values: str) -> list[KeyFigure]:
    return [KeyFigure(value=value, label=f"label {index}") for index, value in enumerate(values)]


def _room(tile_width_pt: float) -> float:
    return tile_width_pt - 2 * typography.PAGE_FIGURE_PADDING_PT


class TestTheRows:
    @pytest.mark.parametrize(
        ("count", "rows"), [(1, [1]), (4, [4]), (5, [3, 2]), (6, [3, 3]), (9, [3, 3, 3])]
    )
    def test_rows_are_as_few_and_as_even_as_a_slide_s(self, count: int, rows: list[int]) -> None:
        planned = plan_band(_figures(*["7"] * count), _WIDTH_PT, narrow_em=AVG_CHAR_WIDTH_EM)
        assert [len(row.figures) for row in planned] == rows
        assert [figure for row in planned for figure in row.figures] == _figures(*["7"] * count)

    def test_no_figure_makes_no_band(self) -> None:
        assert plan_band([], _WIDTH_PT, narrow_em=AVG_CHAR_WIDTH_EM) == []

    @pytest.mark.parametrize("count", range(1, typography.PAGE_FIGURES_PER_ROW + 1))
    def test_the_tiles_and_their_gaps_span_the_width_exactly(self, count: int) -> None:
        (row,) = plan_band(_figures(*["9"] * count), _WIDTH_PT, narrow_em=AVG_CHAR_WIDTH_EM)
        spanned = row.tile_width_pt * count + typography.PAGE_FIGURE_GAP_PT * (count + 1)
        assert spanned == pytest.approx(_WIDTH_PT)


class TestTheValueSize:
    @pytest.mark.parametrize("count", range(1, typography.PAGE_FIGURES_PER_ROW + 1))
    def test_short_values_keep_their_row_s_base_size(self, count: int) -> None:
        (row,) = plan_band(_figures(*["42%"] * count), _WIDTH_PT, narrow_em=AVG_CHAR_WIDTH_EM)
        assert row.value_pt == typography.PAGE_FIGURE_VALUE_PT[count]

    @pytest.mark.parametrize("narrow_em", [AVG_CHAR_WIDTH_EM, SANS_CHAR_WIDTH_EM])
    def test_the_widest_value_fits_its_tile_on_one_line(self, narrow_em: float) -> None:
        figures = _figures("€1,234,567", "3", "12 days", "+18%")
        (row,) = plan_band(figures, _WIDTH_PT, narrow_em=narrow_em)
        widest = max(text_width_em(figure.value, narrow_em=narrow_em) for figure in figures)
        assert widest * typography.BOLD_WIDTH_FACTOR * row.value_pt <= _room(row.tile_width_pt)
        assert row.value_pt < typography.PAGE_FIGURE_VALUE_PT[4]

    def test_the_size_is_rounded_down_never_up(self) -> None:
        """180 pt leaves a value of 6.4 em room for 22.02 pt: it is set in 22, not 22.5."""
        (row,) = plan_band(_figures("€1,234,567,890"), 180, narrow_em=AVG_CHAR_WIDTH_EM)
        assert row.value_pt == 22.0
        widest = text_width_em("€1,234,567,890") * typography.BOLD_WIDTH_FACTOR
        assert widest * row.value_pt <= _room(row.tile_width_pt)

    def test_a_value_too_long_for_any_size_stops_at_the_floor_and_wraps(self) -> None:
        (row,) = plan_band(_figures("1" * 200), _WIDTH_PT, narrow_em=AVG_CHAR_WIDTH_EM)
        assert row.value_pt == typography.PAGE_FIGURE_VALUE_FLOOR_PT

    def test_every_row_of_a_band_shares_one_size(self) -> None:
        """Five read 3 + 2: the two wider tiles below may not shout over the three above."""
        rows = plan_band(_figures(*"12345"), _WIDTH_PT, narrow_em=AVG_CHAR_WIDTH_EM)
        assert [len(row.figures) for row in rows] == [3, 2]
        assert {row.value_pt for row in rows} == {typography.PAGE_FIGURE_VALUE_PT[3]}

    def test_the_band_takes_the_size_its_tightest_row_allows(self) -> None:
        figures = _figures("€1,234,567", "2", "3", "4", "5")  # the long one in the narrow row
        rows = plan_band(figures, _WIDTH_PT, narrow_em=AVG_CHAR_WIDTH_EM)
        (size,) = {row.value_pt for row in rows}
        room = _room(rows[0].tile_width_pt)
        assert text_width_em("€1,234,567") * typography.BOLD_WIDTH_FACTOR * size <= room

    def test_a_chinese_value_is_measured_full_width(self) -> None:
        latin = plan_band(_figures("12345678"), 200, narrow_em=AVG_CHAR_WIDTH_EM)[0]
        chinese = plan_band(_figures("一二三四五六七八"), 200, narrow_em=AVG_CHAR_WIDTH_EM)[0]
        assert chinese.value_pt < latin.value_pt
