"""Source normalization, uncommitted insertion and acknowledged creation telemetry."""

from dataclasses import dataclass
from uuid import UUID

from src.domains.rag_spaces.models import RAGSpace
from src.domains.rag_spaces.repository import RAGSpaceRepository
from src.domains.rag_spaces.schemas import RAGSpaceCreate
from src.infrastructure.observability.metrics_rag_spaces import (
    rag_spaces_active_count,
    rag_spaces_total_count,
)


@dataclass(frozen=True)
class SpaceCreationScope:
    request: RAGSpaceCreate
    owned_count: int
    max_spaces: int


def normalize_creation(name: str, description: str | None) -> RAGSpaceCreate:
    """Validate the normalized source values, so whitespace cannot evade name bounds."""
    return RAGSpaceCreate(
        name=name.strip(), description=description.strip() if description else None
    )


async def create_space_row(
    repo: RAGSpaceRepository,
    user_id: UUID,
    request: RAGSpaceCreate,
    *,
    space_id: UUID | None = None,
) -> RAGSpace:
    values: dict[str, object] = {"user_id": user_id, **request.model_dump()}
    if space_id is not None:
        values["id"] = space_id
    return await repo.create(values)


def publish_space_creation() -> None:
    """Only an acknowledged creation increments source gauges."""
    rag_spaces_total_count.inc()
    rag_spaces_active_count.inc()
