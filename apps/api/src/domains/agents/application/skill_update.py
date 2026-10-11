"""A personal skill switch is an exact confirmed value, never a replayable inversion."""

import asyncio
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.authorization import authorize_actor
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.skill_read import observe_visible_skill, require_skill_access
from src.domains.agents.application.skill_update_schemas import (
    SkillUpdateInput,
    SkillUpdateObservation,
    SkillUpdatePatch,
    canonical_skill_update,
)
from src.domains.agents.application.skill_update_spec import SKILL_UPDATE_OPERATION
from src.domains.skills.personal_state import personal_state, set_personal_state
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.domains.users.repository import UserRepository


async def prepare_skill_update(
    db: AsyncSession, actor_id: UUID, request: SkillUpdateInput, *, command_id: UUID | None = None
) -> ApplicationActionDraftContent:
    desired = SkillUpdateInput.model_validate(request.model_dump())
    await require_skill_access(db, actor_id)
    expected = await observe_visible_skill(db, actor_id, desired.skill_id)
    await require_skill_access(db, actor_id)
    return build_action_content(
        actor_id,
        SKILL_UPDATE_OPERATION,
        SkillUpdatePatch(
            skill_personal_state=SkillUpdateObservation(request=desired, expected=expected)
        ),
        {"skill_personal_state": expected.model_dump(mode="json")},
        {
            "skill_personal_state": expected.model_copy(
                update={"enabled_for_user": desired.enabled}
            ).model_dump(mode="json")
        },
        command_id=command_id,
    )


async def execute_skill_update(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    if draft.actor_id != actor_id or draft.operation_id != SKILL_UPDATE_OPERATION.operation_id:
        raise CommandRejected("FORBIDDEN")
    if not canonical_skill_update(draft):
        raise CommandRejected("INVALID_INPUT")
    selected = SkillUpdatePatch.model_validate(draft.intent).skill_personal_state
    await require_skill_access(db, actor_id)
    authorize_actor(await UserRepository(db).get_by_id_for_preference_update(actor_id))
    await personal_state(db, actor_id, selected.request.skill_id)
    if await observe_visible_skill(db, actor_id, selected.request.skill_id) != selected.expected:
        raise CommandRejected("STALE_STATE")
    if datetime.now(UTC) >= draft.expires_at:
        raise CommandRejected("EXPIRED")
    await set_personal_state(
        db, actor_id, selected.request.skill_id, enabled=selected.request.enabled
    )
    await require_skill_access(db, actor_id)
    if datetime.now(UTC) >= draft.expires_at:
        raise CommandRejected("EXPIRED")
    try:
        await db.commit()
    except (Exception, asyncio.CancelledError) as error:
        raise CommandRejected("COMPLETION_UNKNOWN") from error
    receipt.committed = True
    receipt.no_op = selected.expected.enabled_for_user == selected.request.enabled
    receipt.values = draft.after
