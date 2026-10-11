"""Exact confirmed psyche preferences share source locks, comparisons and commit semantics."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.psyche_catalogue import PSYCHE_SETTINGS_OPERATION
from src.domains.agents.application.psyche_queries import require_psyche_access
from src.domains.agents.application.psyche_settings_schemas import PsycheSettingsPatch
from src.domains.psyche.preference_commands import (
    PsycheSettingsCompletionUnknown,
    update_psyche_preferences,
)
from src.domains.users.preference_cas import PreferenceWriteReceipt


async def prepare_psyche_settings(
    db: AsyncSession, actor_id: UUID, patch: PsycheSettingsPatch, *, command_id: UUID | None = None
) -> ApplicationActionDraftContent:
    desired = PsycheSettingsPatch.model_validate(patch.model_dump(exclude_unset=True))
    actor = await require_psyche_access(db, actor_id)
    before = {name: getattr(actor, name) for name in desired.model_fields_set}
    PsycheSettingsPatch.model_validate(before)
    await require_psyche_access(db, actor_id)
    return build_action_content(
        actor_id,
        PSYCHE_SETTINGS_OPERATION,
        desired,
        before,
        desired.model_dump(mode="json", exclude_unset=True),
        command_id=command_id,
    )


async def psyche_settings_fence(
    db: AsyncSession, actor_id: UUID, draft: ApplicationActionDraftContent
) -> None:
    await require_psyche_access(db, actor_id)
    if datetime.now(UTC) >= draft.expires_at:
        raise CommandRejected("EXPIRED")


async def execute_psyche_settings(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    if draft.actor_id != actor_id or draft.operation_id != "psyche_settings.update":
        raise CommandRejected("FORBIDDEN")
    desired = PsycheSettingsPatch.model_validate(draft.intent)
    PsycheSettingsPatch.model_validate(draft.before)
    if draft.intent != draft.after or set(draft.before) != desired.model_fields_set:
        raise ValueError("Psyche settings require the exact confirmed before/after scope")
    await psyche_settings_fence(db, actor_id, draft)

    async def check() -> None:
        await psyche_settings_fence(db, actor_id, draft)

    try:
        await update_psyche_preferences(
            db, actor_id, desired, expected=draft.before, receipt=receipt, check=check
        )
    except PsycheSettingsCompletionUnknown as exc:
        raise CommandRejected("COMPLETION_UNKNOWN") from exc
