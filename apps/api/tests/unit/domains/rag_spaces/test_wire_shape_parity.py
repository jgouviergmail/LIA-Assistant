"""The space and document the API sends are the ones the web app reads.

``RAGSpaceResponse`` / ``RAGDocumentResponse`` and the frontend's ``RAGSpace``
/ ``RAGDocument`` interfaces must carry the same fields (the ADR-282 guard,
extended to the spaces when ``kind`` joined the wire so a managed space can be
drawn as such).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.domains.rag_spaces.schemas import RAGDocumentResponse, RAGSpaceResponse

pytestmark = pytest.mark.unit

_TYPES = Path(__file__).resolve().parents[5] / "web" / "src" / "types" / "rag-spaces.ts"


def _interface_fields(name: str) -> set[str]:
    source = _TYPES.read_text(encoding="utf-8")
    body = source.split(f"export interface {name} {{", 1)[1].split("}", 1)[0]
    return set(re.findall(r"^\s{2}([a-z_]+)\??:", body, re.M))


def test_a_space_exposes_its_kind_so_a_managed_space_is_drawn_as_such() -> None:
    assert "kind" in RAGSpaceResponse.model_fields


def test_one_space_has_the_same_fields_on_both_sides() -> None:
    assert _interface_fields("RAGSpace") == set(RAGSpaceResponse.model_fields)


def test_one_document_has_the_same_fields_on_both_sides() -> None:
    assert _interface_fields("RAGDocument") == set(RAGDocumentResponse.model_fields)
