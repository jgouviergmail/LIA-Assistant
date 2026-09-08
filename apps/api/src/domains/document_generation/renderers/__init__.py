"""Pure renderers: canonical content -> document bytes (ADR-226, ADR-274).

One module per format; every renderer is a pure function of the NORMALIZED
content and a ``RenderContext``, so it is unit-tested without I/O and the
CPU-bound work is offloaded with ``asyncio.to_thread`` by the CALLER (service
layer). Heavy libraries (openpyxl, python-docx, python-pptx, PyMuPDF) are
imported lazily inside their renderer so importing this package stays cheap.
The registry is completeness-asserted at import (ADR-085).

Renderers never see raw model output: ``render_document`` puts the content in
canonical form first (``normalize``), so no renderer has to ask whether a table
has rows or a comparison has two sides.
"""

from __future__ import annotations

from collections.abc import Callable

from src.domains.document_generation.context import RenderContext, default_render_context
from src.domains.document_generation.normalize import normalize_content
from src.domains.document_generation.renderers.docx import render_docx
from src.domains.document_generation.renderers.pdf import render_pdf
from src.domains.document_generation.renderers.pptx import render_pptx
from src.domains.document_generation.renderers.text import render_csv, render_md, render_txt
from src.domains.document_generation.renderers.xlsx import render_xlsx
from src.domains.document_generation.schemas import DocumentContent, DocumentType

Renderer = Callable[[DocumentContent, RenderContext], bytes]

DOCUMENT_MIME_TYPES: dict[DocumentType, str] = {
    DocumentType.CSV: "text/csv",
    DocumentType.XLSX: ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    DocumentType.DOCX: ("application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    DocumentType.PPTX: (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    ),
    DocumentType.PDF: "application/pdf",
    DocumentType.MD: "text/markdown",
    DocumentType.TXT: "text/plain",
}

DOCUMENT_EXTENSIONS: dict[DocumentType, str] = {
    DocumentType.CSV: "csv",
    DocumentType.XLSX: "xlsx",
    DocumentType.DOCX: "docx",
    DocumentType.PPTX: "pptx",
    DocumentType.PDF: "pdf",
    DocumentType.MD: "md",
    DocumentType.TXT: "txt",
}

RENDERERS: dict[DocumentType, Renderer] = {
    DocumentType.CSV: render_csv,
    DocumentType.MD: render_md,
    DocumentType.TXT: render_txt,
    DocumentType.XLSX: render_xlsx,
    DocumentType.DOCX: render_docx,
    DocumentType.PPTX: render_pptx,
    DocumentType.PDF: render_pdf,
}

# Boot-time completeness (ADR-085): a partial map refuses to import.
assert set(RENDERERS) == set(DocumentType), "RENDERERS must cover every DocumentType"
assert set(DOCUMENT_MIME_TYPES) == set(DocumentType), "DOCUMENT_MIME_TYPES must be total"
assert set(DOCUMENT_EXTENSIONS) == set(DocumentType), "DOCUMENT_EXTENSIONS must be total"


def render_document(
    doc_type: DocumentType,
    content: DocumentContent,
    context: RenderContext | None = None,
) -> bytes:
    """Render structured content into final document bytes.

    Args:
        doc_type: Target format.
        content: Validated content matching ``SCHEMA_BY_DOC_TYPE[doc_type]``.
        context: Reader and deployment facts; a caller that states nothing gets
            the deployment defaults and no date line.

    Returns:
        The rendered file bytes.

    Raises:
        ValueError: When the content model does not match the format family.
    """
    resolved = context or default_render_context()
    return RENDERERS[doc_type](normalize_content(content, resolved), resolved)
