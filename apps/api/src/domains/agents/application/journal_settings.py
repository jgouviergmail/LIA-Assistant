"""Exact confirmed journal settings reuse the UI consent/revision settlement."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.journal_catalogue import JOURNAL_SETTINGS_OPERATION
from src.domains.agents.application.journal_queries import require_journal_access
from src.domains.agents.application.journal_settings_schemas import JournalSettingsPatch
from src.domains.journals.preference_commands import (
    JournalSettingsCompletionUnknown,
    update_journal_preferences,
)
from src.domains.users.preference_cas import PreferenceWriteReceipt


async def prepare_journal_settings(
    db: AsyncSession, actor_id: UUID, patch: JournalSettingsPatch, *, command_id: UUID | None = None
) -> ApplicationActionDraftContent:
    desired = JournalSettingsPatch.model_validate(patch.model_dump(exclude_unset=True))
    actor = await require_journal_access(db, actor_id)
    before = {name: getattr(actor, name) for name in desired.model_fields_set}
    JournalSettingsPatch.model_validate(before)
    await require_journal_access(db, actor_id)
    return build_action_content(
        actor_id,
        JOURNAL_SETTINGS_OPERATION,
        desired,
        before,
        desired.model_dump(mode="json", exclude_unset=True),
        command_id=command_id,
    )


async def journal_settings_fence(
    db: AsyncSession, actor_id: UUID, draft: ApplicationActionDraftContent
) -> None:
    await require_journal_access(db, actor_id)
    if datetime.now(UTC) >= draft.expires_at:
        raise CommandRejected("EXPIRED")


async def execute_journal_settings(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    if draft.actor_id != actor_id or draft.operation_id != "journal_settings.update":
        raise CommandRejected("FORBIDDEN")
    desired = JournalSettingsPatch.model_validate(draft.intent)
    JournalSettingsPatch.model_validate(draft.before)
    if draft.intent != draft.after or set(draft.before) != desired.model_fields_set:
        raise ValueError("Journal settings require exact approved fields")
    await journal_settings_fence(db, actor_id, draft)

    async def check() -> None:
        await journal_settings_fence(db, actor_id, draft)

    try:
        await update_journal_preferences(
            db, actor_id, desired, expected=draft.before, receipt=receipt, check=check
        )
    except JournalSettingsCompletionUnknown as exc:
        raise CommandRejected("COMPLETION_UNKNOWN") from exc
