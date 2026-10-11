"""Creation is approved before embeddings and committed under current authority."""

from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.journal_create_schemas import (
    JournalCreateConfiguration,
    JournalCreatePatch,
    JournalCreationValues,
)
from src.domains.agents.application.journal_creation_spec import JOURNAL_CREATE_OPERATION
from src.domains.agents.application.journal_queries import require_journal_access
from src.domains.agents.application.journal_settings import journal_settings_fence
from src.domains.journals.creation_commands import (
    JournalCreationCompletionUnknown,
    create_managed_journal_entry,
)
from src.domains.users.preference_cas import PreferenceWriteReceipt


async def prepare_journal_creation(
    db: AsyncSession,
    actor_id: UUID,
    configuration: JournalCreateConfiguration,
    *,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    selected = JournalCreateConfiguration.model_validate(configuration.model_dump())
    await require_journal_access(db, actor_id)
    identity = command_id or uuid4()
    patch = JournalCreatePatch(
        journal_entry_to_create=JournalCreationValues(id=identity, configuration=selected)
    )
    return build_action_content(
        actor_id,
        JOURNAL_CREATE_OPERATION,
        patch,
        {"journal_entry_to_create": None},
        patch.model_dump(mode="json"),
        command_id=identity,
    )


async def execute_journal_creation(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    selected = JournalCreatePatch.model_validate(draft.intent).journal_entry_to_create
    if draft.actor_id != actor_id or draft.operation_id != "journal_entries.create":
        raise CommandRejected("FORBIDDEN")
    if (
        selected.id != draft.command_id
        or draft.before != {"journal_entry_to_create": None}
        or draft.intent != draft.after
    ):
        raise ValueError("Creation must retain the approved identity and complete configuration")
    await journal_settings_fence(db, actor_id, draft)

    async def check() -> None:
        await journal_settings_fence(db, actor_id, draft)

    try:
        await create_managed_journal_entry(
            db, actor_id, selected.configuration, entry_id=selected.id, receipt=receipt, check=check
        )
    except JournalCreationCompletionUnknown as exc:
        raise CommandRejected("COMPLETION_UNKNOWN") from exc
