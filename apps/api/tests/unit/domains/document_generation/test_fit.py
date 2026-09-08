"""The estimator against PowerPoint's own measurements (ADR-274).

The 54 rows of ``fixtures/pptx_calibration.json`` were measured by PowerPoint 16
through COM on 2026-09-08. They are the oracle: the estimator must count lines
EXACTLY and must never under-predict a height — an under-prediction is a slide
that overflows in front of an audience.
"""

import json
from pathlib import Path

import pytest

from src.domains.document_generation import fit
from src.domains.document_generation.fit import (
    AVG_CHAR_WIDTH_EM,
    BODY_SIZE_FLOOR_PT,
    CALIBRATED_CHAR_WIDTH_RANGE,
    TITLE_SIZE_BASE_PT,
    TITLE_SIZE_FLOOR_PT,
    TextFrame,
    base_body_size,
    choose_body_size,
    fit_title,
    fits,
    line_count,
    plan_body,
    rows_per_slide,
    table_font_size,
    text_height,
)

pytestmark = [pytest.mark.unit]

_CALIBRATION = json.loads(
    (Path(__file__).parent / "fixtures" / "pptx_calibration.json").read_text(encoding="utf-8")
)
_FRAME = TextFrame(**_CALIBRATION["frame"])
_ROWS = _CALIBRATION["rows"]


def _bullet(chars: int) -> str:
    """The very text the calibration deck used, rstrip included.

    The nominal length is not the measured one — 140 becomes 139 after the
    strip — and the estimator is fitted on what PowerPoint actually saw.
    """
    return ("mesure " * 40)[:chars].rstrip()


class TestAgainstPowerPointsOwnMeasurements:
    def test_the_fixture_is_the_measurement_it_claims(self) -> None:
        assert len(_ROWS) == 54
        assert "PowerPoint" in _CALIBRATION["measured"]
        assert _FRAME.width_pt > _FRAME.height_pt  # the 16:9 body is wider than tall

    @pytest.mark.parametrize(
        "row", _ROWS, ids=lambda r: f"{r['size']}pt-{r['bullets']}b-{r['chars']}c"
    )
    def test_lines_are_exact_and_height_never_under_predicts(self, row: dict) -> None:
        bullets = [_bullet(row["chars"])] * row["bullets"]
        assert sum(line_count(b, row["size"], _FRAME) for b in bullets) == row["lines"]
        assert text_height(bullets, row["size"], _FRAME) >= row["bound_height"]

    def test_the_char_width_stays_inside_its_zero_error_interval(self) -> None:
        """Moving the constant outside this range makes a line count wrong."""
        low, high = CALIBRATED_CHAR_WIDTH_RANGE
        assert low <= AVG_CHAR_WIDTH_EM <= high

    def test_the_margin_is_not_wasteful(self) -> None:
        """Never under-predicting must not mean predicting twice the truth."""
        for row in _ROWS:
            bullets = [_bullet(row["chars"])] * row["bullets"]
            predicted = text_height(bullets, row["size"], _FRAME)
            assert predicted <= row["bound_height"] * 1.5 + row["size"]


class TestTheArithmeticIsSane:
    def test_monotonic_in_size_and_in_length(self) -> None:
        short, long = ["a" * 40], ["a" * 400]
        assert text_height(short, 14, _FRAME) < text_height(short, 28, _FRAME)
        assert text_height(short, 20, _FRAME) < text_height(long, 20, _FRAME)

    def test_more_paragraphs_are_never_shorter(self) -> None:
        one = ["point"]
        assert text_height(one, 18, _FRAME) < text_height(one * 5, 18, _FRAME)

    def test_an_empty_paragraph_still_takes_a_line(self) -> None:
        assert line_count("", 18, _FRAME) == 1

    def test_a_frame_narrower_than_its_insets_does_not_divide_by_zero(self) -> None:
        assert line_count("text", 12, TextFrame(width_pt=5, height_pt=100)) >= 1


class TestChoosingASizeAndSplitting:
    def test_base_sizes_by_density(self) -> None:
        assert (base_body_size(3), base_body_size(6), base_body_size(7)) == (24, 20, 18)

    def test_a_light_slide_keeps_the_largest_size(self) -> None:
        assert choose_body_size(["x"] * 3, _FRAME) == 24

    def test_a_dense_slide_still_fits_at_the_floor_when_it_really_does(self) -> None:
        """Measured: nine 139-char bullets are 18 lines ≈ 344 pt inside 356 pt."""
        assert choose_body_size([_bullet(140)] * 9, _FRAME) == BODY_SIZE_FLOOR_PT

    def test_a_slide_nothing_can_hold_asks_for_a_split(self) -> None:
        assert choose_body_size([_bullet(140) * 2] * 12, _FRAME) is None
        assert choose_body_size(["short"] * 30, _FRAME) is None

    def test_the_split_keeps_every_bullet_in_order_and_each_slide_fits(self) -> None:
        bullets = [f"{i} " + _bullet(140) * 2 for i in range(12)]
        plans = plan_body(bullets, _FRAME)
        assert len(plans) >= 2
        assert [b for plan in plans for b in plan.bullets] == bullets
        for plan in plans:
            assert plan.size_pt >= BODY_SIZE_FLOOR_PT
            assert fits(list(plan.bullets), plan.size_pt, _FRAME)

    def test_a_bullet_too_long_for_a_slide_is_cut_at_sentences_never_truncated(self) -> None:
        monster = ". ".join(f"Sentence number {i} of a very long bullet" for i in range(200)) + "."
        plans = plan_body([monster], _FRAME)
        assert len(plans) >= 2
        rebuilt = " ".join(b for plan in plans for b in plan.bullets)
        assert rebuilt == monster  # every word survived, in order
        for plan in plans:
            assert fits(list(plan.bullets), plan.size_pt, _FRAME)

    def test_a_single_word_longer_than_a_slide_still_terminates(self) -> None:
        plans = plan_body(["x" * 5000], _FRAME)
        assert plans and all(plan.bullets for plan in plans)

    def test_no_bullets_yields_one_empty_plan(self) -> None:
        assert (
            plan_body([], _FRAME) == [((), base_body_size(0))]
            or plan_body([], _FRAME)[0].bullets == ()
        )


class TestTitlesAndTables:
    def test_a_short_title_keeps_the_base_size(self) -> None:
        title_frame = TextFrame(_FRAME.width_pt, 90.0, indent_pt=0)
        assert fit_title("Short", title_frame) == (TITLE_SIZE_BASE_PT, 1)

    def test_a_long_title_shrinks_and_takes_two_lines(self) -> None:
        title_frame = TextFrame(_FRAME.width_pt, 90.0, indent_pt=0)
        size, lines = fit_title(
            "Un titre de diapositive assez long pour tester la casse sur deux lignes", title_frame
        )
        assert lines == 2
        assert TITLE_SIZE_FLOOR_PT <= size <= 36

    def test_a_title_never_goes_below_the_floor(self) -> None:
        title_frame = TextFrame(_FRAME.width_pt, 90.0, indent_pt=0)
        size, _lines = fit_title("mot " * 200, title_frame)
        assert size == TITLE_SIZE_FLOOR_PT

    def test_table_font_and_row_budget(self) -> None:
        assert table_font_size(6) == 12
        assert table_font_size(7) == 10
        area = TextFrame(864.0, 356.4)
        assert rows_per_slide(3, area) == 11
        assert rows_per_slide(9, area) == 13  # a smaller font fits more rows

    def test_a_tiny_area_still_holds_one_row(self) -> None:
        assert rows_per_slide(3, TextFrame(864.0, 10.0)) == 1


@pytest.mark.unit
class TestAFullWidthGlyphIsOneEm:
    """A CJK ideograph occupies a full em; counting it at the Latin width
    under-measured a Chinese slide by 234 pt, and the overflow oracle agreed
    with the renderer because both read the same estimator (measured)."""

    ZH = "这是一个关于季度业绩的详细说明我们需要在下个季度显著提高团队的整体效率并同时降低运营成本"

    def test_an_ideograph_counts_one_em_and_ascii_keeps_the_calibrated_width(self) -> None:
        assert fit.text_width_em("abc") == pytest.approx(3 * fit.AVG_CHAR_WIDTH_EM)
        assert fit.text_width_em("一二三") == pytest.approx(3.0)
        assert fit.text_width_em("ab一") == pytest.approx(2 * fit.AVG_CHAR_WIDTH_EM + 1.0)

    def test_latin_measurement_is_unchanged_so_the_calibration_still_holds(self) -> None:
        """Every PowerPoint fixture was measured on Latin text: the width of a
        Latin string must be EXACTLY what it was before the rule existed."""
        for sample in ("mesure " * 20, "Ceci est une phrase avec des accents: é à ù — ok."):
            assert fit.text_width_em(sample) == pytest.approx(len(sample) * fit.AVG_CHAR_WIDTH_EM)

    def test_a_chinese_paragraph_takes_more_lines_than_latin_of_equal_length(self) -> None:
        """The discriminating oracle: ``fits`` reads the same estimator as the
        renderer, so an assertion phrased through it is green whatever the
        width rule says. Line COUNTS are independent of it."""
        frame = TextFrame(width_pt=863.98, height_pt=356.38)
        dense = self.ZH * 3
        assert line_count(dense, 18, frame) > line_count("a" * len(dense), 18, frame)

    def test_a_dense_chinese_slide_is_split_instead_of_overflowing(self) -> None:
        """Nine dense Chinese bullets measured 238 pt under the Latin width and
        were emitted as ONE slide; they take 646 pt in a 356 pt frame, so they
        must now be split, with nothing lost."""
        frame = TextFrame(width_pt=863.98, height_pt=356.38)
        plans = fit.plan_body([self.ZH * 3] * 9, frame)
        assert len(plans) >= 2
        for plan in plans:
            assert fits(list(plan.bullets), plan.size_pt, frame), plan
        assert sum(len(plan.bullets) for plan in plans) >= 9  # nothing is lost
