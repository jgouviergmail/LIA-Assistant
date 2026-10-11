"""Fresh owner, report, quota and consent checks precede the original send."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import RateLimitError, ResourceConflictError
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.meeting_email_schemas import (
    MeetingEmailInput,
    MeetingEmailPatch,
    canonical_meeting_email,
    email_states,
)
from src.domains.agents.application.meeting_email_spec import MEETING_EMAIL_OPERATION
from src.domains.agents.application.meeting_preferences import require_meeting_preferences
from src.domains.email_share.rate_limits import rate_limit_email_share
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.infrastructure.meeting_email import (
    MeetingEmailCompletionUnknown,
    MeetingEmailConfirmation,
    MeetingEmailSnapshot,
    get_meeting_email,
)


async def prepare_meeting_email(
    db: AsyncSession, actor_id: UUID, request: MeetingEmailInput, *, command_id: UUID | None = None
) -> ApplicationActionDraftContent:
    await require_meeting_preferences(db, actor_id)
    selected = await get_meeting_email().snapshot(db, actor_id, request.meeting_id)
    await require_meeting_preferences(db, actor_id)
    return build_action_content(
        actor_id,
        MEETING_EMAIL_OPERATION,
        MeetingEmailPatch(meeting_email_send=selected),
        *email_states(selected),
        command_id=command_id,
    )


async def execute_meeting_email(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    if not canonical_meeting_email(draft):
        raise CommandRejected("INVALID_INPUT")
    selected = MeetingEmailPatch.model_validate(draft.intent).meeting_email_send

    async def check() -> None:
        if actor_id != draft.actor_id:
            raise CommandRejected("FORBIDDEN")
        await require_meeting_preferences(db, actor_id)
        if datetime.now(UTC) >= draft.expires_at:
            raise CommandRejected("EXPIRED")

    async def validate(actual: MeetingEmailSnapshot) -> None:
        if actual != selected:
            raise ResourceConflictError("meeting_email", detail={"error_code": "STALE_STATE"})

    actor = await require_meeting_preferences(db, actor_id)
    await check()
    try:
        await rate_limit_email_share(actor)
    except RateLimitError:
        raise CommandRejected("RATE_LIMIT_EXCEEDED") from None
    try:
        await get_meeting_email().send(
            db,
            actor_id,
            selected.meeting_id,
            MeetingEmailConfirmation(validate=validate, check=check, receipt=receipt),
        )
    except MeetingEmailCompletionUnknown:
        raise CommandRejected("COMPLETION_UNKNOWN") from None
