"""One approved macro preserves source partial-write semantics and exact phase boundaries."""

from dataclasses import dataclass
from uuid import UUID

from pydantic import JsonValue
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceConflictError
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.journal_consolidation import (
    consolidation_scope,
    execute_journal_consolidation,
)
from src.domains.agents.application.journal_consolidation_schemas import (
    JournalConsolidationPatch,
    JournalConsolidationScope,
)
from src.domains.agents.application.journal_consolidation_spec import JOURNAL_CONSOLIDATE_OPERATION
from src.domains.agents.application.journal_feedback_schemas import (
    JournalFeedbackPatch,
    JournalFeedbackRequest,
    JournalFeedbackValues,
)
from src.domains.agents.application.journal_feedback_spec import JOURNAL_FEEDBACK_OPERATION
from src.domains.agents.application.journal_settings import journal_settings_fence
from src.domains.journals.creation_commands import (
    JournalCreationCompletionUnknown,
    JournalCreationKind,
    create_managed_journal_entry,
)
from src.domains.journals.portrait_feedback_configuration import portrait_feedback_entry
from src.domains.journals.schemas import JournalEntryResponse
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.infrastructure.llm.usage_guard import enforce_usage_limit


def feedback_public_scope(values: JournalFeedbackValues) -> dict[str, JsonValue]:
    return {
        **values.expected.public_scope(),
        "correction": portrait_feedback_entry(values.request).model_dump(mode="json"),
    }


async def prepare_journal_feedback(
    db: AsyncSession,
    actor_id: UUID,
    request: JournalFeedbackRequest,
    *,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    selected = JournalFeedbackRequest.model_validate(request.model_dump())
    values = JournalFeedbackValues(
        request=selected, expected=await consolidation_scope(db, actor_id)
    )
    public = feedback_public_scope(values)
    return build_action_content(
        actor_id,
        JOURNAL_FEEDBACK_OPERATION,
        JournalFeedbackPatch(journal_feedback=values),
        {"journal_feedback": public},
        {"journal_feedback": {**public, "requested": True}},
        command_id=command_id,
    )


def canonical_journal_feedback(draft: ApplicationActionDraftContent) -> bool:
    selected = JournalFeedbackPatch.model_validate(draft.intent).journal_feedback
    public = feedback_public_scope(selected)
    return draft.before == {"journal_feedback": public} and draft.after == {
        "journal_feedback": {**public, "requested": True}
    }


@dataclass
class _FeedbackCreation:
    db: AsyncSession
    actor_id: UUID
    draft: ApplicationActionDraftContent
    selected: JournalFeedbackValues
    prepared_scope: JournalConsolidationScope | None = None

    async def authority(self) -> None:
        await journal_settings_fence(self.db, self.actor_id, self.draft)

    async def scope(self) -> None:
        current = await consolidation_scope(self.db, self.actor_id)
        old = self.selected.expected
        if (
            not old.corpus.matches(current.corpus)
            or old.source_digest != current.source_digest
            or old.configuration != current.configuration
        ):
            raise ResourceConflictError("journal_feedback", detail={"error_code": "STALE_STATE"})

    async def observe(self, entry: JournalEntryResponse) -> None:
        current = await consolidation_scope(self.db, self.actor_id)
        old = self.selected.expected
        if (
            old.source_digest != current.source_digest
            or old.configuration != current.configuration
            or current.corpus.entries != old.corpus.entries + 1
            or current.corpus.total_chars != old.corpus.total_chars + entry.char_count
            or current.corpus.evidence_events != old.corpus.evidence_events
        ):
            raise ResourceConflictError("journal_feedback", detail={"error_code": "STALE_STATE"})
        self.prepared_scope = current


async def execute_journal_feedback(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    if draft.actor_id != actor_id or draft.operation_id != "journal_portrait.feedback":
        raise CommandRejected("FORBIDDEN")
    if not canonical_journal_feedback(draft):
        raise ValueError("Feedback must retain the exact full correction and source scope")
    selected = JournalFeedbackPatch.model_validate(draft.intent).journal_feedback
    creation = _FeedbackCreation(db, actor_id, draft, selected)
    await creation.authority()
    await creation.scope()
    await enforce_usage_limit(actor_id, layer="journal_consolidation")
    try:
        await create_managed_journal_entry(
            db,
            actor_id,
            portrait_feedback_entry(selected.request),
            entry_id=draft.command_id,
            receipt=receipt,
            check=creation.authority,
            check_scope=creation.scope,
            kind=JournalCreationKind.PORTRAIT_CORRECTION,
            observe=creation.observe,
        )
    except JournalCreationCompletionUnknown as exc:
        raise CommandRejected("COMPLETION_UNKNOWN") from exc
    if creation.prepared_scope is None:
        raise ValueError("The committed correction has no observed maintenance scope")
    await _run_feedback_maintenance(db, actor_id, draft, creation.prepared_scope, receipt)


async def _run_feedback_maintenance(
    db: AsyncSession,
    actor_id: UUID,
    original: ApplicationActionDraftContent,
    scope: JournalConsolidationScope,
    receipt: PreferenceWriteReceipt,
) -> None:
    status: dict[str, JsonValue] = {
        "feedback_saved": True,
        "feedback_entry_id": str(original.command_id),
        "maintenance_status": "not_started",
    }
    receipt.values = {"journal_feedback": status}
    public = scope.public_scope()
    derived = build_action_content(
        actor_id,
        JOURNAL_CONSOLIDATE_OPERATION,
        JournalConsolidationPatch(journal_consolidation=scope),
        {"journal_consolidation": public},
        {"journal_consolidation": {**public, "requested": True}},
        command_id=original.command_id,
    ).model_copy(update={"expires_at": original.expires_at})
    maintenance = PreferenceWriteReceipt()
    try:
        await execute_journal_consolidation(db, actor_id, derived, maintenance)
    except Exception as exc:
        if maintenance.committed and maintenance.values is not None:
            observed = maintenance.values.get("journal_consolidation")
            if isinstance(observed, dict):
                status.update(observed)
                status["maintenance_status"] = observed["status"]
                raise
        status["maintenance_status"] = (
            "completion_unknown"
            if isinstance(exc, CommandRejected) and exc.code == "COMPLETION_UNKNOWN"
            else "failed"
        )
        raise
    if maintenance.values is None:
        raise ValueError("Maintenance returned no observed outcome")
    observed = maintenance.values["journal_consolidation"]
    if not isinstance(observed, dict):
        raise ValueError("Maintenance outcome must be structured")
    receipt.values = {
        "journal_feedback": {**status, **observed, "maintenance_status": observed["status"]}
    }
