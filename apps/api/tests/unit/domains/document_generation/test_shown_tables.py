"""A computed table as Word, PDF and PowerPoint draw it (ADR-274 amendment).

The values are written once, in the reader's conventions, by the computation the
workbook caches; every rich renderer then draws a declared number right-aligned
— even once it is text like « 1 200,50 € » — and the totals row in bold.
"""

from __future__ import annotations

import io

import docx
import pptx
import pymupdf
import pytest
from docx.enum.text import WD_ALIGN_PARAGRAPH
from pptx.enum.text import PP_ALIGN

from src.domains.document_generation.context import RenderContext
from src.domains.document_generation.renderers import render_document
from src.domains.document_generation.schemas import (
    ColumnSpec,
    DocumentType,
    SectionBlock,
    SectionedContent,
    Slide,
    SlideContent,
    TableSheet,
)

pytestmark = [pytest.mark.unit]
_CTX = RenderContext(language="fr")


def _sheet() -> TableSheet:
    return TableSheet(
        name="Ventes",
        headers=["Région", "Recettes", "Coûts"],
        rows=[["Nord", "1200.5", "400"], ["Sud", "800", "0"]],
        columns=[
            ColumnSpec(header="Recettes", kind="amount", unit="EUR", total="sum"),
            ColumnSpec(header="Marge", formula="{Recettes} - {Coûts}", kind="amount", unit="EUR"),
        ],
    )


def test_word_draws_the_values_right_aligned_and_the_total_in_bold() -> None:
    content = SectionedContent(
        filename_stem="v", title="V", blocks=[SectionBlock(kind="table", table=_sheet())]
    )
    document = docx.Document(io.BytesIO(render_document(DocumentType.DOCX, content, _CTX)))
    table = document.tables[0]
    assert [cell.text for cell in table.rows[0].cells] == ["Région", "Recettes", "Coûts", "Marge"]
    first = table.rows[1].cells
    assert first[1].text == "1 200,50 €" and first[3].text == "800,50 €"
    assert first[1].paragraphs[0].alignment == WD_ALIGN_PARAGRAPH.RIGHT
    total = table.rows[-1].cells
    assert total[0].text == "Total" and total[1].text == "2 000,50 €"
    assert all(run.bold for run in total[1].paragraphs[0].runs)
    assert not any(run.bold for run in first[1].paragraphs[0].runs)


def test_powerpoint_draws_the_values_right_aligned_and_the_total_in_bold() -> None:
    content = SlideContent(
        filename_stem="v", title="V", slides=[Slide(title="Ventes", kind="table", table=_sheet())]
    )
    deck = pptx.Presentation(io.BytesIO(render_document(DocumentType.PPTX, content, _CTX)))
    table = next(shape.table for shape in deck.slides[1].shapes if shape.has_table)
    total_row = len(table.rows) - 1
    assert table.cell(total_row, 0).text == "Total"
    assert table.cell(1, 1).text_frame.paragraphs[0].alignment == PP_ALIGN.RIGHT
    assert table.cell(total_row, 1).text_frame.paragraphs[0].font.bold
    assert not table.cell(1, 1).text_frame.paragraphs[0].font.bold


def test_the_pdf_writes_the_total_in_bold() -> None:
    content = SectionedContent(
        filename_stem="v", title="V", blocks=[SectionBlock(kind="table", table=_sheet())]
    )
    with pymupdf.open(stream=render_document(DocumentType.PDF, content, _CTX)) as pdf:
        spans = [
            span
            for block in pdf[0].get_text("dict")["blocks"]
            for line in block.get("lines", [])
            for span in line["spans"]
        ]
    total = next(span for span in spans if span["text"].strip() == "Total")
    assert total["flags"] & 16 or "Bold" in total["font"]
    nord = next(span for span in spans if span["text"].strip() == "Nord")
    assert not (nord["flags"] & 16) and "Bold" not in nord["font"]
