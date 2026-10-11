"""The native request delegates generation and publication to the guarded source workflow."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AuthorizationError, ResourceConflictError
from src.core.i18n import normalize_language
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.journal_consolidation_schemas import (
    JournalConsolidationPatch,
    JournalConsolidationRequest,
    JournalConsolidationScope,
)
from src.domains.agents.application.journal_consolidation_spec import JOURNAL_CONSOLIDATE_OPERATION
from src.domains.agents.application.journal_queries import require_journal_access
from src.domains.agents.application.journal_settings import journal_settings_fence
from src.domains.agents.effects.digest import payload_digest
from src.domains.journals.consolidation_controls import (
    ConsolidationCompletionUnknown,
    ConsolidationControlRefused,
    ConsolidationControls,
    installed_consolidation_controls,
)
from src.domains.journals.consolidation_lifecycle import ConsolidationAttempt
from src.domains.journals.consolidation_service import consolidate_journals_for_user
from src.domains.journals.removal_snapshot import journal_removal_snapshot
from src.domains.journals.schemas import JournalSettingsUpdate
from src.domains.journals.source_state import portrait_source_state
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.infrastructure.database.session import get_db_context
from src.infrastructure.llm.usage_guard import enforce_usage_limit


async def consolidation_scope(db: AsyncSession, actor_id: UUID) -> JournalConsolidationScope:
    actor = await require_journal_access(db, actor_id)
    if not actor.journals_enabled:
        raise AuthorizationError(detail={"error_code": "FORBIDDEN"})
    corpus = await journal_removal_snapshot(db, actor, None)
    sources = await portrait_source_state(db, actor)
    configuration = JournalSettingsUpdate.model_validate(
        {name: getattr(actor, name) for name in JournalSettingsUpdate.model_fields}
    ).model_dump(mode="json")
    await require_journal_access(db, actor_id)
    return JournalConsolidationScope(
        corpus=corpus, source_digest=payload_digest(sources), configuration=configuration
    )


async def prepare_journal_consolidation(
    db: AsyncSession,
    actor_id: UUID,
    request: JournalConsolidationRequest,
    *,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    JournalConsolidationRequest.model_validate(request.model_dump())
    scope = await consolidation_scope(db, actor_id)
    public = scope.public_scope()
    return build_action_content(
        actor_id,
        JOURNAL_CONSOLIDATE_OPERATION,
        JournalConsolidationPatch(journal_consolidation=scope),
        {"journal_consolidation": public},
        {"journal_consolidation": {**public, "requested": True}},
        command_id=command_id,
    )


def canonical_journal_consolidation(draft: ApplicationActionDraftContent) -> bool:
    scope = JournalConsolidationPatch.model_validate(draft.intent).journal_consolidation
    public = scope.public_scope()
    return draft.before == {"journal_consolidation": public} and draft.after == {
        "journal_consolidation": {**public, "requested": True}
    }


@dataclass(frozen=True)
class _ApprovedConsolidation:
    actor_id: UUID
    draft: ApplicationActionDraftContent
    selected: JournalConsolidationScope
    receipt: PreferenceWriteReceipt

    async def authority(self, current: AsyncSession) -> None:
        await journal_settings_fence(current, self.actor_id, self.draft)
        actor = await require_journal_access(current, self.actor_id)
        if not actor.journals_enabled:
            raise AuthorizationError(detail={"error_code": "FORBIDDEN"})

    async def work(self, current: AsyncSession) -> None:
        await self.authority(current)
        observed = await consolidation_scope(current, self.actor_id)
        if (
            not self.selected.corpus.matches(observed.corpus)
            or self.selected.source_digest != observed.source_digest
            or self.selected.configuration != observed.configuration
        ):
            raise ResourceConflictError(
                "journal_consolidation", detail={"error_code": "STALE_STATE"}
            )

    async def embedding(self) -> None:
        async with get_db_context() as current:
            await self.work(current)

    def committed(self, count: int, status: str) -> None:
        self.receipt.committed = True
        # A source no-op still spends tokens and advances the maintenance watermark.
        self.receipt.no_op = False
        self.receipt.values = {
            "journal_consolidation": {"actions_applied": count, "status": status}
        }


async def execute_journal_consolidation(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    if draft.actor_id != actor_id or draft.operation_id != "journals.consolidate":
        raise CommandRejected("FORBIDDEN")
    if not canonical_journal_consolidation(draft):
        raise ValueError("Consolidation requires the exact confirmed source scope")
    selected = JournalConsolidationPatch.model_validate(draft.intent).journal_consolidation
    approved = _ApprovedConsolidation(actor_id, draft, selected, receipt)
    await approved.work(db)
    await enforce_usage_limit(actor_id, layer="journal_consolidation")
    language = normalize_language((await require_journal_access(db, actor_id)).language)
    await db.commit()  # The source run owns independent short transactions.
    attempt = ConsolidationAttempt()
    controls = ConsolidationControls(
        actor_id, approved.work, approved.authority, approved.embedding, approved.committed
    )
    try:
        with installed_consolidation_controls(controls):
            await consolidate_journals_for_user(
                actor_id, None, None, language, manual=True, attempt=attempt
            )
    except ConsolidationControlRefused as exc:
        raise exc.cause from exc
    except (ConsolidationCompletionUnknown, SQLAlchemyError) as exc:
        raise CommandRejected("COMPLETION_UNKNOWN") from exc
    if not receipt.committed:
        raise CommandRejected(
            "STALE_STATE" if attempt.status in {"busy", "stale"} else "EXECUTION_FAILED"
        )
