"""Structured content models produced by the document_generation LLM (ADR-226, ADR-274).

One schema family per output shape — the service selects the schema by
``doc_type`` BEFORE the LLM call, so each call is a plain (strict-compatible)
Pydantic schema rather than a discriminated union:

- Tabular (csv, xlsx): sheets of headers + string rows.
- Sectioned (docx, pdf, md, txt): an ordered tree of blocks, a cover picture
  and the sources the text cites.
- Slides (pptx): title + typed slides with optional speaker notes, and how
  the deck will be used (presented or read).

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

from pydantic import BaseModel, Field, JsonValue
from pydantic.json_schema import JsonDict


class DocumentType(str, Enum):
    """Supported output formats for generate_document."""

    CSV = "csv"
    XLSX = "xlsx"
    DOCX = "docx"
    PPTX = "pptx"
    PDF = "pdf"
    MD = "md"
    TXT = "txt"


#: What a column's values are. Declared by the writer when the cells alone
#: cannot say it (a year and a postal code are integers too); repaired to
#: « inferred » when unknown, never refused (ADR-184).
COLUMN_KINDS: tuple[str, ...] = (
    "text",
    "amount",
    "quantity",
    "percent",
    "date",
    "datetime",
    "year",
    "code",
)
#: What a workbook's key figure is: a number or a date, never a text (ADR-388).
FIGURE_KINDS: tuple[str, ...] = tuple(kind for kind in COLUMN_KINDS if kind not in ("text", "code"))
#: What a totals row computes for a column.
TOTAL_FUNCTIONS: tuple[str, ...] = ("sum", "average", "min", "max", "count")
#: Which way a measure is good (a spreadsheet then emphasizes it).
BETTER_DIRECTIONS: tuple[str, ...] = ("higher", "lower")
#: What a grouped summary computes per group.
SUMMARY_FUNCTIONS: tuple[str, ...] = ("sum", "average", "count")
#: What a chart shows. The writer says what it MEANS; the renderer picks the form
#: the data can bear (``charts.chart_form``).
CHART_INTENTS: tuple[str, ...] = ("compare", "trend", "share", "relation")
#: A document's look, in words (``typography.PALETTES`` says in colours); empty
#: keeps it grey.
DOCUMENT_TONES: tuple[str, ...] = ("sober", "institutional", "warm", "technical")
#: The forms a writer may name when the person asked for one; empty lets the
#: renderer choose.
CHART_FORMS: tuple[str, ...] = (
    "column",
    "bar",
    "line",
    "area",
    "scatter",
    "segmented",
    "pie",
    "doughnut",
)
#: How a deck will be used. A presented deck may move — the person's
#: ``DocumentAnimations`` decides — and a deck to read stays still; empty when
#: the request does not say, which reads as « read ».
DECK_DELIVERIES: tuple[str, ...] = ("presented", "read")
#: The pictograms a slide may carry: Lucide names (ISC), drawn from the geometry
#: vendored in ``lucide_icons.json`` (``icons.py``, held equal by a test). A
#: CLOSED set on purpose — a name the renderer cannot draw is repaired to none —
#: and a small one: the list is published to the writer on every call.
SLIDE_ICONS: tuple[str, ...] = (
    "award",
    "banknote",
    "briefcase",
    "building",
    "calendar",
    "chart-column",
    "chart-pie",
    "circle-check",
    "clock",
    "cpu",
    "globe",
    "graduation-cap",
    "handshake",
    "heart-pulse",
    "leaf",
    "lightbulb",
    "map-pin",
    "message-circle",
    "rocket",
    "scale",
    "settings",
    "shield-check",
    "sparkles",
    "target",
    "trending-down",
    "trending-up",
    "triangle-alert",
    "users",
)


def _one_of(values: tuple[str, ...]) -> JsonDict:
    """The JSON-schema guidance of a closed vocabulary that is repaired, not refused.

    The schema PUBLISHES the values (the writer is guided, a grammar-constrained
    provider decodes within them) while validation accepts any string: an unknown
    value is repaired at normalization rather than failing the document — three
    paid times — over one word (ADR-269).
    """
    enum: list[JsonValue] = [*values]
    return {"enum": enum}


class ColumnSpec(BaseModel):
    """What one column of a table is, when its cells alone cannot say it."""

    header: str = Field(
        description="The column this describes: one of the table's headers, or a new "
        "computed column."
    )
    kind: str = Field(
        default="",
        description="What the values are; empty means inferred from the cells.",
        json_schema_extra=_one_of(COLUMN_KINDS),
    )
    unit: str = Field(
        default="",
        description="Currency code of an amount (EUR, USD…) or unit symbol of a quantity (kg, h…).",
    )
    formula: str = Field(
        default="",
        description="Computed column: an expression over {Column} names of this table "
        "(and {Input} names in a workbook). Leave its cells empty.",
    )
    total: str = Field(
        default="",
        description="What the table's totals row shows for this column.",
        json_schema_extra=_one_of(TOTAL_FUNCTIONS),
    )
    better: str = Field(
        default="",
        description="Spreadsheets: which direction is good for this measure.",
        json_schema_extra=_one_of(BETTER_DIRECTIONS),
    )
    choices: list[str] = Field(
        default_factory=list,
        description="Spreadsheets: the closed list of values this column admits (a drop-down).",
    )


class GroupSummary(BaseModel):
    """A summary of a table grouped by one of its columns."""

    by: str = Field(description="The column whose values group the rows.")
    measures: list[str] = Field(
        default_factory=list, description="The numeric columns computed per group."
    )
    function: str = Field(
        default="sum",
        description="What is computed per group.",
        json_schema_extra=_one_of(SUMMARY_FUNCTIONS),
    )
    title: str = Field(default="", description="Short title of the summary.")


class ChartSpec(BaseModel):
    """A chart drawn from a table's columns."""

    intent: str = Field(
        default="compare",
        description="What the chart shows: compare values, a trend over an ordered "
        "sequence, the shares of a whole, or a relation between two measures.",
        json_schema_extra=_one_of(CHART_INTENTS),
    )
    form: str = Field(
        default="",
        description="Only when the person named a chart type; empty lets the renderer "
        "choose from the data.",
        json_schema_extra=_one_of(CHART_FORMS),
    )
    category: str = Field(
        default="",
        description="The column naming each point (a label, a month); empty means the "
        "first column of words.",
    )
    values: list[str] = Field(
        default_factory=list,
        description="The numeric columns drawn, sharing one unit; empty means every one.",
    )
    title: str = Field(default="", description="Short title of the chart.")


class TableSheet(BaseModel):
    """A single table: one CSV file, one XLSX worksheet, or an embedded table."""

    name: str = Field(description="Sheet/table name (short, human readable).")
    headers: list[str] = Field(description="Column headers, in order, unique and non-empty.")
    rows: list[list[str]] = Field(
        description="Data rows; every cell as a string, aligned with headers."
    )
    columns: list[ColumnSpec] = Field(
        default_factory=list,
        description="What some columns are: kind, unit, a formula, a total.",
    )
    summary: GroupSummary | None = Field(
        default=None, description="A summary of this table grouped by one of its columns."
    )
    chart: ChartSpec | None = Field(default=None, description="A chart of this table's values.")


class SheetInput(BaseModel):
    """One assumption a workbook's formulas read by name."""

    name: str = Field(description="Name of the assumption, read as {Name} in formulas.")
    value: str = Field(
        description="Its value: a plain number, a percentage (12.5%) or an ISO date."
    )
    # A formula reads an input as a number or a date: the kinds a key figure has.
    kind: str = Field(
        default="",
        description="What the value is; empty means inferred.",
        json_schema_extra=_one_of(FIGURE_KINDS),
    )
    unit: str = Field(default="", description="Currency code or unit symbol.")
    note: str = Field(default="", description="Where the value comes from, or what it assumes.")


class WorkbookFigure(BaseModel):
    """A figure a workbook computes once, from its inputs and its sheets' whole columns."""

    label: str = Field(description="What the figure is; another figure reads it as {Label}.")
    formula: str = Field(
        description="How it is computed: inputs and other figures as {Name}, a sheet's whole "
        "column as SUM({Sheet/Column}) or AVERAGE({Sheet/Column}); never a row.",
    )
    kind: str = Field(
        default="",
        description="What the value is; empty means a plain number.",
        json_schema_extra=_one_of(FIGURE_KINDS),
    )
    unit: str = Field(default="", description="Currency code or unit symbol.")


class TabularContent(BaseModel):
    """Content for csv/xlsx outputs."""

    filename_stem: str = Field(description="Suggested filename without extension.")
    title: str = Field(description="Document title (used as metadata).")
    tone: str = Field(
        default="",
        description="The document's look: sober for most documents, institutional for "
        "official ones, warm for people and culture, technical for engineering and data; "
        "empty keeps it grey.",
        json_schema_extra=_one_of(DOCUMENT_TONES),
    )
    sheets: list[TableSheet] = Field(
        min_length=1,
        description="Worksheets; csv output uses ONLY the first sheet.",
    )
    inputs: list[SheetInput] = Field(
        default_factory=list,
        description="Assumptions the formulas read, gathered on the workbook's first sheet.",
    )
    figures: list[WorkbookFigure] = Field(
        default_factory=list,
        description="Key figures computed once for the whole workbook, on a sheet of their own.",
    )


class Illustration(BaseModel):
    """A picture the image model draws for this place in the document."""

    # The subject is in English whatever the document's language: it is a
    # prompt for an image model, never shown. The alt is what a reader who
    # cannot see the picture is told, in the document's language.
    subject: str = Field(
        description="What the picture shows, in English: the scene, never any text."
    )
    alt: str = Field(
        default="", description="What it shows, in the document's language, in one sentence."
    )


class KeyFigure(BaseModel):
    """One number that carries the message, with what it measures."""

    value: str = Field(description="The figure as it should read: 42%, +18%, $1.2M, 3 days.")
    label: str = Field(default="", description="What it measures, in a few words.")
    # A page sets its figures as type alone: a report's figure carries no
    # pictogram, and normalization clears one a writer gave it anyway.
    icon: str = Field(
        default="",
        description="Slides only: a pictogram named in the slide's `icon` list, or empty.",
    )


class SectionBlock(BaseModel):
    """One block of a sectioned document, rendered in order."""

    kind: Literal[
        "heading",
        "paragraph",
        "bullets",
        "numbered",
        "quote",
        "callout",
        "table",
        "chart",
        "figures",
        "illustration",
    ] = Field(
        description=(
            "What the block is: a heading, running text, an unordered list, an "
            "ordered sequence of steps, a verbatim quote, a callout (a warning "
            "or the one thing to remember), a table, a chart (its table holds "
            "the data, its table's chart says what to draw), key figures (the few "
            "numbers that carry the message), or an illustration (a picture, only "
            "as the illustration rules allow)."
        )
    )
    # No bound: an out-of-range level is clamped at normalization. A bound here
    # would fail the whole document — three paid times — over one heading.
    level: int = Field(default=2, description="Heading level 1-4 (headings only).")
    text: str = Field(
        default="", description="Text for heading, paragraph, quote and callout blocks."
    )
    items: list[str] = Field(default_factory=list, description="Items (bullets and numbered only).")
    table: TableSheet | None = Field(
        default=None, description="Table payload (table and chart only)."
    )
    caption: str = Field(
        default="", description="Caption naming a table, a chart or an illustration."
    )
    figures: list[KeyFigure] = Field(
        default_factory=list, description="The figures (figures only)."
    )
    illustration: Illustration | None = Field(
        default=None, description="The picture (illustration only)."
    )


class Source(BaseModel):
    """A source the text cites as [n], n being its position in the list."""

    title: str = Field(description="Its title, as the source names itself.")
    # Copied, never written: a model completes an address it half remembers,
    # and a link to a page that does not exist is worse than no link.
    url: str = Field(
        default="",
        description="Its web address, copied exactly from the material; never invented.",
    )


class SectionedContent(BaseModel):
    """Content for docx/pdf/md/txt outputs."""

    filename_stem: str = Field(description="Suggested filename without extension.")
    title: str = Field(description="Document title (rendered as the top heading).")
    subtitle: str = Field(default="", description="One line under the title: audience or purpose.")
    tone: str = Field(
        default="",
        description="The document's look: sober for most documents, institutional for "
        "official ones, warm for people and culture, technical for engineering and data; "
        "empty keeps it grey.",
        json_schema_extra=_one_of(DOCUMENT_TONES),
    )
    illustration: Illustration | None = Field(
        default=None,
        description="A picture for the document's cover, only as the illustration rules allow.",
    )
    image_style: str = Field(
        default="",
        description="The one visual style every picture of the document shares, in English "
        "(medium, palette, mood); empty when there is no picture.",
    )
    blocks: list[SectionBlock] = Field(min_length=1, description="Ordered content blocks.")
    sources: list[Source] = Field(
        default_factory=list,
        description="The sources the text cites as [1], [2]…, in that order; empty when it "
        "cites none.",
    )


class SlideColumn(BaseModel):
    """One side of a comparison slide."""

    heading: str = Field(description="Short heading of this side.")
    bullets: list[str] = Field(default_factory=list, description="Bullet points of this side.")


class Slide(BaseModel):
    """A single presentation slide."""

    title: str = Field(description="Slide title: an assertion or a precise topic.")
    kind: Literal["content", "section", "comparison", "table", "chart", "figures", "quote"] = Field(
        default="content",
        description=(
            "What the slide is: content (an idea supported by bullets), a section "
            "opener, a comparison of two sides, data (a table), a chart (its table "
            "holds the data, its table's chart says what to draw), key figures (the "
            "few numbers that carry the message), or a quote (someone's own words)."
        ),
    )
    # Drawn by a section opener and a quote only: a « lead line of a content
    # slide » was advertised here until 2026-11-13 and never drawn anywhere.
    subtitle: str = Field(
        default="", description="Tagline of a section opener, or who said a quote."
    )
    bullets: list[str] = Field(default_factory=list, description="Bullet points (content).")
    columns: list[SlideColumn] = Field(
        default_factory=list, description="The two sides (comparison)."
    )
    table: TableSheet | None = Field(default=None, description="Data (table and chart).")
    figures: list[KeyFigure] = Field(default_factory=list, description="The figures (figures).")
    quote: str = Field(default="", description="The quoted words, without quotation marks.")
    icon: str = Field(
        default="",
        description="A pictogram for a section opener, or empty.",
        json_schema_extra=_one_of(SLIDE_ICONS),
    )
    illustration: Illustration | None = Field(
        default=None,
        description="A picture beside a section opener or a content slide, only as the "
        "illustration rules allow.",
    )
    notes: str = Field(default="", description="Speaker notes: the full sentences.")


class SlideContent(BaseModel):
    """Content for pptx output."""

    filename_stem: str = Field(description="Suggested filename without extension.")
    title: str = Field(description="Presentation title (cover slide).")
    subtitle: str = Field(default="", description="Cover subtitle: audience, occasion or date.")
    tone: str = Field(
        default="",
        description="The document's look: sober for most documents, institutional for "
        "official ones, warm for people and culture, technical for engineering and data; "
        "empty keeps it grey.",
        json_schema_extra=_one_of(DOCUMENT_TONES),
    )
    delivery: str = Field(
        default="",
        description="How the deck will be used: presented (a speaker shows it to an "
        "audience) or read (sent and read alone); empty when the request does not say.",
        json_schema_extra=_one_of(DECK_DELIVERIES),
    )
    illustration: Illustration | None = Field(
        default=None, description="A picture for the cover, only as the illustration rules allow."
    )
    image_style: str = Field(
        default="",
        description="The one visual style every picture of the deck shares, in English "
        "(medium, palette, mood); empty when there is no picture.",
    )
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
