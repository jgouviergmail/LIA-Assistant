"""Bounded source UI metadata queries; storage names and document bodies never leave DTOs."""

from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import raise_not_found_or_unauthorized
from src.domains.rag_spaces.models import (
    RAGDocument,
    RAGDocumentStatus,
    RAGDriveSource,
    RAGMailSource,
    RAGSpace,
)
from src.domains.rag_spaces.repository import RAGDocumentRepository
from src.domains.rag_spaces.schemas import (
    RAGDocumentResponse,
    RAGDriveSourceResponse,
    RAGMailSourceResponse,
    RAGSpaceResponse,
)


async def owned_space(db: AsyncSession, user_id: UUID, space_id: UUID) -> RAGSpace:
    """Read current non-system ownership, including inactive user spaces."""
    space = await db.scalar(
        select(RAGSpace)
        .where(RAGSpace.id == space_id, RAGSpace.user_id == user_id, RAGSpace.is_system.is_(False))
        .execution_options(populate_existing=True)
    )
    if space is None:
        raise_not_found_or_unauthorized("space", space_id)
    return space


async def space_metadata(db: AsyncSession, space: RAGSpace) -> RAGSpaceResponse:
    """Reuse source totals and the exact public UI DTO, with no raw ORM dump."""
    stats = await RAGDocumentRepository(db).get_space_stats(space.id)
    return RAGSpaceResponse.model_validate(
        {**RAGSpaceResponse.model_validate(space).model_dump(), **stats}
    )


async def spaces_page(
    db: AsyncSession, user_id: UUID, *, limit: int, offset: int
) -> tuple[list[RAGSpaceResponse], int]:
    """One account page and whole-set totals, with constant query count."""
    scope = (RAGSpace.user_id == user_id, RAGSpace.is_system.is_(False))
    total = int(await db.scalar(select(func.count(RAGSpace.id)).where(*scope)) or 0)
    statement = (
        select(
            RAGSpace,
            func.count(RAGDocument.id),
            func.coalesce(func.sum(RAGDocument.file_size), 0),
            func.count(RAGDocument.id).filter(RAGDocument.status == RAGDocumentStatus.READY),
        )
        .outerjoin(RAGDocument, RAGDocument.space_id == RAGSpace.id)
        .where(*scope)
        .group_by(RAGSpace.id)
        .order_by(RAGSpace.created_at.desc(), RAGSpace.id.desc())
        .limit(limit)
        .offset(offset)
        .execution_options(populate_existing=True)
    )
    rows = (await db.execute(statement)).all()
    return [
        RAGSpaceResponse.model_validate(
            {
                **RAGSpaceResponse.model_validate(space).model_dump(),
                "document_count": count,
                "total_size": size,
                "ready_document_count": ready,
            }
        )
        for space, count, size, ready in rows
    ], total


async def count_owned_observations(db: AsyncSession, user_id: UUID, identities: list[UUID]) -> int:
    """Recheck all returned space identities in one query before publication."""
    if not identities:
        return 0
    return int(
        await db.scalar(
            select(func.count(RAGSpace.id)).where(
                RAGSpace.id.in_(identities),
                RAGSpace.user_id == user_id,
                RAGSpace.is_system.is_(False),
            )
        )
        or 0
    )


async def _page[Row, Projection: BaseModel](
    db: AsyncSession,
    statement: Select[tuple[Row]],
    model: type[Projection],
    limit: int,
    offset: int,
) -> tuple[list[Projection], int]:
    total = int(
        await db.scalar(select(func.count()).select_from(statement.order_by(None).subquery())) or 0
    )
    rows = await db.scalars(
        statement.limit(limit).offset(offset).execution_options(populate_existing=True)
    )
    return [model.model_validate(row) for row in rows], total


async def documents_page(
    db: AsyncSession, space_id: UUID, *, limit: int, offset: int
) -> tuple[list[RAGDocumentResponse], int]:
    statement = (
        select(RAGDocument)
        .where(RAGDocument.space_id == space_id)
        .order_by(RAGDocument.created_at.desc(), RAGDocument.id.desc())
    )
    return await _page(db, statement, RAGDocumentResponse, limit, offset)


async def drive_sources_page(
    db: AsyncSession, space_id: UUID, *, limit: int, offset: int
) -> tuple[list[RAGDriveSourceResponse], int]:
    statement = (
        select(RAGDriveSource)
        .where(RAGDriveSource.space_id == space_id)
        .order_by(RAGDriveSource.created_at.desc(), RAGDriveSource.id.desc())
    )
    return await _page(db, statement, RAGDriveSourceResponse, limit, offset)


async def mail_sources_page(
    db: AsyncSession, space_id: UUID, *, limit: int, offset: int
) -> tuple[list[RAGMailSourceResponse], int]:
    statement = (
        select(RAGMailSource)
        .where(RAGMailSource.space_id == space_id)
        .order_by(RAGMailSource.created_at.desc(), RAGMailSource.id.desc())
    )
    return await _page(db, statement, RAGMailSourceResponse, limit, offset)
