"""Mail source endpoints of a RAG space (ADR-262).

Mounted by ``rag_spaces/router.py`` (frozen at its audited size), so the
prefix, the tags and the capability gate are inherited. Ownership is the
space's: a space that is not the caller's answers 404 (hidden existence),
exactly like the Drive endpoints.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import get_db
from src.core.exceptions import BaseAPIException
from src.core.session_dependencies import get_current_active_session
from src.domains.rag_spaces.mail_source_service import RAGMailSyncService
from src.domains.rag_spaces.mail_sync import sync_label_background
from src.domains.rag_spaces.schemas import (
    GmailLabelResponse,
    RAGMailSourceCreate,
    RAGMailSourceResponse,
    RAGMailSyncStatusResponse,
)
from src.domains.rag_spaces.service import RAGSpaceService
from src.domains.users.models import User
from src.infrastructure.async_utils import safe_fire_and_forget

router = APIRouter()


def _status_of(source: object) -> RAGMailSyncStatusResponse:
    return RAGMailSyncStatusResponse.model_validate(source, from_attributes=True)


@router.get(
    "/{space_id}/mail-labels",
    response_model=list[GmailLabelResponse],
    summary="List the Gmail labels a space may follow",
)
async def list_mail_labels(
    space_id: UUID,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> list[GmailLabelResponse]:
    """The user's own Gmail labels (system labels are never offered)."""
    labels = await RAGMailSyncService(db).list_labels(space_id, user.id)
    return [GmailLabelResponse(**label) for label in labels]


@router.post(
    "/{space_id}/mail-sources",
    response_model=RAGMailSourceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Link a Gmail label",
)
async def link_mail_label(
    space_id: UUID,
    data: RAGMailSourceCreate,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> RAGMailSourceResponse:
    """Link a Gmail label to a space: its threads become documents."""
    source = await RAGMailSyncService(db).link_label(
        space_id, user.id, data.label_id, data.label_name
    )
    return RAGMailSourceResponse.model_validate(source)


@router.get(
    "/{space_id}/mail-sources",
    response_model=list[RAGMailSourceResponse],
    summary="List linked Gmail labels",
)
async def list_mail_sources(
    space_id: UUID,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> list[RAGMailSourceResponse]:
    """Every Gmail label linked to the space."""
    sources = await RAGSpaceService(db).list_mail_sources(space_id, user.id)
    return [RAGMailSourceResponse.model_validate(source) for source in sources]


@router.delete(
    "/{space_id}/mail-sources/{source_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Unlink a Gmail label",
)
async def unlink_mail_label(
    space_id: UUID,
    source_id: UUID,
    delete_documents: bool = Query(default=False),
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Unlink a label; its documents are kept (unlinked) unless asked otherwise."""
    await RAGMailSyncService(db).unlink_label(space_id, source_id, user.id, delete_documents)


@router.post(
    "/{space_id}/mail-sources/{source_id}/sync",
    response_model=RAGMailSyncStatusResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger a full label sync",
)
async def sync_mail_label(
    space_id: UUID,
    source_id: UUID,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> RAGMailSyncStatusResponse:
    """Run a full sync of the label in the background (202)."""
    service = RAGMailSyncService(db)
    await service.get_sync_status(space_id, source_id, user.id)
    if not await service.try_acquire_sync_lock(source_id):
        raise BaseAPIException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Sync already in progress",
            log_event="rag_mail_sync_already_running",
            source_id=str(source_id),
        )
    safe_fire_and_forget(
        sync_label_background(source_id, user.id),
        name=f"mail_sync_{source_id}",
    )
    return _status_of(await service.get_sync_status(space_id, source_id, user.id))


@router.get(
    "/{space_id}/mail-sources/{source_id}/sync-status",
    response_model=RAGMailSyncStatusResponse,
    summary="Get a label's sync status",
)
async def get_mail_sync_status(
    space_id: UUID,
    source_id: UUID,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> RAGMailSyncStatusResponse:
    """The current sync status of a label source."""
    return _status_of(await RAGMailSyncService(db).get_sync_status(space_id, source_id, user.id))
