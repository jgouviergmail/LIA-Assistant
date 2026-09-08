"""The named styles a generated Word document uses (ADR-274).

Everything the renderer writes goes through a NAMED style, redefined once from
``typography``: a reader can then restyle the whole document from Word's own
gallery, which is what makes a .docx a document rather than a picture of one.
Direct formatting appears nowhere.
"""

from __future__ import annotations

from typing import Any

from docx.enum.style import WD_STYLE_TYPE
from docx.shared import Cm, Pt, RGBColor

from src.domains.document_generation import typography
from src.domains.document_generation.renderers import docx_ooxml as ooxml

#: The style the renderer creates for a callout, since Word has no such style.
CALLOUT_STYLE = "Callout"
#: Styles whose face and East-Asian fallback are set on every document.
_FACED_STYLES: tuple[str, ...] = (
    "Normal",
    "Title",
    "Subtitle",
    "Heading 1",
    "Heading 2",
    "Heading 3",
    "Heading 4",
    "Caption",
    "Quote",
    "List Bullet",
    "List Number",
    "Header",
    "Footer",
    "TOC Heading",
)


def _define_body(styles: Any) -> None:
    normal = styles["Normal"]
    normal.font.size = Pt(typography.DOCX_BODY_PT)
    normal.font.color.rgb = RGBColor.from_string(typography.INK)
    normal.paragraph_format.line_spacing = typography.DOCX_LINE_SPACING
    normal.paragraph_format.space_after = Pt(typography.DOCX_SPACE_AFTER_PT)
    normal.paragraph_format.widow_control = True


def _define_title(styles: Any) -> None:
    title = styles["Title"]
    title.font.size = Pt(typography.DOCX_TITLE_PT)
    title.font.color.rgb = RGBColor.from_string(typography.INK)
    ooxml.recolor_title_rule(title, typography.RULE)
    subtitle = styles["Subtitle"]
    subtitle.font.size = Pt(typography.DOCX_SUBTITLE_PT)
    subtitle.font.color.rgb = RGBColor.from_string(typography.MUTED)
    subtitle.font.italic = False


def _define_headings(styles: Any) -> None:
    for level, size in typography.DOCX_HEADING_PT.items():
        heading = styles[f"Heading {level}"]
        heading.font.size = Pt(size)
        heading.font.bold = True
        heading.font.color.rgb = RGBColor.from_string(typography.HEADING_INK)
    toc_heading = styles["TOC Heading"]
    toc_heading.font.color.rgb = RGBColor.from_string(typography.HEADING_INK)


def _define_notes(styles: Any) -> None:
    for name in ("Caption", "Header", "Footer"):
        style = styles[name]
        style.font.size = Pt(typography.DOCX_CAPTION_PT)
        style.font.color.rgb = RGBColor.from_string(typography.MUTED)
    quote = styles["Quote"]
    quote.font.italic = True
    quote.font.color.rgb = RGBColor.from_string(typography.MUTED)
    quote.paragraph_format.left_indent = Cm(typography.DOCX_QUOTE_INDENT_CM)


def _define_callout(document: Any) -> None:
    """Word has no callout style: one is created, shaded and ruled."""
    styles = document.styles
    if CALLOUT_STYLE in {style.name for style in styles}:
        return
    callout = styles.add_style(CALLOUT_STYLE, WD_STYLE_TYPE.PARAGRAPH)
    callout.base_style = styles["Normal"]
    callout.paragraph_format.left_indent = Cm(typography.DOCX_CALLOUT_INDENT_CM)
    callout.paragraph_format.space_before = Pt(typography.DOCX_SPACE_AFTER_PT)
    callout.paragraph_format.space_after = Pt(typography.DOCX_SPACE_AFTER_PT + 4)
    ooxml.shade_paragraph_style(callout, typography.BAND)
    ooxml.left_border_style(callout, typography.MUTED)


def _define_toc_entries(document: Any) -> None:
    """``TOC 1..3`` exist in Word but not always in the bare template."""
    styles = document.styles
    present = {style.name for style in styles}
    for level in range(1, ooxml.NUMBERED_LEVELS + 1):
        name = f"TOC {level}"
        if name in present:
            continue
        entry = styles.add_style(name, WD_STYLE_TYPE.PARAGRAPH)
        entry.base_style = styles["Normal"]
        entry.paragraph_format.left_indent = Cm(typography.DOCX_TOC_INDENT_CM * (level - 1))
        entry.paragraph_format.space_after = Pt(2)


def define_styles(document: Any, *, numbered: bool) -> None:
    """Redefine every style the renderer uses, neutrally.

    Args:
        document: A fresh python-docx document.
        numbered: Whether the long-document apparatus is on, which adds the
            heading numbering definition.
    """
    styles = document.styles
    for name in _FACED_STYLES:
        style = styles[name]
        style.font.name = typography.FONT_BODY
        ooxml.set_east_asian_font(style, typography.FONT_EAST_ASIA)
    _define_body(styles)
    _define_title(styles)
    _define_headings(styles)
    _define_notes(styles)
    _define_callout(document)
    _define_toc_entries(document)
    ooxml.detach_toc_heading(document)
    if numbered:
        ooxml.add_heading_numbering(document)
