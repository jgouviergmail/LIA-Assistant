"""A document's tone: palettes held to the validator's gates (ADR-274 amendment).

Every series palette was chosen by an exhaustive search of the dataviz
validator over the documented hues; ``palette_gates`` re-runs its gates here, so
a palette nobody re-validated never ships. The accents and washes are held to
WCAG, and the neutral palette to the greys every document had before tones —
the look meeting minutes keep.
"""

from __future__ import annotations

import pytest

from src.domains.document_generation import typography

from . import palette_gates as gates

pytestmark = [pytest.mark.unit]

TONED = [tone for tone in typography.PALETTES if tone]


class TestThePortIsTheValidator:
    def test_it_reproduces_the_validator_s_figures(self) -> None:
        """Measured with validate_palette.js on 2026-11-13: adjacent CVD 13.0, normal 19.3."""
        palette = typography.NEUTRAL_SERIES
        assert gates.worst_cvd(palette, gates.adjacent(palette)) == pytest.approx(13.0, abs=0.1)
        assert gates.worst_normal(palette, gates.adjacent(palette)) == pytest.approx(19.3, abs=0.1)

    def test_it_reproduces_the_lot_two_palette_s_weaker_figures(self) -> None:
        """The previous order measured 8.4 under the validator — the port says the same."""
        previous = ("2A78D6", "D95926", "199E70", "C98500", "D55181", "008300")
        assert gates.worst_cvd(previous, gates.adjacent(previous)) == pytest.approx(8.4, abs=0.1)


class TestEverySeriesPalettePassesTheGates:
    @pytest.mark.parametrize("tone", list(typography.PALETTES))
    def test_lightness_chroma_and_contrast(self, tone: str) -> None:
        for color in typography.PALETTES[tone].series:
            lightness, chroma = gates.lightness_and_chroma(color)
            assert gates.LIGHT_BAND[0] <= lightness <= gates.LIGHT_BAND[1], (tone, color)
            assert chroma >= gates.CHROMA_FLOOR, (tone, color)
            assert typography.contrast(color, "FFFFFF") >= gates.MARK_CONTRAST, (tone, color)

    @pytest.mark.parametrize("tone", list(typography.PALETTES))
    def test_neighbours_stay_apart_for_every_reader(self, tone: str) -> None:
        series = typography.PALETTES[tone].series
        assert gates.worst_cvd(series, gates.adjacent(series)) >= gates.CVD_TARGET
        assert gates.worst_normal(series, gates.adjacent(series)) >= gates.NORMAL_FLOOR

    @pytest.mark.parametrize("tone", list(typography.PALETTES))
    def test_a_scatter_s_three_series_stay_apart_pair_by_pair(self, tone: str) -> None:
        first = typography.PALETTES[tone].series[: typography.CHART_SCATTER_MAX_SERIES]
        pairs = gates.every_pair(len(first))
        assert gates.worst_cvd(first, pairs) >= gates.CVD_TARGET
        assert gates.worst_normal(first, pairs) >= gates.NORMAL_FLOOR


class TestTheAccents:
    @pytest.mark.parametrize("tone", TONED)
    def test_an_accent_holds_large_type_and_marks_on_paper(self, tone: str) -> None:
        accent = typography.PALETTES[tone].accent
        assert accent is not None
        assert typography.contrast(accent, "FFFFFF") >= 3.0

    @pytest.mark.parametrize("tone", TONED)
    def test_words_on_an_accent_divider_read(self, tone: str) -> None:
        accent = typography.PALETTES[tone].accent
        assert accent is not None
        assert typography.contrast(typography.label_on(accent), accent) >= 3.0

    @pytest.mark.parametrize("tone", TONED)
    def test_ink_reads_on_every_wash(self, tone: str) -> None:
        wash = typography.PALETTES[tone].wash
        assert typography.contrast(typography.INK, wash) >= 7.0

    @pytest.mark.parametrize("tone", sorted(typography.PALETTES))
    def test_a_key_figure_and_its_label_read_on_their_tile(self, tone: str) -> None:
        """A figure is large bold type (3:1); its label is small text (4.5:1)."""
        palette = typography.PALETTES[tone]
        assert typography.PPTX_FIGURE_VALUE_FLOOR_PT >= 18
        # A report's band sets its values bold: from 14 pt bold, large type too.
        assert typography.PAGE_FIGURE_VALUE_FLOOR_PT >= 14
        assert typography.contrast(palette.title_ink, palette.wash) >= 3.0
        assert typography.contrast(typography.MUTED, palette.wash) >= 4.5

    @pytest.mark.parametrize("tone", sorted(typography.PALETTES))
    def test_a_link_reads_as_running_text(self, tone: str) -> None:
        link = typography.PALETTES[tone].link_ink
        assert typography.contrast(link, typography.PAPER) >= typography.BODY_TEXT_CONTRAST

    def test_an_accent_too_light_for_running_text_leaves_the_link_in_ink(self) -> None:
        warm, institutional = typography.PALETTES["warm"], typography.PALETTES["institutional"]
        assert warm.accent is not None
        assert typography.contrast(warm.accent, typography.PAPER) < typography.BODY_TEXT_CONTRAST
        assert warm.link_ink == typography.HEADING_INK
        assert institutional.link_ink == institutional.accent

    def test_a_wash_is_a_tenth_of_its_accent(self) -> None:
        assert typography.tint("1C5CAB") == "E8EFF7"
        assert typography.tint("000000", 0.5) == "80" * 3


class TestNeutralIsTheGreyOfBefore:
    def test_every_role_falls_back_to_its_grey(self) -> None:
        neutral = typography.palette_for("")
        assert neutral.accent is None
        assert (neutral.title_ink, neutral.heading_ink) == (typography.INK, typography.HEADING_INK)
        assert (neutral.rule, neutral.marker, neutral.wash) == (
            typography.RULE,
            typography.MUTED,
            typography.BAND,
        )

    def test_an_unknown_tone_is_neutral(self) -> None:
        assert typography.palette_for("psychedelic") is typography.PALETTES[""]


class TestALabelInsideAFill:
    @pytest.mark.parametrize(
        "fill",
        sorted({color for palette in typography.PALETTES.values() for color in palette.series}),
    )
    def test_its_ink_is_the_one_that_contrasts_more(self, fill: str) -> None:
        chosen = typography.label_on(fill)
        other = typography.INK if chosen == "FFFFFF" else "FFFFFF"
        assert typography.contrast(chosen, fill) >= typography.contrast(other, fill)

    def test_ink_on_ochre_white_on_blue(self) -> None:
        assert typography.label_on("C98500") == typography.INK
        assert typography.label_on("2A78D6") == "FFFFFF"

    def test_contrast_is_wcag_s(self) -> None:
        assert typography.contrast("000000", "FFFFFF") == pytest.approx(21.0)
        assert typography.contrast("FFFFFF", "FFFFFF") == pytest.approx(1.0)
