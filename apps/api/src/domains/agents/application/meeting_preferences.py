"""No recording or model call occurs when reading/changing future meeting defaults."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import AuthorizationError
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.meeting_preference_schemas import (
    MeetingPreferenceInput,
    MeetingPreferenceObservation,
    MeetingPreferencePatch,
    canonical_meeting_preferences,
    requested_meeting_preferences,
)
from src.domains.agents.application.meeting_preference_spec import (
    MEETING_PREFERENCE_UPDATE_OPERATION,
)
from src.domains.feature_switches.guard import require_capability_fresh
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.infrastructure.meeting_preferences import (
    MeetingPreferenceCompletionUnknown,
    MeetingPreferenceState,
    get_meeting_preferences,
)


async def require_meeting_preferences(db: AsyncSession, actor_id: UUID) -> User:
    await require_application_tools(db)
    await require_capability_fresh(db, PlatformCapability.MEETINGS)
    actor = await load_actor(db, actor_id)
    if not settings.meetings_enabled:
        raise AuthorizationError(detail={"error_code": "CAPABILITY_DISABLED"})
    return actor


async def read_meeting_preferences(db: AsyncSession, actor_id: UUID) -> MeetingPreferenceState:
    await require_meeting_preferences(db, actor_id)
    state = await get_meeting_preferences().read(db, actor_id)
    await require_meeting_preferences(db, actor_id)
    return state


async def prepare_meeting_preferences(
    db: AsyncSession,
    actor_id: UUID,
    request: MeetingPreferenceInput,
    *,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    desired = MeetingPreferenceInput.model_validate(request.model_dump(exclude_unset=True))
    before = await read_meeting_preferences(db, actor_id)
    selected = MeetingPreferenceObservation(request=desired, expected=before)
    return build_action_content(
        actor_id,
        MEETING_PREFERENCE_UPDATE_OPERATION,
        MeetingPreferencePatch(meeting_preferences=selected),
        {"meeting_preferences": before.model_dump(mode="json")},
        {"meeting_preferences": requested_meeting_preferences(selected).model_dump(mode="json")},
        command_id=command_id,
    )


async def execute_meeting_preferences(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    if not canonical_meeting_preferences(draft):
        raise ValueError("Meeting settings require the exact confirmed selection")
    selected = MeetingPreferencePatch.model_validate(draft.intent).meeting_preferences

    async def check() -> None:
        if draft.actor_id != actor_id:
            raise CommandRejected("FORBIDDEN")
        await require_meeting_preferences(db, actor_id)
        if datetime.now(UTC) >= draft.expires_at:
            raise CommandRejected("EXPIRED")

    await check()
    try:
        await get_meeting_preferences().write(
            db,
            actor_id,
            requested_meeting_preferences(selected),
            expected=selected.expected,
            receipt=receipt,
            check=check,
        )
    except MeetingPreferenceCompletionUnknown as error:
        raise CommandRejected("COMPLETION_UNKNOWN") from error
