"""Every corpus document renders in every applicable format (ADR-274).

Thirteen deterministic documents — a short memo, a long report, a twelve-column
table, six decks (one of them Chinese, where a full-width glyph is one em), a
Chinese report, edge cases, typed and empty workbooks, and a minutes-shaped
document — rendered here through the format's OWN reader.
The same fixtures feed ``task documents:corpus:render``, whose output a human
looks at and Word / PowerPoint / Excel measure.
"""

import io
import json
from pathlib import Path

import docx
import fitz
import openpyxl
import pptx
import pytest

from src.domains.document_generation.context import RenderContext
from src.domains.document_generation.normalize import normalize_content
from src.domains.document_generation.renderers import render_document
from src.domains.document_generation.schemas import (
    SCHEMA_BY_DOC_TYPE,
    DocumentContent,
    DocumentType,
)

from .pptx_oracles import assert_nothing_overflows

pytestmark = [pytest.mark.unit]

CORPUS_DIR = Path(__file__).parents[3] / "fixtures" / "document_corpus"
CORPUS = sorted(CORPUS_DIR.glob("*.json"))


def load(path: Path) -> tuple[list[DocumentType], DocumentContent, RenderContext]:
    """One fixture as (formats, content, context)."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    doc_types = [DocumentType(value) for value in raw["doc_types"]]
    content = SCHEMA_BY_DOC_TYPE[doc_types[0]].model_validate(raw["content"])
    context = RenderContext(
        language=raw.get("language", "en"), structure=raw.get("structure", "auto")
    )
    return doc_types, content, context


def _open_docx(data: bytes) -> object:
    return docx.Document(io.BytesIO(data))


def _open_pptx(data: bytes) -> object:
    presentation = pptx.Presentation(io.BytesIO(data))
    assert_nothing_overflows(presentation)
    return presentation


def _open_xlsx(data: bytes) -> object:
    return openpyxl.load_workbook(io.BytesIO(data))


def _open_pdf(data: bytes) -> object:
    document = fitz.open(stream=data, filetype="pdf")
    assert document.page_count >= 1
    document.close()
    return document


_OPENERS = {
    DocumentType.DOCX: _open_docx,
    DocumentType.PPTX: _open_pptx,
    DocumentType.XLSX: _open_xlsx,
    DocumentType.PDF: _open_pdf,
    DocumentType.CSV: lambda data: data.decode("utf-8-sig"),
    DocumentType.MD: lambda data: data.decode("utf-8"),
    DocumentType.TXT: lambda data: data.decode("utf-8"),
}


@pytest.mark.parametrize("path", CORPUS, ids=lambda path: path.stem)
def test_every_corpus_document_renders_and_reopens(path: Path) -> None:
    doc_types, content, context = load(path)
    for doc_type in doc_types:
        data = render_document(doc_type, content, context)
        assert data, (path.stem, doc_type)
        _OPENERS[doc_type](data)


def test_the_corpus_covers_every_format_and_both_structures() -> None:
    """A format nobody exercises is a format nobody notices breaking."""
    seen: set[DocumentType] = set()
    structures: set[str] = set()
    languages: set[str] = set()
    for path in CORPUS:
        raw = json.loads(path.read_text(encoding="utf-8"))
        seen.update(DocumentType(value) for value in raw["doc_types"])
        structures.add(raw.get("structure", "auto"))
        languages.add(raw.get("language", "en"))
    assert seen == set(DocumentType)
    assert structures == {"auto", "plain"}
    assert len(languages) >= 2  # at least one non-Latin script


def test_the_corpus_is_not_empty() -> None:
    assert len(CORPUS) >= 13


@pytest.mark.parametrize("path", CORPUS, ids=lambda path: path.stem)
def test_normalization_is_idempotent_over_the_corpus(path: Path) -> None:
    """Normalizing a normalized document changes nothing.

    Renderers normalize on entry, and the corpus harness renders the SAME
    content object in several formats — so the second pass must not strip a
    heading number the first pass wrote, re-widen a row it already padded, or
    re-parse markdown it already converted. The property is documented; without
    this test nothing would hold the code to it.
    """
    _doc_types, content, context = load(path)
    once = normalize_content(content, context)
    assert normalize_content(once, context) == once, path.stem
