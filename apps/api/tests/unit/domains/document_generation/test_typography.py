"""One source for the look; the CSS is built from it, never written twice (ADR-274)."""

import re

import pytest

from src.domains.document_generation import typography

pytestmark = [pytest.mark.unit]


class TestTheStylesheetComesFromTheConstants:
    def test_sizes_and_colours_are_the_module_s_own(self) -> None:
        css = typography.pdf_css()
        assert f"font-size: {typography.PDF_BODY_PT}pt" in css
        assert f"h1 {{ font-size: {typography.PDF_HEADING_PT[1]}pt" in css
        assert f"#{typography.INK}" in css and f"#{typography.BAND}" in css

    def test_the_safe_table_recipe_is_enforced(self) -> None:
        """The MuPDF phantom rectangle, measured 2026-09-08: no th background,
        no border-collapse. Banding lives on td only."""
        css = typography.pdf_css()
        header_rule = css.split("th {")[1].split("}")[0]
        assert "background" not in header_rule
        assert "border-bottom" in header_rule
        assert "border-collapse" not in css
        assert "tr:nth-child(even) td" in css

    def test_every_hex_colour_is_grey(self) -> None:
        """Neutral means neutral: no hue may creep into a document."""
        for name in ("INK", "HEADING_INK", "MUTED", "RULE", "RULE_LIGHT", "BAND"):
            value = getattr(typography, name)
            red, green, blue = (int(value[i : i + 2], 16) for i in (0, 2, 4))
            assert red == green == blue, f"{name} carries a hue"

    def test_the_css_declares_every_block_kind_the_vocabulary_has(self) -> None:
        css = typography.pdf_css()
        for selector in ("blockquote", "div.callout", "ol", "ul", "p.caption", "table"):
            assert selector in css, selector


class TestGeometries:
    def test_page_names_and_margins(self) -> None:
        assert typography.page_rect_name("a4") == "a4"
        assert typography.page_rect_name("letter") == "letter"
        assert typography.docx_margin_cm("a4") == 2.5
        assert typography.docx_margin_cm("letter") == pytest.approx(2.54)

    def test_slides_are_landscape(self) -> None:
        """16:9 landscape, never portrait — the owner's constraint, pinned."""
        assert typography.PPTX_SLIDE_WIDTH_IN > typography.PPTX_SLIDE_HEIGHT_IN
        ratio = typography.PPTX_SLIDE_WIDTH_IN / typography.PPTX_SLIDE_HEIGHT_IN
        assert ratio == pytest.approx(16 / 9, abs=0.01)

    def test_the_pdf_bottom_margin_clears_the_stamped_footer(self) -> None:
        _left, _top, _right, bottom = typography.PDF_MARGIN_PT
        assert bottom > typography.PDF_FOOTER_BASELINE_FROM_BOTTOM_PT

    def test_heading_sizes_decrease_with_depth(self) -> None:
        for scale in (typography.DOCX_HEADING_PT, typography.PDF_HEADING_PT):
            levels = sorted(scale)
            assert all(scale[a] >= scale[b] for a, b in zip(levels, levels[1:], strict=False))

    def test_built_in_style_identifiers_have_the_shape_their_library_expects(self) -> None:
        assert re.fullmatch(r"\{[0-9A-F-]{36}\}", typography.PPTX_TABLE_STYLE_ID)
        assert "Accent" not in typography.DOCX_TABLE_STYLE  # accent styles carry the theme blue
        assert typography.XLSX_TABLE_STYLE.startswith("TableStyle")
