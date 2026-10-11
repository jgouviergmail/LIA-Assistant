"""Explicit management provenance uses the same live source resolver and DTO as the UI."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import raise_memory_not_found
from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.memory_provenance_schemas import MemoryProvenanceRequest
from src.domains.memories.repository import MemoryRepository
from src.domains.shared.provenance_repository import ProvenanceRepository
from src.domains.shared.schemas import ProvenanceResponse


async def read_memory_provenance(
    db: AsyncSession, actor_id: UUID, request: MemoryProvenanceRequest
) -> ProvenanceResponse:
    selected = MemoryProvenanceRequest.model_validate(request.model_dump())
    await require_application_tools(db)
    await load_actor(db, actor_id)
    # The existing UI permits provenance for an owned superseded row too.
    if await MemoryRepository(db).get_by_id_for_user(selected.memory_id, actor_id) is None:
        raise_memory_not_found(str(selected.memory_id))
    references = await ProvenanceRepository(db).resolve_for(
        user_id=actor_id, memory_id=selected.memory_id
    )
    result = ProvenanceResponse.from_references(references)
    await require_application_tools(db)
    await load_actor(db, actor_id)
    return result
