"""A confirmed owned source token identity cannot be silently changed by model input."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.health_queries import require_health_access
from src.domains.agents.application.health_token_schemas import (
    HealthTokenRevokePatch,
    HealthTokenRevokeRequest,
)
from src.domains.agents.application.health_token_spec import HEALTH_TOKEN_REVOKE_OPERATION
from src.domains.health_metrics.token_commands import (
    HealthTokenRevocationCompletionUnknown,
    read_owned_health_token,
    revoke_managed_health_token,
)
from src.domains.users.preference_cas import PreferenceWriteReceipt


async def prepare_health_token_revocation(
    db: AsyncSession,
    actor_id: UUID,
    request: HealthTokenRevokeRequest,
    *,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    selected = HealthTokenRevokeRequest.model_validate(request.model_dump())
    await require_health_access(db, actor_id, data=False)
    expected = await read_owned_health_token(db, actor_id, selected.token_id)
    await require_health_access(db, actor_id, data=False)
    return build_action_content(
        actor_id,
        HEALTH_TOKEN_REVOKE_OPERATION,
        HealthTokenRevokePatch(health_token_to_revoke=expected),
        {"health_token_to_revoke": expected.public_scope()},
        {"health_token_to_revoke": {**expected.public_scope(), "revoked": True}},
        command_id=command_id,
    )


def canonical_health_token_revocation(draft: ApplicationActionDraftContent) -> bool:
    selected = HealthTokenRevokePatch.model_validate(draft.intent).health_token_to_revoke
    return draft.before == {"health_token_to_revoke": selected.public_scope()} and draft.after == {
        "health_token_to_revoke": {**selected.public_scope(), "revoked": True}
    }


async def execute_health_token_revocation(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    if draft.actor_id != actor_id or draft.operation_id != "health_token.revoke":
        raise CommandRejected("FORBIDDEN")
    if not canonical_health_token_revocation(draft):
        raise ValueError("Token revocation requires the exact approved source identity")
    selected = HealthTokenRevokePatch.model_validate(draft.intent).health_token_to_revoke

    async def check() -> None:
        await require_health_access(db, actor_id, data=False)
        if datetime.now(UTC) >= draft.expires_at:
            raise CommandRejected("EXPIRED")

    await check()
    try:
        await revoke_managed_health_token(db, actor_id, selected, receipt, check)
    except HealthTokenRevocationCompletionUnknown as exc:
        raise CommandRejected("COMPLETION_UNKNOWN") from exc
