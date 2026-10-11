"""Freeze an owned complete export scope without copying source text into a prompt."""

from contextlib import aclosing
from datetime import UTC, datetime
from hashlib import sha256
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.application_origin import ApplicationOrigin
from src.core.exceptions import AuthorizationError
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.management_export_schemas import (
    ManagementExportPatch,
    ManagementExportRequest,
    ManagementExportSnapshot,
)
from src.domains.agents.application.management_export_sources import MANAGEMENT_EXPORT_SOURCES
from src.domains.agents.effects.digest import payload_digest


async def authorize_management_export(
    db: AsyncSession, actor_id: UUID, origin: ApplicationOrigin | None
) -> None:
    if origin is None:
        raise AuthorizationError(detail={"error_code": "SESSION_UNAVAILABLE"})
    await require_application_tools(db)
    await load_actor(db, actor_id)
    await origin.require_session(actor_id, expected_binding=origin.binding_id)
    await require_application_tools(db)
    await load_actor(db, actor_id)


async def prepare_interest_export(
    db: AsyncSession,
    actor_id: UUID,
    request: ManagementExportRequest,
    *,
    origin: ApplicationOrigin | None,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    return await prepare_management_export(
        db, actor_id, request, "interests.export", origin=origin, command_id=command_id
    )


async def prepare_memory_export(
    db: AsyncSession,
    actor_id: UUID,
    request: ManagementExportRequest,
    *,
    origin: ApplicationOrigin | None,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    return await prepare_management_export(
        db, actor_id, request, "memories.export", origin=origin, command_id=command_id
    )


async def prepare_management_export(
    db: AsyncSession,
    actor_id: UUID,
    request: ManagementExportRequest,
    operation_id: str,
    *,
    origin: ApplicationOrigin | None,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    source = MANAGEMENT_EXPORT_SOURCES[operation_id]
    request = ManagementExportRequest.model_validate(request.model_dump())
    await authorize_management_export(db, actor_id, origin)
    await source.require_available(db)
    now, count, digest = datetime.now(UTC), 0, sha256(source.digest_prefix(request.format))
    if source.metadata is not None:
        metadata = await source.export_metadata(db, actor_id, request.format, now, 0)
        digest.update(bytes.fromhex(payload_digest(metadata)))
    async with aclosing(source.rows(db, actor_id, request.format, now, False)) as records:
        async for record in records:
            count += 1
            digest.update(bytes.fromhex(payload_digest(record)))
    selected = ManagementExportSnapshot(
        format=request.format,
        observed_at=now,
        selected_count=count,
        selection_digest=digest.hexdigest(),
    )
    patch = ManagementExportPatch(management_export=selected)
    await authorize_management_export(db, actor_id, origin)
    await source.require_available(db)
    return build_action_content(
        actor_id,
        source.operation,
        patch,
        {"management_export": None},
        patch.model_dump(mode="json"),
        command_id=command_id,
    )
