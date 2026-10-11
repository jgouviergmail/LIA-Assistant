"""Exact bounded public deletion scope and streaming private source-state digest."""

import hashlib
import json
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.space_delete_schemas import (
    SpaceDeleteDocument,
    SpaceDeleteInput,
    SpaceDeleteSelection,
    SpaceDeleteSource,
)
from src.domains.agents.application.space_update_schemas import SpaceUpdateTarget
from src.domains.rag_spaces import ui_queries
from src.domains.rag_spaces.models import (
    RAGChunk,
    RAGDocument,
    RAGDriveSource,
    RAGMailSource,
    RAGSpace,
)
from src.domains.rag_spaces.service import raise_space_managed_by_domain

_CHILDREN = (RAGDriveSource, RAGMailSource, RAGDocument, RAGChunk)


async def private_scope_digest(db: AsyncSession, space_id: UUID) -> str:
    """Hash complete source rows one at a time; no document content enters the draft or LLM."""
    digest = hashlib.sha256()
    for model in (RAGSpace, *_CHILDREN):
        scope = model.id == space_id if model is RAGSpace else model.space_id == space_id
        rows = await db.stream_scalars(
            select(func.to_jsonb(model.__table__.table_valued()))
            .where(scope)
            .order_by(model.id)
            .execution_options(yield_per=32)
        )
        try:
            digest.update(model.__tablename__.encode("ascii"))
            async for row in rows:
                encoded = json.dumps(
                    row, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                ).encode("utf-8")
                if len(encoded) > 64_000:
                    raise ValueError("Source row too large for exact deletion approval")
                digest.update(len(encoded).to_bytes(8, "big"))
                digest.update(encoded)
        finally:
            await rows.close()
    return digest.hexdigest()


async def deletion_selection(
    db: AsyncSession, actor_id: UUID, request: SpaceDeleteInput
) -> SpaceDeleteSelection:
    space = await ui_queries.owned_space(db, actor_id, request.space_id)
    if space.kind is not None:
        raise_space_managed_by_domain(space.id, space.kind)
    documents = list(
        (
            await db.scalars(
                select(RAGDocument)
                .where(RAGDocument.space_id == space.id)
                .order_by(RAGDocument.id)
                .execution_options(populate_existing=True)
            )
        ).all()
    )
    drive = list(
        (
            await db.scalars(
                select(RAGDriveSource)
                .where(RAGDriveSource.space_id == space.id)
                .order_by(RAGDriveSource.id)
                .execution_options(populate_existing=True)
            )
        ).all()
    )
    mail = list(
        (
            await db.scalars(
                select(RAGMailSource)
                .where(RAGMailSource.space_id == space.id)
                .order_by(RAGMailSource.id)
                .execution_options(populate_existing=True)
            )
        ).all()
    )
    # Refuse active source work before acquiring child locks: a provider job may
    # still hold its own row/chunks and may write files from its captured scope.
    if any(doc.status in {"processing", "reindexing"} for doc in documents) or any(
        source.sync_status == "syncing" for source in (*drive, *mail)
    ):
        raise CommandRejected("BUSY")
    if any(row.user_id != actor_id for row in (*documents, *drive, *mail)):
        raise CommandRejected("FORBIDDEN")
    selected = SpaceDeleteSelection(
        request=request,
        space=SpaceUpdateTarget.model_validate(space),
        items=[SpaceDeleteDocument.model_validate(doc) for doc in documents],
        drive_sources=[SpaceDeleteSource(id=row.id, name=row.folder_name) for row in drive],
        mail_sources=[SpaceDeleteSource(id=row.id, name=row.label_name) for row in mail],
        chunks=int(
            await db.scalar(select(func.count(RAGChunk.id)).where(RAGChunk.space_id == space.id))
            or 0
        ),
        owned_spaces=int(
            await db.scalar(select(func.count(RAGSpace.id)).where(RAGSpace.user_id == actor_id))
            or 0
        ),
        state_digest=await private_scope_digest(db, space.id),
    )
    if len(json.dumps(selected.public_scope(), ensure_ascii=False).encode("utf-8")) > 64_000:
        raise ValueError("Deletion scope too large to present whole")
    return selected


async def lock_deletion_children(db: AsyncSession, space_id: UUID) -> None:
    # Parent FOR UPDATE prevents new children through their FK; stable child
    # ordering serializes current source status writes before revalidation.
    for model in (RAGDriveSource, RAGMailSource):
        await db.execute(
            select(model.id).where(model.space_id == space_id).order_by(model.id).with_for_update()
        )
        if await db.scalar(
            select(func.count(model.id)).where(
                model.space_id == space_id, model.sync_status == "syncing"
            )
        ):
            raise CommandRejected("BUSY")
    await db.execute(
        select(RAGDocument.id)
        .where(RAGDocument.space_id == space_id)
        .order_by(RAGDocument.id)
        .with_for_update()
    )
    # Never lock chunks before rereading the now-fenced document state. A worker
    # may hold old chunk rows while its insert waits on this parent's FK lock.
