"""Structured content models produced by the document_generation LLM (ADR-226, ADR-274).

One schema family per output shape — the service selects the schema by
``doc_type`` BEFORE the LLM call, so each call is a plain (strict-compatible)
Pydantic schema rather than a discriminated union:

- Tabular (csv, xlsx): sheets of headers + string rows.
- Sectioned (docx, pdf, md, txt): an ordered tree of blocks.
- Slides (pptx): title + typed slides with optional speaker notes.

The vocabulary is SEMANTIC, never a layout: the model says what a thing IS —
an ordered sequence, a quote, a warning, a section opener, a comparison, data
— and the renderer decides how it is drawn (ADR-274). Nothing here carries a
bound: a bound REFUSES the whole document for a detail (ADR-269), so every
incoherence is repaired instead, in ``normalize.py``. The one deliberate
refusal is ``min_length=1`` on the three content lists: a document with
nothing has nothing to render.

Class docstrings reach the model as the schema's ``description``: one line
each, with the reasoning in comments like this one.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal, get_args

from pydantic import BaseModel, Field


class DocumentType(str, Enum):
    """Supported output formats for generate_document."""

    CSV = "csv"
    XLSX = "xlsx"
    DOCX = "docx"
    PPTX = "pptx"
    PDF = "pdf"
    MD = "md"
    TXT = "txt"


class TableSheet(BaseModel):
    """A single table: one CSV file, one XLSX worksheet, or an embedded table."""

    name: str = Field(description="Sheet/table name (short, human readable).")
    headers: list[str] = Field(description="Column headers, in order, unique and non-empty.")
    rows: list[list[str]] = Field(
        description="Data rows; every cell as a string, aligned with headers."
    )


class TabularContent(BaseModel):
    """Content for csv/xlsx outputs."""

    filename_stem: str = Field(description="Suggested filename without extension.")
    title: str = Field(description="Document title (used as metadata).")
    sheets: list[TableSheet] = Field(
        min_length=1,
        description="Worksheets; csv output uses ONLY the first sheet.",
    )


class SectionBlock(BaseModel):
    """One block of a sectioned document, rendered in order."""

    kind: Literal["heading", "paragraph", "bullets", "numbered", "quote", "callout", "table"] = (
        Field(
            description=(
                "What the block is: a heading, running text, an unordered list, an "
                "ordered sequence of steps, a verbatim quote, a callout (a warning "
                "or the one thing to remember), or a table."
            )
        )
    )
    # No bound: an out-of-range level is clamped at normalization. A bound here
    # would fail the whole document — three paid times — over one heading.
    level: int = Field(default=2, description="Heading level 1-4 (headings only).")
    text: str = Field(
        default="", description="Text for heading, paragraph, quote and callout blocks."
    )
    items: list[str] = Field(default_factory=list, description="Items (bullets and numbered only).")
    table: TableSheet | None = Field(default=None, description="Table payload (table only).")
    caption: str = Field(default="", description="Caption naming a table (table only).")


class SectionedContent(BaseModel):
    """Content for docx/pdf/md/txt outputs."""

    filename_stem: str = Field(description="Suggested filename without extension.")
    title: str = Field(description="Document title (rendered as the top heading).")
    subtitle: str = Field(default="", description="One line under the title: audience or purpose.")
    blocks: list[SectionBlock] = Field(min_length=1, description="Ordered content blocks.")


class SlideColumn(BaseModel):
    """One side of a comparison slide."""

    heading: str = Field(description="Short heading of this side.")
    bullets: list[str] = Field(default_factory=list, description="Bullet points of this side.")


class Slide(BaseModel):
    """A single presentation slide."""

    title: str = Field(description="Slide title: an assertion or a precise topic.")
    kind: Literal["content", "section", "comparison", "table"] = Field(
        default="content",
        description=(
            "What the slide is: content (an idea supported by bullets), a section "
            "opener, a comparison of two sides, or data (a table)."
        ),
    )
    subtitle: str = Field(
        default="",
        description="Tagline of a section opener, or lead line of a content slide.",
    )
    bullets: list[str] = Field(default_factory=list, description="Bullet points (content).")
    columns: list[SlideColumn] = Field(
        default_factory=list, description="The two sides (comparison)."
    )
    table: TableSheet | None = Field(default=None, description="Data (table).")
    notes: str = Field(default="", description="Speaker notes: the full sentences.")


class SlideContent(BaseModel):
    """Content for pptx output."""

    filename_stem: str = Field(description="Suggested filename without extension.")
    title: str = Field(description="Presentation title (cover slide).")
    subtitle: str = Field(default="", description="Cover subtitle: audience, occasion or date.")
    slides: list[Slide] = Field(min_length=1, description="Ordered slides.")


#: The block vocabulary, read from the schema itself: a renderer registry that
#: does not cover it is refused at import (ADR-085), and a hand-typed copy here
#: would be the drift that guard exists to prevent.
BLOCK_KINDS: frozenset[str] = frozenset(get_args(SectionBlock.model_fields["kind"].annotation))
#: The slide vocabulary, same rule.
SLIDE_KINDS: frozenset[str] = frozenset(get_args(Slide.model_fields["kind"].annotation))

DocumentContent = TabularContent | SectionedContent | SlideContent

SCHEMA_BY_DOC_TYPE: dict[
    DocumentType, type[TabularContent] | type[SectionedContent] | type[SlideContent]
] = {
    DocumentType.CSV: TabularContent,
    DocumentType.XLSX: TabularContent,
    DocumentType.DOCX: SectionedContent,
    DocumentType.PDF: SectionedContent,
    DocumentType.MD: SectionedContent,
    DocumentType.TXT: SectionedContent,
    DocumentType.PPTX: SlideContent,
}

# Boot-time completeness (ADR-085): refuse to import with a partial map.
assert set(SCHEMA_BY_DOC_TYPE) == set(
    DocumentType
), "SCHEMA_BY_DOC_TYPE must cover every DocumentType"
