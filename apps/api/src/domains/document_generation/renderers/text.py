"""Text family: csv (BOM + neutralization), md, txt (ADR-226, ADR-274).

csv is unchanged from ADR-226 — Excel needs the BOM and the OWASP
neutralization is not negotiable. md and txt gain the vocabulary: an ordered
sequence is numbered, a quote is quoted, a callout is set apart, a table is
named. Markdown keeps the model's inline markup; plain text strips it, because
a ``**`` in a .txt is noise, not emphasis.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Callable

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
    TableSheet,
    TabularContent,
)

#: Width of the rules a callout is framed with in plain text.
_TXT_RULE_WIDTH = 40


def render_csv(content: DocumentContent, context: RenderContext) -> bytes:  # noqa: ARG001
    """One sheet as a CSV file, Excel-readable and formula-safe."""
    if not isinstance(content, TabularContent):
        raise ValueError("csv rendering requires TabularContent")
    sheet = content.sheets[0]
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([neutralize_formula(header) for header in sheet.headers])
    for row in sheet.rows:
        writer.writerow([neutralize_formula(cell) for cell in row])
    # utf-8-sig: Excel needs the BOM to detect UTF-8 (probe 2026-08-17).
    return buf.getvalue().encode("utf-8-sig")


class _Doc:
    """Per-document state the block renderers share: numbering and table count."""

    def __init__(self, content: SectionedContent, context: RenderContext) -> None:
        self.context = context
        self.numbered = document_is_numbered(content, context)
        self.numberer = HeadingNumberer()
        self.tables = 0

    def heading(self, block: SectionBlock) -> str:
        """The heading text, numbered when the document is."""
        number = self.numberer.number(block.level) if self.numbered else ""
        return f"{number} {block.text}".strip()

    def table_label(self, block: SectionBlock) -> str:
        """« Table 3 — Key figures », in the reader's language."""
        self.tables += 1
        label = self.context.label("documents.table_label", n=self.tables)
        return f"{label} — {block.caption}" if block.caption else label


def _md_cell(value: str) -> str:
    """One cell, with the two characters markdown reads as structure disarmed.

    A pipe splits the row and every later cell lands under the wrong header;
    a newline ends the row halfway through the data.
    """
    escaped = value.replace("|", "\\|")
    return escaped.replace("\n", " ").replace("\r", " ")


def _md_table(table: TableSheet) -> list[str]:
    header = "| " + " | ".join(_md_cell(name) for name in table.headers) + " |"
    rule = "| " + " | ".join("---" for _ in table.headers) + " |"
    body = ("| " + " | ".join(_md_cell(cell) for cell in row) + " |" for row in table.rows)
    return [header, rule, *body]


def _md_heading(block: SectionBlock, doc: _Doc) -> list[str]:
    # The document title owns "#": content headings start at "##" even when the
    # model says level 1 — the same shift the PDF renderer applies.
    return [f"{'#' * max(block.level, 2)} {doc.heading(block)}"]


def _md_table_block(block: SectionBlock, doc: _Doc) -> list[str]:
    if block.table is None:
        return []
    return [f"*{doc.table_label(block)}*", "", *_md_table(block.table)]


_MD_BLOCKS: dict[str, Callable[[SectionBlock, _Doc], list[str]]] = {
    "heading": _md_heading,
    "paragraph": lambda block, _doc: [block.text],
    "bullets": lambda block, _doc: [f"- {item}" for item in block.items],
    "numbered": lambda block, _doc: [
        f"{index}. {item}" for index, item in enumerate(block.items, start=1)
    ],
    "quote": lambda block, _doc: [f"> {block.text}"],
    "callout": lambda block, _doc: [f"> **Note.** {block.text}"],
    "table": _md_table_block,
}

# Boot-time completeness (ADR-085): every block kind the schema allows is written.
assert set(_MD_BLOCKS) == BLOCK_KINDS, "_MD_BLOCKS must cover every block kind"


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
        lines += [*_MD_BLOCKS[block.kind](block, doc), ""]
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
        lines += [*_TXT_BLOCKS[block.kind](block, doc), ""]
    return "\n".join(lines).encode("utf-8")
