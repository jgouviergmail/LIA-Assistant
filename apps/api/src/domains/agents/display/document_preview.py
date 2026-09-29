"""Ephemeral projections of authorized RAG excerpts, never a whole-file judgment."""

import structlog

from src.domains.agents.data_registry.models import (
    RegistryItem,
    RegistryItemMeta,
    RegistryItemType,
    generate_registry_id,
)
from src.domains.rag_spaces.retrieval import RAGContext

logger = structlog.get_logger(__name__)


def document_preview_registry(context: RAGContext) -> dict[str, RegistryItem]:
    """Reuse retrieved chunks without another search, persistence or source access."""
    try:
        return _project(context)
    except (AttributeError, TypeError, ValueError) as exc:
        # Optional presentation must never erase the primary RAG injection.
        logger.debug("jev_document_preview_unavailable", error_type=type(exc).__name__)
        return {}


def _project(context: RAGContext) -> dict[str, RegistryItem]:
    if context.context_type != "user":
        return {}
    result: dict[str, RegistryItem] = {}
    for index, chunk in enumerate(context.chunks):
        identity = generate_registry_id(
            RegistryItemType.NOTE,
            f"{index}:{chunk.space_name}:{chunk.original_filename}:{chunk.chunk_index}",
        )
        result[identity] = RegistryItem(
            id=identity,
            type=RegistryItemType.NOTE,
            payload={
                "title": chunk.original_filename,
                "space": chunk.space_name,
                "content": chunk.content,
                "evidence_scope": "document_excerpt",
            },
            meta=RegistryItemMeta(source="rag_user_excerpt", domain="documents"),
        )
    return result
