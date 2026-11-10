"""Complete metadata-only listing, aggregated in one account-scoped SQL snapshot."""

from uuid import UUID

from sqlalchemy import and_, func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.repository import BaseRepository
from src.domains.rag_spaces.models import RAGDocument, RAGDocumentStatus, RAGSpace
from src.domains.rag_spaces.schemas import RAGSpaceListQuery, RAGSpaceResponse
from src.domains.shared.text_normalization import normalize_search_text


def _sort_spaces(spaces: list[RAGSpaceResponse], ordering: str) -> None:
    """Keep name and primary-key ties deterministic under every primary ordering."""
    spaces.sort(key=lambda space: (normalize_search_text(space.name), space.id))
    if ordering == "recent":
        spaces.sort(key=lambda space: space.created_at, reverse=True)
    elif ordering == "files":
        spaces.sort(key=lambda space: space.document_count, reverse=True)
    elif ordering == "active":
        spaces.sort(key=lambda space: not space.is_active)


class SpaceListingRepository(BaseRepository[RAGSpace]):
    """Read owned spaces without document bodies, per-space queries or hidden caps."""

    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db, RAGSpace)

    async def list_metadata(
        self, user_id: UUID, criteria: RAGSpaceListQuery
    ) -> list[RAGSpaceResponse]:
        """Aggregate all statuses and match normalized metadata without a narrower SQL filter.

        Args:
            user_id: Authenticated owner; system spaces are never included.
            criteria: Validated literal search and ordering.

        Returns:
            Complete matching spaces. Filenames stay on the server and are read
            only when requested; counts and records share this statement's snapshot.
        """
        needle = normalize_search_text(criteria.q.strip())
        search_files = bool(needle) and criteria.field == "filename"
        names = func.array_agg(RAGDocument.original_filename).filter(
            RAGDocument.id.is_not(None), literal(search_files)
        )
        statement = (
            select(
                RAGSpace,
                func.count(RAGDocument.id),
                func.coalesce(func.sum(RAGDocument.file_size), 0),
                func.count(RAGDocument.id).filter(RAGDocument.status == RAGDocumentStatus.READY),
                names,
            )
            .outerjoin(
                RAGDocument,
                and_(
                    RAGDocument.space_id == RAGSpace.id,
                    RAGDocument.user_id == user_id,
                ),
            )
            .where(RAGSpace.user_id == user_id, RAGSpace.is_system.is_(False))
            .group_by(RAGSpace.id)
            .execution_options(populate_existing=True)
        )
        spaces: list[RAGSpaceResponse] = []
        for space, count, size, ready, filenames in (await self.db.execute(statement)).all():
            candidates = (filenames or []) if search_files else [space.name]
            if needle and not any(needle in normalize_search_text(name) for name in candidates):
                continue
            spaces.append(
                RAGSpaceResponse.model_validate(
                    {
                        **RAGSpaceResponse.model_validate(space).model_dump(),
                        "document_count": count,
                        "total_size": size,
                        "ready_document_count": ready,
                    }
                )
            )
        _sort_spaces(spaces, criteria.sort)
        return spaces
