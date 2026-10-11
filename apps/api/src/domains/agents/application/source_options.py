"""Read existing provider pickers without an import, sync, embedding or model call."""

import asyncio
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import AuthorizationError, raise_not_found_or_unauthorized
from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.source_options_schemas import (
    DrivePickerPage,
    SourceOptionsProjection,
    SourceOptionsQuery,
)
from src.domains.agents.application.space_read_schemas import SPACE_READ_MAX_BYTES
from src.domains.feature_switches.guard import require_capability_fresh
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.rag_spaces.drive_sync import RAGDriveSyncService
from src.domains.rag_spaces.mail_source_service import RAGMailSyncService
from src.domains.rag_spaces.models import RAGDriveSource
from src.domains.rag_spaces.schemas import GmailLabelResponse, RAGDrivePreflightResponse
from src.domains.rag_spaces.ui_queries import owned_space


async def _require_access(db: AsyncSession, actor_id: UUID, query: SourceOptionsQuery) -> None:
    await require_application_tools(db)
    await require_capability_fresh(db, PlatformCapability.RAG_SPACES)
    await load_actor(db, actor_id)
    flag = (
        settings.rag_spaces_drive_sync_enabled
        if query.section != "mail_labels"
        else settings.rag_spaces_mail_sync_enabled
    )
    if not flag:
        raise AuthorizationError(detail={"error_code": "CAPABILITY_DISABLED"})
    await owned_space(db, actor_id, query.space_id)


async def _source_identity(
    db: AsyncSession, actor_id: UUID, space_id: UUID, source_id: UUID
) -> tuple[str, str]:
    result = await db.execute(
        select(RAGDriveSource.folder_id, RAGDriveSource.folder_name).where(
            RAGDriveSource.id == source_id,
            RAGDriveSource.space_id == space_id,
            RAGDriveSource.user_id == actor_id,
        )
    )
    row = result.one_or_none()
    if row is None:
        raise_not_found_or_unauthorized("source", source_id)
    return row[0], row[1]


async def _read_preflight(
    db: AsyncSession, actor_id: UUID, query: SourceOptionsQuery, result: SourceOptionsProjection
) -> None:
    if query.source_id is None:
        raise ValueError("Preflight requires a linked source")
    before = await _source_identity(db, actor_id, query.space_id, query.source_id)
    report = await RAGDriveSyncService(db).preflight(query.space_id, query.source_id, actor_id)
    if before != await _source_identity(db, actor_id, query.space_id, query.source_id):
        raise CommandRejected("STALE_SELECTION")
    result.source_id = query.source_id
    result.source_name = before[1]
    result.preflight = RAGDrivePreflightResponse.model_validate(report)


async def read_source_options(
    db: AsyncSession, actor_id: UUID, query: SourceOptionsQuery
) -> SourceOptionsProjection:
    selected = SourceOptionsQuery.model_validate(query.model_dump())
    await _require_access(db, actor_id, selected)
    await db.commit()  # Provider work never borrows the authority read transaction.
    result = SourceOptionsProjection(
        section=selected.section, space_id=selected.space_id, observed_at=datetime.now(UTC)
    )
    async with asyncio.timeout(settings.http_timeout_external_api):
        if selected.section == "drive_contents":
            raw = await RAGDriveSyncService(db).browse_drive_contents(
                actor_id,
                selected.folder_id or "root",
                selected.page_token,
                max_results=selected.limit,
            )
            page = DrivePickerPage.model_validate(raw)
            if len(page.files) > selected.limit:
                raise ValueError("Provider did not honor its requested page bound")
            result.drive_files = page.files
            result.next_page_token = page.next_page_token
        elif selected.section == "mail_labels":
            labels = await RAGMailSyncService(db).list_labels(selected.space_id, actor_id)
            result.total = len(labels)
            result.mail_labels = [
                GmailLabelResponse.model_validate(label)
                for label in labels[selected.offset : selected.offset + selected.limit]
            ]
            next_offset = selected.offset + len(result.mail_labels)
            result.next_offset = next_offset if next_offset < result.total else None
        else:
            await _read_preflight(db, actor_id, selected, result)
    await _require_access(db, actor_id, selected)
    if len(result.model_dump_json().encode("utf-8")) > SPACE_READ_MAX_BYTES:
        raise ValueError("Source picker page too large; reduce limit")
    return result
