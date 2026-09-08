"""The one place a document's look is decided (ADR-274).

Neutral by design — ink on paper, one grey band, one grey rule — because these
files leave the person's hands: no brand, no theme colour, no vendored
template. Every renderer reads its sizes, colours, geometries and built-in
style identifiers here, so a future theme is a parametrisation of THIS module
rather than a sweep through five renderers.

What is NOT here: anything a reader could mistake for an identity, and anything
a setting owns (page size, density budgets live in ``core.config``).
"""

from __future__ import annotations

from typing import Literal

PageSize = Literal["a4", "letter"]

# ---------------------------------------------------------------------------
# Faces
# ---------------------------------------------------------------------------
#: Metric-compatible with Carlito, which is what LibreOffice substitutes.
FONT_BODY = "Calibri"
#: Declared so CJK never falls back to a Latin face mid-sentence.
FONT_EAST_ASIA = "Microsoft YaHei"
FONT_MONO = "Consolas"
#: PyMuPDF bundles Nimbus Sans and Droid Sans Fallback (CJK) — no system font.
PDF_FONT_FAMILY = "sans-serif"

# ---------------------------------------------------------------------------
# Ink (greyscale only: the hierarchy comes from size and space, not colour)
# ---------------------------------------------------------------------------
INK = "1A1A1A"
HEADING_INK = "262626"
MUTED = "595959"
RULE = "BFBFBF"
RULE_LIGHT = "DDDDDD"
BAND = "F2F2F2"

# ---------------------------------------------------------------------------
# DOCX
# ---------------------------------------------------------------------------
DOCX_BODY_PT = 11
DOCX_TITLE_PT = 26
DOCX_SUBTITLE_PT = 13
DOCX_HEADING_PT: dict[int, int] = {1: 18, 2: 14, 3: 12, 4: 11}
DOCX_CAPTION_PT = 9
DOCX_LINE_SPACING = 1.15
DOCX_SPACE_AFTER_PT = 6
#: A non-accent built-in style: the accent variants carry the theme's blue.
DOCX_TABLE_STYLE = "Light List"
DOCX_TOC_INDENT_CM = 0.75
DOCX_QUOTE_INDENT_CM = 1.0
DOCX_CALLOUT_INDENT_CM = 0.5
_DOCX_MARGIN_CM: dict[str, float] = {"a4": 2.5, "letter": 2.54}

# ---------------------------------------------------------------------------
# PPTX — 16:9 LANDSCAPE, never portrait
# ---------------------------------------------------------------------------
PPTX_SLIDE_WIDTH_IN = 13.333
PPTX_SLIDE_HEIGHT_IN = 7.5
#: "Light Style 1": greyscale header and banding, confirmed by PowerPoint.
PPTX_TABLE_STYLE_ID = "{9D7B26C5-4107-4FEC-AEDC-1716B250A1EF}"
PPTX_SUBTITLE_PT = 24
PPTX_DATE_PT = 16
PPTX_SECTION_TAGLINE_PT = 20
PPTX_COMPARISON_HEADING_PT = 22

# ---------------------------------------------------------------------------
# XLSX
# ---------------------------------------------------------------------------
#: Greyscale built-in table style with row stripes.
XLSX_TABLE_STYLE = "TableStyleLight1"
XLSX_COLUMN_WIDTH_MIN = 8
XLSX_COLUMN_WIDTH_MAX = 60

# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------
PDF_BODY_PT = 10.5
PDF_HEADING_PT: dict[int, float] = {1: 22, 2: 15, 3: 12.5, 4: 11}
PDF_LINE_HEIGHT = 1.35
#: left, top, right, bottom — the bottom is deeper to clear the stamped footer.
PDF_MARGIN_PT: tuple[float, float, float, float] = (56, 56, 56, 64)
PDF_STAMP_PT = 8
PDF_HEADER_BASELINE_PT = 40
PDF_FOOTER_BASELINE_FROM_BOTTOM_PT = 36
_PAGE_RECT_NAME: dict[str, str] = {"a4": "a4", "letter": "letter"}

# A wide table RUNS OFF the page: MuPDF sizes columns from their content and
# honours neither ``width: 100%`` nor ``table-layout: fixed`` once the columns
# are many. Measured 2026-09-08 on A4 with long headers, reading where the
# table's RULES stop — the text alone stops at the last glyph and HIDES the
# overflow (12 columns: text 544, rules 714, on a 595 pt page).
#
#   columns   base    9pt    7pt    6pt     right edge = 539 pt
#        8     526      —      —      —     fits at the base size
#       10     606    526      —      —
#       12     714    594    527      —
#       14       —      —    542    526
#       16       —      —    610    527
#
#: (columns from, font size) — read in order, first match wins.
PDF_TABLE_SIZE_LADDER: tuple[tuple[int, float], ...] = ((13, 6.0), (11, 7.0), (9, 9.0))
#: Beyond this, nothing fits: 20 columns overflow even at 5 pt, and a table
#: that narrow is unreadable anyway. Stated as a limit rather than hidden.
PDF_TABLE_MAX_FITTING_COLUMNS = 16
_PDF_TABLE_CLASSES: dict[float, str] = {6.0: "xxwide", 7.0: "xwide", 9.0: "wide"}


def pdf_table_class(columns: int) -> str:
    """The CSS class a table of ``columns`` columns needs to stay on the page.

    Args:
        columns: How many columns the table has.

    Returns:
        A class name, or an empty string when the base size already fits.
    """
    for threshold, size in PDF_TABLE_SIZE_LADDER:
        if columns >= threshold:
            return _PDF_TABLE_CLASSES[size]
    return ""


def page_rect_name(page_size: PageSize) -> str:
    """The ``fitz.paper_rect`` name of a page size."""
    return _PAGE_RECT_NAME[page_size]


def docx_margin_cm(page_size: PageSize) -> float:
    """Word margins: 2.5 cm on A4, one inch on Letter."""
    return _DOCX_MARGIN_CM[page_size]


def pdf_css() -> str:
    """The stylesheet PyMuPDF's Story lays the document out with.

    Tables carry NO header background and NO ``border-collapse``: with both,
    MuPDF repaints a phantom header rectangle at the top of every continuation
    page (measured 2026-09-08). The header is separated by a rule instead, and
    banding sits on ``td`` only.

    Returns:
        A CSS string built from the constants above — never a second palette.
    """
    return (
        f"body {{ font-family: {PDF_FONT_FAMILY}; font-size: {PDF_BODY_PT}pt; "
        f"line-height: {PDF_LINE_HEIGHT}; color: #{INK}; }}\n"
        f"h1 {{ font-size: {PDF_HEADING_PT[1]}pt; margin: 0 0 4pt 0; color: #{INK}; }}\n"
        f"h2 {{ font-size: {PDF_HEADING_PT[2]}pt; margin: 18pt 0 6pt 0; color: #{HEADING_INK}; "
        f"border-bottom: 0.5pt solid #{RULE}; }}\n"
        f"h3 {{ font-size: {PDF_HEADING_PT[3]}pt; margin: 12pt 0 4pt 0; color: #{HEADING_INK}; }}\n"
        f"h4 {{ font-size: {PDF_HEADING_PT[4]}pt; margin: 10pt 0 3pt 0; color: #{HEADING_INK}; }}\n"
        f"h5 {{ font-size: {PDF_HEADING_PT[4]}pt; margin: 10pt 0 3pt 0; color: #{HEADING_INK}; }}\n"
        "p { margin: 0 0 8pt 0; }\n"
        f"p.subtitle {{ font-size: {PDF_BODY_PT + 2}pt; color: #{MUTED}; margin-bottom: 2pt; }}\n"
        f"p.date {{ font-size: {PDF_BODY_PT - 1}pt; color: #{MUTED}; margin-bottom: 14pt; }}\n"
        f"p.caption {{ font-size: {PDF_BODY_PT - 1.5}pt; color: #{MUTED}; "
        "font-style: italic; margin: 8pt 0 3pt 0; }\n"
        "p.toc1 { margin: 0 0 3pt 0; }\n"
        "p.toc2 { margin: 0 0 3pt 14pt; }\n"
        "p.toc3 { margin: 0 0 3pt 28pt; }\n"
        "ul, ol { margin: 0 0 8pt 0; }\n"
        "li { margin: 0 0 2pt 0; }\n"
        f"blockquote {{ margin: 6pt 18pt; padding-left: 8pt; "
        f"border-left: 2pt solid #{RULE}; color: #{MUTED}; }}\n"
        f"div.callout {{ background-color: #{BAND}; border-left: 2pt solid #{MUTED}; "
        "padding: 6pt 8pt; margin: 6pt 0 10pt 0; }\n"
        "table { width: 100%; margin: 2pt 0 10pt 0; }\n"
        "th { font-weight: bold; text-align: left; padding: 3pt 5pt; "
        f"border-bottom: 1pt solid #{MUTED}; }}\n"
        f"td {{ padding: 3pt 5pt; border-bottom: 0.3pt solid #{RULE_LIGHT}; }}\n"
        f"tr:nth-child(even) td {{ background-color: #{BAND}; }}\n"
        "td.num, th.num { text-align: right; }\n"
        "table.wide th, table.wide td { font-size: 9pt; padding: 2pt 3pt; }\n"
        "table.xwide th, table.xwide td { font-size: 7pt; padding: 1pt 2pt; }\n"
        "table.xxwide th, table.xxwide td { font-size: 6pt; padding: 1pt 1pt; }\n"
        f"code {{ font-family: monospace; color: #{HEADING_INK}; }}\n"
    )
