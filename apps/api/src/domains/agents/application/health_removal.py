"""Approved source erasure cannot expand silently to changed or newly ingested samples."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.health_queries import require_health_access
from src.domains.agents.application.health_removal_schemas import (
    HealthRemovalPatch,
    HealthRemovalRequest,
)
from src.domains.agents.application.health_removal_spec import HEALTH_REMOVAL_OPERATION
from src.domains.health_metrics.removal_commands import (
    HealthRemovalCompletionUnknown,
    remove_health_samples,
)
from src.domains.health_metrics.removal_snapshot import health_removal_snapshot
from src.domains.users.preference_cas import PreferenceWriteReceipt


async def prepare_health_removal(
    db: AsyncSession,
    actor_id: UUID,
    request: HealthRemovalRequest,
    *,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    selected = HealthRemovalRequest.model_validate(request.model_dump())
    await require_health_access(db, actor_id, data=False)
    expected = await health_removal_snapshot(db, actor_id, selected.kind)
    await require_health_access(db, actor_id, data=False)
    return build_action_content(
        actor_id,
        HEALTH_REMOVAL_OPERATION,
        HealthRemovalPatch(health_samples_to_delete=expected),
        {"health_samples_to_delete": expected.public_scope()},
        {"health_samples_to_delete": None},
        command_id=command_id,
    )


def canonical_health_removal(draft: ApplicationActionDraftContent) -> bool:
    selected = HealthRemovalPatch.model_validate(draft.intent).health_samples_to_delete
    HealthRemovalRequest.model_validate({"kind": selected.kind})
    return draft.before == {
        "health_samples_to_delete": selected.public_scope()
    } and draft.after == {"health_samples_to_delete": None}


async def execute_health_removal(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    if draft.actor_id != actor_id or draft.operation_id != "health_samples.delete":
        raise CommandRejected("FORBIDDEN")
    if not canonical_health_removal(draft):
        raise ValueError("Health erasure requires exact confirmed owned scope")
    selected = HealthRemovalPatch.model_validate(draft.intent).health_samples_to_delete

    async def check() -> None:
        await require_health_access(db, actor_id, data=False)
        if datetime.now(UTC) >= draft.expires_at:
            raise CommandRejected("EXPIRED")

    await check()
    try:
        await remove_health_samples(
            db, actor_id, selected.kind, expected=selected, receipt=receipt, check=check
        )
    except HealthRemovalCompletionUnknown as exc:
        raise CommandRejected("COMPLETION_UNKNOWN") from exc
