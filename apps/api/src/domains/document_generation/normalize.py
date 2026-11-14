"""The canonical form of what the model produced (ADR-274).

Every incoherence a writer can plausibly produce is REPAIRED here,
mechanically, and never reported as a defect (ADR-184): a heading level outside
1..4 is clamped, an empty block is dropped, markdown that leaked into a
paragraph becomes the block it is, a heading the model numbered itself loses
its prefix when the renderer numbers, a slide's effective kind follows the
payload it actually carries, an unknown tone leaves the document grey, a
pictogram the renderer cannot draw is none, a figure without its number is no
figure, a picture past the person's budget — or with no subject — is none. A
source keeps its place in the list, which is its number in the text, and links
only to a web address.

Renderers consume the output of this module and never the raw content, so no
renderer has to ask whether a table has rows or a comparison has two sides.
The transformation is idempotent: normalizing twice changes nothing.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from itertools import zip_longest
from urllib.parse import urlsplit

from src.core.config import settings
from src.domains.document_generation.columns import (
    NAME_MAX_CHARS,
    UNIT_KINDS,
    UNIT_MAX_CHARS,
    column_key,
    normalize_table,
    reads_as_percent,
)
from src.domains.document_generation.computation import input_value, materialize_table
from src.domains.document_generation.context import RenderContext
from src.domains.document_generation.pictures import illustration_budget
from src.domains.document_generation.sanitize import strip_control_characters
from src.domains.document_generation.schemas import (
    DECK_DELIVERIES,
    DOCUMENT_TONES,
    FIGURE_KINDS,
    SCHEMA_BY_DOC_TYPE,
    SLIDE_ICONS,
    ChartSpec,
    DocumentContent,
    Illustration,
    KeyFigure,
    SectionBlock,
    SectionedContent,
    SheetInput,
    Slide,
    SlideColumn,
    SlideContent,
    Source,
    TableSheet,
    TabularContent,
)
from src.domains.document_generation.tables import infer_column_types, sanitize_headers
from src.domains.document_generation.workbook_figures import normalize_figures

#: Word and the PDF renderer number three levels; deeper headings are plain.
MAX_HEADING_LEVEL = 4
NUMBERED_LEVELS = 3

_HEADING_NUMBER = re.compile(r"^\s*\d+(?:\.\d+)*[.)]?\s+")
_MD_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_MD_BULLET = re.compile(r"^\s*[-*•]\s+(.+?)\s*$")
_MD_NUMBERED = re.compile(r"^\s*\d+[.)]\s+(.+?)\s*$")
#: A comparison of three or more sides is a table, not a slide of columns.
MAX_COMPARISON_COLUMNS = 2
#: The schemes a document links to: its reader opens nothing else.
_WEB_SCHEMES = frozenset({"http", "https"})


def _clean(text: str) -> str:
    """Collapse whitespace and drop what a document writer refuses.

    The ONE funnel every piece of prose passes through, so no renderer has to
    know that XML forbids a form feed.
    """
    return strip_control_characters(" ".join(text.split()))


def _tone(value: str) -> str:
    """A tone the renderer knows, or none: an unknown tone keeps the document grey."""
    tone = value.strip().casefold()
    return tone if tone in DOCUMENT_TONES else ""


def _icon(value: str) -> str:
    """A pictogram the renderer draws, or none: « Trending up » reads as ``trending-up``."""
    name = "-".join(value.replace("_", " ").casefold().split())
    return name if name in SLIDE_ICONS else ""


def _delivery(value: str) -> str:
    """How the deck will be used, or empty — which the renderer reads as « read »."""
    delivery = value.strip().casefold()
    return delivery if delivery in DECK_DELIVERIES else ""


def _heading_count(content: SectionedContent) -> int:
    return sum(1 for block in content.blocks if block.kind == "heading" and block.text.strip())


def document_is_numbered(content: SectionedContent, context: RenderContext) -> bool:
    """Whether the long-document apparatus is on for this document.

    ONE predicate drives the table of contents, the heading numbering and the
    page break before each part: a note never grows half an apparatus.

    Args:
        content: The document (canonical or raw — only headings are counted).
        context: The render context; ``plain`` pins the apparatus off.

    Returns:
        True when the renderer numbers and adds a table of contents.
    """
    return (
        context.structure == "auto"
        and _heading_count(content) >= settings.document_generation_toc_min_headings
    )


class HeadingNumberer:
    """1 / 1.1 / 1.1.1 counters for levels 1-3; deeper levels stay unnumbered."""

    def __init__(self) -> None:
        self._counters = [0] * NUMBERED_LEVELS

    def number(self, level: int) -> str:
        """The number of the next heading at ``level``, advancing the counters.

        Args:
            level: Heading level, already clamped to 1..4.

        Returns:
            The dotted number, or an empty string beyond the numbered levels.
        """
        if level > NUMBERED_LEVELS:
            return ""
        self._counters[level - 1] += 1
        for deeper in range(level, NUMBERED_LEVELS):
            self._counters[deeper] = 0
        return ".".join(str(count) for count in self._counters[:level])


def _leaked_markdown(text: str) -> SectionBlock | None:
    """A paragraph that is really a list or a heading, or ``None``."""
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return None
    if len(lines) == 1 and (match := _MD_HEADING.match(lines[0])):
        return SectionBlock(kind="heading", level=len(match.group(1)), text=match.group(2))
    for pattern, kind in ((_MD_BULLET, "bullets"), (_MD_NUMBERED, "numbered")):
        matches = [pattern.match(line) for line in lines]
        if all(matches):
            items = [match.group(1) for match in matches if match is not None]
            return SectionBlock(kind=kind, items=items)
    return None


def _shown_table(
    sheet: TableSheet | None, language: str
) -> tuple[TableSheet | None, TableSheet | None]:
    """A report's table with its values written out, and its summary when it has one.

    A report, a slide and a Markdown file show TEXT: the computed columns, the
    totals row and the grouped summary are written once here, in the reader's
    conventions, by the same computation the workbook caches (ADR-274 amendment).
    """
    canonical = normalize_table(sheet, language) if sheet is not None else None
    if canonical is None:
        return None, None
    return materialize_table(canonical, language)


def _chart_table(sheet: TableSheet | None, language: str, caption: str = "") -> TableSheet | None:
    """A chart's data: the canonical table, its chart settled and named.

    A chart reads the table the workbook would compute — its formulas symbolic,
    its values computed at drawing time — never the text a report shows. Its
    title IS its caption: one name, wherever the figure is drawn.
    """
    if sheet is None:
        return None
    chart = sheet.chart or ChartSpec()
    title = caption or _clean(chart.title)
    canonical = normalize_table(
        sheet.model_copy(
            update={"chart": chart.model_copy(update={"title": title}), "summary": None}
        ),
        language,
    )
    return canonical if canonical is not None and canonical.chart is not None else None


def _figure(chart: TableSheet) -> SectionBlock:
    title = chart.chart.title if chart.chart is not None else ""
    return SectionBlock(kind="chart", table=chart, caption=title)


def _canonical_blocks(block: SectionBlock, language: str) -> list[SectionBlock]:
    """A block in canonical form: none, itself, or a table followed by its summary and chart.

    A chart that cannot be drawn — nothing to measure, a single row — shows its
    data as a table instead: the figures are never lost with the figure.
    """
    if block.kind == "figures":
        return _figures_block(block, language)
    if block.kind == "illustration":
        return _illustration_block(block)
    if block.kind == "chart":
        chart = _chart_table(block.table, language, _clean(block.caption))
        if chart is not None:
            return [_figure(chart)]
        block = block.model_copy(update={"kind": "table"})
    if block.kind != "table":
        canonical = _canonical_block(block, language)
        return [canonical] if canonical is not None else []
    shown, summary = _shown_table(block.table, language)
    if shown is None:
        return []
    blocks = [SectionBlock(kind="table", table=shown, caption=_clean(block.caption))]
    if summary is not None:
        blocks.append(SectionBlock(kind="table", table=summary, caption=summary.name))
    if block.table is not None and block.table.chart is not None:
        chart = _chart_table(block.table, language)
        if chart is not None:
            blocks.append(_figure(chart))
    return blocks


def _canonical_block(block: SectionBlock, language: str) -> SectionBlock | None:
    """One non-table block in canonical form, or ``None`` when there is nothing to render."""
    if block.kind == "paragraph" and (leaked := _leaked_markdown(block.text)) is not None:
        block = leaked
    if block.kind in ("bullets", "numbered"):
        items = [_clean(item) for item in block.items if item.strip()]
        if items:
            return SectionBlock(kind=block.kind, items=items)
        # ``items`` is optional, so a writer can put its list in ``text``. Read
        # that text through the SAME paragraph path rather than flattening it:
        # collapsing it here merged "- a\n- b" into one line of prose carrying a
        # stray dash, and left the markdown for a second pass to recognise.
        return _canonical_block(SectionBlock(kind="paragraph", text=block.text), language)
    text = _clean(block.text)
    if not text:
        return None
    if block.kind == "heading":
        return SectionBlock(
            kind="heading", level=min(max(block.level, 1), MAX_HEADING_LEVEL), text=text
        )
    return SectionBlock(kind=block.kind, text=text)


def _figures_block(block: SectionBlock, language: str) -> list[SectionBlock]:
    """Key figures with their number — and no pictogram, which a page does not draw.

    A figures block whose numbers came as words keeps them, as a paragraph.
    """
    figures = [figure.model_copy(update={"icon": ""}) for figure in _clean_figures(block.figures)]
    if figures:
        return [SectionBlock(kind="figures", figures=figures)]
    words = _canonical_block(SectionBlock(kind="paragraph", text=block.text), language)
    return [words] if words is not None else []


def _illustration_block(block: SectionBlock) -> list[SectionBlock]:
    """A picture with something to draw, and the caption that names it."""
    picture = _canonical_illustration(block.illustration)
    if picture is None:
        return []
    return [SectionBlock(kind="illustration", illustration=picture, caption=_clean(block.caption))]


class _Budget:
    """The pictures a document may still carry, spent in document order — the cover first."""

    def __init__(self, pictures: int) -> None:
        self._left = pictures

    def admit(self, picture: Illustration | None) -> Illustration | None:
        """The picture while the budget lasts, spending one; none past it."""
        if picture is None or self._left <= 0:
            return None
        self._left -= 1
        return picture


def _web_address(value: str) -> str:
    """A web address with a host, as written; anything else links nowhere."""
    address = strip_control_characters(value.strip())
    if not address or any(character.isspace() for character in address):
        return ""
    try:
        parts = urlsplit(address)
    except ValueError:  # a malformed IPv6 host
        return ""
    return address if parts.scheme.casefold() in _WEB_SCHEMES and parts.hostname else ""


def _canonical_source(source: Source) -> Source:
    """A source cleaned: a title — its address when it has none — and a web address or none."""
    address = _web_address(source.url)
    return Source(title=_clean(source.title) or address, url=address)


def _canonical_sources(sources: list[Source]) -> list[Source]:
    """Every source in its place: its position is its number in the text.

    Dropping one from the middle would renumber every later citation, so an
    entry is never dropped but cleaned; only empty entries at the END go,
    where nothing follows them to renumber.
    """
    kept = [_canonical_source(source) for source in sources]
    while kept and not kept[-1].title:
        kept.pop()
    return kept


def _report_pictures(
    content: SectionedContent, context: RenderContext
) -> tuple[Illustration | None, list[SectionBlock]]:
    """The cover and the canonical blocks, pictures within the budget: the cover first."""
    budget = _Budget(illustration_budget(context.preferences))
    cover = budget.admit(_canonical_illustration(content.illustration))
    blocks = [
        canonical
        for block in content.blocks
        for canonical in _canonical_blocks(block, context.language)
        if canonical.kind != "illustration" or budget.admit(canonical.illustration) is not None
    ]
    return cover, blocks


def normalize_sectioned(content: SectionedContent, context: RenderContext) -> SectionedContent:
    """Canonical blocks and sources; pictures within the budget; heading prefixes
    stripped when the renderer numbers.

    Args:
        content: What the model produced.
        context: Reader and deployment facts (its ``structure`` decides the
            apparatus, hence whether model-written numbers are stripped; its
            ``preferences`` the pictures the document may carry).

    Returns:
        A document whose blocks a renderer can draw without asking questions.
    """
    cover, blocks = _report_pictures(content, context)
    pictured = cover is not None or any(block.kind == "illustration" for block in blocks)
    title = _clean(content.title)
    canonical_content = SectionedContent(
        filename_stem=content.filename_stem,
        title=title,
        subtitle=_clean(content.subtitle),
        tone=_tone(content.tone),
        illustration=cover,
        image_style=_clean(content.image_style) if pictured else "",
        # A document of nothing still has its title to show.
        blocks=blocks or [SectionBlock(kind="paragraph", text=title)],
        sources=_canonical_sources(content.sources),
    )
    if document_is_numbered(canonical_content, context):
        for block in canonical_content.blocks:
            if block.kind == "heading":
                # Stripping must never empty a heading that IS a number.
                block.text = _HEADING_NUMBER.sub("", block.text) or block.text
    return canonical_content


def _columns_to_table(columns: list[SlideColumn], language: str) -> TableSheet | None:
    """Three or more compared sides read as a table, not as a crowded slide."""
    headers = [column.heading for column in columns]
    rows = [
        list(cells) for cells in zip_longest(*(column.bullets for column in columns), fillvalue="")
    ]
    return normalize_table(TableSheet(name="comparison", headers=headers, rows=rows), language)


def _clean_columns(columns: list[SlideColumn]) -> list[SlideColumn]:
    return [
        SlideColumn(
            heading=_clean(column.heading),
            bullets=[_clean(bullet) for bullet in column.bullets if bullet.strip()],
        )
        for column in columns
        if column.heading.strip() or any(bullet.strip() for bullet in column.bullets)
    ]


def _canonical_illustration(value: Illustration | None) -> Illustration | None:
    """A picture with something to draw, cleaned; no subject is no picture."""
    if value is None:
        return None
    subject = _clean(value.subject)
    return Illustration(subject=subject, alt=_clean(value.alt)) if subject else None


def _clean_figures(figures: list[KeyFigure]) -> list[KeyFigure]:
    """Figures with their number, cleaned; a label alone is not a key figure."""
    return [
        KeyFigure(value=_clean(figure.value), label=_clean(figure.label), icon=_icon(figure.icon))
        for figure in figures
        if figure.value.strip()
    ]


@dataclass(slots=True)
class _Payload:
    """What one authored slide actually carries, cleaned."""

    title: str
    subtitle: str
    notes: str
    bullets: list[str]
    columns: list[SlideColumn]
    table: TableSheet | None
    summary: TableSheet | None = None
    chart: TableSheet | None = None
    figures: list[KeyFigure] = field(default_factory=list)
    quote: str = ""
    author: str = ""
    illustration: Illustration | None = None

    @property
    def has_content(self) -> bool:
        """Whether anything but a title survived the cleaning."""
        return bool(
            self.bullets or self.columns or self.table or self.chart or self.figures or self.quote
        )


def _data_of(slide: Slide, language: str) -> tuple[TableSheet | None, ...]:
    """A slide's table, its summary and its chart — a chart slide draws its data
    as a table only when the chart cannot be drawn."""
    if slide.kind == "chart":
        chart = _chart_table(slide.table, language)
        if chart is not None:
            return None, None, chart
    table, summary = _shown_table(slide.table, language)
    chart = (
        _chart_table(slide.table, language)
        if slide.kind != "chart" and slide.table is not None and slide.table.chart is not None
        else None
    )
    return table, summary, chart


def _payload_of(slide: Slide, language: str) -> _Payload:
    """The slide's content, whitespace collapsed and empties dropped."""
    table, summary, chart = _data_of(slide, language)
    # A quote's subtitle says who spoke: it is no lead line for anything else.
    quoting = slide.kind == "quote"
    return _Payload(
        title=_clean(slide.title),
        subtitle="" if quoting else _clean(slide.subtitle),
        notes=_clean(slide.notes),
        bullets=[_clean(bullet) for bullet in slide.bullets if bullet.strip()],
        columns=_clean_columns(slide.columns),
        table=table,
        summary=summary,
        chart=chart,
        figures=_clean_figures(slide.figures),
        quote=_clean(slide.quote),
        author=_clean(slide.subtitle) if quoting else "",
        illustration=_canonical_illustration(slide.illustration),
    )


def _fold_columns(payload: _Payload, language: str) -> None:
    """Reduce compared sides a slide cannot hold: 1 becomes bullets, 3+ a table."""
    if len(payload.columns) > MAX_COMPARISON_COLUMNS:
        payload.table = payload.table or _columns_to_table(payload.columns, language)
        payload.columns = []
    elif len(payload.columns) == 1:
        payload.bullets = payload.bullets + payload.columns[0].bullets
        payload.columns = []


def _assemble(payload: _Payload) -> list[Slide]:
    """One slide per thing the payload carries; always at least one."""
    slides: list[Slide] = []
    if payload.figures:
        slides.append(
            Slide(
                title=payload.title,
                kind="figures",
                subtitle=payload.subtitle,
                figures=payload.figures,
            )
        )
    if payload.quote:
        slides.append(
            Slide(title=payload.title, kind="quote", subtitle=payload.author, quote=payload.quote)
        )
    if payload.bullets:
        slides.append(
            Slide(
                title=payload.title,
                kind="content",
                subtitle=payload.subtitle,
                bullets=payload.bullets,
            )
        )
    if len(payload.columns) == MAX_COMPARISON_COLUMNS:
        slides.append(
            Slide(
                title=payload.title,
                kind="comparison",
                subtitle=payload.subtitle,
                columns=payload.columns,
            )
        )
    if payload.table is not None:
        slides.append(
            Slide(title=payload.title, kind="table", subtitle=payload.subtitle, table=payload.table)
        )
    if payload.summary is not None:
        slides.append(Slide(title=payload.summary.name, kind="table", table=payload.summary))
    if payload.chart is not None:
        slides.append(
            Slide(title=payload.title, kind="chart", subtitle=payload.subtitle, table=payload.chart)
        )
    if not slides:
        slides.append(Slide(title=payload.title, kind="content", subtitle=payload.subtitle))
    slides[0].notes = payload.notes
    # A picture stands beside words: the first content slide carries it, and a
    # slide of data, figures or a quote has no room for one.
    beside = next((slide for slide in slides if slide.kind == "content"), None)
    if beside is not None:
        beside.illustration = payload.illustration
    return slides


def _effective_slides(slide: Slide, language: str) -> list[Slide]:
    """One authored slide as the slides a renderer can actually draw."""
    payload = _payload_of(slide, language)
    if slide.kind == "section":
        # A section opener says one thing; whatever else it carried follows it
        # on its own slide rather than crowding the divider.
        divider = Slide(
            title=payload.title,
            kind="section",
            subtitle=payload.subtitle,
            notes=payload.notes,
            icon=_icon(slide.icon),
            illustration=payload.illustration,
        )
        if not payload.has_content:
            return [divider]
        payload.notes = ""
        payload.illustration = None
        _fold_columns(payload, language)
        return [divider, *_assemble(payload)]
    _fold_columns(payload, language)
    return _assemble(payload)


def normalize_slides(
    content: SlideContent, language: str, *, max_illustrations: int = 0
) -> SlideContent:
    """Effective kinds, cleaned text, payloads a renderer can trust.

    Args:
        content: What the model produced.
        language: Reader's language, for any generated table header.
        max_illustrations: The pictures the deck may carry (``illustration_budget``);
            0 strips every picture and the style that goes with them.

    Returns:
        A deck whose every slide carries exactly what its kind implies.
    """
    budget = _Budget(max_illustrations)
    cover = budget.admit(_canonical_illustration(content.illustration))
    slides = [
        (
            slide
            if slide.illustration is None
            else slide.model_copy(update={"illustration": budget.admit(slide.illustration)})
        )
        for authored in content.slides
        for slide in _effective_slides(authored, language)
    ]
    pictured = cover is not None or any(slide.illustration for slide in slides)
    return SlideContent(
        filename_stem=content.filename_stem,
        title=_clean(content.title),
        subtitle=_clean(content.subtitle),
        tone=_tone(content.tone),
        delivery=_delivery(content.delivery),
        illustration=cover,
        image_style=_clean(content.image_style) if pictured else "",
        slides=slides,
    )


def _canonical_inputs(inputs: list[SheetInput]) -> list[SheetInput]:
    """Named, unique, and with a value a formula can read — the others go.

    An input is a number or a date, as a key figure is: a formula reads it as
    one, so a kind that would write its cell as a TEXT (``text``, ``code``) reads
    « inferred » — Excel compares a text as larger than any number and skips it
    in ``MIN`` and ``MAX``, where the cached values read the number. A percentage
    is written with its sign, or as a fraction: « 20 » declared ``percent`` keeps
    its value and loses the declaration (``columns.reads_as_percent``).
    """
    kept: list[SheetInput] = []
    seen: set[str] = set()
    for item in inputs:
        name = _clean(item.name)[:NAME_MAX_CHARS]
        kind = item.kind.strip().casefold()
        kind = kind if kind in FIGURE_KINDS else ""
        value = _clean(item.value)
        written = infer_column_types(["value"], [[value]])[0]
        if kind == "percent" and not reads_as_percent(written, [value]):
            kind = ""
        candidate = SheetInput(
            name=name,
            value=value,
            kind=kind,
            unit=_clean(item.unit)[:UNIT_MAX_CHARS] if kind in UNIT_KINDS else "",
            note=_clean(item.note),
        )
        key = column_key(name)
        if not key or key in seen or input_value(candidate) is None:
            continue
        seen.add(key)
        kept.append(candidate)
    return kept


def normalize_tabular(content: TabularContent, language: str) -> TabularContent:
    """Rectangular sheets with legal headers and settled declarations; inputs a formula reads;
    key figures each one computable (``workbook_figures``).

    A workbook keeps its formulas symbolic — the renderer writes them live — and
    always has one sheet.
    """
    inputs = _canonical_inputs(content.inputs)
    names = [item.name for item in inputs]
    sheets = [
        sheet
        for raw in content.sheets
        if (sheet := normalize_table(raw, language, inputs=names)) is not None
    ]
    if not sheets:
        # Sanitized like every other sheet: a workbook with no title would
        # otherwise carry the one column nobody named.
        sheets = [
            TableSheet(
                name=_clean(content.title),
                headers=sanitize_headers([_clean(content.title)], language),
                rows=[],
            )
        ]
    return TabularContent(
        filename_stem=content.filename_stem,
        title=_clean(content.title),
        tone=_tone(content.tone),
        sheets=sheets,
        inputs=inputs,
        figures=normalize_figures(content.figures, inputs, sheets),
    )


def _as[Family: (SectionedContent, SlideContent, TabularContent)](
    content: DocumentContent, family: type[Family]
) -> Family:
    """The content as the family the dispatch chose it for (``type(content)``)."""
    if not isinstance(content, family):
        raise TypeError(f"{family.__name__} expected, got {type(content).__name__}")
    return content


def _sectioned(content: DocumentContent, context: RenderContext) -> DocumentContent:
    return normalize_sectioned(_as(content, SectionedContent), context)


def _slides(content: DocumentContent, context: RenderContext) -> DocumentContent:
    return normalize_slides(
        _as(content, SlideContent),
        context.language,
        max_illustrations=illustration_budget(context.preferences),
    )


def _tabular(content: DocumentContent, context: RenderContext) -> DocumentContent:
    return normalize_tabular(_as(content, TabularContent), context.language)


_NORMALIZERS: dict[type, Callable[[DocumentContent, RenderContext], DocumentContent]] = {
    SectionedContent: _sectioned,
    SlideContent: _slides,
    TabularContent: _tabular,
}

# Boot-time completeness (ADR-085): a family the dispatch cannot canonicalise
# would reach a renderer raw, so the module refuses to import instead.
assert set(_NORMALIZERS) == set(
    SCHEMA_BY_DOC_TYPE.values()
), "_NORMALIZERS must cover every content family"


def normalize_content(content: DocumentContent, context: RenderContext) -> DocumentContent:
    """The canonical form of any content family.

    Args:
        content: Any of the three content families.
        context: Reader and deployment facts.

    Returns:
        The same family, in canonical form.
    """
    return _NORMALIZERS[type(content)](content, context)
