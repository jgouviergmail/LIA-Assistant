"""Office renderers round-trip through their own readers (ADR-226).

The oracles are the same libraries the RAG extractors already embed
(openpyxl / python-docx / python-pptx), so "what we write is what a reader
sees" is asserted, not assumed.
"""

import io

import docx
import pptx
import pytest

from src.domains.document_generation.renderers import render_document
from src.domains.document_generation.schemas import (
    DocumentType,
    SectionBlock,
    SectionedContent,
    Slide,
    SlideContent,
    TableSheet,
)


@pytest.mark.unit
class TestDocxRenderer:
    """docx: every block kind lands where python-docx can read it back."""

    def test_round_trip_blocks(self) -> None:
        content = SectionedContent(
            filename_stem="rapport",
            title="Rapport",
            blocks=[
                SectionBlock(kind="heading", level=2, text="Partie 1"),
                SectionBlock(kind="paragraph", text="Texte accentué éàü."),
                SectionBlock(kind="bullets", items=["un", "deux"]),
                SectionBlock(
                    kind="table",
                    table=TableSheet(name="T", headers=["k"], rows=[["v"]]),
                ),
            ],
        )
        data = render_document(DocumentType.DOCX, content)
        document = docx.Document(io.BytesIO(data))
        texts = [p.text for p in document.paragraphs]
        assert "Rapport" in texts
        assert "Partie 1" in texts
        assert "Texte accentué éàü." in texts
        assert "un" in texts and "deux" in texts
        assert document.tables
        assert document.tables[0].cell(0, 0).text == "k"
        assert document.tables[0].cell(1, 0).text == "v"


@pytest.mark.unit
class TestPptxRenderer:
    """pptx: title slide + one slide per spec, bullets and notes intact."""

    def test_round_trip_slides_and_notes(self) -> None:
        content = SlideContent(
            filename_stem="alsace",
            title="L'Alsace",
            slides=[
                Slide(
                    title="Géographie",
                    bullets=["Rhin", "Vosges"],
                    notes="parler lentement",
                )
            ],
        )
        data = render_document(DocumentType.PPTX, content)
        presentation = pptx.Presentation(io.BytesIO(data))
        assert len(presentation.slides) == 2  # title slide + 1 content slide
        all_text = [
            paragraph.text
            for slide in presentation.slides
            for shape in slide.shapes
            if shape.has_text_frame
            for paragraph in shape.text_frame.paragraphs
        ]
        assert "L'Alsace" in all_text
        assert "Géographie" in all_text
        assert "Rhin" in all_text and "Vosges" in all_text
        notes_slide = presentation.slides[1].notes_slide
        assert "parler lentement" in notes_slide.notes_text_frame.text

    def test_slide_without_bullets_is_valid(self) -> None:
        content = SlideContent(
            filename_stem="x",
            title="T",
            slides=[Slide(title="Vide")],
        )
        data = render_document(DocumentType.PPTX, content)
        presentation = pptx.Presentation(io.BytesIO(data))
        assert len(presentation.slides) == 2
