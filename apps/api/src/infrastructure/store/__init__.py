"""
Store infrastructure module.

Hosts the BM25 lexical index used by RAG Spaces retrieval (hybrid semantic +
lexical search over user documents).

Historical note: this package also exposed a LangGraph-store-based semantic
memory layer (`semantic_store.py`, including a `search_hybrid` combining BM25
and pgvector). Long-term memory moved to a dedicated PostgreSQL/pgvector model
in v1.14.0 (`domains/memories/`), and that module was left behind with no
caller. It was removed in ADR-168 along with its four orphan settings.
"""

from .bm25_index import (
    BM25IndexManager,
    get_bm25_manager,
    tokenize_text,
)

__all__ = [
    "BM25IndexManager",
    "get_bm25_manager",
    "tokenize_text",
]
