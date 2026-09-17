"""What the API says about a kept answer's projection — pure, and light.

Two readers need it: the schemas (every response) and the indexing module
(the settle). Neither may drag the other's imports along — the schemas must
not import the pipeline, and the pipeline must not import the wire shapes —
so the two functions live here with the models alone.
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from src.core.llm_usage import LLMUsage
from src.domains.bookmarks.models import BookmarkIndexState
from src.domains.rag_spaces.models import RAGDocumentStatus


class IndexedRecord(Protocol):
    """What the API reads on a bookmark row about its projection."""

    rag_document_id: UUID | None
    index_state: str | None


class ProjectedDocument(Protocol):
    """What the API reads on the projection's ``rag_documents`` row."""

    status: str
    embedding_tokens: int | None
    embedding_cost_eur: float | None
    embedding_model: str | None


#: The document's lifecycle, read as the bookmark's state while it exists.
_DOCUMENT_STATE: dict[str, str] = {
    RAGDocumentStatus.READY: BookmarkIndexState.INDEXED.value,
    RAGDocumentStatus.ERROR: BookmarkIndexState.ERROR.value,
}


def derived_index_state(bookmark: IndexedRecord, document: ProjectedDocument | None) -> str | None:
    """The state the API exposes: the document's while it exists, else the stored reason.

    The document row is the authority on its own lifecycle; the bookmark only
    says why there is none (or, on success, that there was one). A crash
    between processing and the settle therefore loses nothing: the reaper
    re-drives the document and the state reads from it.

    Args:
        bookmark: The row.
        document: Its projection, when the link still resolves.

    Returns:
        A ``BookmarkIndexState`` value, or None when never attempted.
    """
    if document is not None:
        return _DOCUMENT_STATE.get(document.status, BookmarkIndexState.PENDING.value)
    state = bookmark.index_state
    return str(state) if state is not None else None


def index_usage_of(document: ProjectedDocument | None) -> LLMUsage | None:
    """What the projection cost, once — and only once — it is READY.

    A zero is a claim, so a document that is not READY (or missing) reports
    nothing rather than « 0,00 € » (ADR-269's rule on displayed costs).

    Args:
        document: The projection row.

    Returns:
        The embedding tokens and cost, or None.
    """
    if document is None or document.status != RAGDocumentStatus.READY:
        return None
    return LLMUsage(
        tokens_in=int(document.embedding_tokens or 0),
        tokens_out=0,
        tokens_cache=0,
        cost_eur=float(document.embedding_cost_eur or 0.0),
        model_name=document.embedding_model,
    )


__all__ = ["IndexedRecord", "ProjectedDocument", "derived_index_state", "index_usage_of"]
