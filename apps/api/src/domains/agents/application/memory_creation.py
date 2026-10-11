"""An exact creation is approved before provider work and committed under fresh authority."""

from datetime import UTC, datetime
from functools import partial
from uuid import UUID, uuid4

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceConflictError
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.memory_create_schemas import (
    MemoryCreateConfiguration,
    MemoryCreatePatch,
    MemoryCreationValues,
)
from src.domains.agents.application.memory_creation_embeddings import (
    prepare_memory_creation_embeddings,
)
from src.domains.agents.application.memory_spec import MEMORY_CREATE_OPERATION
from src.domains.memories.management_commands import lock_memory_actor
from src.domains.memories.protection import initial_memory_pin
from src.domains.memories.service import MemoryService
from src.domains.users.extraction_consent import invalidate_extractions
from src.domains.users.preference_cas import PreferenceWriteReceipt


async def prepare_memory_creation(
    db: AsyncSession,
    actor_id: UUID,
    configuration: MemoryCreateConfiguration,
    *,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    validated = MemoryCreateConfiguration.model_validate(configuration.model_dump())
    await require_application_tools(db)
    await load_actor(db, actor_id)
    identity = command_id or uuid4()
    patch = MemoryCreatePatch(
        memory_to_create=MemoryCreationValues(
            id=identity,
            configuration=validated,
            pinned=initial_memory_pin(validated.category),
        )
    )
    return build_action_content(
        actor_id,
        MEMORY_CREATE_OPERATION,
        patch,
        {"memory_to_create": None},
        patch.model_dump(mode="json"),
        command_id=identity,
    )


async def _creation_fence(
    db: AsyncSession, actor_id: UUID, draft: ApplicationActionDraftContent
) -> None:
    await require_application_tools(db)
    await load_actor(db, actor_id)
    if datetime.now(UTC) >= draft.expires_at:
        raise CommandRejected("EXPIRED")


async def execute_memory_creation(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    proposal = MemoryCreatePatch.model_validate(draft.intent).memory_to_create
    if (
        proposal.id != draft.command_id
        or draft.before != {"memory_to_create": None}
        or draft.intent != draft.after
    ):
        raise ValueError("Creation must retain the confirmed identity and full configuration")
    if proposal.pinned != initial_memory_pin(proposal.configuration.category):
        raise ResourceConflictError("memory", detail={"error_code": "STALE_STATE"})
    guard = partial(_creation_fence, db, actor_id, draft)
    await guard()
    prepared = await prepare_memory_creation_embeddings(
        actor_id,
        proposal.id,
        proposal.configuration.content,
        proposal.configuration.trigger_topic,
        guard,
    )
    await guard()
    actor = await lock_memory_actor(db, actor_id)
    await guard()
    invalidate_extractions(actor)
    await MemoryService(db, embedder=prepared.resolve).create_from_management(
        actor_id,
        proposal.configuration,
        memory_id=proposal.id,
    )
    await guard()
    try:
        await db.commit()
    except SQLAlchemyError as exc:
        raise CommandRejected("COMPLETION_UNKNOWN") from exc
    receipt.committed = True
