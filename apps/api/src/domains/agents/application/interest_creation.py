"""Exact human approval precedes source defaults, paid work and the fresh write fence."""

from datetime import UTC, datetime
from functools import partial
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceConflictError
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.authorization import authorize_actor, load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.interest_create_schemas import (
    InterestCreateConfiguration,
    InterestCreatePatch,
    InterestCreationValues,
)
from src.domains.agents.application.interest_embeddings import prepare_interest_embedding
from src.domains.agents.application.interest_spec import INTEREST_CREATE_OPERATION
from src.domains.interests.management_commands import create_managed_interest
from src.domains.interests.repository import InterestRepository
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.domains.users.repository import UserRepository


async def require_available_interest_topic(
    db: AsyncSession, actor_id: UUID, configuration: InterestCreateConfiguration
) -> None:
    if (
        await InterestRepository(db).get_by_user_topic_category(
            actor_id, configuration.topic, configuration.category.value
        )
        is not None
    ):
        raise ResourceConflictError("interest", detail={"error_code": "STALE_STATE"})


async def prepare_interest_creation(
    db: AsyncSession,
    actor_id: UUID,
    configuration: InterestCreateConfiguration,
    *,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    validated = InterestCreateConfiguration.model_validate(configuration.model_dump())
    await require_application_tools(db)
    await load_actor(db, actor_id)
    await require_available_interest_topic(db, actor_id, validated)
    identity = command_id or uuid4()
    patch = InterestCreatePatch(
        interest_to_create=InterestCreationValues(id=identity, configuration=validated)
    )
    await require_application_tools(db)
    await load_actor(db, actor_id)
    return build_action_content(
        actor_id,
        INTEREST_CREATE_OPERATION,
        patch,
        {"interest_to_create": None},
        patch.model_dump(mode="json"),
        command_id=identity,
    )


async def interest_creation_fence(
    db: AsyncSession, actor_id: UUID, draft: ApplicationActionDraftContent
) -> None:
    await require_application_tools(db)
    await load_actor(db, actor_id)
    if datetime.now(UTC) >= draft.expires_at:
        raise CommandRejected("EXPIRED")


async def execute_interest_creation(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    creation = InterestCreatePatch.model_validate(draft.intent).interest_to_create
    if (
        creation.id != draft.command_id
        or draft.before != {"interest_to_create": None}
        or draft.intent != draft.after
    ):
        raise ValueError("Interest creation must retain the exact confirmed identity and fields")
    guard = partial(interest_creation_fence, db, actor_id, draft)
    await guard()
    await require_available_interest_topic(db, actor_id, creation.configuration)
    embedding = await prepare_interest_embedding(
        actor_id, creation.id, creation.configuration.topic, guard
    )
    await guard()
    authorize_actor(await UserRepository(db).get_by_id_for_preference_update(actor_id))
    await guard()
    await require_available_interest_topic(db, actor_id, creation.configuration)
    try:
        await create_managed_interest(
            db, actor_id, creation.configuration, embedding=embedding, interest_id=creation.id
        )
    except IntegrityError as exc:
        raise ResourceConflictError("interest", detail={"error_code": "STALE_STATE"}) from exc
    await guard()
    try:
        await db.commit()
    except SQLAlchemyError as exc:
        raise CommandRejected("COMPLETION_UNKNOWN") from exc
    receipt.committed = True
