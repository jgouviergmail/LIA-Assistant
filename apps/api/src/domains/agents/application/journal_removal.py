"""Complete journal erasure is conditional on the exact human-approved scope."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.journal_queries import require_journal_access
from src.domains.agents.application.journal_removal_schemas import (
    JournalDeletePatch,
    JournalDeleteRequest,
)
from src.domains.agents.application.journal_removal_spec import JOURNAL_DELETE_OPERATION
from src.domains.agents.application.journal_settings import journal_settings_fence
from src.domains.journals.removal_commands import (
    JournalRemovalCompletionUnknown,
    remove_journal_entries,
)
from src.domains.journals.removal_snapshot import journal_removal_snapshot
from src.domains.users.preference_cas import PreferenceWriteReceipt


async def prepare_journal_removal(
    db: AsyncSession,
    actor_id: UUID,
    request: JournalDeleteRequest,
    *,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    selected = JournalDeleteRequest.model_validate(request.model_dump())
    actor = await require_journal_access(db, actor_id)
    expected = await journal_removal_snapshot(db, actor, selected.entry_id)
    await require_journal_access(db, actor_id)
    return build_action_content(
        actor_id,
        JOURNAL_DELETE_OPERATION,
        JournalDeletePatch(journal_entries_to_delete=expected),
        {"journal_entries_to_delete": expected.public_scope()},
        {"journal_entries_to_delete": None},
        command_id=command_id,
    )


def canonical_journal_removal(draft: ApplicationActionDraftContent) -> bool:
    selected = JournalDeletePatch.model_validate(draft.intent).journal_entries_to_delete
    return draft.before == {
        "journal_entries_to_delete": selected.public_scope()
    } and draft.after == {"journal_entries_to_delete": None}


async def execute_journal_removal(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    if draft.actor_id != actor_id or draft.operation_id != "journal_entries.delete":
        raise CommandRejected("FORBIDDEN")
    if not canonical_journal_removal(draft):
        raise ValueError("Journal deletion requires the exact approved complete scope")
    selected = JournalDeletePatch.model_validate(draft.intent).journal_entries_to_delete
    await journal_settings_fence(db, actor_id, draft)

    async def check() -> None:
        await journal_settings_fence(db, actor_id, draft)

    try:
        await remove_journal_entries(
            db, actor_id, selected.entry_id, expected=selected, receipt=receipt, check=check
        )
    except JournalRemovalCompletionUnknown as exc:
        raise CommandRejected("COMPLETION_UNKNOWN") from exc
