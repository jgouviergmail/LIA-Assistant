"""PDF renderer: HTML -> Story -> paged PDF; text extraction is the oracle (ADR-226)."""

import fitz
import pytest

from src.domains.document_generation.renderers import RENDERERS, render_document
from src.domains.document_generation.schemas import (
    DocumentType,
    SectionBlock,
    SectionedContent,
    TableSheet,
)


def _content() -> SectionedContent:
    return SectionedContent(
        filename_stem="alsace",
        title="Rapport Alsace",
        blocks=[
            SectionBlock(kind="heading", level=2, text="Villes"),
            SectionBlock(kind="paragraph", text="Texte avec accents éàü & <balise>."),
            SectionBlock(kind="bullets", items=["Strasbourg", "Colmar"]),
            SectionBlock(
                kind="table",
                table=TableSheet(name="V", headers=["ville"], rows=[["Mulhouse"]]),
            ),
        ],
    )


@pytest.mark.unit
class TestPdfRenderer:
    """Round-trip via PyMuPDF extraction — the RAG PDF reader is the oracle."""

    def test_round_trip_text(self) -> None:
        data = render_document(DocumentType.PDF, _content())
        document = fitz.open(stream=data, filetype="pdf")
        text = "".join(page.get_text() for page in document)
        document.close()
        for fragment in (
            "Rapport Alsace",
            "Villes",
            "éàü & <balise>",  # html.escape round-trips literally in extraction
            "Strasbourg",
            "Colmar",
            "Mulhouse",
        ):
            assert fragment in text

    def test_long_content_paginates(self) -> None:
        blocks = [
            SectionBlock(kind="paragraph", text=f"Paragraphe {i} — " + "texte " * 60)
            for i in range(60)
        ]
        content = SectionedContent(filename_stem="long", title="Long", blocks=blocks)
        data = render_document(DocumentType.PDF, content)
        document = fitz.open(stream=data, filetype="pdf")
        assert document.page_count > 1  # the Story loop actually paginates
        document.close()

    def test_requires_sectioned_content(self) -> None:
        from src.domains.document_generation.schemas import TabularContent

        tabular = TabularContent(
            filename_stem="x",
            title="T",
            sheets=[TableSheet(name="S", headers=["a"], rows=[["1"]])],
        )
        with pytest.raises(ValueError, match="SectionedContent"):
            render_document(DocumentType.PDF, tabular)


@pytest.mark.unit
class TestRendererRegistryCompleteness:
    """ADR-085: the registry covers every DocumentType, or the module refuses to import."""

    def test_registry_is_complete(self) -> None:
        assert set(RENDERERS) == set(DocumentType)
