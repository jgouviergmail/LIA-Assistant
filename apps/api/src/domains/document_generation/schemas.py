"""Structured content models produced by the document_generation LLM (ADR-226).

One schema family per output shape — the service selects the schema by
``doc_type`` BEFORE the LLM call, so each call is a plain (strict-compatible)
Pydantic schema rather than a discriminated union:

- Tabular (csv, xlsx): sheets of headers + string rows.
- Sectioned (docx, pdf, md, txt): an ordered tree of heading / paragraph /
  bullets / table blocks.
- Slides (pptx): title + bullet slides with optional speaker notes.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

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
    headers: list[str] = Field(description="Column headers, in order.")
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

    kind: Literal["heading", "paragraph", "bullets", "table"] = Field(description="Block type.")
    level: int = Field(default=2, ge=1, le=4, description="Heading level (headings only).")
    text: str = Field(default="", description="Text for heading/paragraph blocks.")
    items: list[str] = Field(default_factory=list, description="Bullet items (bullets only).")
    table: TableSheet | None = Field(default=None, description="Table payload (table only).")


class SectionedContent(BaseModel):
    """Content for docx/pdf/md/txt outputs."""

    filename_stem: str = Field(description="Suggested filename without extension.")
    title: str = Field(description="Document title (rendered as the top heading).")
    blocks: list[SectionBlock] = Field(min_length=1, description="Ordered content blocks.")


class Slide(BaseModel):
    """A single presentation slide."""

    title: str = Field(description="Slide title.")
    bullets: list[str] = Field(default_factory=list, description="Bullet points.")
    notes: str = Field(default="", description="Optional speaker notes.")


class SlideContent(BaseModel):
    """Content for pptx output."""

    filename_stem: str = Field(description="Suggested filename without extension.")
    title: str = Field(description="Presentation title (first slide).")
    slides: list[Slide] = Field(min_length=1, description="Ordered slides.")


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
