"""pptx: a layout per kind, slide numbers, text that always fits (ADR-226, ADR-274).

The deck is 16:9 LANDSCAPE and uses the template's own layouts — Section
Header for a part opener, Comparison for two sides, Title Only for data, key
figures and quotes — so a reader gets the deck PowerPoint would have made, not
eleven identical bullet slides. A deck of three parts or more opens on an
agenda the renderer writes from the parts' own titles.

Nothing overflows: every body is measured by ``fit`` before it is placed,
shrunk to the floor, then SPLIT into "Title (2/3)" slides. A bullet that does
not fit alone is cut at sentence boundaries — never clipped. A row of figures
or a quote that cannot fit becomes bullets, which split.

A deck that is presented moves (``pptx_motion``): every slide fades in, and
the points of a slide, the tiles of a key-figures slide, wait for the
speaker's click. A deck to read stays still.

A picture the writer asked for and the image model drew stands beside the
words of the cover, a part opener or a content slide (``pptx_pictures``); the
words are narrowed BEFORE they are measured. A picture nobody drew changes
nothing.
"""

from __future__ import annotations

import io
from collections.abc import Callable, Sequence
from typing import Any

from pptx.dml.color import RGBColor
from pptx.opc.constants import RELATIONSHIP_TYPE
from pptx.oxml.xmlchemy import OxmlElement
from pptx.util import Pt

from src.domains.document_generation import typography
from src.domains.document_generation.charts import chart_data
from src.domains.document_generation.computation import (
    compute_table,
    numeric_columns,
    totals_row_index,
)
from src.domains.document_generation.context import RenderContext
from src.domains.document_generation.fit import (
    BODY_SIZE_FLOOR_PT,
    BODY_SIZE_STEP_PT,
    SlidePlan,
    balanced_rows,
    fit_title,
    fits,
    plan_body,
)
from src.domains.document_generation.inline import parse_inline
from src.domains.document_generation.pictures import Picture, picture_key
from src.domains.document_generation.renderers import (
    pptx_charts,
    pptx_figures,
    pptx_pictures,
    pptx_tables,
)
from src.domains.document_generation.renderers import pptx_geometry as geometry
from src.domains.document_generation.renderers.office_theme import recolor_theme
from src.domains.document_generation.renderers.pptx_motion import (
    Reveal,
    Target,
    add_reveals,
    add_transition,
    deck_moves,
)
from src.domains.document_generation.schemas import (
    SLIDE_KINDS,
    DocumentContent,
    Illustration,
    KeyFigure,
    Slide,
    SlideContent,
)


def _continued(title: str, index: int, total: int) -> str:
    """« Cities (2/4) » — a numeric label, so it needs no translation."""
    return title if total == 1 else f"{title} ({index}/{total})"


def _set_title(shape: Any, text: str, color: str | None = None) -> None:
    """Write a title at the largest size that fits its frame, in the tone's ink."""
    size, _lines = fit_title(text, geometry.frame_of(shape, indent_pt=0))
    frame = shape.text_frame
    frame.text = ""
    run = frame.paragraphs[0].add_run()
    run.text = text
    run.font.size = Pt(size)
    if color is not None:
        run.font.color.rgb = RGBColor.from_string(color)


def _fit_single(lines: Sequence[str], shape: Any, base_pt: int) -> int:
    """The largest size from ``base_pt`` down to the floor at which ``lines`` fit."""
    frame = geometry.frame_of(shape)
    size = base_pt
    while size > BODY_SIZE_FLOOR_PT and not fits(lines, size, frame):
        size -= BODY_SIZE_STEP_PT
    return size


def _number(text_frame: Any, start: int) -> None:
    """Number the paragraphs « 1. 2. 3. », counting from ``start`` — PowerPoint's own list."""
    for paragraph in text_frame.paragraphs:
        properties = paragraph._p.get_or_add_pPr()
        font = OxmlElement("a:buFont")
        font.set("typeface", "+mj-lt")
        numbering = OxmlElement("a:buAutoNum")
        numbering.set("type", "arabicPeriod")
        if start > 1:
            numbering.set("startAt", str(start))
        properties.append(font)
        properties.append(numbering)


def _as_bullets(figures: Sequence[KeyFigure], context: RenderContext) -> list[str]:
    """Key figures as the bullets a crowded row falls back to, in the reader's convention."""
    return [
        (
            context.label("documents.figure_bullet", value=figure.value, label=figure.label)
            if figure.label
            else figure.value
        )
        for figure in figures
    ]


def _fill(
    text_frame: Any, items: Sequence[str], size_pt: float, *, color: str | None = None
) -> None:
    """Write items as paragraphs, carrying the model's inline emphasis."""
    text_frame.text = ""
    for index, item in enumerate(items):
        paragraph = text_frame.paragraphs[0] if index == 0 else text_frame.add_paragraph()
        for span in parse_inline(item):
            run = paragraph.add_run()
            run.text = span.text
            run.font.size = Pt(size_pt)
            run.font.bold = span.bold or None
            run.font.italic = span.italic or None
            if color is not None:
                run.font.color.rgb = RGBColor.from_string(color)
            if span.url:
                run.hyperlink.address = span.url


def _paint_divider(slide: Any, accent: str | None, ink: str) -> None:
    """A part opener's ground: the accent in a toned deck, its words and number in its ink."""
    if accent:
        slide.background.fill.solid()
        slide.background.fill.fore_color.rgb = RGBColor.from_string(accent)
        geometry.color_slide_number(slide, ink)
    for paragraph in slide.shapes.title.text_frame.paragraphs:
        for run in paragraph.runs:
            # The master shouts section titles in capitals; a document does not.
            run.font._rPr.set("cap", "none")
            if accent:
                run.font.color.rgb = RGBColor.from_string(ink)


def _tagline(slide: Any, words: str, ink: str, room: Any) -> None:
    """A part opener's tagline, beside its picture when it has one; none removes it."""
    tagline = geometry.placeholder(slide, geometry.BODY_IDX)
    if not words:
        geometry.remove_shape(tagline)
        return
    if room is not None:
        pptx_pictures.make_room(tagline, room)
    size = _fit_single([words], tagline, typography.PPTX_SECTION_TAGLINE_PT)
    _fill(tagline.text_frame, [words], size, color=ink)


class _Deck:
    """Per-deck state: the presentation, its layouts and the two body frames."""

    def __init__(self, content: SlideContent, context: RenderContext) -> None:
        self.content = content
        self.context = context
        self.presentation = geometry.base_presentation()
        self.palette = typography.palette_for(content.tone)
        if content.tone:
            master = self.presentation.slide_master.part
            recolor_theme(master.part_related_by(RELATIONSHIP_TYPE.THEME), self.palette.series)
        self.layouts = self.presentation.slide_layouts
        # Layout placeholders carry the geometry every slide of that layout gets,
        # so the frames are read once rather than probed slide by slide.
        self.body_frame = geometry.frame_of(
            geometry.placeholder(self.layouts[geometry.LAYOUT_CONTENT], geometry.BODY_IDX)
        )
        self.half_frame = geometry.frame_of(
            geometry.placeholder(self.layouts[geometry.LAYOUT_COMPARISON], 2)
        )
        self.moves = deck_moves(context.preferences.animations, content.delivery)
        self.side_frame = pptx_pictures.side_body_frame()

    def _picture(self, placement: Any, illustration: Illustration | None) -> Picture | None:
        """The drawn picture for this place, or none when nobody drew it."""
        if illustration is None:
            return None
        return self.context.pictures.get(picture_key(placement.frame.name, illustration.subject))

    def _new(self, layout_index: int, title: str, notes: str = "", room: Any = None) -> Any:
        layout = self.layouts[layout_index]
        slide = self.presentation.slides.add_slide(layout)
        if room is not None:
            pptx_pictures.make_room(slide.shapes.title, room)
        _set_title(slide.shapes.title, title, self.palette.accent)
        geometry.add_slide_number(slide, layout)
        if notes:
            slide.notes_slide.notes_text_frame.text = notes
        if self.moves:
            add_transition(slide)
        return slide

    def _reveal(self, slide: Any, reveals: Sequence[Reveal]) -> None:
        """Hold the reveals back for clicks — only in a deck that moves, and only
        when there is more than one thing to show."""
        if self.moves and len(reveals) > 1:
            add_reveals(slide, reveals)

    # -- kinds ------------------------------------------------------------
    def cover(self) -> None:
        """The title slide: the deck's subject, its audience, its date — and its picture."""
        layout = self.layouts[geometry.LAYOUT_TITLE]
        slide = self.presentation.slides.add_slide(layout)
        title = slide.shapes.title
        subtitle = geometry.placeholder(slide, geometry.BODY_IDX)
        illustration = self.content.illustration
        picture = self._picture(pptx_pictures.COVER, illustration)
        if picture is not None:
            for shape in (title, subtitle):
                pptx_pictures.make_room(
                    shape, pptx_pictures.COVER, left_in=pptx_pictures.COVER_TEXT_LEFT_IN
                )
        _set_title(title, self.content.title, self.palette.accent)
        if self.moves:
            add_transition(slide)
        kept = self._cover_lines(subtitle)
        if picture is not None and illustration is not None:
            pptx_pictures.align_left(title)
            if kept:
                pptx_pictures.align_left(subtitle)
            pptx_pictures.place(slide, picture, pptx_pictures.COVER, illustration.alt)

    def _cover_lines(self, subtitle: Any) -> bool:
        """The audience and the date under the title; False when there is neither."""
        lines = [line for line in (self.content.subtitle, self.context.date_line) if line]
        if not lines:
            geometry.remove_shape(subtitle)
            return False
        size = _fit_single(lines, subtitle, typography.PPTX_SUBTITLE_PT)
        _fill(subtitle.text_frame, lines[:1], size)
        if len(lines) > 1:
            paragraph = subtitle.text_frame.add_paragraph()
            run = paragraph.add_run()
            run.text = lines[1]
            run.font.size = Pt(min(size, typography.PPTX_DATE_PT))
            run.font.color.rgb = RGBColor.from_string(typography.MUTED)
        return True

    def content_slide(self, spec: Slide) -> None:
        """One idea per slide; a dense one becomes "Title (k/n)" slides.

        A picture stands beside the first part only: the points are measured in
        the narrowed frame, so the later parts, given their full width back,
        still hold what was planned for them.
        """
        placement = pptx_pictures.content_placement(bool(spec.bullets))
        picture = self._picture(placement, spec.illustration)
        plans = plan_body(spec.bullets, self.side_frame if picture else self.body_frame)
        for index, plan in enumerate(plans, start=1):
            slide = self._new(
                geometry.LAYOUT_CONTENT,
                _continued(spec.title, index, len(plans)),
                spec.notes if index == 1 else "",
            )
            body = geometry.placeholder(slide, geometry.BODY_IDX)
            if picture is not None and spec.illustration is not None and index == 1:
                if plan.bullets:
                    pptx_pictures.make_room(body, placement)
                pptx_pictures.place(slide, picture, placement, spec.illustration.alt)
            if plan.bullets:
                _fill(body.text_frame, plan.bullets, plan.size_pt)
                body_id = int(body.shape_id)
                self._reveal(
                    slide,
                    [
                        Reveal((Target(body_id, paragraph, has_text=True),))
                        for paragraph in range(len(plan.bullets))
                    ],
                )
            else:
                geometry.remove_shape(body)

    def agenda(self, parts: Sequence[str]) -> None:
        """The deck's parts, numbered, right after the cover."""
        title = self.context.label("documents.agenda_title")
        plans = plan_body(parts, self.body_frame)
        first = 1
        for index, plan in enumerate(plans, start=1):
            slide = self._new(geometry.LAYOUT_CONTENT, _continued(title, index, len(plans)))
            body = geometry.placeholder(slide, geometry.BODY_IDX)
            _fill(body.text_frame, plan.bullets, plan.size_pt)
            _number(body.text_frame, first)
            first += len(plan.bullets)

    def section(self, spec: Slide) -> None:
        """A part opener on the template's own Section Header layout.

        A toned deck opens each part on the accent: the divider is the one
        slide where colour IS the content, its words in the ink that reads on it.
        """
        picture = self._picture(pptx_pictures.SECTION, spec.illustration)
        room = pptx_pictures.SECTION if picture is not None else None
        slide = self._new(geometry.LAYOUT_SECTION, spec.title, spec.notes, room=room)
        accent = self.palette.accent
        ink = typography.label_on(accent) if accent else typography.MUTED
        _paint_divider(slide, accent, ink)
        _tagline(slide, spec.subtitle, ink, room)
        if picture is not None and spec.illustration is not None:
            # The picture says what the pictogram would have: one image per opener.
            pptx_pictures.place(slide, picture, pptx_pictures.SECTION, spec.illustration.alt)
        elif spec.icon:
            pptx_figures.draw_section_icon(slide, spec.icon, ink if accent else self.palette.marker)

    def comparison(self, spec: Slide) -> None:
        """Two sides on the Comparison layout, each split independently if needed."""
        plans = [plan_body(column.bullets, self.half_frame) for column in spec.columns]
        total = max(len(side) for side in plans)
        for index in range(total):
            slide = self._new(
                geometry.LAYOUT_COMPARISON,
                _continued(spec.title, index + 1, total),
                spec.notes if index == 0 else "",
            )
            for side, (heading_idx, body_idx) in enumerate(geometry.COMPARISON_SIDES):
                self._side(slide, spec, side, heading_idx, body_idx, plans[side], index)

    def _side(
        self,
        slide: Any,
        spec: Slide,
        side: int,
        heading_idx: int,
        body_idx: int,
        plans: list[SlidePlan],
        index: int,
    ) -> None:
        heading_shape = geometry.placeholder(slide, heading_idx)
        heading = spec.columns[side].heading
        size = _fit_single([heading], heading_shape, typography.PPTX_COMPARISON_HEADING_PT)
        _fill(heading_shape.text_frame, [heading], size)
        body = geometry.placeholder(slide, body_idx)
        plan = plans[index] if index < len(plans) else None
        if plan is not None and plan.bullets:
            _fill(body.text_frame, plan.bullets, plan.size_pt)
        else:
            geometry.remove_shape(body)

    def table(self, spec: Slide) -> None:
        """Data as native tables, chunked, header repeated on every part."""
        sheet = spec.table
        if sheet is None:
            return
        numeric = numeric_columns(sheet)
        totals = totals_row_index(sheet, self.context.language)
        chunks = pptx_tables.split_rows(sheet)
        first = 0
        for index, rows in enumerate(chunks, start=1):
            slide = self._new(
                geometry.LAYOUT_TITLE_ONLY,
                _continued(spec.title, index, len(chunks)),
                spec.notes if index == 1 else "",
            )
            chunk = sheet.model_copy(update={"rows": rows})
            bold = (
                totals - first
                if totals is not None and first <= totals < first + len(rows)
                else None
            )
            pptx_tables.add_table(slide, chunk, numeric, bold_row=bold)
            first += len(rows)

    def chart(self, spec: Slide) -> None:
        """A native chart in the data area of a Title Only slide."""
        if spec.table is None:
            return
        data = chart_data(compute_table(spec.table), self.context.language, self.palette.series)
        if data is None:
            return
        slide = self._new(geometry.LAYOUT_TITLE_ONLY, spec.title, spec.notes)
        pptx_charts.add_chart(slide, data, self.context.language)

    def figures(self, spec: Slide) -> None:
        """Key figures as tiles, a row per slide; a row that cannot fit becomes bullets."""
        rows = balanced_rows(spec.figures, typography.PPTX_FIGURES_PER_SLIDE)
        for index, figures in enumerate(rows, start=1):
            title = _continued(spec.title, index, len(rows))
            notes = spec.notes if index == 1 else ""
            row = pptx_figures.plan_tiles(figures)
            if row is None:
                bullets = _as_bullets(figures, self.context)
                self.content_slide(Slide(title=title, bullets=bullets, notes=notes))
                continue
            slide = self._new(geometry.LAYOUT_TITLE_ONLY, title, notes)
            self._reveal(slide, pptx_figures.draw_tiles(slide, row, self.palette))

    def quote(self, spec: Slide) -> None:
        """Someone's words beside a rule; words that cannot fit become a bullet."""
        author = (
            self.context.label("documents.quote_attribution", author=spec.subtitle)
            if spec.subtitle
            else ""
        )
        plan = pptx_figures.plan_quote(spec.quote, author)
        if plan is None:
            words = f"{spec.quote} {author}".strip()
            self.content_slide(Slide(title=spec.title, bullets=[words], notes=spec.notes))
            return
        slide = self._new(geometry.LAYOUT_TITLE_ONLY, spec.title, spec.notes)
        pptx_figures.draw_quote(slide, plan, self.palette)


_KINDS: dict[str, Callable[[_Deck, Slide], None]] = {
    "content": _Deck.content_slide,
    "section": _Deck.section,
    "comparison": _Deck.comparison,
    "table": _Deck.table,
    "chart": _Deck.chart,
    "figures": _Deck.figures,
    "quote": _Deck.quote,
}

# Boot-time completeness (ADR-085): every slide kind the schema allows is drawn.
assert set(_KINDS) == SLIDE_KINDS, "_KINDS must cover every slide kind"


def render_pptx(content: DocumentContent, context: RenderContext) -> bytes:
    """A 16:9 deck whose every slide is the shape its content deserves."""
    if not isinstance(content, SlideContent):
        raise ValueError("pptx rendering requires SlideContent")
    deck = _Deck(content, context)
    deck.cover()
    parts = [spec.title for spec in content.slides if spec.kind == "section"]
    if len(parts) >= typography.PPTX_AGENDA_MIN_PARTS:
        deck.agenda(parts)
    for spec in content.slides:
        _KINDS[spec.kind](deck, spec)
    buf = io.BytesIO()
    deck.presentation.save(buf)
    return buf.getvalue()
