"""The canonical form of what the model produced (ADR-274).

Every incoherence a writer can plausibly produce is REPAIRED here,
mechanically, and never reported as a defect (ADR-184): a heading level outside
1..4 is clamped, an empty block is dropped, markdown that leaked into a
paragraph becomes the block it is, a heading the model numbered itself loses
its prefix when the renderer numbers, a slide's effective kind follows the
payload it actually carries.

Renderers consume the output of this module and never the raw content, so no
renderer has to ask whether a table has rows or a comparison has two sides.
The transformation is idempotent: normalizing twice changes nothing.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from itertools import zip_longest

from src.core.config import settings
from src.domains.document_generation.context import RenderContext
from src.domains.document_generation.sanitize import strip_control_characters
from src.domains.document_generation.schemas import (
    SCHEMA_BY_DOC_TYPE,
    DocumentContent,
    SectionBlock,
    SectionedContent,
    Slide,
    SlideColumn,
    SlideContent,
    TableSheet,
    TabularContent,
)
from src.domains.document_generation.tables import normalize_sheet, sanitize_headers

#: Word and the PDF renderer number three levels; deeper headings are plain.
MAX_HEADING_LEVEL = 4
NUMBERED_LEVELS = 3

_HEADING_NUMBER = re.compile(r"^\s*\d+(?:\.\d+)*[.)]?\s+")
_MD_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_MD_BULLET = re.compile(r"^\s*[-*•]\s+(.+?)\s*$")
_MD_NUMBERED = re.compile(r"^\s*\d+[.)]\s+(.+?)\s*$")
#: A comparison of three or more sides is a table, not a slide of columns.
MAX_COMPARISON_COLUMNS = 2


def _clean(text: str) -> str:
    """Collapse whitespace and drop what a document writer refuses.

    The ONE funnel every piece of prose passes through, so no renderer has to
    know that XML forbids a form feed.
    """
    return strip_control_characters(" ".join(text.split()))


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


def _canonical_block(block: SectionBlock, language: str) -> SectionBlock | None:
    """One block in canonical form, or ``None`` when there is nothing to render."""
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
    if block.kind == "table":
        sheet = normalize_sheet(block.table, language) if block.table is not None else None
        if sheet is None:
            return None
        return SectionBlock(kind="table", table=sheet, caption=_clean(block.caption))
    text = _clean(block.text)
    if not text:
        return None
    if block.kind == "heading":
        return SectionBlock(
            kind="heading", level=min(max(block.level, 1), MAX_HEADING_LEVEL), text=text
        )
    return SectionBlock(kind=block.kind, text=text)


def normalize_sectioned(content: SectionedContent, context: RenderContext) -> SectionedContent:
    """Canonical blocks; heading prefixes stripped when the renderer numbers.

    Args:
        content: What the model produced.
        context: Reader and deployment facts (its ``structure`` decides the
            apparatus, hence whether model-written numbers are stripped).

    Returns:
        A document whose blocks a renderer can draw without asking questions.
    """
    blocks = [
        canonical
        for block in content.blocks
        if (canonical := _canonical_block(block, context.language)) is not None
    ]
    title = _clean(content.title)
    canonical_content = SectionedContent(
        filename_stem=content.filename_stem,
        title=title,
        subtitle=_clean(content.subtitle),
        # A document of nothing still has its title to show.
        blocks=blocks or [SectionBlock(kind="paragraph", text=title)],
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
    return normalize_sheet(TableSheet(name="comparison", headers=headers, rows=rows), language)


def _clean_columns(columns: list[SlideColumn]) -> list[SlideColumn]:
    return [
        SlideColumn(
            heading=_clean(column.heading),
            bullets=[_clean(bullet) for bullet in column.bullets if bullet.strip()],
        )
        for column in columns
        if column.heading.strip() or any(bullet.strip() for bullet in column.bullets)
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

    @property
    def has_content(self) -> bool:
        """Whether anything but a title survived the cleaning."""
        return bool(self.bullets or self.columns or self.table)


def _payload_of(slide: Slide, language: str) -> _Payload:
    """The slide's content, whitespace collapsed and empties dropped."""
    return _Payload(
        title=_clean(slide.title),
        subtitle=_clean(slide.subtitle),
        notes=_clean(slide.notes),
        bullets=[_clean(bullet) for bullet in slide.bullets if bullet.strip()],
        columns=_clean_columns(slide.columns),
        table=normalize_sheet(slide.table, language) if slide.table is not None else None,
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
    if not slides:
        slides.append(Slide(title=payload.title, kind="content", subtitle=payload.subtitle))
    slides[0].notes = payload.notes
    return slides


def _effective_slides(slide: Slide, language: str) -> list[Slide]:
    """One authored slide as the slides a renderer can actually draw."""
    payload = _payload_of(slide, language)
    if slide.kind == "section":
        # A section opener says one thing; whatever else it carried follows it
        # on its own slide rather than crowding the divider.
        divider = Slide(
            title=payload.title, kind="section", subtitle=payload.subtitle, notes=payload.notes
        )
        if not payload.has_content:
            return [divider]
        payload.notes = ""
        _fold_columns(payload, language)
        return [divider, *_assemble(payload)]
    _fold_columns(payload, language)
    return _assemble(payload)


def normalize_slides(content: SlideContent, language: str) -> SlideContent:
    """Effective kinds, cleaned text, payloads a renderer can trust.

    Args:
        content: What the model produced.
        language: Reader's language, for any generated table header.

    Returns:
        A deck whose every slide carries exactly what its kind implies.
    """
    slides = [
        effective for slide in content.slides for effective in _effective_slides(slide, language)
    ]
    return SlideContent(
        filename_stem=content.filename_stem,
        title=_clean(content.title),
        subtitle=_clean(content.subtitle),
        slides=slides,
    )


def normalize_tabular(content: TabularContent, language: str) -> TabularContent:
    """Rectangular sheets with legal headers; a workbook always has one sheet."""
    sheets = [
        sheet for raw in content.sheets if (sheet := normalize_sheet(raw, language)) is not None
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
        filename_stem=content.filename_stem, title=_clean(content.title), sheets=sheets
    )


_NORMALIZERS: dict[type, Callable[[DocumentContent, RenderContext], DocumentContent]] = {
    SectionedContent: lambda content, context: normalize_sectioned(content, context),  # type: ignore[arg-type]
    SlideContent: lambda content, context: normalize_slides(content, context.language),  # type: ignore[arg-type]
    TabularContent: lambda content, context: normalize_tabular(content, context.language),  # type: ignore[arg-type]
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
