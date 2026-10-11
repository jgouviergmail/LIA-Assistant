"""Exact source-derived manual journal editing is approved before embeddings."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.journal_queries import require_journal_access
from src.domains.agents.application.journal_settings import journal_settings_fence
from src.domains.agents.application.journal_update_schemas import (
    JournalUpdatePatch,
    JournalUpdateRequest,
    JournalUpdateValues,
)
from src.domains.agents.application.journal_update_spec import JOURNAL_UPDATE_OPERATION
from src.domains.journals.update_commands import (
    JournalUpdateCompletionUnknown,
    read_manual_journal_update,
    update_managed_journal_entry,
)
from src.domains.users.preference_cas import PreferenceWriteReceipt


async def prepare_journal_update(
    db: AsyncSession,
    actor_id: UUID,
    request: JournalUpdateRequest,
    *,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    selected = JournalUpdateRequest.model_validate(request.model_dump(exclude_unset=True))
    await require_journal_access(db, actor_id)
    expected, projection = await read_manual_journal_update(
        db, actor_id, selected.entry_id, selected.changes
    )
    await require_journal_access(db, actor_id)
    patch = JournalUpdatePatch(
        journal_configuration=JournalUpdateValues(
            expected=expected,
            changes=selected.changes,
            projected=projection.after,
            invalidates_portrait=projection.invalidates_portrait,
        )
    )
    return build_action_content(
        actor_id,
        JOURNAL_UPDATE_OPERATION,
        patch,
        {"journal_entry": projection.before},
        {"journal_entry": projection.after},
        command_id=command_id,
    )


def canonical_journal_update(draft: ApplicationActionDraftContent) -> bool:
    selected = JournalUpdatePatch.model_validate(draft.intent).journal_configuration
    return (
        selected.expected.entry is not None
        and draft.before
        == {
            "journal_entry": selected.expected.entry.model_dump(
                mode="json", exclude={"updated_at", "injection_count", "last_injected_at"}
            )
        }
        and draft.after == {"journal_entry": selected.projected}
    )


async def execute_journal_update(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    if draft.actor_id != actor_id or draft.operation_id != "journal_entries.update":
        raise CommandRejected("FORBIDDEN")
    if not canonical_journal_update(draft):
        raise ValueError("Journal editing requires the exact approved source transition")
    selected = JournalUpdatePatch.model_validate(draft.intent).journal_configuration
    entry_id = selected.expected.entry_id
    if entry_id is None:
        raise ValueError("An edit selects exactly one owned entry")
    await journal_settings_fence(db, actor_id, draft)

    async def check() -> None:
        await journal_settings_fence(db, actor_id, draft)

    try:
        await update_managed_journal_entry(
            db,
            actor_id,
            entry_id,
            selected.changes,
            operation_id=draft.command_id,
            expected=selected.expected,
            expected_projection=selected.projected,
            receipt=receipt,
            check=check,
        )
    except JournalUpdateCompletionUnknown as exc:
        raise CommandRejected("COMPLETION_UNKNOWN") from exc
