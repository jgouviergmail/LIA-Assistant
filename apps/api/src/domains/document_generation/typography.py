"""The one place a document's look is decided (ADR-274).

Neutral by design — ink on paper, one grey band, one grey rule — because these
files leave the person's hands: no brand, no theme colour, no vendored
template — unless the writer gives the document a TONE: its palette then
colours the structure (a title, the large headings, the rules) and the charts,
every colour validated rather than chosen by eye. A document without a tone, a
meeting's minutes among them, keeps the grey it always had.
Every renderer reads its sizes, colours, geometries and built-in style
identifiers here, so a future theme is a parametrisation of THIS module rather
than a sweep through five renderers.

What is NOT here: anything a reader could mistake for an identity, and anything
a setting owns (page size, density budgets live in ``core.config``).
"""

from __future__ import annotations

from dataclasses import dataclass
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
#: The ground every contrast is measured against.
PAPER = "FFFFFF"
#: WCAG 1.4.3: running text holds 4.5:1 on its ground; large type and marks 3:1.
BODY_TEXT_CONTRAST = 4.5

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
#: A deck of this many parts or more opens on an agenda the renderer writes.
PPTX_AGENDA_MIN_PARTS = 3
#: Key figures: at most this many tiles side by side; more continue on a slide
#: of their own (« Title (2/2) »). Published to the writer.
PPTX_FIGURES_PER_SLIDE = 4
#: A tile's height, its widest (a lone figure is not a banner), the gap between two.
PPTX_FIGURE_TILE_HEIGHT_IN = 3.9
PPTX_FIGURE_TILE_MAX_WIDTH_IN = 4.2
PPTX_FIGURE_GAP_IN = 0.35
#: Inside a tile: the padding, the pictogram's side and the space under it.
PPTX_FIGURE_PADDING_IN = 0.25
PPTX_FIGURE_ICON_IN = 0.75
PPTX_FIGURE_ICON_GAP_IN = 0.15
#: The figure's size by how many share the row, shrunk to the floor on one line.
PPTX_FIGURE_VALUE_PT: dict[int, int] = {1: 60, 2: 54, 3: 48, 4: 40}
assert set(PPTX_FIGURE_VALUE_PT) == set(
    range(1, PPTX_FIGURES_PER_SLIDE + 1)
), "every row length a figures slide can hold has its base size"
PPTX_FIGURE_VALUE_FLOOR_PT = 24
PPTX_FIGURE_LABEL_PT = 18
PPTX_FIGURE_LABEL_FLOOR_PT = 12
#: A quote: its words beside a rule, then who said them.
PPTX_QUOTE_PT = 32
PPTX_QUOTE_FLOOR_PT = 18
PPTX_ATTRIBUTION_PT = 18
PPTX_ATTRIBUTION_FLOOR_PT = 12
#: A section opener's pictogram, above its tagline.
PPTX_SECTION_ICON_IN = 1.4

# ---------------------------------------------------------------------------
# XLSX
# ---------------------------------------------------------------------------
#: Greyscale built-in table style with row stripes.
XLSX_TABLE_STYLE = "TableStyleLight1"
XLSX_COLUMN_WIDTH_MIN = 8
XLSX_COLUMN_WIDTH_MAX = 60
#: Beyond this many columns a sheet prints in landscape (one page wide either way).
XLSX_PORTRAIT_MAX_COLUMNS = 6
#: Excel's paper codes.
XLSX_PAPER: dict[str, int] = {"a4": 9, "letter": 1}
#: A defined name is a label a formula reads, never a sentence.
XLSX_NAME_MAX_CHARS = 60
#: The two ends of the scale that colours a measure by which way is good.
XLSX_SCALE_NEUTRAL = "#FFFFFF"
XLSX_SCALE_GOOD = "#A9D8B8"

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
#: The most pages a layout pass may produce. PyMuPDF's Story can cycle forever —
#: a floated picture straddling a page end is never placed, and ``place()``
#: answers « more » on every page of a three-page cycle (measured 2026-11-13) —
#: and no signal tells such a cycle from a long table. A slot writing 100 000
#: output tokens of prose fills ~120 A4 pages (~55 000 words), of table ~115: the
#: bound leaves more than twice that, and still stops a cycle before its pages
#: hold hundreds of megabytes on the production board.
PDF_MAX_PAGES = 300
_PDF_TABLE_CLASSES: dict[float, str] = {6.0: "xxwide", 7.0: "xwide", 9.0: "wide"}

# ---------------------------------------------------------------------------
# Pages — a report's key figures, cover and wide tables (docx and pdf)
# ---------------------------------------------------------------------------
#: How many key figures share one row of a report's band; more wrap onto rows
#: as even as possible (``fit.balanced_rows``).
PAGE_FIGURES_PER_ROW = 4
#: A value's size by how many figures share its row. Every value of a row takes
#: one size, shrunk until the widest fits its tile on one line.
PAGE_FIGURE_VALUE_PT: dict[int, int] = {1: 28, 2: 26, 3: 24, 4: 20}
assert set(PAGE_FIGURE_VALUE_PT) == set(
    range(1, PAGE_FIGURES_PER_ROW + 1)
), "every row length a band can hold has its base size"
#: Below this a value stops shrinking: it wraps inside its tile instead. 14 pt
#: bold is WCAG's « large text », the size from which an accent on its wash
#: (3:1, not 4.5:1) still reads.
PAGE_FIGURE_VALUE_FLOOR_PT = 14
PAGE_FIGURE_LABEL_PT = 9
#: The space around and between the tiles, and inside each one.
PAGE_FIGURE_GAP_PT = 6.0
PAGE_FIGURE_PADDING_PT = 6.0
#: Bold glyphs run wider than the regular ones every measure is calibrated on.
BOLD_WIDTH_FACTOR = 1.1
#: How far below the top margin a long document's cover sets its title.
COVER_TITLE_DROP_PT = 144
#: From this many columns a table takes a landscape page of its own in Word,
#: which would otherwise squeeze the columns until the words break mid-word.
#: The PDF shrinks the type instead (``PDF_TABLE_SIZE_LADDER``).
DOCX_LANDSCAPE_MIN_COLUMNS = 8
#: A source's number hangs in the margin of its entry, the entry's lines aligned.
SOURCE_HANGING_PT = 22

# ---------------------------------------------------------------------------
# Tones and their palettes — the one place colour enters a document
# ---------------------------------------------------------------------------
#: Series colours of a NEUTRAL or sober document, assigned in this order and
#: never cycled: the ORDER keeps neighbours apart for a colour-blind reader. Every
#: series palette below was chosen by an exhaustive search of the dataviz
#: validator over the documented hues, one shade per hue family (2026-11-13),
#: and passes its gates against white paper — every slot ≥ 3:1, worst adjacent
#: pair ΔE ≥ 13 under protanopia/deuteranopia (target 8), normal vision ≥ 19.3
#: (floor 15), the first three apart pair by pair (a scatter draws three at most).
#: ``test_document_palettes.py`` re-runs those gates. Text never wears these.
NEUTRAL_SERIES: tuple[str, ...] = ("2A78D6", "C98500", "D55181", "008300", "6250D6", "D95926")
#: How much of the accent a wash keeps (the rest is paper).
_WASH_STRENGTH = 0.1


def tint(color: str, strength: float = _WASH_STRENGTH) -> str:
    """``color`` mixed with paper: a wash a dark text reads on."""
    channels = (int(color[index : index + 2], 16) for index in (0, 2, 4))
    return "".join(f"{round(255 - (255 - channel) * strength):02X}" for channel in channels)


@dataclass(frozen=True, slots=True)
class Palette:
    """A tone's colours: one accent for large type and rules, its wash, the series.

    The accent marks STRUCTURE — a title, the two largest heading levels, a
    slide title, a rule, a section divider — never small text: some accents
    hold 3:1 on paper (enough for large type and marks, WCAG 1.4.3 / 1.4.11),
    not the 4.5:1 body text needs. A neutral palette has no accent at all, and
    every role falls back to the grey a document had before tones existed —
    which is what keeps meeting minutes exactly as they were.
    """

    accent: str | None
    series: tuple[str, ...]

    @property
    def title_ink(self) -> str:
        return self.accent or INK

    @property
    def heading_ink(self) -> str:
        return self.accent or HEADING_INK

    @property
    def rule(self) -> str:
        return self.accent or RULE

    @property
    def marker(self) -> str:
        """A callout's edge, a header row's rule."""
        return self.accent or MUTED

    @property
    def wash(self) -> str:
        return tint(self.accent) if self.accent else BAND

    @property
    def link_ink(self) -> str:
        """A link's words: the accent where it reads as running text, else ink.

        A link is running text, so it needs 4.5:1 — which a warm or a technical
        accent does not hold. Its underline says « link » whatever its colour
        (WCAG 1.4.1).
        """
        if self.accent and contrast(self.accent, PAPER) >= BODY_TEXT_CONTRAST:
            return self.accent
        return HEADING_INK


#: tone -> palette. The empty tone is neutral: grey type, sober series.
PALETTES: dict[str, Palette] = {
    "": Palette(accent=None, series=NEUTRAL_SERIES),
    "sober": Palette(accent="1C5CAB", series=NEUTRAL_SERIES),
    "institutional": Palette(
        accent="104281", series=("1C5CAB", "D95926", "9085E9", "C98500", "D55181", "008300")
    ),
    "warm": Palette(
        accent="D95926", series=("D95926", "1C5CAB", "9085E9", "C98500", "D55181", "008300")
    ),
    "technical": Palette(
        accent="199E70", series=("199E70", "1C5CAB", "9085E9", "C98500", "D55181", "008300")
    ),
}


def palette_for(tone: str) -> Palette:
    """The palette of a canonical tone (neutral when unknown)."""
    return PALETTES.get(tone, PALETTES[""])


#: More series than colours is never solved by inventing a colour.
CHART_MAX_SERIES = len(NEUTRAL_SERIES)
assert all(
    len(palette.series) == CHART_MAX_SERIES for palette in PALETTES.values()
), "every palette carries the same number of series colours"
#: Any two dots of a scatter can touch: only the pairwise-safe slots.
CHART_SCATTER_MAX_SERIES = 3
#: Up to this many categories with short labels, values stand as columns.
CHART_COLUMN_MAX_CATEGORIES = 8
#: Horizontal bars carry long labels, up to this many before they crowd.
CHART_BAR_MAX_CATEGORIES = 30
#: A label longer than this many average characters reads better on a bar's side.
CHART_SHORT_LABEL_COLUMNS = 12
#: A whole split into more parts than this is compared, not glanced at.
CHART_SHARE_MAX_PARTS = 6
#: Values are written on single-series bars up to this many categories.
CHART_VALUE_LABELS_MAX = 12
#: Report figures: drawn at the text width, this tall (a bar chart grows per bar).
CHART_FIGURE_HEIGHT_PT = 250.0
CHART_BAR_STEP_PT = 18.0
#: Word receives the figure as a picture at this resolution.
CHART_RASTER_DPI = 200
#: Workbook charts, in pixels as Excel sizes them.
XLSX_CHART_WIDTH_PX = 576
XLSX_CHART_HEIGHT_PX = 336
XLSX_CHART_SEGMENTED_HEIGHT_PX = 160


def _luminance(hex_color: str) -> float:
    """WCAG relative luminance of an ``RRGGBB`` colour."""
    channels = [int(hex_color[index : index + 2], 16) / 255 for index in (0, 2, 4)]
    linear = [
        value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4
        for value in channels
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(first: str, second: str) -> float:
    """The WCAG contrast ratio of two ``RRGGBB`` colours (1 to 21)."""
    light, dark = sorted((_luminance(first), _luminance(second)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def label_on(fill: str) -> str:
    """The ink of a label set INSIDE a coloured fill: white or ink, whichever reads better.

    Computed, never chosen by eye: on four of the six series colours ink
    contrasts more than white (5.67 against 3.07 on the ochre).
    """
    return "FFFFFF" if contrast("FFFFFF", fill) >= contrast(INK, fill) else INK


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
    """The ``pymupdf.paper_rect`` name of a page size."""
    return _PAGE_RECT_NAME[page_size]


def docx_margin_cm(page_size: PageSize) -> float:
    """Word margins: 2.5 cm on A4, one inch on Letter."""
    return _DOCX_MARGIN_CM[page_size]


def pdf_css(palette: Palette = PALETTES[""]) -> str:
    """The stylesheet PyMuPDF's Story lays the document out with.

    Tables carry NO header background and NO ``border-collapse``: with both,
    MuPDF repaints a phantom header rectangle at the top of every continuation
    page (measured 2026-09-08). The header is separated by a rule instead, and
    banding sits on ``td`` only.

    Args:
        palette: The document's tone; the neutral one gives the grey sheet.

    Returns:
        A CSS string built from the constants above — never a second palette.
    """
    return (
        f"body {{ font-family: {PDF_FONT_FAMILY}; font-size: {PDF_BODY_PT}pt; "
        f"line-height: {PDF_LINE_HEIGHT}; color: #{INK}; }}\n"
        f"h1 {{ font-size: {PDF_HEADING_PT[1]}pt; margin: 0 0 4pt 0; "
        f"color: #{palette.title_ink}; }}\n"
        f"h2 {{ font-size: {PDF_HEADING_PT[2]}pt; margin: 18pt 0 6pt 0; "
        f"color: #{palette.heading_ink}; border-bottom: 0.5pt solid #{palette.rule}; }}\n"
        f"h3 {{ font-size: {PDF_HEADING_PT[3]}pt; margin: 12pt 0 4pt 0; color: #{HEADING_INK}; }}\n"
        f"h4 {{ font-size: {PDF_HEADING_PT[4]}pt; margin: 10pt 0 3pt 0; color: #{HEADING_INK}; }}\n"
        f"h5 {{ font-size: {PDF_HEADING_PT[4]}pt; margin: 10pt 0 3pt 0; color: #{HEADING_INK}; }}\n"
        "p { margin: 0 0 8pt 0; }\n"
        f"p.subtitle {{ font-size: {PDF_BODY_PT + 2}pt; color: #{MUTED}; margin-bottom: 2pt; }}\n"
        f"p.date {{ font-size: {PDF_BODY_PT - 1}pt; color: #{MUTED}; margin-bottom: 14pt; }}\n"
        f"p.caption {{ font-size: {PDF_BODY_PT - 1.5}pt; color: #{MUTED}; "
        "font-style: italic; margin: 8pt 0 3pt 0; }\n"
        "p.figure { margin: 10pt 0 0 0; text-align: center; }\n"
        "p.toc1 { margin: 0 0 3pt 0; }\n"
        "p.toc2 { margin: 0 0 3pt 14pt; }\n"
        "p.toc3 { margin: 0 0 3pt 28pt; }\n"
        "ul, ol { margin: 0 0 8pt 0; }\n"
        "li { margin: 0 0 2pt 0; }\n"
        f"blockquote {{ margin: 6pt 18pt; padding-left: 8pt; "
        f"border-left: 2pt solid #{RULE}; color: #{MUTED}; }}\n"
        f"div.callout {{ background-color: #{palette.wash}; "
        f"border-left: 2pt solid #{palette.marker}; "
        "padding: 6pt 8pt; margin: 6pt 0 10pt 0; }\n"
        "table { width: 100%; margin: 2pt 0 10pt 0; }\n"
        "th { font-weight: bold; text-align: left; padding: 3pt 5pt; "
        f"border-bottom: 1pt solid #{palette.marker}; }}\n"
        f"td {{ padding: 3pt 5pt; border-bottom: 0.3pt solid #{RULE_LIGHT}; }}\n"
        f"tr:nth-child(even) td {{ background-color: #{BAND}; }}\n"
        "td.num, th.num { text-align: right; }\n"
        f"tr.total td {{ font-weight: bold; border-top: 0.8pt solid #{palette.marker}; }}\n"
        "table.wide th, table.wide td { font-size: 9pt; padding: 2pt 3pt; }\n"
        "table.xwide th, table.xwide td { font-size: 7pt; padding: 1pt 2pt; }\n"
        "table.xxwide th, table.xxwide td { font-size: 6pt; padding: 1pt 1pt; }\n"
        f"code {{ font-family: monospace; color: #{HEADING_INK}; }}\n"
        # ``a[href]``, not ``a``: MuPDF's own sheet colours links blue under that
        # selector, and a plain ``a`` loses to it (measured 2026-11-13).
        f"a[href] {{ color: #{palette.link_ink}; text-decoration: underline; }}\n"
        # A band's gutters are white borders, half a gap per side: MuPDF reads
        # one value of ``border-spacing`` for both axes, which doubled the gap
        # between two rows of tiles (measured 2026-11-13).
        "div.band { margin: 4pt 0 10pt 0; }\n"
        "table.figures { border-spacing: 0; margin: 0; }\n"
        f"table.figures td {{ background-color: #{palette.wash}; text-align: center; "
        f"padding: {PAGE_FIGURE_PADDING_PT}pt; "
        f"border: {PAGE_FIGURE_GAP_PT / 2}pt solid #{PAPER}; }}\n"
        f"p.value {{ font-weight: bold; color: #{palette.title_ink}; margin: 0; "
        "line-height: 1.15; }\n"
        f"p.label {{ font-size: {PAGE_FIGURE_LABEL_PT}pt; color: #{MUTED}; "
        "margin: 2pt 0 0 0; line-height: 1.2; }\n"
        f"div.cover h1 {{ margin-top: {COVER_TITLE_DROP_PT}pt; }}\n"
        f"p.source {{ margin: 0 0 4pt 0; padding-left: {SOURCE_HANGING_PT}pt; "
        f"text-indent: -{SOURCE_HANGING_PT}pt; }}\n"
    )
