"""Read embedding inputs without locks, then prepare provider work without a session."""

from uuid import UUID

from src.domains.journals.extraction_settlement import (
    EmbeddingInput,
    ExtractionSettlement,
    desired_embedding_input,
)
from src.domains.journals.schemas import ExtractedJournalEntry
from src.domains.journals.service import JournalEmbeddings, JournalService, prepare_embeddings
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


def _create_input(action: ExtractedJournalEntry) -> EmbeddingInput | None:
    if action.title is None or action.content is None:
        return None
    return action.title, action.content, action.search_hints


async def _update_input(
    service: JournalService, action: ExtractedJournalEntry, context: ExtractionSettlement
) -> EmbeddingInput | None:
    if action.entry_id is None:
        return None
    entry = await service.repo.get_by_id(UUID(action.entry_id))
    if entry is None or str(entry.user_id) != context.user_id:
        return None
    return desired_embedding_input(action, entry)


async def load_embedding_inputs(
    service: JournalService, actions: list[ExtractedJournalEntry], context: ExtractionSettlement
) -> list[EmbeddingInput | None]:
    """Copy provider inputs while reading; no provider is called on this session."""
    inputs: list[EmbeddingInput | None] = []
    for action in actions:
        if action.action == "create":
            inputs.append(_create_input(action))
        elif action.action == "update":
            inputs.append(await _update_input(service, action, context))
        else:
            inputs.append(None)
    return inputs


async def prepare_embedding_inputs(
    inputs: list[EmbeddingInput | None],
) -> list[JournalEmbeddings | None]:
    """Preserve independent-action failures; None means skip a failed preparation."""
    prepared: list[JournalEmbeddings | None] = []
    for item in inputs:
        if item is None:
            prepared.append((None, None))
            continue
        try:
            prepared.append(await prepare_embeddings(*item))
        except Exception as exc:
            logger.warning("journal_extraction_embedding_failed", error_type=type(exc).__name__)
            prepared.append(None)
    return prepared
