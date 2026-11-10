"""Source metadata normalization and ordered current-owner mutation fence."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import raise_not_found_or_unauthorized
from src.domains.rag_spaces.models import RAGSpace
from src.domains.rag_spaces.schemas import RAGSpaceUpdate
from src.domains.users.repository import UserRepository
from src.infrastructure.observability.metrics_rag_spaces import rag_spaces_active_count


def source_update_values(
    name: str | None, description: str | None, *, is_favorite: bool | None = None
) -> dict[str, str | bool | None]:
    """Normalize sparse metadata and display preferences through the source schema."""
    validated = RAGSpaceUpdate(name=name, description=description, is_favorite=is_favorite)
    result: dict[str, str | bool | None] = {}
    if validated.name is not None:
        result["name"] = validated.name
    if validated.description is not None:
        result["description"] = validated.description.strip() or None
    if validated.is_favorite is not None:
        result["is_favorite"] = validated.is_favorite
    return result


def publish_activation(active: bool) -> None:
    if active:
        rag_spaces_active_count.inc()
    else:
        rag_spaces_active_count.dec()


async def lock_owned_space(db: AsyncSession, user_id: UUID, space_id: UUID) -> RAGSpace | None:
    """Account first, then exact owned parent; foreign ids acquire no foreign row lock."""
    if await UserRepository(db).get_by_id_for_preference_update(user_id) is None:
        raise_not_found_or_unauthorized("account", user_id)
    space: RAGSpace | None = await db.scalar(
        select(RAGSpace)
        .where(RAGSpace.id == space_id, RAGSpace.user_id == user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return space
