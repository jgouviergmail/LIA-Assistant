"""The reason a document failed is a CODE, translated at display (ADR-184 applied).

``rag_documents.error_message`` used to be the only account of a failure — a
technical English sentence shown as a tooltip, whatever the person's language.
A scanned PDF read « No text content extracted », which named neither the cause
(no text layer, no character recognition on this instance) nor the remedy.
The pipeline now stores a closed vocabulary beside the message and the
frontend draws its sentence from the locales. Two guards keep that vocabulary
whole: every code has an English sentence (the i18n parity gate spreads it to
the five other locales), and the frontend mirror lists exactly the backend
codes — a code the frontend does not know would fall back to the tooltip.
"""

from __future__ import annotations

import json
import re

import pytest

from src.domains.rag_spaces.models import RAGDocumentErrorCode
from src.domains.rag_spaces.schemas import RAGDocumentResponse, RAGDocumentStatusResponse
from tests._repo_paths import repo_root_or_skip

pytestmark = pytest.mark.unit

ERRORS_NAMESPACE = ("spaces", "documents", "errors")
FRONTEND_MIRROR = "apps/web/src/lib/rag-spaces/document-errors.ts"


def test_every_code_has_an_english_sentence() -> None:
    root = repo_root_or_skip()
    node = json.loads((root / "apps/web/locales/en/translation.json").read_text(encoding="utf-8"))
    for key in ERRORS_NAMESPACE:
        node = node[key]
    missing = [code.value for code in RAGDocumentErrorCode if not node.get(code.value)]
    assert not missing, f"codes without an English sentence: {missing}"


def test_the_frontend_mirror_lists_exactly_the_backend_codes() -> None:
    root = repo_root_or_skip()
    source = (root / FRONTEND_MIRROR).read_text(encoding="utf-8")
    declaration = source.split("RAG_DOCUMENT_ERROR_CODES", 1)[1].split("]", 1)[0]
    listed = set(re.findall(r"'([a-z_]+)'", declaration))
    assert listed == {code.value for code in RAGDocumentErrorCode}


def test_the_code_travels_on_both_document_responses() -> None:
    assert "error_code" in RAGDocumentResponse.model_fields
    assert "error_code" in RAGDocumentStatusResponse.model_fields
