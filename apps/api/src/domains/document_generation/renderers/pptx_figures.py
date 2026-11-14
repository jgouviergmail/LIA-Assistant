"""Key figures, quotes and pictograms on a slide (ADR-274).

The writer says what a slide IS — the few numbers that carry the message, the
words someone said — and this module draws it: tiles side by side, each figure
over what it measures under an optional pictogram; a quote beside a rule of the
deck's colour, its author after it.

Every frame is measured with ``fit`` BEFORE anything is placed. A row of
figures or a quote that cannot fit at the floor sizes plans to ``None``, and
the deck writes the same words as bullets instead, which split rather than
overflow — never a clipped line. One row shares one type size: figures side by
side read as a set only if they look like one.
"""

from __future__ import annotations

import io
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from lxml import etree
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Inches, Length, Pt

from src.domains.document_generation import typography
from src.domains.document_generation.fit import (
    BODY_SIZE_STEP_PT,
    TextFrame,
    fits,
    line_count,
    stack_fits,
    stack_height,
    text_height,
)
from src.domains.document_generation.icons import icon_names, icon_png
from src.domains.document_generation.renderers import pptx_geometry as geometry
from src.domains.document_generation.renderers.pptx_motion import Reveal, Target
from src.domains.document_generation.schemas import KeyFigure
from src.domains.document_generation.typography import Palette

_POINTS_PER_INCH = 72.0
#: Office's « Mark as decorative »: a reader of the slide skips the picture.
_DECORATIVE_URI = "{C183D7F6-B498-43B3-948B-1728B52AA6E4}"
_DECORATIVE_NS = "http://schemas.microsoft.com/office/drawing/2017/decorative"
_DRAWING_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
#: A quote's rule, its distance from the words, and the space before the author.
_RULE_WIDTH_IN = 0.08
_RULE_TO_WORDS_IN = 0.3
_WORDS_TO_AUTHOR_IN = 0.15
_AUTHOR_HEIGHT_IN = 0.75
#: The space between a section opener's pictogram and the words under it.
_ICON_ABOVE_TEXT_IN = 0.35
#: Rounding EMUs must never turn a frame that fits into one that does not.
_FRAME_SLACK_IN = 0.05
#: How round a tile's corners are (PowerPoint's adjustment, 0-0.5).
_TILE_CORNER = 0.06


@dataclass(frozen=True, slots=True)
class Box:
    """A rectangle on the slide, in inches."""

    left: float
    top: float
    width: float
    height: float

    def frame(self) -> TextFrame:
        """The box as a text frame with no bullet indent."""
        return TextFrame(
            self.width * _POINTS_PER_INCH, self.height * _POINTS_PER_INCH, indent_pt=0.0
        )


@dataclass(frozen=True, slots=True)
class TileRow:
    """A row of key figures, measured: where each tile goes and at what sizes."""

    figures: tuple[KeyFigure, ...]
    tiles: tuple[Box, ...]
    texts: tuple[Box, ...]
    icons: tuple[Box | None, ...]
    value_pt: int
    label_pt: int
    with_icons: bool


@dataclass(frozen=True, slots=True)
class QuotePlan:
    """A quote, measured: its words, their author, the boxes and the sizes."""

    words: str
    author: str
    words_box: Box
    author_box: Box | None
    words_pt: int
    author_pt: int


def _area() -> Box:
    """The data area under a Title Only slide's title."""
    return Box(
        geometry.TABLE_LEFT_IN,
        geometry.TABLE_TOP_IN,
        geometry.TABLE_WIDTH_IN,
        geometry.TABLE_AREA_HEIGHT_IN,
    )


def _drawable(name: str) -> bool:
    return bool(name) and name in icon_names()


def _largest(base: int, floor: int, accepts: Callable[[int], bool]) -> int | None:
    """The largest size from ``base`` down to ``floor`` that ``accepts``."""
    size = base
    while size >= floor:
        if accepts(size):
            return size
        size -= BODY_SIZE_STEP_PT
    return None


def _tile_boxes(count: int) -> list[Box]:
    area = _area()
    gap = typography.PPTX_FIGURE_GAP_IN
    width = min(typography.PPTX_FIGURE_TILE_MAX_WIDTH_IN, (area.width - (count - 1) * gap) / count)
    row = count * width + (count - 1) * gap
    left = area.left + (area.width - row) / 2
    height = typography.PPTX_FIGURE_TILE_HEIGHT_IN
    top = area.top + (area.height - height) / 2
    return [Box(left + index * (width + gap), top, width, height) for index in range(count)]


def _icon_room(with_icons: bool) -> float:
    """The height a row's pictogram takes above its words, gap included."""
    if not with_icons:
        return 0.0
    return typography.PPTX_FIGURE_ICON_IN + typography.PPTX_FIGURE_ICON_GAP_IN


def _room(tile: Box, with_icons: bool) -> Box:
    """Where a tile's words MAY go: inside its padding, under its pictogram."""
    pad = typography.PPTX_FIGURE_PADDING_IN
    icon = _icon_room(with_icons)
    return Box(
        tile.left + pad, tile.top + pad + icon, tile.width - 2 * pad, tile.height - 2 * pad - icon
    )


def _placed(tile: Box, with_icons: bool, text_height_in: float) -> tuple[Box, Box | None]:
    """The words' box and the pictogram's, the pair centred in the tile."""
    pad = typography.PPTX_FIGURE_PADDING_IN
    side = typography.PPTX_FIGURE_ICON_IN
    group = _icon_room(with_icons) + text_height_in
    top = tile.top + (tile.height - group) / 2
    icon = Box(tile.left + (tile.width - side) / 2, top, side, side) if with_icons else None
    words = Box(tile.left + pad, top + _icon_room(with_icons), tile.width - 2 * pad, text_height_in)
    return words, icon


def _stack(figure: KeyFigure, value_pt: int, label_pt: int) -> list[tuple[str, float]]:
    return [(figure.value, value_pt), *([(figure.label, label_pt)] if figure.label else [])]


def plan_tiles(figures: Sequence[KeyFigure]) -> TileRow | None:
    """Measure one row of key figures.

    Args:
        figures: At most ``PPTX_FIGURES_PER_SLIDE`` figures, each with a value.

    Returns:
        The row, or ``None`` when one of them cannot fit at the floor sizes.
    """
    with_icons = any(_drawable(figure.icon) for figure in figures)
    tiles = _tile_boxes(len(figures))
    frames = [_room(tile, with_icons).frame() for tile in tiles]
    base = typography.PPTX_FIGURE_VALUE_PT[len(figures)]

    value_pt = _largest(
        base,
        typography.PPTX_FIGURE_VALUE_FLOOR_PT,
        lambda size: all(
            line_count(figure.value, size, frame) == 1
            for figure, frame in zip(figures, frames, strict=True)
        ),
    )
    if value_pt is None:
        return None
    label_pt = _largest(
        typography.PPTX_FIGURE_LABEL_PT,
        typography.PPTX_FIGURE_LABEL_FLOOR_PT,
        lambda size: all(
            stack_fits(_stack(figure, value_pt, size), frame)
            for figure, frame in zip(figures, frames, strict=True)
        ),
    )
    if label_pt is None:
        return None
    # One height for the row's words, so the figures stand on one line across tiles.
    measured = max(
        stack_height(_stack(figure, value_pt, label_pt), frame)
        for figure, frame in zip(figures, frames, strict=True)
    )
    text_height_in = min(frames[0].height_pt, measured) / _POINTS_PER_INCH + _FRAME_SLACK_IN
    placed = [_placed(tile, with_icons, text_height_in) for tile in tiles]
    return TileRow(
        figures=tuple(figures),
        tiles=tuple(tiles),
        texts=tuple(words for words, _icon in placed),
        icons=tuple(icon for _words, icon in placed),
        value_pt=value_pt,
        label_pt=label_pt,
        with_icons=with_icons,
    )


def _emu(inches: float) -> Length:
    return Inches(inches)


def _text_box(slide: Any, box: Box, anchor: MSO_ANCHOR) -> Any:
    shape = slide.shapes.add_textbox(
        _emu(box.left), _emu(box.top), _emu(box.width), _emu(box.height)
    )
    frame = shape.text_frame
    frame.word_wrap = True
    frame.vertical_anchor = anchor
    return shape


def _run(paragraph: Any, text: str, size: int, color: str, **style: bool) -> None:
    run = paragraph.add_run()
    run.text = text
    run.font.size = Pt(size)
    run.font.color.rgb = RGBColor.from_string(color)
    for name, value in style.items():
        setattr(run.font, name, value)


def mark_decorative(shape: Any) -> None:
    """Office's « Mark as decorative »: no description, and the flag that says why.

    A screen reader skips the shape instead of announcing « picture » or
    « rectangle » with nothing to say; PowerPoint's accessibility checker stops
    asking for a description it should not have.

    Args:
        shape: A python-pptx picture or autoshape.
    """
    properties = shape._element._nvXxPr.cNvPr
    properties.set("descr", "")
    extensions = properties.find(qn("a:extLst"))
    if extensions is None:
        extensions = etree.SubElement(properties, f"{{{_DRAWING_NS}}}extLst")
    # One extension per URI: marking twice leaves one flag.
    if any(ext.get("uri") == _DECORATIVE_URI for ext in extensions.iter(qn("a:ext"))):
        return
    extension = etree.SubElement(extensions, f"{{{_DRAWING_NS}}}ext", uri=_DECORATIVE_URI)
    flag = etree.SubElement(
        extension, f"{{{_DECORATIVE_NS}}}decorative", nsmap={"adec": _DECORATIVE_NS}
    )
    flag.set("val", "1")


def _plain_fill(shape: Any, color: str) -> None:
    """A flat fill with no outline, and no announcement: a ground or a rule is decoration."""
    shape.fill.solid()
    shape.fill.fore_color.rgb = RGBColor.from_string(color)
    shape.line.fill.background()
    mark_decorative(shape)


def draw_icon(slide: Any, name: str, color: str, box: Box) -> int | None:
    """Place a pictogram, marked decorative.

    Args:
        slide: The slide to draw on.
        name: A name of the vendored set.
        color: Six hexadecimal digits, the pictogram's ink.
        box: Where it goes, in inches.

    Returns:
        The picture's shape id, or ``None`` when the set cannot draw ``name``.
    """
    png = icon_png(name, color)
    if png is None:
        return None
    picture = slide.shapes.add_picture(
        io.BytesIO(png), _emu(box.left), _emu(box.top), _emu(box.width), _emu(box.height)
    )
    mark_decorative(picture)
    return int(picture.shape_id)


def draw_tiles(slide: Any, row: TileRow, palette: Palette) -> list[Reveal]:
    """Draw a measured row of key figures.

    Args:
        slide: A Title Only slide.
        row: The row ``plan_tiles`` measured.
        palette: The deck's colours: the wash grounds the tile, the accent inks
            the figure and its pictogram.

    Returns:
        One reveal per tile, its pictogram and its words appearing with it.
    """
    reveals: list[Reveal] = []
    for figure, tile, text, icon in zip(row.figures, row.tiles, row.texts, row.icons, strict=True):
        ground = slide.shapes.add_shape(
            MSO_SHAPE.ROUNDED_RECTANGLE,
            _emu(tile.left),
            _emu(tile.top),
            _emu(tile.width),
            _emu(tile.height),
        )
        ground.adjustments[0] = _TILE_CORNER
        _plain_fill(ground, palette.wash)
        targets = [Target(int(ground.shape_id))]
        if icon is not None and figure.icon:
            icon_id = draw_icon(slide, figure.icon, palette.title_ink, icon)
            if icon_id is not None:
                targets.append(Target(icon_id))
        words = _text_box(slide, text, MSO_ANCHOR.TOP)
        value = words.text_frame.paragraphs[0]
        value.alignment = PP_ALIGN.CENTER
        _run(value, figure.value, row.value_pt, palette.title_ink, bold=True)
        if figure.label:
            label = words.text_frame.add_paragraph()
            label.alignment = PP_ALIGN.CENTER
            _run(label, figure.label, row.label_pt, typography.MUTED)
        targets.append(Target(int(words.shape_id), has_text=True))
        reveals.append(Reveal(tuple(targets)))
    return reveals


def plan_quote(words: str, author_text: str) -> QuotePlan | None:
    """Measure a quote: its words beside the rule, its author under them.

    Args:
        words: The quoted words, cleaned.
        author_text: Who said them, already in the reader's convention
            (``documents.quote_attribution``), or empty.

    Returns:
        The plan, centred vertically in the data area, or ``None`` when the
        words or their author cannot fit at the floor sizes.
    """
    area = _area()
    left = area.left + _RULE_TO_WORDS_IN
    width = area.width - _RULE_TO_WORDS_IN
    reserved = _WORDS_TO_AUTHOR_IN + _AUTHOR_HEIGHT_IN if author_text else 0.0
    available = Box(left, area.top, width, area.height - reserved)
    words_pt = _largest(
        typography.PPTX_QUOTE_PT,
        typography.PPTX_QUOTE_FLOOR_PT,
        lambda size: fits([words], size, available.frame()),
    )
    if words_pt is None:
        return None
    author_frame = Box(left, 0.0, width, _AUTHOR_HEIGHT_IN).frame()
    author_pt = (
        _largest(
            typography.PPTX_ATTRIBUTION_PT,
            typography.PPTX_ATTRIBUTION_FLOOR_PT,
            lambda size: fits([author_text], size, author_frame),
        )
        if author_text
        else typography.PPTX_ATTRIBUTION_PT
    )
    if author_pt is None:
        return None
    measured = text_height([words], words_pt, available.frame()) / _POINTS_PER_INCH
    words_height = min(available.height, measured + _FRAME_SLACK_IN)
    block = words_height + reserved
    top = area.top + (area.height - block) / 2
    author_box = (
        Box(left, top + words_height + _WORDS_TO_AUTHOR_IN, width, _AUTHOR_HEIGHT_IN)
        if author_text
        else None
    )
    return QuotePlan(
        words=words,
        author=author_text,
        words_box=Box(left, top, width, words_height),
        author_box=author_box,
        words_pt=words_pt,
        author_pt=author_pt,
    )


def draw_quote(slide: Any, plan: QuotePlan, palette: Palette) -> None:
    """Draw a measured quote: the rule, the words in italics, then their author.

    Args:
        slide: A Title Only slide.
        plan: The quote ``plan_quote`` measured.
        palette: The deck's colours: its marker draws the rule.
    """
    words_box = plan.words_box
    rule = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE,
        _emu(words_box.left - _RULE_TO_WORDS_IN),
        _emu(words_box.top),
        _emu(_RULE_WIDTH_IN),
        _emu(words_box.height),
    )
    _plain_fill(rule, palette.marker)
    words = _text_box(slide, words_box, MSO_ANCHOR.TOP)
    _run(words.text_frame.paragraphs[0], plan.words, plan.words_pt, typography.INK, italic=True)
    if plan.author_box is not None:
        author = _text_box(slide, plan.author_box, MSO_ANCHOR.TOP)
        _run(author.text_frame.paragraphs[0], plan.author, plan.author_pt, typography.MUTED)


def draw_section_icon(slide: Any, name: str, color: str) -> None:
    """A section opener's pictogram, aligned with its title, above its tagline.

    Args:
        slide: A Section Header slide, its tagline already filled or removed.
        name: A name of the vendored set.
        color: The ink that reads on the slide's ground.
    """
    title = slide.shapes.title
    taglines = [
        shape for shape in slide.placeholders if shape.placeholder_format.idx == geometry.BODY_IDX
    ]
    anchor = (taglines[0] if taglines else title).top / geometry.EMU_PER_IN
    side = typography.PPTX_SECTION_ICON_IN
    box = Box(title.left / geometry.EMU_PER_IN, anchor - _ICON_ABOVE_TEXT_IN - side, side, side)
    draw_icon(slide, name, color, box)


__all__ = [
    "Box",
    "QuotePlan",
    "TileRow",
    "draw_icon",
    "draw_quote",
    "draw_section_icon",
    "draw_tiles",
    "mark_decorative",
    "plan_quote",
    "plan_tiles",
]
