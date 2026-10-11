"""Interest preferences use exact source snapshots and a commit-time authorization fence."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import DEFAULT_USER_DISPLAY_TIMEZONE
from src.core.exceptions import ResourceConflictError
from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.interest_settings_schemas import InterestSettingsPatch
from src.domains.agents.application.preparation import _preference_content
from src.domains.interests.preference_commands import (
    InterestSettingsCompletionUnknown,
    update_interest_settings,
)
from src.domains.interests.read_models import user_to_settings_response
from src.domains.users.preference_cas import PreferenceWriteReceipt


async def prepare_interest_settings(
    db: AsyncSession,
    actor_id: UUID,
    patch: InterestSettingsPatch,
    *,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    desired = InterestSettingsPatch.model_validate(patch.model_dump(exclude_unset=True))
    await require_application_tools(db)
    actor = await load_actor(db, actor_id)
    before = user_to_settings_response(actor).model_dump(
        mode="json", include=desired.model_fields_set
    )
    InterestSettingsPatch.model_validate(before)
    return _preference_content(actor_id, desired, before, command_id=command_id).model_copy(
        update={"user_timezone": actor.timezone or DEFAULT_USER_DISPLAY_TIMEZONE}
    )


async def interest_settings_fence(
    db: AsyncSession, actor_id: UUID, draft: ApplicationActionDraftContent
) -> None:
    await require_application_tools(db)
    actor = await load_actor(db, actor_id)
    if {"interests_notify_start_hour", "interests_notify_end_hour"} & draft.intent.keys():
        if (actor.timezone or DEFAULT_USER_DISPLAY_TIMEZONE) != draft.user_timezone:
            raise ResourceConflictError("interest_settings", detail={"error_code": "STALE_STATE"})
    if datetime.now(UTC) >= draft.expires_at:
        raise CommandRejected("EXPIRED")


async def execute_interest_settings(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    desired = InterestSettingsPatch.model_validate(draft.intent)
    if draft.intent != draft.after or set(draft.before) != desired.model_fields_set:
        raise ValueError("Interest settings require the exact approved before/after scope")
    InterestSettingsPatch.model_validate(draft.before)
    await interest_settings_fence(db, actor_id, draft)

    async def check() -> None:
        await interest_settings_fence(db, actor_id, draft)

    try:
        await update_interest_settings(
            db, actor_id, desired, expected=draft.before, receipt=receipt, check=check
        )
    except InterestSettingsCompletionUnknown as exc:
        raise CommandRejected("COMPLETION_UNKNOWN") from exc
