"""Manual journal embeddings use the existing accounted source provider, outside locks."""

from collections.abc import Awaitable, Callable
from uuid import UUID

from src.domains.journals.service import JournalEmbeddings, _generate_document_embedding
from src.infrastructure.llm.embedding_context import (
    clear_embedding_context,
    get_embedding_context,
    set_embedding_context,
)
from src.infrastructure.llm.usage_guard import enforce_usage_limit


async def prepare_manual_journal_embeddings(
    user_id: UUID,
    operation_id: UUID,
    title: str,
    content: str,
    hints: list[str] | None,
    check: Callable[[], Awaitable[None]],
) -> JournalEmbeddings:
    previous = get_embedding_context()
    set_embedding_context(
        str(user_id), f"journal-management:{operation_id}", run_id=str(operation_id)
    )
    try:
        texts = [f"{title}. {content}."]
        if hints and " ".join(hints).strip():
            texts.append(" ".join(hints))
        vectors: list[list[float] | None] = []
        for text in texts:
            await check()
            await enforce_usage_limit(user_id, layer="journal_management")
            vectors.append(await _generate_document_embedding(text))
        return vectors[0], vectors[1] if len(vectors) == 2 else None
    finally:
        clear_embedding_context()
        if previous is not None:
            set_embedding_context(
                previous.user_id, previous.session_id, previous.conversation_id, previous.run_id
            )
