"""Confirmed native mutations delegate to the guarded original UI write owner."""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceConflictError
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.meeting_preferences import require_meeting_preferences
from src.domains.agents.application.meeting_template_schemas import (
    TemplateCreatePatch,
    TemplateDeletePatch,
    TemplateUpdatePatch,
    canonical_template_creation,
    canonical_template_removal,
    canonical_template_replacement,
)
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.infrastructure.meeting_templates import (
    TemplateCommitUnknown,
    TemplateWriteConfirmation,
    TemplateWriteFacts,
    get_meeting_templates,
)


def _check(
    db: AsyncSession, actor_id: UUID, draft: ApplicationActionDraftContent
) -> Callable[[], Awaitable[None]]:
    async def check() -> None:
        if draft.actor_id != actor_id:
            raise CommandRejected("FORBIDDEN")
        await require_meeting_preferences(db, actor_id)
        if datetime.now(UTC) >= draft.expires_at:
            raise CommandRejected("EXPIRED")

    return check


async def _run(operation: Awaitable[object]) -> None:
    try:
        await operation
    except TemplateCommitUnknown as error:
        raise CommandRejected("COMPLETION_UNKNOWN") from error


async def execute_template_creation(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    if not canonical_template_creation(draft):
        raise ValueError("Template creation requires the exact confirmed facts")
    selected = TemplateCreatePatch.model_validate(draft.intent).meeting_template_create
    check = _check(db, actor_id, draft)
    await check()
    actor = await require_meeting_preferences(db, actor_id)

    async def validate(facts: TemplateWriteFacts) -> None:
        if facts != selected.expected:
            raise ResourceConflictError("meeting_template", detail={"error_code": "STALE_STATE"})

    confirmation = TemplateWriteConfirmation(
        validate=validate, check=check, receipt=receipt, created_id=selected.created_id
    )
    await _run(
        get_meeting_templates().create(
            db, actor_id, selected.request, actor.language, confirmation=confirmation
        )
    )


async def execute_template_replacement(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    if not canonical_template_replacement(draft):
        raise ValueError("Template replacement requires the exact confirmed facts")
    selected = TemplateUpdatePatch.model_validate(draft.intent).meeting_template_update
    check = _check(db, actor_id, draft)
    await check()

    async def validate(facts: TemplateWriteFacts) -> None:
        if facts.current != selected.expected or facts.values != selected.desired.model_dump(
            mode="json"
        ):
            raise ResourceConflictError("meeting_template", detail={"error_code": "STALE_STATE"})

    confirmation = TemplateWriteConfirmation(validate=validate, check=check, receipt=receipt)
    await _run(
        get_meeting_templates().update(
            db, actor_id, selected.request.ref, selected.desired, confirmation=confirmation
        )
    )


async def execute_template_removal(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    if not canonical_template_removal(draft):
        raise ValueError("Template removal requires the exact confirmed facts")
    selected = TemplateDeletePatch.model_validate(draft.intent).meeting_template_delete
    check = _check(db, actor_id, draft)
    await check()

    async def validate(facts: TemplateWriteFacts) -> None:
        if (
            facts.current != selected.expected
            or facts.default_template_ref != selected.default_template_ref
        ):
            raise ResourceConflictError("meeting_template", detail={"error_code": "STALE_STATE"})

    confirmation = TemplateWriteConfirmation(validate=validate, check=check, receipt=receipt)
    await _run(
        get_meeting_templates().delete(
            db, actor_id, selected.request.ref, confirmation=confirmation
        )
    )
