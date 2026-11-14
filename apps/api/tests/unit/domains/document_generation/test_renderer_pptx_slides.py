"""pptx: key figures, quotes, the agenda, pictograms and motion (ADR-274).

Every new frame is held to the same overflow oracle as the bullets, and every
« it cannot fit » ends on the bullets' own layout — never on clipped text.
"""

from __future__ import annotations

import io
from typing import Any

import pptx
import pytest
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.oxml.ns import qn
from pptx.presentation import Presentation

from src.core.document_preferences import DocumentAnimations, DocumentPreferences
from src.domains.document_generation import typography
from src.domains.document_generation.context import RenderContext
from src.domains.document_generation.fit import TextFrame, balanced_rows, line_count
from src.domains.document_generation.normalize import normalize_content
from src.domains.document_generation.renderers import render_document
from src.domains.document_generation.renderers.pptx_figures import mark_decorative
from src.domains.document_generation.renderers.pptx_geometry import EMU_PER_PT
from src.domains.document_generation.schemas import (
    DocumentType,
    KeyFigure,
    Slide,
    SlideContent,
)

from .pptx_oracles import assert_nothing_overflows

pytestmark = pytest.mark.unit

_EMU_PER_IN = 914400
_DECORATIVE_NS = "http://schemas.microsoft.com/office/drawing/2017/decorative"


def _deck(
    *slides: Slide,
    language: str = "en",
    tone: str = "",
    delivery: str = "",
    animations: DocumentAnimations = DocumentAnimations.PRESENTED,
) -> Presentation:
    context = RenderContext(
        language=language, preferences=DocumentPreferences(animations=animations)
    )
    content = SlideContent(
        filename_stem="d", title="Deck", tone=tone, delivery=delivery, slides=list(slides)
    )
    normalized = normalize_content(content, context)
    rendered = render_document(DocumentType.PPTX, normalized, context)
    return pptx.Presentation(io.BytesIO(rendered))


def _texts(slide: Any) -> list[str]:
    return [shape.text_frame.text for shape in slide.shapes if shape.has_text_frame]


def _pictures(slide: Any) -> list[Any]:
    return [shape for shape in slide.shapes if shape.shape_type == MSO_SHAPE_TYPE.PICTURE]


def _title(slide: Any) -> str:
    return str(slide.shapes.title.text_frame.text)


def _figures(count: int, *, label: str = "of revenue", icon: str = "") -> list[KeyFigure]:
    return [
        KeyFigure(value=f"{10 * (index + 1)}%", label=label, icon=icon) for index in range(count)
    ]


class TestKeyFigures:
    def test_each_figure_is_a_tile_with_its_value_over_its_label(self) -> None:
        deck = _deck(Slide(title="Results", kind="figures", figures=_figures(3)))

        slide = deck.slides[1]
        texts = _texts(slide)
        for index in range(3):
            assert f"{10 * (index + 1)}%\nof revenue" in texts
        assert_nothing_overflows(deck)

    def test_the_value_is_the_large_bold_line(self) -> None:
        deck = _deck(Slide(title="Results", kind="figures", figures=_figures(2)))

        box = next(
            shape
            for shape in deck.slides[1].shapes
            if shape.has_text_frame and shape.text_frame.text.startswith("10%")
        )
        value, label = box.text_frame.paragraphs
        assert value.runs[0].font.bold is True
        assert value.runs[0].font.size.pt > label.runs[0].font.size.pt
        assert value.runs[0].font.size.pt >= typography.PPTX_FIGURE_VALUE_FLOOR_PT

    def test_more_figures_than_a_row_continue_in_even_rows(self) -> None:
        per_slide = typography.PPTX_FIGURES_PER_SLIDE
        deck = _deck(Slide(title="Results", kind="figures", figures=_figures(per_slide + 2)))

        assert [_title(slide) for slide in deck.slides][1:] == ["Results (1/2)", "Results (2/2)"]
        # Six figures read three and three, never four then a lonely two.
        half = (per_slide + 2) // 2
        assert len([t for t in _texts(deck.slides[1]) if "\n" in t]) == half
        assert len([t for t in _texts(deck.slides[2]) if "\n" in t]) == half

    @pytest.mark.parametrize(
        ("count", "rows"),
        [(1, [1]), (4, [4]), (5, [3, 2]), (6, [3, 3]), (7, [4, 3]), (9, [3, 3, 3]), (0, [])],
    )
    def test_rows_are_as_few_and_as_even_as_possible(self, count: int, rows: list[int]) -> None:
        split = balanced_rows(_figures(count), 4)
        assert [len(row) for row in split] == rows
        assert [figure for row in split for figure in row] == _figures(count)

    def test_tiles_stay_on_the_slide_under_the_title(self) -> None:
        deck = _deck(Slide(title="Results", kind="figures", figures=_figures(4, icon="target")))

        slide = deck.slides[1]
        title_bottom = slide.shapes.title.top + slide.shapes.title.height
        for shape in slide.shapes:
            if shape == slide.shapes.title or shape.is_placeholder:
                continue
            assert shape.top >= title_bottom, shape.name
            assert shape.left >= 0 and shape.left + shape.width <= deck.slide_width, shape.name
            assert shape.top + shape.height <= deck.slide_height, shape.name

    def test_a_named_icon_is_drawn_and_an_unknown_one_is_not(self) -> None:
        figures = [
            KeyFigure(value="12", label="sites", icon="building"),
            KeyFigure(value="3", label="countries", icon="unicorn"),
        ]
        deck = _deck(Slide(title="Footprint", kind="figures", figures=figures))

        assert len(_pictures(deck.slides[1])) == 1

    def test_a_pictogram_is_marked_decorative(self) -> None:
        deck = _deck(Slide(title="Footprint", kind="figures", figures=_figures(1, icon="globe")))

        (picture,) = _pictures(deck.slides[1])
        properties = picture._element.nvPicPr.cNvPr
        assert properties.get("descr") == ""
        assert "decorative" in pptx.oxml.xmlchemy.serialize_for_reading(properties)

    def test_grounds_are_decoration_a_reader_skips(self) -> None:
        deck = _deck(Slide(title="Footprint", kind="figures", figures=_figures(3, icon="globe")))

        decorations = [
            shape
            for shape in deck.slides[1].shapes
            if shape.shape_type in (MSO_SHAPE_TYPE.AUTO_SHAPE, MSO_SHAPE_TYPE.PICTURE)
        ]
        assert len(decorations) == 6  # three grounds, three pictograms
        for shape in decorations:
            properties = shape._element._nvXxPr.cNvPr
            assert properties.get("descr") == ""
            flags = list(properties.iter(f"{{{_DECORATIVE_NS}}}decorative"))
            assert len(flags) == 1, shape.name

    def test_marking_twice_leaves_one_flag(self) -> None:
        deck = _deck(Slide(title="Footprint", kind="figures", figures=_figures(1)))
        ground = next(s for s in deck.slides[1].shapes if s.shape_type == MSO_SHAPE_TYPE.AUTO_SHAPE)

        mark_decorative(ground)

        properties = ground._element._nvXxPr.cNvPr
        assert len(list(properties.iter(f"{{{_DECORATIVE_NS}}}decorative"))) == 1

    def test_every_figure_stands_on_one_line(self) -> None:
        """A figure two lines long at the row's base size shrinks rather than breaks."""
        figures = [KeyFigure(value="€1,234,567", label="revenue")] * 4
        deck = _deck(Slide(title="Results", kind="figures", figures=figures))

        boxes = [s for s in deck.slides[1].shapes if s.shape_type == MSO_SHAPE_TYPE.TEXT_BOX]
        assert len(boxes) == 4
        for shape in boxes:
            value = shape.text_frame.paragraphs[0]
            size = value.runs[0].font.size.pt
            frame = TextFrame(shape.width / EMU_PER_PT, shape.height / EMU_PER_PT, indent_pt=0.0)
            assert line_count(value.text, size, frame) == 1, (value.text, size)
            assert size < typography.PPTX_FIGURE_VALUE_PT[4], "it had to shrink to stay whole"

    def test_a_figure_too_long_for_one_line_falls_back_to_bullets(self) -> None:
        figures = [KeyFigure(value="1,234,567,890.12 € (net, consolidated)", label="revenue")] * 4
        deck = _deck(Slide(title="Results", kind="figures", figures=figures))

        slide = deck.slides[1]
        assert not [s for s in slide.shapes if s.shape_type == MSO_SHAPE_TYPE.TEXT_BOX]
        assert any(
            s.is_placeholder and "1,234,567,890.12" in s.text_frame.text
            for s in slide.shapes
            if s.has_text_frame
        )

    def test_a_label_too_long_for_its_tile_falls_back_to_bullets(self) -> None:
        wordy = " ".join(["a remarkably long description of what is measured"] * 8)
        deck = _deck(Slide(title="Results", kind="figures", figures=_figures(4, label=wordy)))

        slide = deck.slides[1]
        body = [shape for shape in slide.shapes if shape.is_placeholder and shape.has_text_frame]
        assert any("10% — a remarkably" in shape.text_frame.text for shape in body)
        assert_nothing_overflows(deck)

    def test_a_fallen_back_figure_reads_in_the_reader_s_convention(self) -> None:
        wordy = "的".join(["一个非常长的说明"] * 30)
        deck = _deck(
            Slide(title="结果", kind="figures", figures=_figures(4, label=wordy)),
            language="zh-CN",
        )

        texts = " ".join(_texts(deck.slides[1]))
        assert "10%：" in texts and "10% —" not in texts


class TestQuotes:
    def test_the_words_stand_beside_a_rule_and_their_author_follows(self) -> None:
        deck = _deck(
            Slide(
                title="What clients say",
                kind="quote",
                quote="It changed how we plan our week.",
                subtitle="A logistics manager",
            )
        )

        slide = deck.slides[1]
        texts = _texts(slide)
        assert "It changed how we plan our week." in texts
        assert "— A logistics manager" in texts
        words = next(
            s for s in slide.shapes if s.has_text_frame and s.text_frame.text.startswith("It")
        )
        assert words.text_frame.paragraphs[0].runs[0].font.italic is True
        (rule,) = [s for s in slide.shapes if s.shape_type == MSO_SHAPE_TYPE.AUTO_SHAPE]
        assert not rule.text_frame.text
        assert rule.left + rule.width < words.left
        assert (rule.top, rule.height) == (words.top, words.height)
        assert_nothing_overflows(deck)

    def test_the_author_is_introduced_in_the_reader_s_convention(self) -> None:
        deck = _deck(
            Slide(
                title="客户的话",
                kind="quote",
                quote="它改变了我们的工作方式。",
                subtitle="一位经理",
            ),
            language="zh-CN",
        )
        assert "——一位经理" in _texts(deck.slides[1])

    def test_the_rule_is_decoration_a_reader_skips(self) -> None:
        deck = _deck(Slide(title="Motto", kind="quote", quote="Measure twice, cut once."))

        (rule,) = [s for s in deck.slides[1].shapes if s.shape_type == MSO_SHAPE_TYPE.AUTO_SHAPE]
        properties = rule._element._nvXxPr.cNvPr
        assert len(list(properties.iter(f"{{{_DECORATIVE_NS}}}decorative"))) == 1

    def test_a_quote_without_its_author_says_no_one(self) -> None:
        deck = _deck(Slide(title="Motto", kind="quote", quote="Measure twice, cut once."))
        assert not any(text.startswith("—") for text in _texts(deck.slides[1]))

    def test_a_quote_too_long_for_the_slide_falls_back_to_bullets(self) -> None:
        words = " ".join(["This sentence keeps the speaker talking for quite a while."] * 30)
        deck = _deck(Slide(title="Testimony", kind="quote", quote=words, subtitle="Someone"))

        assert_nothing_overflows(deck)
        assert all(_pictures(slide) == [] for slide in deck.slides)
        assert any(
            shape.is_placeholder and "This sentence" in shape.text_frame.text
            for slide in list(deck.slides)[1:]
            for shape in slide.shapes
            if shape.has_text_frame
        )


class TestSectionPictograms:
    def test_a_section_opener_carries_its_icon_above_the_tagline(self) -> None:
        deck = _deck(
            Slide(title="Growth", kind="section", subtitle="Where we go next", icon="rocket"),
            tone="warm",
        )

        slide = deck.slides[1]
        (picture,) = _pictures(slide)
        side = round(typography.PPTX_SECTION_ICON_IN * _EMU_PER_IN)
        assert (picture.width, picture.height) == (side, side)
        tagline = next(
            s for s in slide.shapes if s.has_text_frame and s.text_frame.text == "Where we go next"
        )
        assert picture.top + picture.height <= tagline.top

    def test_a_section_without_an_icon_draws_none(self) -> None:
        deck = _deck(Slide(title="Growth", kind="section", subtitle="Next"))
        assert _pictures(deck.slides[1]) == []


def _sections(count: int) -> list[Slide]:
    slides: list[Slide] = []
    for index in range(count):
        slides.append(Slide(title=f"Part {index + 1}", kind="section"))
        slides.append(Slide(title=f"Point {index + 1}", bullets=["a", "b"]))
    return slides


class TestTheAgenda:
    def test_three_parts_open_on_an_agenda_of_their_titles(self) -> None:
        deck = _deck(*_sections(typography.PPTX_AGENDA_MIN_PARTS))

        agenda = deck.slides[1]
        assert _title(agenda) == "Agenda"
        body = [s for s in agenda.shapes if s.is_placeholder and s.placeholder_format.idx == 1][0]
        assert [p.text for p in body.text_frame.paragraphs] == ["Part 1", "Part 2", "Part 3"]
        for paragraph in body.text_frame.paragraphs:
            assert paragraph._p.find(qn("a:pPr")).find(qn("a:buAutoNum")) is not None

    def test_two_parts_need_no_agenda(self) -> None:
        deck = _deck(*_sections(typography.PPTX_AGENDA_MIN_PARTS - 1))
        assert _title(deck.slides[1]) == "Part 1"

    def test_the_agenda_speaks_the_reader_s_language(self) -> None:
        deck = _deck(*_sections(3), language="fr")
        assert _title(deck.slides[1]) == "Sommaire"


class TestMotion:
    def _transitions(self, deck: Presentation) -> int:
        return sum(
            1 for slide in deck.slides if slide._element.find(qn("p:transition")) is not None
        )

    def test_a_presented_deck_fades_every_slide_and_reveals_its_points(self) -> None:
        deck = _deck(Slide(title="Plan", bullets=["one", "two", "three"]), delivery="presented")

        assert self._transitions(deck) == len(deck.slides)
        clicks = [
            node
            for node in deck.slides[1]._element.iter(qn("p:cTn"))
            if node.get("nodeType") == "clickEffect"
        ]
        assert len(clicks) == 3

    def test_a_deck_to_read_stays_still_by_default(self) -> None:
        deck = _deck(Slide(title="Plan", bullets=["one", "two"]), delivery="read")

        assert self._transitions(deck) == 0
        assert all(slide._element.find(qn("p:timing")) is None for slide in deck.slides)

    def test_an_undeclared_deck_stays_still_by_default(self) -> None:
        deck = _deck(Slide(title="Plan", bullets=["one", "two"]))
        assert self._transitions(deck) == 0

    def test_always_moves_even_a_deck_to_read(self) -> None:
        deck = _deck(
            Slide(title="Plan", bullets=["one", "two"]),
            delivery="read",
            animations=DocumentAnimations.ALWAYS,
        )
        assert self._transitions(deck) == len(deck.slides)

    def test_never_keeps_even_a_presented_deck_still(self) -> None:
        deck = _deck(
            Slide(title="Plan", bullets=["one", "two"]),
            delivery="presented",
            animations=DocumentAnimations.NEVER,
        )
        assert self._transitions(deck) == 0

    def test_a_single_point_is_not_held_back(self) -> None:
        deck = _deck(Slide(title="Plan", bullets=["only one"]), delivery="presented")
        assert deck.slides[1]._element.find(qn("p:timing")) is None

    def test_each_tile_appears_on_its_own_click_with_its_icon(self) -> None:
        deck = _deck(
            Slide(title="Results", kind="figures", figures=_figures(3, icon="target")),
            delivery="presented",
        )

        nodes = [
            node.get("nodeType")
            for node in deck.slides[1]._element.iter(qn("p:cTn"))
            if node.get("presetID")
        ]
        # tile, then its icon and its words with it — three times.
        assert nodes == ["clickEffect", "withEffect", "withEffect"] * 3


class TestGeometryIsInPoints:
    def test_the_slide_is_still_the_16_9_canvas(self) -> None:
        deck = _deck(Slide(title="Results", kind="figures", figures=_figures(2)))
        assert round(deck.slide_width / EMU_PER_PT) == 960


class TestLinks:
    def test_an_address_in_a_point_opens_when_clicked_and_stays_printed(self) -> None:
        deck = _deck(
            Slide(title="Read more", bullets=["See [the agency](https://example.org/a_b) now"])
        )
        runs = [
            run
            for shape in deck.slides[1].shapes
            if shape.has_text_frame
            for paragraph in shape.text_frame.paragraphs
            for run in paragraph.runs
        ]
        assert "".join(run.text for run in runs).endswith(
            "See the agency (https://example.org/a_b) now"
        )
        (linked,) = [run for run in runs if run.hyperlink.address]
        assert (linked.text, linked.hyperlink.address) == (
            "https://example.org/a_b",
            "https://example.org/a_b",
        )
