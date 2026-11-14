"""pptx: a drawn picture takes its frame, and the words make room for it (ADR-274).

A picture the context does not hold — never drawn, or failed — leaves its slide
exactly as if none had been asked for.
"""

from __future__ import annotations

import io

import pptx
import pytest
from PIL import Image
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.enum.text import PP_ALIGN
from pptx.presentation import Presentation
from pptx.slide import Slide as PptxSlide

from src.core.document_preferences import DocumentPreferences
from src.domains.document_generation.context import RenderContext
from src.domains.document_generation.normalize import normalize_content
from src.domains.document_generation.pictures import Picture, picture_key
from src.domains.document_generation.renderers import render_document
from src.domains.document_generation.renderers.pptx_geometry import EMU_PER_IN
from src.domains.document_generation.renderers.pptx_pictures import COVER, SECTION, SIDE, WIDE
from src.domains.document_generation.schemas import (
    DocumentType,
    Illustration,
    Slide,
    SlideContent,
)

from .pptx_oracles import assert_nothing_overflows

pytestmark = pytest.mark.unit

_DECORATIVE_NS = "http://schemas.microsoft.com/office/drawing/2017/decorative"


def _jpeg() -> Picture:
    buffer = io.BytesIO()
    Image.new("RGB", (60, 80), (30, 90, 160)).save(buffer, format="JPEG")
    return Picture(buffer.getvalue(), 60, 80)


def _render(content: SlideContent, *, drawn: dict[str, Picture]) -> Presentation:
    context = RenderContext(
        language="en",
        preferences=DocumentPreferences(images_allowed=True),
        pictures=drawn,
    )
    data = render_document(DocumentType.PPTX, normalize_content(content, context), context)
    return pptx.Presentation(io.BytesIO(data))


def _pictures(slide: PptxSlide) -> list[object]:
    return [shape for shape in slide.shapes if shape.shape_type == MSO_SHAPE_TYPE.PICTURE]


def _deck(*slides: Slide, cover: Illustration | None = None) -> SlideContent:
    return SlideContent(
        filename_stem="d", title="Annual review", illustration=cover, slides=list(slides)
    )


_CITY = Illustration(subject="a city at dawn", alt="A city waking up")


class TestTheCover:
    def test_the_picture_fills_the_right_panel_and_the_title_moves_left(self) -> None:
        deck = _render(
            _deck(Slide(title="t", bullets=["a"]), cover=_CITY),
            drawn={picture_key(COVER.frame.name, _CITY.subject): _jpeg()},
        )

        cover = deck.slides[0]
        (picture,) = _pictures(cover)
        assert round(picture.left / EMU_PER_IN, 2) == round(COVER.left_in, 2)
        assert round(picture.width / EMU_PER_IN, 2) == round(COVER.frame.width_in, 2)
        title = cover.shapes.title
        assert title.left + title.width <= picture.left
        assert title.text_frame.paragraphs[0].alignment == PP_ALIGN.LEFT
        assert_nothing_overflows(deck)

    def test_the_alt_describes_the_picture(self) -> None:
        deck = _render(
            _deck(Slide(title="t", bullets=["a"]), cover=_CITY),
            drawn={picture_key(COVER.frame.name, _CITY.subject): _jpeg()},
        )
        (picture,) = _pictures(deck.slides[0])
        assert picture._element._nvXxPr.cNvPr.get("descr") == "A city waking up"

    def test_a_picture_with_no_alt_is_decoration(self) -> None:
        bare = Illustration(subject="a city at dawn")
        deck = _render(
            _deck(Slide(title="t", bullets=["a"]), cover=bare),
            drawn={picture_key(COVER.frame.name, bare.subject): _jpeg()},
        )
        (picture,) = _pictures(deck.slides[0])
        flags = list(picture._element._nvXxPr.cNvPr.iter(f"{{{_DECORATIVE_NS}}}decorative"))
        assert len(flags) == 1

    def test_a_cover_whose_picture_was_not_drawn_keeps_its_layout(self) -> None:
        pictured = _render(_deck(Slide(title="t", bullets=["a"]), cover=_CITY), drawn={})
        plain = _render(_deck(Slide(title="t", bullets=["a"])), drawn={})

        assert _pictures(pictured.slides[0]) == []
        assert pictured.slides[0].shapes.title.width == plain.slides[0].shapes.title.width


class TestPartOpenersAndContent:
    def test_a_part_opener_frames_its_picture_and_drops_its_pictogram(self) -> None:
        section = Slide(
            title="Growth", kind="section", subtitle="Next", icon="rocket", illustration=_CITY
        )
        deck = _render(
            _deck(section), drawn={picture_key(SECTION.frame.name, _CITY.subject): _jpeg()}
        )

        slide = deck.slides[1]
        (picture,) = _pictures(slide)
        assert round(picture.top / EMU_PER_IN, 2) == round(SECTION.top_in, 2)
        # The title and the tagline end before the picture; the slide number sits under it.
        words = [shape for shape in slide.placeholders if shape.placeholder_format.idx in (0, 1)]
        assert len(words) == 2
        assert all(shape.left + shape.width <= picture.left for shape in words)
        assert picture.top + picture.height <= min(
            shape.top for shape in slide.placeholders if shape.placeholder_format.idx == 12
        )
        assert_nothing_overflows(deck)

    def test_a_part_opener_without_its_picture_keeps_its_pictogram(self) -> None:
        section = Slide(title="Growth", kind="section", icon="rocket", illustration=_CITY)
        deck = _render(_deck(section), drawn={})
        assert len(_pictures(deck.slides[1])) == 1  # the pictogram

    def test_a_content_slide_sets_its_points_beside_the_picture(self) -> None:
        content = Slide(title="Why it matters", bullets=["one", "two"], illustration=_CITY)
        deck = _render(_deck(content), drawn={picture_key(SIDE.frame.name, _CITY.subject): _jpeg()})

        slide = deck.slides[1]
        (picture,) = _pictures(slide)
        body = next(s for s in slide.placeholders if s.placeholder_format.idx == 1)
        assert body.left + body.width <= picture.left
        assert picture.top >= slide.shapes.title.top + slide.shapes.title.height
        assert_nothing_overflows(deck)

    def test_a_split_slide_shows_its_picture_once(self) -> None:
        long_points = [
            f"A point long enough to need its own line, number {index}." for index in range(30)
        ]
        content = Slide(title="Everything", bullets=long_points, illustration=_CITY)
        deck = _render(_deck(content), drawn={picture_key(SIDE.frame.name, _CITY.subject): _jpeg()})

        parts = list(deck.slides)[1:]
        assert len(parts) > 1
        assert [len(_pictures(slide)) for slide in parts] == [1] + [0] * (len(parts) - 1)
        assert_nothing_overflows(deck)

    def test_a_picture_alone_fills_the_area_under_its_title(self) -> None:
        deck = _render(
            _deck(Slide(title="The view", illustration=_CITY)),
            drawn={picture_key(WIDE.frame.name, _CITY.subject): _jpeg()},
        )
        (picture,) = _pictures(deck.slides[1])
        assert round(picture.left / EMU_PER_IN, 2) == round(WIDE.left_in, 2)
        assert round(picture.width / EMU_PER_IN, 2) == round(WIDE.frame.width_in, 2)

    def test_an_opener_s_frame_keeps_its_margin_on_every_side(self) -> None:
        from src.domains.document_generation.typography import PPTX_SLIDE_WIDTH_IN

        right_margin = PPTX_SLIDE_WIDTH_IN - SECTION.left_in - SECTION.frame.width_in
        assert round(right_margin, 3) == round(SECTION.top_in, 3)


class TestTheWeightOfADeck:
    def test_a_fully_illustrated_deck_stays_light(self) -> None:
        """Each picture is embedded once, resampled: a full deck stays far under 3 MB."""
        from src.core.config import settings
        from src.domains.document_generation.illustrations import fit_to_frame

        count = max(1, settings.document_illustrations_max)
        buffer = io.BytesIO()
        # Noise compresses worst: the heaviest picture a vendor could return.
        Image.effect_noise((1536, 1024), 64).convert("RGB").save(buffer, format="PNG")
        drawn = {}
        slides = []
        for index in range(count):
            illustration = Illustration(subject=f"scene {index}")
            drawn[picture_key(SIDE.frame.name, illustration.subject)] = fit_to_frame(
                buffer.getvalue(), SIDE.frame
            )
            slides.append(Slide(title=f"Slide {index}", bullets=["a"], illustration=illustration))

        data = render_document(
            DocumentType.PPTX,
            _deck(*slides),
            RenderContext(
                language="en",
                preferences=DocumentPreferences(images_allowed=True),
                pictures=drawn,
            ),
        )

        placed = pptx.Presentation(io.BytesIO(data))
        assert sum(len(_pictures(slide)) for slide in placed.slides) == min(
            count, settings.document_illustrations_max
        )
        assert len(data) < 3 * 1024 * 1024
