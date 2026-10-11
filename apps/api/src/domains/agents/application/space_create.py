"""Confirmed creation reuses source normalization and serialized account quota enforcement."""

import asyncio
from datetime import UTC, datetime
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import BaseAPIException, ResourceConflictError, ValidationError
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.space_create_schemas import (
    SpaceCreateInput,
    SpaceCreatePatch,
    SpaceCreateSelection,
    canonical_space_creation,
)
from src.domains.agents.application.space_create_spec import SPACE_CREATE_OPERATION
from src.domains.feature_switches.guard import require_capability_fresh
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.rag_spaces import space_creation, ui_queries
from src.domains.rag_spaces.models import RAGSpace
from src.domains.rag_spaces.schemas import RAGSpaceResponse
from src.domains.rag_spaces.service import RAGSpaceService
from src.domains.users.preference_cas import PreferenceWriteReceipt

logger = structlog.get_logger(__name__)


async def _access(db: AsyncSession, actor_id: UUID) -> None:
    await require_application_tools(db)
    await require_capability_fresh(db, PlatformCapability.RAG_SPACES)
    await load_actor(db, actor_id)


async def _verify_creation(
    db: AsyncSession,
    service: RAGSpaceService,
    actor_id: UUID,
    identity: UUID,
    created_id: UUID,
    expected: SpaceCreateSelection,
) -> RAGSpaceResponse:
    actual = await ui_queries.owned_space(db, actor_id, identity)
    if (
        created_id != identity
        or actual.name != expected.request.name
        or actual.description != expected.request.description
    ):
        raise ValueError("Source did not persist the exact approved space")
    if not actual.is_active or actual.kind is not None:
        raise ValueError("Source creation differs from the approved empty active space")
    if await service.space_repo.count_for_user(actor_id) != expected.owned_count + 1:
        raise ValueError("Source creation must insert exactly one owned space")
    metadata = await ui_queries.space_metadata(db, actual)
    if metadata.document_count != 0:
        raise ValueError("Source must create an empty space")
    return metadata


async def _selection(
    service: RAGSpaceService, actor_id: UUID, request: SpaceCreateInput
) -> SpaceCreateSelection:
    try:
        source = await service.validate_creation(actor_id, request.name, request.description)
    except BaseAPIException as exc:
        if exc.status_code not in {400, 409}:
            raise
        raise ValidationError(
            "SPACE_LIMIT_EXCEEDED" if exc.status_code == 400 else "SPACE_NAME_EXISTS"
        ) from exc
    return SpaceCreateSelection(
        request=SpaceCreateInput.model_validate(source.request.model_dump()),
        owned_count=source.owned_count,
        max_spaces=source.max_spaces,
    )


async def prepare_space_creation(
    db: AsyncSession, actor_id: UUID, request: SpaceCreateInput, *, command_id: UUID | None = None
) -> ApplicationActionDraftContent:
    selected = SpaceCreateInput.model_validate(request.model_dump())
    await _access(db, actor_id)
    scope = await _selection(RAGSpaceService(db), actor_id, selected)
    await _access(db, actor_id)
    return build_action_content(
        actor_id,
        SPACE_CREATE_OPERATION,
        SpaceCreatePatch(space_create=scope),
        {"space_create": scope.public_scope()},
        {"space_create": scope.public_scope(after=True)},
        command_id=command_id,
    )


async def execute_space_creation(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    if draft.actor_id != actor_id or draft.operation_id != SPACE_CREATE_OPERATION.operation_id:
        raise CommandRejected("FORBIDDEN")
    if not canonical_space_creation(draft):
        raise ValueError("Creation requires exact canonical source configuration")
    expected = SpaceCreatePatch.model_validate(draft.intent).space_create

    async def check() -> None:
        await _access(db, actor_id)
        if datetime.now(UTC) >= draft.expires_at:
            raise CommandRejected("EXPIRED")

    await check()
    service = RAGSpaceService(db)
    await service.lock_creation_owner(actor_id)
    await check()
    if await _selection(service, actor_id, expected.request) != expected:
        raise ResourceConflictError("space_create", detail={"error_code": "STALE_STATE"})
    if await db.scalar(select(RAGSpace.id).where(RAGSpace.id == draft.command_id)) is not None:
        raise ResourceConflictError("space_create", detail={"error_code": "STALE_STATE"})
    created = await service.create_space(
        actor_id,
        expected.request.name,
        expected.request.description,
        commit=False,
        space_id=draft.command_id,
    )
    await db.flush()
    actual = await _verify_creation(db, service, actor_id, draft.command_id, created.id, expected)
    public = {
        **expected.public_scope(after=True),
        "space_id": str(actual.id),
        "space": actual.model_dump(mode="json"),
    }
    await check()
    try:
        await db.commit()
    except (Exception, asyncio.CancelledError) as exc:
        raise CommandRejected("COMPLETION_UNKNOWN") from exc
    receipt.committed = True
    receipt.values = {"space_create": public}
    try:
        space_creation.publish_space_creation()
    except Exception as exc:
        logger.warning("space_creation_telemetry_failed", error_type=type(exc).__name__)
