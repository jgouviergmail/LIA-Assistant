"""Where a deck's pictures go, and the room the words leave them (ADR-274).

Four frames, one per place a writer may ask for a picture:

- ``cover``: the right of the title slide, full height and bleeding to the
  edge — the cover carries no slide number to hide;
- ``section``: the right of a part opener, framed above the slide number;
- ``side``: the right of a content slide, under its title, beside its points;
- ``wide``: the whole area under the title of a slide with no points — a picture
  alone is not pushed into a corner.

The words move left to leave the frame free: a text placeholder is narrowed by
writing its FOUR coordinates, never its width alone — a placeholder that
inherits its position reports what it inherits, and writing one coordinate of
an inherited box freezes the others at zero (``pptx_geometry``). The text is then
measured in the narrowed frame like any other.

A picture nobody drew is absent from the context: its slide is laid out exactly
as if none had been asked for.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Any

from pptx.enum.text import PP_ALIGN
from pptx.util import Inches

from src.domains.document_generation import typography
from src.domains.document_generation.fit import BULLET_INDENT_PT, TextFrame
from src.domains.document_generation.pictures import Frame, IllustrationRequest, Picture
from src.domains.document_generation.renderers import pptx_geometry as geometry
from src.domains.document_generation.renderers.pptx_figures import mark_decorative
from src.domains.document_generation.schemas import SlideContent

#: The space between the words and the picture beside them.
_GAP_IN = 0.4
#: Where the cover's title and subtitle start once a picture stands beside them.
COVER_TEXT_LEFT_IN = 1.0


@dataclass(frozen=True, slots=True)
class _Placement:
    """A frame and where it sits on the 16:9 slide, in inches."""

    frame: Frame
    left_in: float
    top_in: float


def _right(width_in: float, height_in: float, top_in: float, name: str) -> _Placement:
    """A frame against the right edge, as far from it as from the top (0 bleeds)."""
    return _Placement(
        Frame(name, width_in, height_in),
        typography.PPTX_SLIDE_WIDTH_IN - top_in - width_in,
        top_in,
    )


#: The four places of a deck's pictures.
COVER = _right(4.8, typography.PPTX_SLIDE_HEIGHT_IN, 0.0, "cover")
SECTION = _right(4.4, 6.2, 0.5, "section")
SIDE = _Placement(
    Frame("side", 4.2, geometry.TABLE_AREA_HEIGHT_IN),
    geometry.TABLE_LEFT_IN + geometry.TABLE_WIDTH_IN - 4.2,
    geometry.TABLE_TOP_IN,
)
WIDE = _Placement(
    Frame("wide", geometry.TABLE_WIDTH_IN, geometry.TABLE_AREA_HEIGHT_IN),
    geometry.TABLE_LEFT_IN,
    geometry.TABLE_TOP_IN,
)


def content_placement(slide_has_points: bool) -> _Placement:
    """Beside the points, or the whole area when there are none."""
    return SIDE if slide_has_points else WIDE


def picture_requests(content: SlideContent) -> list[IllustrationRequest]:
    """Every picture a normalized deck asks for, in its order: the cover, then the slides.

    Args:
        content: A normalized deck, its pictures already within the budget.

    Returns:
        One request per picture, its frame decided by where it goes.
    """
    requests: list[IllustrationRequest] = []
    if content.illustration is not None:
        requests.append(IllustrationRequest(content.illustration.subject, COVER.frame))
    for slide in content.slides:
        if slide.illustration is None:
            continue
        placement = SECTION if slide.kind == "section" else content_placement(bool(slide.bullets))
        requests.append(IllustrationRequest(slide.illustration.subject, placement.frame))
    return requests


def side_body_frame() -> TextFrame:
    """The body of a content slide once a picture stands beside it."""
    width_in = SIDE.left_in - _GAP_IN - geometry.TABLE_LEFT_IN
    return TextFrame(
        width_in * 72.0, geometry.TABLE_AREA_HEIGHT_IN * 72.0, indent_pt=BULLET_INDENT_PT
    )


def make_room(shape: Any, placement: _Placement, *, left_in: float | None = None) -> None:
    """Narrow a text placeholder so it ends before the picture.

    Args:
        shape: A slide placeholder, possibly inheriting its box from its layout.
        placement: The picture's place on the slide, to the right of the words.
        left_in: A new left edge, when the words should move left too.

    Raises:
        ValueError: When the picture leaves the words no room at all.
    """
    left, top, height = shape.left, shape.top, shape.height
    new_left = Inches(left_in) if left_in is not None else left
    width = Inches(placement.left_in - _GAP_IN) - new_left
    if width <= 0:
        raise ValueError(f"the {placement.frame.name} frame leaves no room for words")
    shape.left, shape.top, shape.height = new_left, top, height
    shape.width = width


def align_left(shape: Any) -> None:
    """Words beside a picture read from its left edge, not from the slide's centre."""
    for paragraph in shape.text_frame.paragraphs:
        paragraph.alignment = PP_ALIGN.LEFT


def place(slide: Any, picture: Picture, placement: _Placement, alt: str) -> int:
    """Put a drawn picture in its frame.

    Args:
        slide: The slide.
        picture: The picture, already cropped to the frame's proportions.
        placement: Where it goes.
        alt: What a reader who cannot see it is told; empty marks it decorative.

    Returns:
        The picture's shape id.
    """
    shape = slide.shapes.add_picture(
        io.BytesIO(picture.data),
        Inches(placement.left_in),
        Inches(placement.top_in),
        Inches(placement.frame.width_in),
        Inches(placement.frame.height_in),
    )
    if alt:
        shape._element._nvXxPr.cNvPr.set("descr", alt)
    else:
        mark_decorative(shape)
    return int(shape.shape_id)


__all__ = [
    "COVER",
    "COVER_TEXT_LEFT_IN",
    "SECTION",
    "SIDE",
    "WIDE",
    "align_left",
    "content_placement",
    "make_room",
    "picture_requests",
    "place",
    "side_body_frame",
]
