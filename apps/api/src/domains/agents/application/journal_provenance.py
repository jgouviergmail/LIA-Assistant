"""Live source provenance reuses the UI resolver and refuses withdrawn authority."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceNotFoundError
from src.domains.agents.application.journal_provenance_schemas import JournalProvenanceRequest
from src.domains.agents.application.journal_queries import require_journal_access
from src.domains.journals.service import JournalService
from src.domains.shared.provenance_repository import ProvenanceRepository
from src.domains.shared.schemas import ProvenanceResponse


async def read_journal_provenance(
    db: AsyncSession, actor_id: UUID, request: JournalProvenanceRequest
) -> ProvenanceResponse:
    selected = JournalProvenanceRequest.model_validate(request.model_dump())
    await require_journal_access(db, actor_id)
    if await JournalService(db).get_entry_for_user(selected.entry_id, actor_id) is None:
        raise ResourceNotFoundError("journal_entry", selected.entry_id)
    references = await ProvenanceRepository(db).resolve_for(
        user_id=actor_id, journal_entry_id=selected.entry_id
    )
    observed = ProvenanceResponse.from_references(references)
    await require_journal_access(db, actor_id)
    return observed
