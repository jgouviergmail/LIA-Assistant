"""A document's tone, in every format — and none at all for a record (ADR-274 amendment).

A toned document wears its accent on its STRUCTURE (title, the two largest
heading levels, slide titles, rules, a section divider), its wash under a
callout or a header row, its series in its charts, and its series again as the
Office theme a reader's own additions pick from. A document without a tone —
meeting minutes among them — renders exactly as it did before tones existed.
Each oracle is the format's own reader.
"""

from __future__ import annotations

import io
import re
import zipfile

import docx
import openpyxl
import pptx
import pytest
from docx.opc.constants import RELATIONSHIP_TYPE

from src.domains.document_generation import typography
from src.domains.document_generation.context import RenderContext
from src.domains.document_generation.normalize import normalize_content
from src.domains.document_generation.renderers import render_document
from src.domains.document_generation.schemas import (
    ChartSpec,
    DocumentType,
    SectionBlock,
    SectionedContent,
    Slide,
    SlideContent,
    TableSheet,
    TabularContent,
)

pytestmark = [pytest.mark.unit]

_CONTEXT = RenderContext(language="en")
WARM = typography.PALETTES["warm"]


def _report(tone: str) -> SectionedContent:
    return SectionedContent(
        filename_stem="r",
        title="Report",
        tone=tone,
        blocks=[
            SectionBlock(kind="heading", level=1, text="Findings"),
            SectionBlock(kind="heading", level=3, text="Detail"),
            SectionBlock(kind="callout", text="Remember this."),
        ],
    )


def _deck(tone: str) -> SlideContent:
    return SlideContent(
        filename_stem="d",
        title="Deck",
        tone=tone,
        slides=[
            Slide(title="Part one", kind="section", subtitle="Where we stand"),
            Slide(
                title="Sales",
                kind="chart",
                table=TableSheet(
                    name="s",
                    headers=["Region", "Revenue"],
                    rows=[["North", "10"], ["South", "12"]],
                    chart=ChartSpec(),
                ),
            ),
        ],
    )


def _sheet(tone: str) -> TabularContent:
    return TabularContent(
        filename_stem="w",
        title="Workbook",
        tone=tone,
        sheets=[
            TableSheet(
                name="Sales",
                headers=["Region", "Revenue", "Cost"],
                rows=[["North", "10", "4"], ["South", "12", "5"]],
                chart=ChartSpec(),
            )
        ],
    )


def _theme_accents(blob: bytes) -> list[str]:
    xml = blob.decode("utf-8")
    return [
        re.search(r'srgbClr val="([0-9A-Fa-f]{6})"', block).group(1).upper()  # type: ignore[union-attr]
        for block in re.findall(r"<a:accent\d>(.*?)</a:accent\d>", xml, flags=re.S)
    ]


class TestTheToneIsRepaired:
    @pytest.mark.parametrize(("written", "kept"), [("Warm ", "warm"), ("neon", ""), ("", "")])
    def test_an_unknown_tone_is_no_tone(self, written: str, kept: str) -> None:
        canonical = normalize_content(_report(written), _CONTEXT)
        assert isinstance(canonical, SectionedContent) and canonical.tone == kept


class TestWord:
    def _open(self, tone: str) -> docx.document.Document:
        return docx.Document(
            io.BytesIO(render_document(DocumentType.DOCX, _report(tone), _CONTEXT))
        )

    def test_a_toned_report_wears_its_accent_on_its_large_headings(self) -> None:
        styles = self._open("warm").styles
        assert str(styles["Title"].font.color.rgb) == WARM.accent
        assert str(styles["Heading 1"].font.color.rgb) == WARM.accent
        assert str(styles["Heading 3"].font.color.rgb) == typography.HEADING_INK

    def test_its_callout_lies_on_the_wash(self) -> None:
        callout = self._open("warm").styles["Callout"]
        shading = callout.element.xpath(".//w:shd")[0]
        assert (
            shading.get(
                "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}fill"
            ).upper()
            == WARM.wash
        )

    def test_its_theme_offers_the_tone_s_series(self) -> None:
        theme = self._open("warm").part.part_related_by(RELATIONSHIP_TYPE.THEME)
        assert _theme_accents(theme.blob) == list(WARM.series)

    def test_a_report_without_a_tone_keeps_its_grey_and_its_theme(self) -> None:
        document = self._open("")
        assert str(document.styles["Heading 1"].font.color.rgb) == typography.HEADING_INK
        assert str(document.styles["Title"].font.color.rgb) == typography.INK
        theme = document.part.part_related_by(RELATIONSHIP_TYPE.THEME)
        pristine = docx.Document().part.part_related_by(RELATIONSHIP_TYPE.THEME)
        assert theme.blob == pristine.blob


class TestPdf:
    def test_the_stylesheet_of_no_tone_is_the_grey_one(self) -> None:
        assert typography.pdf_css() == typography.pdf_css(typography.PALETTES[""])
        assert typography.palette_for("").accent is None

    def test_a_toned_stylesheet_colours_structure_never_body_text(self) -> None:
        css = typography.pdf_css(WARM)
        assert f"h1 {{ font-size: {typography.PDF_HEADING_PT[1]}pt" in css
        assert f"color: #{WARM.accent}" in css
        body = css.split("\n")[0]
        assert WARM.accent not in body and f"color: #{typography.INK}" in body


class TestPowerPoint:
    def test_a_toned_divider_opens_on_its_accent_with_readable_words(self) -> None:
        data = render_document(DocumentType.PPTX, _deck("warm"), _CONTEXT)
        presentation = pptx.Presentation(io.BytesIO(data))
        divider = presentation.slides[1]
        assert str(divider.background.fill.fore_color.rgb) == WARM.accent
        title_runs = [run for p in divider.shapes.title.text_frame.paragraphs for run in p.runs]
        assert str(title_runs[0].font.color.rgb) == typography.label_on(WARM.accent)

    def test_its_chart_takes_the_tone_s_first_colour_and_its_theme_the_series(self) -> None:
        data = render_document(DocumentType.PPTX, _deck("warm"), _CONTEXT)
        with zipfile.ZipFile(io.BytesIO(data)) as package:
            chart = next(
                package.read(name).decode("utf-8")
                for name in package.namelist()
                if name.startswith("ppt/charts/chart")
            )
            theme = package.read("ppt/theme/theme1.xml")
        assert f'<a:srgbClr val="{WARM.series[0]}"/>' in chart
        assert _theme_accents(theme) == list(WARM.series)

    def test_a_deck_without_a_tone_keeps_its_plain_divider(self) -> None:
        """Read in the XML: python-pptx's ``background.fill`` creates what it reads."""
        data = render_document(DocumentType.PPTX, _deck(""), _CONTEXT)
        with zipfile.ZipFile(io.BytesIO(data)) as package:
            divider = package.read("ppt/slides/slide2.xml").decode("utf-8")
            theme = package.read("ppt/theme/theme1.xml")
        assert "<p:bg>" not in divider
        assert _theme_accents(theme) != list(typography.NEUTRAL_SERIES)


class TestExcel:
    def test_a_toned_workbook_lays_its_header_on_the_wash(self) -> None:
        data = render_document(DocumentType.XLSX, _sheet("warm"), _CONTEXT)
        sheet = openpyxl.load_workbook(io.BytesIO(data)).active
        assert sheet["A1"].fill.fgColor.rgb.upper().endswith(WARM.wash)

    def test_its_chart_takes_the_tone_s_series(self) -> None:
        data = render_document(DocumentType.XLSX, _sheet("warm"), _CONTEXT)
        with zipfile.ZipFile(io.BytesIO(data)) as package:
            chart = package.read("xl/charts/chart1.xml").decode("utf-8")
        assert chart.index(WARM.series[0]) < chart.index(WARM.series[1])

    def test_a_workbook_without_a_tone_keeps_its_plain_header(self) -> None:
        data = render_document(DocumentType.XLSX, _sheet(""), _CONTEXT)
        sheet = openpyxl.load_workbook(io.BytesIO(data)).active
        assert sheet["A1"].fill.fill_type is None


class TestMinutesStayAsTheyWere:
    def test_a_report_without_a_tone_keeps_the_grey_band_of_before_tones(self) -> None:
        """No tone means the neutral palette, whose every role is the old grey."""
        plain = _report("")
        neutral_docx = render_document(DocumentType.DOCX, plain, _CONTEXT)
        styles = docx.Document(io.BytesIO(neutral_docx)).styles
        callout = styles["Callout"]
        shading = callout.element.xpath(".//w:shd")[0]
        fill = shading.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}fill")
        assert fill.upper() == typography.BAND


class TestTheDividerSNumberReads:
    def test_the_slide_number_takes_the_divider_s_ink(self) -> None:
        data = render_document(DocumentType.PPTX, _deck("institutional"), _CONTEXT)
        with zipfile.ZipFile(io.BytesIO(data)) as package:
            divider = package.read("ppt/slides/slide2.xml").decode("utf-8")
        accent = typography.PALETTES["institutional"].accent
        assert accent is not None
        ink = typography.label_on(accent)
        field = divider[divider.index('type="slidenum"') :]
        assert f'<a:srgbClr val="{ink}"/>' in field[: field.index("</a:fld>")]
