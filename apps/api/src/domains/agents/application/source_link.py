"""Fresh provider inspection precedes exact native scope and Source-owned SQL fences."""

import asyncio
from datetime import UTC, datetime
from uuid import UUID

import structlog
from httpx import HTTPError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import AuthorizationError, BaseAPIException
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.source_link_schemas import (
    SourceLinkInput,
    SourceLinkPatch,
    SourceLinkSelection,
    canonical_source_link,
)
from src.domains.agents.application.source_link_spec import SOURCE_LINK_OPERATION
from src.domains.agents.application.space_update import _source_row
from src.domains.agents.application.space_update_schemas import SpaceUpdateTarget
from src.domains.agents.effects.digest import payload_digest
from src.domains.feature_switches.guard import require_capability_fresh
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.rag_spaces.drive_sync import RAGDriveSyncService
from src.domains.rag_spaces.mail_source_service import RAGMailSyncService
from src.domains.rag_spaces.models import RAGDriveSource, RAGMailSource
from src.domains.rag_spaces.service import RAGSpaceService
from src.domains.rag_spaces.source_link_observation import SourceLinkObservation
from src.domains.rag_spaces.ui_queries import owned_space
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.infrastructure.observability.metrics_rag_spaces import (
    rag_drive_sources_total_count,
    rag_mail_sources_total_count,
)

logger = structlog.get_logger(__name__)


async def _access(db: AsyncSession, actor_id: UUID, request: SourceLinkInput) -> None:
    await require_application_tools(db)
    await require_capability_fresh(db, PlatformCapability.RAG_SPACES)
    await load_actor(db, actor_id)
    if not (
        settings.rag_spaces_drive_sync_enabled
        if request.kind == "drive"
        else settings.rag_spaces_mail_sync_enabled
    ):
        raise AuthorizationError(detail={"error_code": "CAPABILITY_DISABLED"})
    await owned_space(db, actor_id, request.space_id)


async def _inspect(
    db: AsyncSession, actor_id: UUID, request: SourceLinkInput
) -> SourceLinkObservation:
    try:
        async with asyncio.timeout(settings.http_timeout_external_api):
            if request.kind == "drive":
                return await RAGDriveSyncService(db).prepare_folder_link(
                    request.space_id, actor_id, request.provider_id
                )
            return await RAGMailSyncService(db).prepare_label_link(
                request.space_id, actor_id, request.provider_id
            )
    except TimeoutError as error:
        raise CommandRejected("TIMEOUT") from error
    except BaseAPIException as error:
        if error.status_code in {400, 409}:
            raise CommandRejected("CONSTRAINT_VIOLATION") from error
        raise
    except HTTPError as error:
        raise CommandRejected("DEPENDENCY_ERROR") from error
    except ValueError as error:
        raise CommandRejected("INVALID_RESPONSE_FORMAT") from error


async def _selection(
    db: AsyncSession, actor_id: UUID, request: SourceLinkInput, observation: SourceLinkObservation
) -> SourceLinkSelection:
    space = await owned_space(db, actor_id, request.space_id)
    model = RAGDriveSource if request.kind == "drive" else RAGMailSource
    count = int(
        await db.scalar(select(func.count(model.id)).where(model.space_id == request.space_id)) or 0
    )
    limit = (
        settings.rag_drive_max_sources_per_space
        if request.kind == "drive"
        else settings.rag_mail_max_sources_per_space
    )
    if count >= limit:
        raise CommandRejected("CONSTRAINT_VIOLATION")
    return SourceLinkSelection(
        request=request,
        space=SpaceUpdateTarget.model_validate(space),
        source_name=observation.name,
        owned_count=count,
        max_sources=limit,
        state_digest=payload_digest(await _source_row(db, actor_id, request.space_id)),
    )


async def prepare_source_link(
    db: AsyncSession, actor_id: UUID, request: SourceLinkInput, *, command_id: UUID | None = None
) -> ApplicationActionDraftContent:
    request = SourceLinkInput.model_validate(request.model_dump())
    await _access(db, actor_id, request)
    observation = await _inspect(db, actor_id, request)
    await _access(db, actor_id, request)
    selected = await _selection(db, actor_id, request, observation)
    return build_action_content(
        actor_id,
        SOURCE_LINK_OPERATION,
        SourceLinkPatch(source_to_link=selected),
        {"source_to_link": selected.public_scope()},
        {"source_to_link": selected.public_scope(after=True)},
        command_id=command_id,
    )


async def execute_source_link(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    if draft.actor_id != actor_id or draft.operation_id != SOURCE_LINK_OPERATION.operation_id:
        raise CommandRejected("FORBIDDEN")
    if not canonical_source_link(draft):
        raise CommandRejected("INVALID_INPUT")
    selected = SourceLinkPatch.model_validate(draft.intent).source_to_link
    request = selected.request

    async def check() -> None:
        await _access(db, actor_id, request)
        if datetime.now(UTC) >= draft.expires_at:
            raise CommandRejected("EXPIRED")

    await check()
    observation = await _inspect(db, actor_id, request)
    await check()
    await RAGSpaceService(db).get_space(request.space_id, actor_id, for_update=True)
    await check()
    if await _selection(db, actor_id, request, observation) != selected:
        raise CommandRejected("STALE_STATE")
    service = RAGDriveSyncService(db) if request.kind == "drive" else RAGMailSyncService(db)
    try:
        if isinstance(service, RAGDriveSyncService):
            source = await service.link_folder(
                request.space_id,
                actor_id,
                request.provider_id,
                selected.source_name,
                observation=observation,
                commit=False,
            )
        else:
            source = await service.link_label(
                request.space_id,
                actor_id,
                request.provider_id,
                selected.source_name,
                observation=observation,
                commit=False,
            )
    except (ValueError, BaseAPIException) as error:
        raise CommandRejected("CONSTRAINT_VIOLATION") from error
    identity = source.id
    await _verify_link(db, actor_id, selected, identity)
    await check()
    try:
        await db.commit()
    except (Exception, asyncio.CancelledError) as error:
        raise CommandRejected("COMPLETION_UNKNOWN") from error
    receipt.committed = True
    receipt.values = {
        "source_to_link": {**selected.public_scope(after=True), "source_id": str(identity)}
    }
    try:
        (
            rag_drive_sources_total_count
            if request.kind == "drive"
            else rag_mail_sources_total_count
        ).inc()
    except Exception as error:
        logger.warning("source_link_telemetry_failed", error_type=type(error).__name__)


async def _verify_link(
    db: AsyncSession, actor_id: UUID, selected: SourceLinkSelection, identity: UUID
) -> None:
    request = selected.request
    model = RAGDriveSource if request.kind == "drive" else RAGMailSource
    provider = model.folder_id if request.kind == "drive" else model.label_id
    name = model.folder_name if request.kind == "drive" else model.label_name
    actual = await db.scalar(
        select(model.id).where(
            model.id == identity,
            model.space_id == request.space_id,
            model.user_id == actor_id,
            provider == request.provider_id,
            name == selected.source_name,
            model.sync_status == "idle",
        )
    )
    count = await db.scalar(select(func.count(model.id)).where(model.space_id == request.space_id))
    if actual != identity or count != selected.owned_count + 1:
        raise ValueError("Source did not create the exact one approved idle source")
    if payload_digest(await _source_row(db, actor_id, request.space_id)) != selected.state_digest:
        raise ValueError("Source must not change the approved parent metadata")
