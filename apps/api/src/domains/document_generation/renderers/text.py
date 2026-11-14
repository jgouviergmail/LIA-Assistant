"""Text family: csv (BOM + neutralization), md, txt (ADR-226, ADR-274).

csv is unchanged from ADR-226 — Excel needs the BOM and the OWASP
neutralization is not negotiable. md and txt gain the vocabulary: an ordered
sequence is numbered, a quote is quoted, a callout is set apart, a table is
named, a chart becomes the table of the values it draws, key figures are listed
value first, and the sources the text cites close the document. A picture is
the one thing neither can hold: the service asks none of their writer, and a
picture that reaches them anyway writes nothing. Markdown keeps the model's
inline markup; plain text strips it, because a ``**`` in a .txt is noise, not
emphasis.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Callable

from src.domains.document_generation.charts import chart_data, chart_table
from src.domains.document_generation.computation import (
    compute_table,
    input_values,
    machine_text,
    numeric_columns,
    totals_row_index,
)
from src.domains.document_generation.context import RenderContext
from src.domains.document_generation.fit import display_columns
from src.domains.document_generation.inline import strip_inline
from src.domains.document_generation.normalize import HeadingNumberer, document_is_numbered
from src.domains.document_generation.sanitize import neutralize_formula
from src.domains.document_generation.schemas import (
    BLOCK_KINDS,
    DocumentContent,
    SectionBlock,
    SectionedContent,
    Source,
    TableSheet,
    TabularContent,
)

#: Width of the rules a callout is framed with in plain text.
_TXT_RULE_WIDTH = 40
#: Markdown has six heading levels.
_MD_DEEPEST_HEADING = 6


def render_csv(content: DocumentContent, context: RenderContext) -> bytes:  # noqa: ARG001
    """One sheet as a CSV file, Excel-readable and formula-safe.

    CSV is data for another program: a computed column carries its VALUES in
    machine form (``computation.machine_text``), never a formula, and there is
    no totals row a reader would sum a second time.
    """
    if not isinstance(content, TabularContent):
        raise ValueError("csv rendering requires TabularContent")
    sheet = content.sheets[0]
    table = compute_table(sheet, input_values(content.inputs))
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([neutralize_formula(header) for header in sheet.headers])
    for index, row in enumerate(sheet.rows):
        writer.writerow(
            [
                (
                    machine_text(column, table.cells[index][position])
                    if column.computed
                    else neutralize_formula(cell)
                )
                for position, (column, cell) in enumerate(zip(table.columns, row, strict=True))
            ]
        )
    # utf-8-sig: Excel needs the BOM to detect UTF-8 (probe 2026-08-17).
    return buf.getvalue().encode("utf-8-sig")


class _Doc:
    """Per-document state the block renderers share: numbering, table and figure counts."""

    def __init__(self, content: SectionedContent, context: RenderContext) -> None:
        self.context = context
        self.numbered = document_is_numbered(content, context)
        self.numberer = HeadingNumberer()
        self.tables = 0
        self.figures = 0

    def heading(self, block: SectionBlock) -> str:
        """The heading text, numbered when the document is."""
        number = self.numberer.number(block.level) if self.numbered else ""
        return f"{number} {block.text}".strip()

    def table_label(self, block: SectionBlock) -> str:
        """« Table 3 — Key figures », in the reader's language."""
        self.tables += 1
        label = self.context.label("documents.table_label", n=self.tables)
        return f"{label} — {block.caption}" if block.caption else label

    def figure_label(self, block: SectionBlock) -> str:
        """« Figure 2 — Revenue by region », in the reader's language."""
        self.figures += 1
        label = self.context.label("documents.figure_label", n=self.figures)
        return f"{label} — {block.caption}" if block.caption else label

    def figure_line(self, value: str, label: str) -> str:
        """« 42% — of the market », in the reader's word order; the value alone without a label."""
        if not label:
            return value
        return self.context.label("documents.figure_bullet", value=value, label=label)

    def figure_data(self, block: SectionBlock) -> TableSheet | None:
        """A chart's values as a table: a text cannot draw, it can say every value."""
        if block.table is None:
            return None
        data = chart_data(compute_table(block.table), self.context.language)
        return chart_table(data, self.context.language) if data is not None else None


def _md_cell(value: str) -> str:
    """One cell, with the two characters markdown reads as structure disarmed.

    A pipe splits the row and every later cell lands under the wrong header;
    a newline ends the row halfway through the data.
    """
    escaped = value.replace("|", "\\|")
    return escaped.replace("\n", " ").replace("\r", " ")


def _md_table(table: TableSheet, language: str) -> list[str]:
    """A pipe table: numbers aligned right, the totals row in bold."""
    header = "| " + " | ".join(_md_cell(name) for name in table.headers) + " |"
    rule = (
        "| " + " | ".join("---:" if numeric else "---" for numeric in numeric_columns(table)) + " |"
    )
    totals = totals_row_index(table, language)
    body = (
        "| "
        + " | ".join(
            f"**{_md_cell(cell)}**" if index == totals and cell.strip() else _md_cell(cell)
            for cell in row
        )
        + " |"
        for index, row in enumerate(table.rows)
    )
    return [header, rule, *body]


def _md_heading(block: SectionBlock, doc: _Doc) -> list[str]:
    # The document title owns "#": every content heading moves one level down —
    # level 1 is "##", level 2 "###" — the same shift the PDF renderer applies.
    # (``max(level, 2)`` set levels 1 and 2 both at "##" until 2026-11-13.)
    return [f"{'#' * min(block.level + 1, _MD_DEEPEST_HEADING)} {doc.heading(block)}"]


def _md_table_block(block: SectionBlock, doc: _Doc) -> list[str]:
    if block.table is None:
        return []
    return [f"*{doc.table_label(block)}*", "", *_md_table(block.table, doc.context.language)]


def _md_chart_block(block: SectionBlock, doc: _Doc) -> list[str]:
    table = doc.figure_data(block)
    if table is None:
        return []
    return [f"*{doc.figure_label(block)}*", "", *_md_table(table, doc.context.language)]


def _md_figures(block: SectionBlock, doc: _Doc) -> list[str]:
    return [f"- {doc.figure_line(f'**{figure.value}**', figure.label)}" for figure in block.figures]


def _no_picture(_block: SectionBlock, _doc: _Doc) -> list[str]:
    """A text file cannot hold a picture: it writes nothing — no caption of a missing figure."""
    return []


_MD_BLOCKS: dict[str, Callable[[SectionBlock, _Doc], list[str]]] = {
    "heading": _md_heading,
    "paragraph": lambda block, _doc: [block.text],
    "bullets": lambda block, _doc: [f"- {item}" for item in block.items],
    "numbered": lambda block, _doc: [
        f"{index}. {item}" for index, item in enumerate(block.items, start=1)
    ],
    "quote": lambda block, _doc: [f"> {block.text}"],
    "callout": lambda block, doc: [
        f"> **{doc.context.label('documents.note_label')}** {block.text}"
    ],
    "table": _md_table_block,
    "chart": _md_chart_block,
    "figures": _md_figures,
    "illustration": _no_picture,
}

# Boot-time completeness (ADR-085): every block kind the schema allows is written.
assert set(_MD_BLOCKS) == BLOCK_KINDS, "_MD_BLOCKS must cover every block kind"


def _md_address(url: str) -> str:
    """An address inside angle brackets, which hold parentheses but never ``<`` or ``>``."""
    return url.replace("<", "%3C").replace(">", "%3E")


def _md_source(source: Source) -> str:
    """A source as a link to its address, or its title alone when it has none."""
    if not source.url:
        return source.title
    if source.title == source.url:
        return f"<{_md_address(source.url)}>"
    words = source.title.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")
    return f"[{words}](<{_md_address(source.url)}>)"


def _md_sources(content: SectionedContent, doc: _Doc) -> list[str]:
    """The sources the text cites as [n], numbered in that order."""
    if not content.sources:
        return []
    heading = doc.context.label("documents.sources_heading")
    entries = [
        f"{number}. {_md_source(source)}" for number, source in enumerate(content.sources, start=1)
    ]
    return [f"## {heading}", "", *entries, ""]


def render_md(content: DocumentContent, context: RenderContext) -> bytes:
    """A markdown document: the title owns ``#``, the vocabulary keeps its shape."""
    if not isinstance(content, SectionedContent):
        raise ValueError("md rendering requires SectionedContent")
    doc = _Doc(content, context)
    lines: list[str] = [f"# {content.title}", ""]
    if content.subtitle:
        lines += [f"*{content.subtitle}*", ""]
    if context.date_line:
        lines += [context.date_line, ""]
    for block in content.blocks:
        # A block that writes nothing leaves no blank line behind.
        if written := _MD_BLOCKS[block.kind](block, doc):
            lines += [*written, ""]
    lines += _md_sources(content, doc)
    return "\n".join(lines).encode("utf-8")


def _rule(text: str, character: str) -> str:
    """A rule as wide as what it underlines — in COLUMNS, not code points."""
    return character * int(display_columns(text))


def _txt_heading(block: SectionBlock, doc: _Doc) -> list[str]:
    heading = doc.heading(block)
    return [heading, _rule(heading, "-")]


def _txt_table(block: SectionBlock, doc: _Doc) -> list[str]:
    if block.table is None:
        return []
    return [
        doc.table_label(block),
        " / ".join(block.table.headers),
        *(" / ".join(row) for row in block.table.rows),
    ]


def _txt_chart(block: SectionBlock, doc: _Doc) -> list[str]:
    table = doc.figure_data(block)
    if table is None:
        return []
    return [
        doc.figure_label(block),
        " / ".join(table.headers),
        *(" / ".join(row) for row in table.rows),
    ]


_TXT_BLOCKS: dict[str, Callable[[SectionBlock, _Doc], list[str]]] = {
    "heading": _txt_heading,
    "paragraph": lambda block, _doc: [strip_inline(block.text)],
    "bullets": lambda block, _doc: [f"  * {strip_inline(item)}" for item in block.items],
    "numbered": lambda block, _doc: [
        f"  {index}) {strip_inline(item)}" for index, item in enumerate(block.items, start=1)
    ],
    "quote": lambda block, _doc: [f"    {strip_inline(block.text)}"],
    "callout": lambda block, _doc: [
        "-" * _TXT_RULE_WIDTH,
        strip_inline(block.text),
        "-" * _TXT_RULE_WIDTH,
    ],
    "table": _txt_table,
    "chart": _txt_chart,
    "figures": lambda block, doc: [
        f"  * {doc.figure_line(figure.value, figure.label)}" for figure in block.figures
    ],
    "illustration": _no_picture,
}

# Boot-time completeness (ADR-085): every block kind the schema allows is written.
assert set(_TXT_BLOCKS) == BLOCK_KINDS, "_TXT_BLOCKS must cover every block kind"


def render_txt(content: DocumentContent, context: RenderContext) -> bytes:
    """A plain-text document: complete, and free of markup a reader cannot use."""
    if not isinstance(content, SectionedContent):
        raise ValueError("txt rendering requires SectionedContent")
    doc = _Doc(content, context)
    lines: list[str] = [content.title, _rule(content.title, "=")]
    if content.subtitle:
        lines.append(content.subtitle)
    if context.date_line:
        lines.append(context.date_line)
    lines.append("")
    for block in content.blocks:
        if written := _TXT_BLOCKS[block.kind](block, doc):
            lines += [*written, ""]
    lines += _txt_sources(content, doc)
    return "\n".join(lines).encode("utf-8")


def _txt_sources(content: SectionedContent, doc: _Doc) -> list[str]:
    """The sources the text cites as [n]: « [1] Title — address », the address spelled out."""
    if not content.sources:
        return []
    heading = doc.context.label("documents.sources_heading")
    lines = [heading, _rule(heading, "-")]
    for number, source in enumerate(content.sources, start=1):
        entry = (
            doc.context.label("documents.source_entry", title=source.title, url=source.url)
            if source.url and source.title != source.url
            else source.title
        )
        lines.append(f"[{number}] {entry}")
    return [*lines, ""]
