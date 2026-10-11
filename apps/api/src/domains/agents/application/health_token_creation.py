"""Exact non-secret creation intent remains bound to the authenticated browser."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.application_origin import ApplicationOrigin
from src.core.exceptions import AuthorizationError
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.health_queries import require_health_access
from src.domains.agents.application.health_token_creation_schemas import (
    HealthTokenCreatePatch,
    HealthTokenCreateRequest,
)
from src.domains.agents.application.health_token_creation_spec import HEALTH_TOKEN_CREATE_OPERATION


async def authorize_health_token_creation(
    db: AsyncSession, actor_id: UUID, origin: ApplicationOrigin | None
) -> None:
    await require_health_access(db, actor_id, data=False)
    if origin is None:
        raise AuthorizationError(detail={"error_code": "SESSION_UNAVAILABLE"})
    await origin.require_session(actor_id, expected_binding=origin.binding_id)
    await require_health_access(db, actor_id, data=False)


async def prepare_health_token_creation(
    db: AsyncSession,
    actor_id: UUID,
    request: HealthTokenCreateRequest,
    *,
    origin: ApplicationOrigin | None,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    selected = HealthTokenCreateRequest.model_validate(request.model_dump())
    await authorize_health_token_creation(db, actor_id, origin)
    patch = HealthTokenCreatePatch(health_token_to_create=selected)
    return build_action_content(
        actor_id,
        HEALTH_TOKEN_CREATE_OPERATION,
        patch,
        {"health_token_to_create": None},
        patch.model_dump(mode="json"),
        command_id=command_id,
    )


def canonical_health_token_creation(draft: ApplicationActionDraftContent) -> bool:
    HealthTokenCreatePatch.model_validate(draft.intent)
    return draft.before == {"health_token_to_create": None} and draft.after == draft.intent
