"""
Unit tests for RAG Spaces document processing pipeline.

Tests text extraction functions (plain, PDF, DOCX), the extract_text
dispatcher, and the async process_document background task with mocked
DB sessions, embeddings, and metrics.

Phase: evolution — RAG Spaces (User Knowledge Documents)
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.rag_spaces.models import RAGDocumentStatus
from src.domains.rag_spaces.processing import (
    EMBEDDING_BATCH_SIZE,
    _odf_extract_text,
    extract_text,
    extract_text_csv,
    extract_text_epub,
    extract_text_html,
    extract_text_json,
    extract_text_odp,
    extract_text_ods,
    extract_text_odt,
    extract_text_plain,
    extract_text_pptx,
    extract_text_rtf,
    extract_text_xlsx,
    extract_text_xml,
    process_document,
)

# ============================================================================
# Text Extraction — Plain / Markdown
# ============================================================================


class TestExtractTextPlain:
    """Tests for extract_text_plain (UTF-8 text/markdown files)."""

    @pytest.mark.unit
    def test_reads_utf8_text(self, tmp_path: Path) -> None:
        """Plain text file is read with UTF-8 encoding."""
        file = tmp_path / "note.txt"
        file.write_text("Hello, world!", encoding="utf-8")

        result = extract_text_plain(file)

        assert result == "Hello, world!"

    @pytest.mark.unit
    def test_handles_unicode_characters(self, tmp_path: Path) -> None:
        """Unicode characters (accents, CJK) are preserved."""
        content = "Resume: cafe\u0301 \u2014 \u4f60\u597d \u2014 \u00fc\u00f6\u00e4"
        file = tmp_path / "unicode.md"
        file.write_text(content, encoding="utf-8")

        result = extract_text_plain(file)

        assert result == content

    @pytest.mark.unit
    def test_empty_file_returns_empty_string(self, tmp_path: Path) -> None:
        """An empty file returns an empty string."""
        file = tmp_path / "empty.txt"
        file.write_text("", encoding="utf-8")

        result = extract_text_plain(file)

        assert result == ""


# ============================================================================
# Text Extraction — PDF
# ============================================================================


class TestExtractTextPdf:
    """Tests for extract_text_pdf (PyMuPDF / fitz)."""

    @pytest.mark.unit
    def test_extracts_text_from_pdf(self, tmp_path: Path) -> None:
        """PDF text extraction returns joined page text."""
        mock_page_1 = MagicMock()
        mock_page_1.get_text.return_value = "Page one content."
        mock_page_2 = MagicMock()
        mock_page_2.get_text.return_value = "Page two content."

        mock_doc = MagicMock()
        mock_doc.__enter__ = MagicMock(return_value=mock_doc)
        mock_doc.__exit__ = MagicMock(return_value=False)
        mock_doc.__iter__ = MagicMock(return_value=iter([mock_page_1, mock_page_2]))

        mock_fitz = MagicMock()
        mock_fitz.open.return_value = mock_doc

        with patch.dict(sys.modules, {"fitz": mock_fitz}):
            from src.domains.rag_spaces.processing import extract_text_pdf

            result = extract_text_pdf(tmp_path / "dummy.pdf")

        assert result == "Page one content.\nPage two content."

    @pytest.mark.unit
    def test_empty_pdf_returns_empty_string(self, tmp_path: Path) -> None:
        """A PDF with no pages returns an empty string."""
        mock_doc = MagicMock()
        mock_doc.__enter__ = MagicMock(return_value=mock_doc)
        mock_doc.__exit__ = MagicMock(return_value=False)
        mock_doc.__iter__ = MagicMock(return_value=iter([]))

        mock_fitz = MagicMock()
        mock_fitz.open.return_value = mock_doc

        with patch.dict(sys.modules, {"fitz": mock_fitz}):
            from src.domains.rag_spaces.processing import extract_text_pdf

            result = extract_text_pdf(tmp_path / "empty.pdf")

        assert result == ""


# ============================================================================
# Text Extraction — DOCX
# ============================================================================


class TestExtractTextDocx:
    """Tests for extract_text_docx (python-docx)."""

    @pytest.mark.unit
    def test_extracts_paragraphs_from_docx(self, tmp_path: Path) -> None:
        """DOCX extraction joins non-empty paragraphs with newlines."""
        mock_para_1 = MagicMock()
        mock_para_1.text = "First paragraph."
        mock_para_2 = MagicMock()
        mock_para_2.text = ""
        mock_para_3 = MagicMock()
        mock_para_3.text = "Third paragraph."

        mock_document = MagicMock()
        mock_document.paragraphs = [mock_para_1, mock_para_2, mock_para_3]

        mock_docx_module = MagicMock()
        mock_docx_module.Document.return_value = mock_document

        with patch.dict(sys.modules, {"docx": mock_docx_module}):
            from src.domains.rag_spaces.processing import extract_text_docx

            result = extract_text_docx(tmp_path / "test.docx")

        assert result == "First paragraph.\nThird paragraph."

    @pytest.mark.unit
    def test_whitespace_only_paragraphs_are_skipped(self, tmp_path: Path) -> None:
        """Paragraphs with only whitespace are excluded."""
        mock_para = MagicMock()
        mock_para.text = "   "

        mock_document = MagicMock()
        mock_document.paragraphs = [mock_para]

        mock_docx_module = MagicMock()
        mock_docx_module.Document.return_value = mock_document

        with patch.dict(sys.modules, {"docx": mock_docx_module}):
            from src.domains.rag_spaces.processing import extract_text_docx

            result = extract_text_docx(tmp_path / "ws.docx")

        assert result == ""


# ============================================================================
# Text Extraction — PPTX
# ============================================================================


class TestExtractTextPptx:
    """Tests for extract_text_pptx (python-pptx)."""

    @pytest.mark.unit
    def test_extracts_text_from_slides(self, tmp_path: Path) -> None:
        """PPTX extraction collects text frames, tables, and notes."""
        # Build a mock paragraph inside a text frame
        mock_para = MagicMock()
        mock_para.text = "Slide title"

        mock_text_frame = MagicMock()
        mock_text_frame.paragraphs = [mock_para]

        mock_shape_tf = MagicMock()
        mock_shape_tf.has_text_frame = True
        mock_shape_tf.has_table = False
        mock_shape_tf.text_frame = mock_text_frame

        # Build a mock table shape
        mock_cell_1 = MagicMock()
        mock_cell_1.text.strip.return_value = "A1"
        mock_cell_1.text = "A1"
        mock_cell_2 = MagicMock()
        mock_cell_2.text.strip.return_value = "B1"
        mock_cell_2.text = "B1"
        mock_row = MagicMock()
        mock_row.cells = [mock_cell_1, mock_cell_2]

        mock_shape_tbl = MagicMock()
        mock_shape_tbl.has_text_frame = False
        mock_shape_tbl.has_table = True
        mock_shape_tbl.table.rows = [mock_row]

        # Build a mock slide with notes
        mock_notes_tf = MagicMock()
        mock_notes_tf.text.strip.return_value = "Speaker notes"
        mock_notes_tf.text = "Speaker notes"
        mock_notes_slide = MagicMock()
        mock_notes_slide.notes_text_frame = mock_notes_tf

        mock_slide = MagicMock()
        mock_slide.shapes = [mock_shape_tf, mock_shape_tbl]
        mock_slide.has_notes_slide = True
        mock_slide.notes_slide = mock_notes_slide

        mock_prs = MagicMock()
        mock_prs.slides = [mock_slide]

        mock_pptx = MagicMock()
        mock_pptx.Presentation.return_value = mock_prs

        with patch.dict(sys.modules, {"pptx": mock_pptx}):
            result = extract_text_pptx(tmp_path / "deck.pptx")

        assert "Slide title" in result
        assert "A1\tB1" in result
        assert "Speaker notes" in result

    @pytest.mark.unit
    def test_empty_presentation(self, tmp_path: Path) -> None:
        """A presentation with no slides returns an empty string."""
        mock_prs = MagicMock()
        mock_prs.slides = []

        mock_pptx = MagicMock()
        mock_pptx.Presentation.return_value = mock_prs

        with patch.dict(sys.modules, {"pptx": mock_pptx}):
            result = extract_text_pptx(tmp_path / "empty.pptx")

        assert result == ""


# ============================================================================
# Text Extraction — XLSX
# ============================================================================


class TestExtractTextXlsx:
    """Tests for extract_text_xlsx (openpyxl)."""

    @pytest.mark.unit
    def test_multi_sheet_extraction(self, tmp_path: Path) -> None:
        """XLSX extraction includes [SheetName] headers and cell values."""
        mock_sheet1 = MagicMock()
        mock_sheet1.title = "Sales"
        mock_sheet1.iter_rows.return_value = [("Product", "Price"), ("Widget", 9.99)]

        mock_sheet2 = MagicMock()
        mock_sheet2.title = "Expenses"
        mock_sheet2.iter_rows.return_value = [("Item", "Cost"), ("Rent", 1000)]

        mock_wb = MagicMock()
        mock_wb.worksheets = [mock_sheet1, mock_sheet2]

        mock_openpyxl = MagicMock()
        mock_openpyxl.load_workbook.return_value = mock_wb

        with patch.dict(sys.modules, {"openpyxl": mock_openpyxl}):
            result = extract_text_xlsx(tmp_path / "data.xlsx")

        assert "[Sales]" in result
        assert "[Expenses]" in result
        assert "Product\tPrice" in result
        assert "Widget\t9.99" in result

    @pytest.mark.unit
    def test_empty_cells_handled(self, tmp_path: Path) -> None:
        """Rows with only None cells are excluded."""
        mock_sheet = MagicMock()
        mock_sheet.title = "Empty"
        mock_sheet.iter_rows.return_value = [(None, None, None)]

        mock_wb = MagicMock()
        mock_wb.worksheets = [mock_sheet]

        mock_openpyxl = MagicMock()
        mock_openpyxl.load_workbook.return_value = mock_wb

        with patch.dict(sys.modules, {"openpyxl": mock_openpyxl}):
            result = extract_text_xlsx(tmp_path / "empty.xlsx")

        assert result == ""


# ============================================================================
# Text Extraction — CSV
# ============================================================================


class TestExtractTextCsv:
    """Tests for extract_text_csv (stdlib csv)."""

    @pytest.mark.unit
    def test_standard_csv(self, tmp_path: Path) -> None:
        """Standard CSV rows are joined as tab-separated lines."""
        file = tmp_path / "data.csv"
        file.write_text("Name,Age\nAlice,30\nBob,25\n", encoding="utf-8")

        result = extract_text_csv(file)

        assert "Name\tAge" in result
        assert "Alice\t30" in result
        assert "Bob\t25" in result

    @pytest.mark.unit
    def test_empty_rows_filtered(self, tmp_path: Path) -> None:
        """Rows containing only empty cells are excluded."""
        file = tmp_path / "sparse.csv"
        file.write_text("a,b\n,,\nc,d\n", encoding="utf-8")

        result = extract_text_csv(file)

        lines = [line for line in result.split("\n") if line.strip()]
        assert len(lines) == 2


# ============================================================================
# Text Extraction — RTF
# ============================================================================


class TestExtractTextRtf:
    """Tests for extract_text_rtf (striprtf)."""

    @pytest.mark.unit
    def test_rtf_to_text_conversion(self, tmp_path: Path) -> None:
        """RTF content is converted to plain text via striprtf."""
        file = tmp_path / "doc.rtf"
        file.write_text("{\\rtf1 Hello RTF}", encoding="utf-8")

        mock_striprtf_module = MagicMock()
        mock_rtf_to_text = MagicMock(return_value="Hello RTF")
        mock_striprtf_module.rtf_to_text = mock_rtf_to_text

        with patch.dict(
            sys.modules, {"striprtf": MagicMock(), "striprtf.striprtf": mock_striprtf_module}
        ):
            result = extract_text_rtf(file)

        assert result == "Hello RTF"
        mock_rtf_to_text.assert_called_once()


# ============================================================================
# Text Extraction — HTML
# ============================================================================


class TestExtractTextHtml:
    """Tests for extract_text_html (markdownify)."""

    @pytest.mark.unit
    def test_html_to_markdown(self, tmp_path: Path) -> None:
        """HTML content is converted to markdown text."""
        file = tmp_path / "page.html"
        file.write_text(
            "<html><body><h1>Title</h1><p>Hello world</p></body></html>",
            encoding="utf-8",
        )

        result = extract_text_html(file)

        # markdownify should produce markdown heading and paragraph text
        assert "Title" in result
        assert "Hello world" in result


# ============================================================================
# Text Extraction — ODF helper
# ============================================================================


class TestOdfExtractText:
    """Tests for the _odf_extract_text recursive helper."""

    @pytest.mark.unit
    def test_text_node_returns_data(self) -> None:
        """A node with nodeType==3 returns its data attribute."""
        node = MagicMock()
        node.nodeType = 3
        node.data = "leaf text"

        result = _odf_extract_text(node)

        assert result == "leaf text"

    @pytest.mark.unit
    def test_element_node_with_children(self) -> None:
        """An element node (nodeType==1) concatenates text from children."""
        child_1 = MagicMock()
        child_1.nodeType = 3
        child_1.data = "Hello "

        child_2 = MagicMock()
        child_2.nodeType = 3
        child_2.data = "World"

        parent = MagicMock()
        parent.nodeType = 1
        parent.childNodes = [child_1, child_2]

        result = _odf_extract_text(parent)

        assert result == "Hello World"


# ============================================================================
# Text Extraction — ODT
# ============================================================================


class TestExtractTextOdt:
    """Tests for extract_text_odt (odf.opendocument)."""

    @pytest.mark.unit
    def test_paragraph_extraction(self, tmp_path: Path) -> None:
        """ODT paragraphs are extracted and joined with newlines."""
        # Build mock paragraph nodes
        mock_text_node_1 = MagicMock()
        mock_text_node_1.nodeType = 3
        mock_text_node_1.data = "First paragraph"

        mock_para_1 = MagicMock()
        mock_para_1.nodeType = 1
        mock_para_1.childNodes = [mock_text_node_1]

        mock_text_node_2 = MagicMock()
        mock_text_node_2.nodeType = 3
        mock_text_node_2.data = "Second paragraph"

        mock_para_2 = MagicMock()
        mock_para_2.nodeType = 1
        mock_para_2.childNodes = [mock_text_node_2]

        mock_doc = MagicMock()
        mock_doc.getElementsByType.return_value = [mock_para_1, mock_para_2]

        mock_odf_text = MagicMock()
        mock_odf_load = MagicMock(return_value=mock_doc)

        mock_odf_opendoc = MagicMock()
        mock_odf_opendoc.load = mock_odf_load

        with patch.dict(
            sys.modules,
            {
                "odf": MagicMock(),
                "odf.text": mock_odf_text,
                "odf.opendocument": mock_odf_opendoc,
            },
        ):
            result = extract_text_odt(tmp_path / "doc.odt")

        assert "First paragraph" in result
        assert "Second paragraph" in result

    @pytest.mark.unit
    def test_empty_odt(self, tmp_path: Path) -> None:
        """An ODT with no paragraphs returns an empty string."""
        mock_doc = MagicMock()
        mock_doc.getElementsByType.return_value = []

        mock_odf_opendoc = MagicMock()
        mock_odf_opendoc.load.return_value = mock_doc

        with patch.dict(
            sys.modules,
            {
                "odf": MagicMock(),
                "odf.text": MagicMock(),
                "odf.opendocument": mock_odf_opendoc,
            },
        ):
            result = extract_text_odt(tmp_path / "empty.odt")

        assert result == ""


# ============================================================================
# Text Extraction — ODS
# ============================================================================


class TestExtractTextOds:
    """Tests for extract_text_ods (odf.opendocument)."""

    @pytest.mark.unit
    def test_table_cell_extraction(self, tmp_path: Path) -> None:
        """ODS tables are extracted with [SheetName] headers."""
        # Build a mock cell with a P element containing text
        mock_text_node = MagicMock()
        mock_text_node.nodeType = 3
        mock_text_node.data = "CellValue"

        mock_p = MagicMock()
        mock_p.nodeType = 1
        mock_p.childNodes = [mock_text_node]

        mock_cell = MagicMock()
        mock_cell.getElementsByType.return_value = [mock_p]

        mock_row = MagicMock()
        mock_row.getElementsByType.return_value = [mock_cell]

        mock_table = MagicMock()
        mock_table.getAttribute.return_value = "Budget"
        mock_table.getElementsByType.side_effect = lambda cls: {
            "TableRow": [mock_row],
        }.get(cls.__name__, [mock_row])

        mock_doc = MagicMock()

        # getElementsByType is called for Table, then TableRow, then TableCell, then P
        # We use side_effect keyed on the type class
        mock_odf_table = MagicMock()
        mock_odf_p = MagicMock()

        def get_elements_side_effect(cls):
            if cls is mock_odf_table.Table:
                return [mock_table]
            return []

        mock_doc.getElementsByType.side_effect = lambda cls: [mock_table]
        mock_table.getElementsByType.side_effect = lambda cls: [mock_row]
        mock_row.getElementsByType.side_effect = lambda cls: [mock_cell]
        mock_cell.getElementsByType.side_effect = lambda cls: [mock_p]

        mock_odf_opendoc = MagicMock()
        mock_odf_opendoc.load.return_value = mock_doc

        with patch.dict(
            sys.modules,
            {
                "odf": MagicMock(),
                "odf.opendocument": mock_odf_opendoc,
                "odf.table": mock_odf_table,
                "odf.text": mock_odf_p,
            },
        ):
            result = extract_text_ods(tmp_path / "data.ods")

        assert "[Budget]" in result
        assert "CellValue" in result


# ============================================================================
# Text Extraction — ODP
# ============================================================================


class TestExtractTextOdp:
    """Tests for extract_text_odp (odf.opendocument)."""

    @pytest.mark.unit
    def test_slide_frame_extraction(self, tmp_path: Path) -> None:
        """ODP slides extract text from frames."""
        mock_text_node = MagicMock()
        mock_text_node.nodeType = 3
        mock_text_node.data = "Slide content"

        mock_p = MagicMock()
        mock_p.nodeType = 1
        mock_p.childNodes = [mock_text_node]

        mock_frame = MagicMock()
        mock_frame.getElementsByType.return_value = [mock_p]

        mock_page = MagicMock()
        mock_page.getElementsByType.return_value = [mock_frame]

        mock_doc = MagicMock()
        mock_doc.getElementsByType.return_value = [mock_page]

        mock_odf_draw = MagicMock()
        mock_odf_opendoc = MagicMock()
        mock_odf_opendoc.load.return_value = mock_doc
        mock_odf_text = MagicMock()

        with patch.dict(
            sys.modules,
            {
                "odf": MagicMock(),
                "odf.draw": mock_odf_draw,
                "odf.opendocument": mock_odf_opendoc,
                "odf.text": mock_odf_text,
            },
        ):
            result = extract_text_odp(tmp_path / "slides.odp")

        assert "Slide content" in result

    @pytest.mark.unit
    def test_empty_odp(self, tmp_path: Path) -> None:
        """An ODP with no pages returns an empty string."""
        mock_doc = MagicMock()
        mock_doc.getElementsByType.return_value = []

        mock_odf_opendoc = MagicMock()
        mock_odf_opendoc.load.return_value = mock_doc

        with patch.dict(
            sys.modules,
            {
                "odf": MagicMock(),
                "odf.draw": MagicMock(),
                "odf.opendocument": mock_odf_opendoc,
                "odf.text": MagicMock(),
            },
        ):
            result = extract_text_odp(tmp_path / "empty.odp")

        assert result == ""


# ============================================================================
# Text Extraction — EPUB
# ============================================================================


class TestExtractTextEpub:
    """Tests for extract_text_epub (ebooklib + markdownify)."""

    @pytest.mark.unit
    def test_spine_order_extraction(self, tmp_path: Path) -> None:
        """EPUB chapters are extracted in spine order."""
        mock_item_1 = MagicMock()
        mock_item_1.get_type.return_value = 9  # ebooklib.ITEM_DOCUMENT
        mock_item_1.get_content.return_value = b"<h1>Chapter 1</h1><p>Content one</p>"

        mock_item_2 = MagicMock()
        mock_item_2.get_type.return_value = 9
        mock_item_2.get_content.return_value = b"<h1>Chapter 2</h1><p>Content two</p>"

        mock_book = MagicMock()
        mock_book.spine = [("ch1", True), ("ch2", True)]
        mock_book.get_item_with_id.side_effect = lambda item_id: {
            "ch1": mock_item_1,
            "ch2": mock_item_2,
        }.get(item_id)

        mock_ebooklib = MagicMock()
        mock_ebooklib.ITEM_DOCUMENT = 9

        mock_epub = MagicMock()
        mock_epub.read_epub.return_value = mock_book

        mock_ebooklib.epub = mock_epub

        with patch.dict(
            sys.modules,
            {
                "ebooklib": mock_ebooklib,
                "ebooklib.epub": mock_epub,
            },
        ):
            result = extract_text_epub(tmp_path / "book.epub")

        assert "Chapter 1" in result
        assert "Chapter 2" in result
        assert "Content one" in result
        assert "Content two" in result

    @pytest.mark.unit
    def test_warnings_are_suppressed(self, tmp_path: Path) -> None:
        """EPUB reading suppresses warnings via catch_warnings."""
        mock_book = MagicMock()
        mock_book.spine = []

        mock_ebooklib = MagicMock()
        mock_ebooklib.ITEM_DOCUMENT = 9

        mock_epub = MagicMock()
        mock_epub.read_epub.return_value = mock_book
        mock_ebooklib.epub = mock_epub

        with patch.dict(
            sys.modules,
            {
                "ebooklib": mock_ebooklib,
                "ebooklib.epub": mock_epub,
            },
        ):
            with patch("warnings.catch_warnings") as mock_catch:
                mock_catch.return_value.__enter__ = MagicMock()
                mock_catch.return_value.__exit__ = MagicMock(return_value=False)

                result = extract_text_epub(tmp_path / "book.epub")

                mock_catch.assert_called_once()

        assert result == ""


# ============================================================================
# Text Extraction — JSON
# ============================================================================


class TestExtractTextJson:
    """Tests for extract_text_json (stdlib json)."""

    @pytest.mark.unit
    def test_valid_json_pretty_printed(self, tmp_path: Path) -> None:
        """Valid JSON is reformatted with 2-space indentation."""
        file = tmp_path / "data.json"
        file.write_text('{"name":"Alice","age":30}', encoding="utf-8")

        result = extract_text_json(file)

        assert '"name": "Alice"' in result
        assert '"age": 30' in result
        # Verify indentation
        assert "  " in result

    @pytest.mark.unit
    def test_malformed_json_falls_back_to_raw(self, tmp_path: Path) -> None:
        """Malformed JSON returns raw file content."""
        raw = "{invalid json content"
        file = tmp_path / "bad.json"
        file.write_text(raw, encoding="utf-8")

        result = extract_text_json(file)

        assert result == raw


# ============================================================================
# Text Extraction — XML
# ============================================================================


class TestExtractTextXml:
    """Tests for extract_text_xml (defusedxml)."""

    @pytest.mark.unit
    def test_valid_xml_formatted(self, tmp_path: Path) -> None:
        """Valid XML is parsed and formatted with indentation."""
        import xml.etree.ElementTree as ET

        file = tmp_path / "data.xml"
        file.write_text(
            '<?xml version="1.0"?><root><item>Hello</item></root>',
            encoding="utf-8",
        )

        real_tree = ET.ElementTree(ET.fromstring("<root><item>Hello</item></root>"))

        mock_defused = MagicMock()
        mock_defused.parse.return_value = real_tree

        mock_defusedxml_parent = MagicMock()
        mock_defusedxml_parent.ElementTree = mock_defused

        with patch.dict(
            sys.modules,
            {
                "defusedxml": mock_defusedxml_parent,
                "defusedxml.ElementTree": mock_defused,
            },
        ):
            # Re-import to pick up the mocked defusedxml

            import src.domains.rag_spaces.processing as proc_mod

            result = proc_mod.extract_text_xml(file)

        assert "<root>" in result
        assert "Hello" in result

    @pytest.mark.unit
    def test_malformed_xml_falls_back_to_raw(self, tmp_path: Path) -> None:
        """Malformed XML returns raw file content."""
        import xml.etree.ElementTree as ET

        raw = "<unclosed>broken xml"
        file = tmp_path / "bad.xml"
        file.write_text(raw, encoding="utf-8")

        mock_defused = MagicMock()
        mock_defused.parse.side_effect = ET.ParseError("not well-formed")

        mock_defusedxml_parent = MagicMock()
        mock_defusedxml_parent.ElementTree = mock_defused

        with patch.dict(
            sys.modules,
            {
                "defusedxml": mock_defusedxml_parent,
                "defusedxml.ElementTree": mock_defused,
            },
        ):
            result = extract_text_xml(file)

        assert result == raw


# ============================================================================
# extract_text dispatcher
# ============================================================================


class TestExtractText:
    """Tests for the extract_text dispatcher function."""

    @pytest.mark.unit
    def test_dispatches_plain_text(self, tmp_path: Path) -> None:
        """text/plain MIME type dispatches to extract_text_plain."""
        file = tmp_path / "note.txt"
        file.write_text("plain content", encoding="utf-8")

        result = extract_text(file, "text/plain")

        assert result == "plain content"

    @pytest.mark.unit
    def test_dispatches_markdown(self, tmp_path: Path) -> None:
        """text/markdown MIME type dispatches to extract_text_plain."""
        file = tmp_path / "readme.md"
        file.write_text("# Title\n\nBody", encoding="utf-8")

        result = extract_text(file, "text/markdown")

        assert result == "# Title\n\nBody"

    @pytest.mark.unit
    def test_raises_for_unsupported_content_type(self, tmp_path: Path) -> None:
        """Unsupported MIME type raises ValueError."""
        file = tmp_path / "image.png"
        file.write_bytes(b"\x89PNG")

        with pytest.raises(ValueError, match="Unsupported content type"):
            extract_text(file, "image/png")

    @pytest.mark.unit
    def test_dispatches_pdf(self, tmp_path: Path) -> None:
        """application/pdf dispatches to extract_text_pdf."""
        with patch(
            "src.domains.rag_spaces.processing.extract_text_pdf",
            return_value="pdf content",
        ) as mock_pdf:
            result = extract_text(tmp_path / "doc.pdf", "application/pdf")

        assert result == "pdf content"
        mock_pdf.assert_called_once()

    @pytest.mark.unit
    def test_dispatches_docx(self, tmp_path: Path) -> None:
        """DOCX MIME type dispatches to extract_text_docx."""
        docx_mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        with patch(
            "src.domains.rag_spaces.processing.extract_text_docx",
            return_value="docx content",
        ) as mock_docx:
            result = extract_text(tmp_path / "doc.docx", docx_mime)

        assert result == "docx content"
        mock_docx.assert_called_once()

    @pytest.mark.unit
    def test_dispatches_pptx(self, tmp_path: Path) -> None:
        """PPTX MIME type dispatches to extract_text_pptx."""
        pptx_mime = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
        with patch(
            "src.domains.rag_spaces.processing.extract_text_pptx",
            return_value="pptx content",
        ) as mock_pptx:
            result = extract_text(tmp_path / "deck.pptx", pptx_mime)

        assert result == "pptx content"
        mock_pptx.assert_called_once()

    @pytest.mark.unit
    def test_dispatches_xlsx(self, tmp_path: Path) -> None:
        """XLSX MIME type dispatches to extract_text_xlsx."""
        xlsx_mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        with patch(
            "src.domains.rag_spaces.processing.extract_text_xlsx",
            return_value="xlsx content",
        ) as mock_xlsx:
            result = extract_text(tmp_path / "data.xlsx", xlsx_mime)

        assert result == "xlsx content"
        mock_xlsx.assert_called_once()

    @pytest.mark.unit
    def test_dispatches_csv(self, tmp_path: Path) -> None:
        """text/csv dispatches to extract_text_csv."""
        file = tmp_path / "data.csv"
        file.write_text("a,b\n1,2\n", encoding="utf-8")

        with patch(
            "src.domains.rag_spaces.processing.extract_text_csv",
            return_value="csv content",
        ) as mock_csv:
            result = extract_text(file, "text/csv")

        assert result == "csv content"
        mock_csv.assert_called_once()

    @pytest.mark.unit
    def test_dispatches_rtf(self, tmp_path: Path) -> None:
        """application/rtf dispatches to extract_text_rtf."""
        with patch(
            "src.domains.rag_spaces.processing.extract_text_rtf",
            return_value="rtf content",
        ) as mock_rtf:
            result = extract_text(tmp_path / "doc.rtf", "application/rtf")

        assert result == "rtf content"
        mock_rtf.assert_called_once()

    @pytest.mark.unit
    def test_dispatches_html(self, tmp_path: Path) -> None:
        """text/html dispatches to extract_text_html."""
        with patch(
            "src.domains.rag_spaces.processing.extract_text_html",
            return_value="html content",
        ) as mock_html:
            result = extract_text(tmp_path / "page.html", "text/html")

        assert result == "html content"
        mock_html.assert_called_once()

    @pytest.mark.unit
    def test_dispatches_odt(self, tmp_path: Path) -> None:
        """application/vnd.oasis.opendocument.text dispatches to extract_text_odt."""
        with patch(
            "src.domains.rag_spaces.processing.extract_text_odt",
            return_value="odt content",
        ) as mock_odt:
            result = extract_text(
                tmp_path / "doc.odt",
                "application/vnd.oasis.opendocument.text",
            )

        assert result == "odt content"
        mock_odt.assert_called_once()

    @pytest.mark.unit
    def test_dispatches_ods(self, tmp_path: Path) -> None:
        """application/vnd.oasis.opendocument.spreadsheet dispatches to extract_text_ods."""
        with patch(
            "src.domains.rag_spaces.processing.extract_text_ods",
            return_value="ods content",
        ) as mock_ods:
            result = extract_text(
                tmp_path / "data.ods",
                "application/vnd.oasis.opendocument.spreadsheet",
            )

        assert result == "ods content"
        mock_ods.assert_called_once()

    @pytest.mark.unit
    def test_dispatches_odp(self, tmp_path: Path) -> None:
        """application/vnd.oasis.opendocument.presentation dispatches to extract_text_odp."""
        with patch(
            "src.domains.rag_spaces.processing.extract_text_odp",
            return_value="odp content",
        ) as mock_odp:
            result = extract_text(
                tmp_path / "slides.odp",
                "application/vnd.oasis.opendocument.presentation",
            )

        assert result == "odp content"
        mock_odp.assert_called_once()

    @pytest.mark.unit
    def test_dispatches_epub(self, tmp_path: Path) -> None:
        """application/epub+zip dispatches to extract_text_epub."""
        with patch(
            "src.domains.rag_spaces.processing.extract_text_epub",
            return_value="epub content",
        ) as mock_epub:
            result = extract_text(tmp_path / "book.epub", "application/epub+zip")

        assert result == "epub content"
        mock_epub.assert_called_once()

    @pytest.mark.unit
    def test_dispatches_json(self, tmp_path: Path) -> None:
        """application/json dispatches to extract_text_json."""
        with patch(
            "src.domains.rag_spaces.processing.extract_text_json",
            return_value="json content",
        ) as mock_json:
            result = extract_text(tmp_path / "data.json", "application/json")

        assert result == "json content"
        mock_json.assert_called_once()

    @pytest.mark.unit
    def test_dispatches_xml_application(self, tmp_path: Path) -> None:
        """application/xml dispatches to extract_text_xml."""
        with patch(
            "src.domains.rag_spaces.processing.extract_text_xml",
            return_value="xml content",
        ) as mock_xml:
            result = extract_text(tmp_path / "data.xml", "application/xml")

        assert result == "xml content"
        mock_xml.assert_called_once()

    @pytest.mark.unit
    def test_dispatches_xml_text(self, tmp_path: Path) -> None:
        """text/xml dispatches to extract_text_xml."""
        with patch(
            "src.domains.rag_spaces.processing.extract_text_xml",
            return_value="xml content",
        ) as mock_xml:
            result = extract_text(tmp_path / "data.xml", "text/xml")

        assert result == "xml content"
        mock_xml.assert_called_once()


# ============================================================================
# process_document — async background task
# ============================================================================


class TestProcessDocument:
    """Tests for the async process_document background pipeline."""

    @pytest.fixture
    def ids(self):
        """Generate fresh UUIDs for each test."""
        return {
            "document_id": uuid4(),
            "space_id": uuid4(),
            "user_id": uuid4(),
        }

    @pytest.fixture
    def mock_document(self, ids):
        """Create a mock RAGDocument."""
        doc = MagicMock()
        doc.id = ids["document_id"]
        doc.file_size = 1024
        return doc

    @pytest.fixture
    def mock_db_context(self):
        """Create a mock async context manager for get_db_context."""
        mock_db = AsyncMock()
        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=mock_db)
        ctx.__aexit__ = AsyncMock(return_value=False)
        return ctx, mock_db

    def _patch_processing(self):
        """Return a dict of common patches for process_document tests."""
        return {
            "db_ctx": patch(
                "src.domains.rag_spaces.processing.get_db_context",
            ),
            "embeddings": patch(
                "src.domains.rag_spaces.processing.get_rag_embeddings",
            ),
            "set_ctx": patch(
                "src.domains.rag_spaces.processing.set_embedding_context",
            ),
            "clear_ctx": patch(
                "src.domains.rag_spaces.processing.clear_embedding_context",
            ),
            "settings": patch(
                "src.domains.rag_spaces.processing.settings",
            ),
            "metrics_processed": patch(
                "src.domains.rag_spaces.processing.rag_documents_processed_total",
            ),
            "metrics_duration": patch(
                "src.domains.rag_spaces.processing.rag_document_processing_duration_seconds",
            ),
            "metrics_chunks": patch(
                "src.domains.rag_spaces.processing.rag_document_chunks_total",
            ),
            "metrics_size": patch(
                "src.domains.rag_spaces.processing.rag_document_upload_size_bytes",
            ),
            "metrics_tokens": patch(
                "src.domains.rag_spaces.processing.rag_embedding_tokens_total",
            ),
            "estimate_cost": patch(
                "src.infrastructure.llm.tracked_embeddings.estimate_embedding_cost_sync",
                return_value=0.001,
            ),
            "cached_rate": patch(
                "src.infrastructure.cache.pricing_cache.get_cached_usd_eur_rate",
                return_value=0.92,
            ),
        }

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_file_not_found_marks_error(self, ids, mock_document) -> None:
        """When the uploaded file does not exist on disk, document is marked as error."""
        patches = self._patch_processing()

        mock_db = AsyncMock()
        mock_doc_repo = AsyncMock()
        mock_doc_repo.get_by_id.return_value = mock_document

        with (
            patches["db_ctx"] as mock_get_db,
            patches["set_ctx"],
            patches["clear_ctx"],
            patches["settings"] as mock_settings,
            patches["metrics_processed"],
        ):
            ctx_manager = AsyncMock()
            ctx_manager.__aenter__ = AsyncMock(return_value=mock_db)
            ctx_manager.__aexit__ = AsyncMock(return_value=False)
            mock_get_db.return_value = ctx_manager

            mock_settings.rag_spaces_storage_path = "/nonexistent/storage"

            with (
                patch(
                    "src.domains.rag_spaces.processing.RAGDocumentRepository",
                    return_value=mock_doc_repo,
                ),
                patch(
                    "src.domains.rag_spaces.processing.RAGChunkRepository",
                ),
                patch(
                    "src.domains.rag_spaces.processing._mark_document_error",
                    new_callable=AsyncMock,
                ) as mock_mark_error,
            ):
                await process_document(
                    document_id=ids["document_id"],
                    space_id=ids["space_id"],
                    user_id=ids["user_id"],
                    filename="abc123.txt",
                    original_filename="my_doc.txt",
                    content_type="text/plain",
                )

                mock_mark_error.assert_awaited_once()
                call_args = mock_mark_error.call_args
                assert "File not found" in call_args[0][3]

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_empty_text_marks_error(self, ids, mock_document, tmp_path) -> None:
        """When extracted text is empty/whitespace, document is marked as error."""
        patches = self._patch_processing()

        # Create an actual empty file
        storage_dir = tmp_path / str(ids["user_id"]) / str(ids["space_id"])
        storage_dir.mkdir(parents=True)
        empty_file = storage_dir / "abc123.txt"
        empty_file.write_text("   ", encoding="utf-8")

        mock_db = AsyncMock()
        mock_doc_repo = AsyncMock()
        mock_doc_repo.get_by_id.return_value = mock_document

        with (
            patches["db_ctx"] as mock_get_db,
            patches["set_ctx"],
            patches["clear_ctx"],
            patches["settings"] as mock_settings,
            patches["metrics_processed"],
        ):
            ctx_manager = AsyncMock()
            ctx_manager.__aenter__ = AsyncMock(return_value=mock_db)
            ctx_manager.__aexit__ = AsyncMock(return_value=False)
            mock_get_db.return_value = ctx_manager

            mock_settings.rag_spaces_storage_path = str(tmp_path)

            with (
                patch(
                    "src.domains.rag_spaces.processing.RAGDocumentRepository",
                    return_value=mock_doc_repo,
                ),
                patch(
                    "src.domains.rag_spaces.processing.RAGChunkRepository",
                ),
                patch(
                    "src.domains.rag_spaces.processing._mark_document_error",
                    new_callable=AsyncMock,
                ) as mock_mark_error,
            ):
                await process_document(
                    document_id=ids["document_id"],
                    space_id=ids["space_id"],
                    user_id=ids["user_id"],
                    filename="abc123.txt",
                    original_filename="empty.txt",
                    content_type="text/plain",
                )

                mock_mark_error.assert_awaited_once()
                call_args = mock_mark_error.call_args
                assert "No text content" in call_args[0][3]

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_too_many_chunks_marks_error(self, ids, mock_document, tmp_path) -> None:
        """When chunk count exceeds max_chunks_per_document, document is marked as error."""
        patches = self._patch_processing()

        # Create a file with enough content to produce many chunks
        storage_dir = tmp_path / str(ids["user_id"]) / str(ids["space_id"])
        storage_dir.mkdir(parents=True)
        big_file = storage_dir / "abc123.txt"
        big_file.write_text("word " * 50000, encoding="utf-8")

        mock_db = AsyncMock()
        mock_doc_repo = AsyncMock()
        mock_doc_repo.get_by_id.return_value = mock_document

        with (
            patches["db_ctx"] as mock_get_db,
            patches["set_ctx"],
            patches["clear_ctx"],
            patches["settings"] as mock_settings,
            patches["metrics_processed"],
        ):
            ctx_manager = AsyncMock()
            ctx_manager.__aenter__ = AsyncMock(return_value=mock_db)
            ctx_manager.__aexit__ = AsyncMock(return_value=False)
            mock_get_db.return_value = ctx_manager

            mock_settings.rag_spaces_storage_path = str(tmp_path)
            mock_settings.rag_spaces_chunk_size = 100
            mock_settings.rag_spaces_chunk_overlap = 10
            # Set max chunks very low to trigger the guard
            mock_settings.rag_spaces_max_chunks_per_document = 2

            with (
                patch(
                    "src.domains.rag_spaces.processing.RAGDocumentRepository",
                    return_value=mock_doc_repo,
                ),
                patch(
                    "src.domains.rag_spaces.processing.RAGChunkRepository",
                ),
                patch(
                    "src.domains.rag_spaces.processing._mark_document_error",
                    new_callable=AsyncMock,
                ) as mock_mark_error,
            ):
                await process_document(
                    document_id=ids["document_id"],
                    space_id=ids["space_id"],
                    user_id=ids["user_id"],
                    filename="abc123.txt",
                    original_filename="big.txt",
                    content_type="text/plain",
                )

                mock_mark_error.assert_awaited_once()
                call_args = mock_mark_error.call_args
                assert "exceeding limit" in call_args[0][3]

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_successful_processing(self, ids, mock_document, tmp_path) -> None:
        """Happy path: text extracted, chunks created, embeddings generated, status set to READY."""
        patches = self._patch_processing()

        # Create a small file
        storage_dir = tmp_path / str(ids["user_id"]) / str(ids["space_id"])
        storage_dir.mkdir(parents=True)
        doc_file = storage_dir / "abc123.txt"
        doc_file.write_text(
            "This is paragraph one about artificial intelligence.\n\n"
            "This is paragraph two about machine learning.",
            encoding="utf-8",
        )

        mock_db = AsyncMock()
        mock_doc_repo = AsyncMock()
        mock_doc_repo.get_by_id.return_value = mock_document
        mock_chunk_repo = AsyncMock()
        mock_chunk_repo.bulk_create_chunks.return_value = 2

        mock_embeddings = AsyncMock()
        # Return one vector per chunk (dynamic based on input)
        mock_embeddings.aembed_documents.side_effect = lambda texts: [
            [0.1 * (i + 1)] * 10 for i in range(len(texts))
        ]

        with (
            patches["db_ctx"] as mock_get_db,
            patches["embeddings"] as mock_get_emb,
            patches["set_ctx"],
            patches["clear_ctx"],
            patches["settings"] as mock_settings,
            patches["metrics_processed"],
            patches["metrics_duration"],
            patches["metrics_chunks"],
            patches["metrics_size"],
            patches["metrics_tokens"],
            patches["estimate_cost"],
            patches["cached_rate"],
        ):
            ctx_manager = AsyncMock()
            ctx_manager.__aenter__ = AsyncMock(return_value=mock_db)
            ctx_manager.__aexit__ = AsyncMock(return_value=False)
            mock_get_db.return_value = ctx_manager

            mock_settings.rag_spaces_storage_path = str(tmp_path)
            mock_settings.rag_spaces_chunk_size = 500
            mock_settings.rag_spaces_chunk_overlap = 50
            mock_settings.rag_spaces_max_chunks_per_document = 1000
            mock_settings.rag_spaces_embedding_model = "text-embedding-3-small"

            mock_get_emb.return_value = mock_embeddings

            with (
                patch(
                    "src.domains.rag_spaces.processing.RAGDocumentRepository",
                    return_value=mock_doc_repo,
                ),
                patch(
                    "src.domains.rag_spaces.processing.RAGChunkRepository",
                    return_value=mock_chunk_repo,
                ),
            ):
                await process_document(
                    document_id=ids["document_id"],
                    space_id=ids["space_id"],
                    user_id=ids["user_id"],
                    filename="abc123.txt",
                    original_filename="notes.txt",
                    content_type="text/plain",
                )

            # Verify embeddings were requested
            mock_embeddings.aembed_documents.assert_awaited()

            # Verify chunks were bulk-inserted
            mock_chunk_repo.bulk_create_chunks.assert_awaited_once()
            created_chunks = mock_chunk_repo.bulk_create_chunks.call_args[0][0]
            assert len(created_chunks) > 0

            # Verify document status updated to READY
            mock_doc_repo.update.assert_awaited_once()
            update_data = mock_doc_repo.update.call_args[0][1]
            assert update_data["status"] == RAGDocumentStatus.READY
            assert update_data["error_message"] is None
            assert update_data["chunk_count"] > 0

            # Verify DB commit
            mock_db.commit.assert_awaited()

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_document_not_found_returns_early(self, ids) -> None:
        """When document ID does not exist in DB, function returns without error."""
        patches = self._patch_processing()

        mock_db = AsyncMock()
        mock_doc_repo = AsyncMock()
        mock_doc_repo.get_by_id.return_value = None

        with (
            patches["db_ctx"] as mock_get_db,
            patches["set_ctx"],
            patches["clear_ctx"],
            patches["settings"],
        ):
            ctx_manager = AsyncMock()
            ctx_manager.__aenter__ = AsyncMock(return_value=mock_db)
            ctx_manager.__aexit__ = AsyncMock(return_value=False)
            mock_get_db.return_value = ctx_manager

            with (
                patch(
                    "src.domains.rag_spaces.processing.RAGDocumentRepository",
                    return_value=mock_doc_repo,
                ),
                patch(
                    "src.domains.rag_spaces.processing.RAGChunkRepository",
                ),
            ):
                # Should not raise
                await process_document(
                    document_id=ids["document_id"],
                    space_id=ids["space_id"],
                    user_id=ids["user_id"],
                    filename="abc.txt",
                    original_filename="missing.txt",
                    content_type="text/plain",
                )

            # update should NOT have been called
            mock_doc_repo.update.assert_not_awaited()

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_embedding_context_always_cleared(self, ids, mock_document) -> None:
        """Embedding context is cleared even when processing raises an exception."""
        with (
            patch(
                "src.domains.rag_spaces.processing.get_db_context",
                side_effect=RuntimeError("DB connection failed"),
            ),
            patch(
                "src.domains.rag_spaces.processing.set_embedding_context",
            ),
            patch(
                "src.domains.rag_spaces.processing.clear_embedding_context",
            ) as mock_clear,
            patch("src.domains.rag_spaces.processing.rag_documents_processed_total"),
        ):
            await process_document(
                document_id=ids["document_id"],
                space_id=ids["space_id"],
                user_id=ids["user_id"],
                filename="abc.txt",
                original_filename="crash.txt",
                content_type="text/plain",
            )

            mock_clear.assert_called_once()

    @pytest.mark.unit
    def test_embedding_batch_size_constant(self) -> None:
        """EMBEDDING_BATCH_SIZE is set to the expected value."""
        assert EMBEDDING_BATCH_SIZE == 100
