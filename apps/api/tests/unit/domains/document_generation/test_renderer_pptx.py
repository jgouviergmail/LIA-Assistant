"""pptx: 16:9 landscape, a layout per kind, and nothing overflows (ADR-274)."""

import io

import pptx
import pytest

from src.domains.document_generation.context import RenderContext
from src.domains.document_generation.renderers import render_document
from src.domains.document_generation.renderers.pptx_geometry import EMU_PER_PT
from src.domains.document_generation.schemas import (
    DocumentType,
    SectionBlock,
    SectionedContent,
    Slide,
    SlideColumn,
    SlideContent,
    TableSheet,
)

from .pptx_oracles import assert_nothing_overflows

pytestmark = [pytest.mark.unit]
_CTX = RenderContext(language="en")


def _deck(*slides: Slide, subtitle: str = "") -> pptx.presentation.Presentation:
    content = SlideContent(filename_stem="d", title="Deck", subtitle=subtitle, slides=list(slides))
    return pptx.Presentation(io.BytesIO(render_document(DocumentType.PPTX, content, _CTX)))


def _has_slide_number(slide: pptx.slide.Slide) -> bool:
    return any("slidenum" in shape._element.xml for shape in slide.shapes)


class TestTheDeckIsLandscapeAndComplete:
    def test_slides_are_16_9_landscape(self) -> None:
        """The owner's constraint: a slide is never portrait."""
        presentation = _deck(Slide(title="t", bullets=["a"]))
        width = round(presentation.slide_width / EMU_PER_PT)
        height = round(presentation.slide_height / EMU_PER_PT)
        assert (width, height) == (960, 540)
        assert width > height

    def test_a_layout_per_kind(self) -> None:
        table = TableSheet(name="t", headers=["City", "Pop"], rows=[["A", "1"]])
        presentation = _deck(
            Slide(title="Part", kind="section", subtitle="tag"),
            Slide(title="Content", bullets=["a", "b"]),
            Slide(
                title="A vs B",
                kind="comparison",
                columns=[
                    SlideColumn(heading="A", bullets=["a"]),
                    SlideColumn(heading="B", bullets=["b"]),
                ],
            ),
            Slide(title="Data", kind="table", table=table),
            subtitle="Board",
        )
        assert [slide.slide_layout.name for slide in presentation.slides] == [
            "Title Slide",
            "Section Header",
            "Title and Content",
            "Comparison",
            "Title Only",
        ]
        assert any(shape.has_table for shape in presentation.slides[4].shapes)

    def test_every_slide_but_the_cover_is_numbered(self) -> None:
        presentation = _deck(Slide(title="a", bullets=["x"]), Slide(title="b", bullets=["y"]))
        assert [_has_slide_number(slide) for slide in presentation.slides] == [False, True, True]

    def test_the_cover_carries_subtitle_and_date(self) -> None:
        from datetime import UTC, datetime

        content = SlideContent(
            filename_stem="d", title="Deck", subtitle="For the board", slides=[Slide(title="t")]
        )
        context = RenderContext(
            language="en", generated_at=datetime(2026, 9, 8, tzinfo=UTC), timezone="Europe/Paris"
        )
        presentation = pptx.Presentation(
            io.BytesIO(render_document(DocumentType.PPTX, content, context))
        )
        cover_text = "\n".join(
            shape.text_frame.text for shape in presentation.slides[0].shapes if shape.has_text_frame
        )
        assert "For the board" in cover_text and "2026" in cover_text

    def test_a_cover_with_nothing_to_add_drops_its_placeholder(self) -> None:
        """No "Click to add subtitle" prompt may survive in a delivered deck."""
        presentation = _deck(Slide(title="t", bullets=["a"]))
        texts = [
            shape.text_frame.text for shape in presentation.slides[0].shapes if shape.has_text_frame
        ]
        assert texts == ["Deck"]


class TestNothingOverflows:
    def test_a_dense_slide_that_still_fits_is_not_split_for_nothing(self) -> None:
        """Measured: nine 139-char bullets are 18 lines ≈ 344 pt inside 356 pt."""
        bullets = [
            f"Point {index} — " + "texte assez long pour tester le débordement " * 3
            for index in range(9)
        ]
        presentation = _deck(Slide(title="Dense", bullets=bullets))
        content_slides = [
            slide for slide in presentation.slides if slide.slide_layout.name == "Title and Content"
        ]
        assert len(content_slides) == 1
        assert content_slides[0].shapes.title.text == "Dense"  # no "(1/1)" noise
        assert_nothing_overflows(presentation)

    def test_a_dense_slide_is_split_never_overflowed(self) -> None:
        bullets = [
            f"Point {index} — " + "texte assez long pour tester le débordement " * 6
            for index in range(9)
        ]
        presentation = _deck(Slide(title="Dense", bullets=bullets, notes="say this"))
        content_slides = [
            slide for slide in presentation.slides if slide.slide_layout.name == "Title and Content"
        ]
        assert len(content_slides) >= 2
        assert content_slides[0].shapes.title.text.endswith(f"(1/{len(content_slides)})")
        written = " ".join(
            paragraph.text
            for slide in content_slides
            for paragraph in slide.placeholders[1].text_frame.paragraphs
        )
        assert written.count("Point") == 9  # every bullet survived the split
        assert "say this" in content_slides[0].notes_slide.notes_text_frame.text
        assert_nothing_overflows(presentation)

    def test_a_long_title_shrinks(self) -> None:
        presentation = _deck(
            Slide(
                title="Un titre de diapositive assez long pour tester la casse sur deux lignes",
                bullets=["a"],
            )
        )
        title = presentation.slides[1].shapes.title
        sizes = [
            run.font.size.pt
            for paragraph in title.text_frame.paragraphs
            for run in paragraph.runs
            if run.font.size
        ]
        assert sizes and max(sizes) < 40
        assert_nothing_overflows(presentation)

    def test_a_single_monstrous_bullet_is_cut_at_sentences(self) -> None:
        monster = ". ".join(f"Phrase numéro {i} de la puce" for i in range(200)) + "."
        presentation = _deck(Slide(title="Monster", bullets=[monster]))
        assert_nothing_overflows(presentation)
        written = " ".join(
            paragraph.text
            for slide in presentation.slides
            for shape in slide.shapes
            if shape.has_text_frame and shape != slide.shapes.title
            for paragraph in shape.text_frame.paragraphs
        )
        assert "Phrase numéro 199 de la puce" in written  # nothing was clipped


class TestTablesAndComparisons:
    def test_tables_are_chunked_with_the_header_repeated(self) -> None:
        rows = [[f"City {index}", str(100000 + index)] for index in range(30)]
        presentation = _deck(
            Slide(
                title="Cities",
                kind="table",
                table=TableSheet(name="t", headers=["City", "Population"], rows=rows),
            )
        )
        table_slides = [
            slide for slide in presentation.slides if any(s.has_table for s in slide.shapes)
        ]
        assert len(table_slides) == 3
        assert [slide.shapes.title.text for slide in table_slides] == [
            "Cities (1/3)",
            "Cities (2/3)",
            "Cities (3/3)",
        ]
        for slide in table_slides:
            table = next(shape for shape in slide.shapes if shape.has_table).table
            assert table.cell(0, 0).text == "City"
        assert "{9D7B26C5-4107-4FEC-AEDC-1716B250A1EF}" in table_slides[0]._element.xml

    def test_numeric_table_columns_are_right_aligned(self) -> None:
        from pptx.enum.text import PP_ALIGN

        presentation = _deck(
            Slide(
                title="Cities",
                kind="table",
                table=TableSheet(name="t", headers=["City", "Pop"], rows=[["A", "12"]]),
            )
        )
        table = next(shape for shape in presentation.slides[1].shapes if shape.has_table).table
        assert table.cell(1, 1).text_frame.paragraphs[0].alignment == PP_ALIGN.RIGHT
        assert table.cell(1, 0).text_frame.paragraphs[0].alignment is None

    def test_a_section_opener_does_not_shout(self) -> None:
        presentation = _deck(Slide(title="Part", kind="section", subtitle="tag"))
        assert 'cap="none"' in presentation.slides[1].shapes.title._element.xml

    def test_both_comparison_sides_are_written(self) -> None:
        presentation = _deck(
            Slide(
                title="A vs B",
                kind="comparison",
                columns=[
                    SlideColumn(heading="A", bullets=["a1"]),
                    SlideColumn(heading="B", bullets=["b1"]),
                ],
            )
        )
        texts = {
            shape.text_frame.text for shape in presentation.slides[1].shapes if shape.has_text_frame
        }
        assert {"A", "B", "a1", "b1"} <= texts
        assert_nothing_overflows(presentation)

    def test_inline_emphasis_becomes_runs(self) -> None:
        presentation = _deck(Slide(title="t", bullets=["a **b** c"]))
        runs = [
            run
            for paragraph in presentation.slides[1].placeholders[1].text_frame.paragraphs
            for run in paragraph.runs
        ]
        assert [(run.text, bool(run.font.bold)) for run in runs] == [
            ("a ", False),
            ("b", True),
            (" c", False),
        ]

    def test_requires_slide_content(self) -> None:
        content = SectionedContent(
            filename_stem="x", title="T", blocks=[SectionBlock(kind="paragraph", text="p")]
        )
        with pytest.raises(ValueError, match="SlideContent"):
            render_document(DocumentType.PPTX, content, _CTX)


@pytest.mark.unit
class TestAColumnIsSizedByWidthNotByCharacterCount:
    """Ten ideographs are twice as wide as ten letters: sizing a column by
    ``len`` starves the CJK column, its cells wrap, and the rows grow past the
    height the renderer reserved — where the overflow oracle cannot see them,
    a table being a graphic frame and not a text frame."""

    ZH = "一丁丂七丄丅丆万丈三"

    def test_a_chinese_column_gets_more_width_than_a_latin_one_of_equal_length(self) -> None:
        from src.domains.document_generation.renderers.pptx_tables import _column_weights

        sheet = TableSheet(name="t", headers=["a", "b"], rows=[[self.ZH, "abcdefghij"]])
        chinese, latin = _column_weights(sheet)
        assert chinese > latin
