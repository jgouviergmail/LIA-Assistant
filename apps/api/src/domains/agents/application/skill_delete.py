"""Original durable approval precedes one exact owned skill row commit and bounded cleanup."""

import asyncio
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.authorization import authorize_actor
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.skill_delete_schemas import (
    SkillDeleteInput,
    SkillDeletePatch,
    SkillDeleteSnapshot,
    canonical_skill_deletion,
)
from src.domains.agents.application.skill_delete_spec import SKILL_DELETE_OPERATION
from src.domains.agents.application.skill_read import require_skill_access
from src.domains.agents.application.skill_read_schemas import SkillReadItem
from src.domains.agents.effects.digest import payload_digest
from src.domains.skills.cache import SkillsCache
from src.domains.skills.removal import SkillRemoval, cleanup_removal, observe_removal, stage_removal
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.domains.users.repository import UserRepository
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


def _snapshot(observed: SkillRemoval) -> SkillDeleteSnapshot:
    return SkillDeleteSnapshot(
        request=SkillDeleteInput(skill_id=observed.skill_id),
        skill=SkillReadItem.model_validate(observed.metadata),
        files_present=observed.directory_identity is not None,
        state_digest=payload_digest(
            {
                "directory": str(observed.directory),
                "identity": (
                    list(observed.directory_identity)
                    if observed.directory_identity is not None
                    else None
                ),
                "archive": observed.archive_digest,
            }
        ),
    )


async def prepare_skill_deletion(
    db: AsyncSession, actor_id: UUID, request: SkillDeleteInput, *, command_id: UUID | None = None
) -> ApplicationActionDraftContent:
    desired = SkillDeleteInput.model_validate(request.model_dump())
    await require_skill_access(db, actor_id)
    selected = _snapshot(await observe_removal(db, actor_id, desired.skill_id))
    await require_skill_access(db, actor_id)
    return build_action_content(
        actor_id,
        SKILL_DELETE_OPERATION,
        SkillDeletePatch(skill_to_delete=selected),
        {"skill_to_delete": selected.public_scope()},
        {"skill_to_delete": None},
        command_id=command_id,
    )


async def execute_skill_deletion(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    if draft.actor_id != actor_id or draft.operation_id != SKILL_DELETE_OPERATION.operation_id:
        raise CommandRejected("FORBIDDEN")
    if not canonical_skill_deletion(draft):
        raise CommandRejected("INVALID_INPUT")
    expected = SkillDeletePatch.model_validate(draft.intent).skill_to_delete
    await require_skill_access(db, actor_id)
    authorize_actor(await UserRepository(db).get_by_id_for_preference_update(actor_id))
    actual = await observe_removal(db, actor_id, expected.request.skill_id, lock=True)
    if _snapshot(actual) != expected:
        raise CommandRejected("STALE_STATE")
    await stage_removal(db, actor_id, actual)
    await require_skill_access(db, actor_id)
    if datetime.now(UTC) >= draft.expires_at:
        raise CommandRejected("EXPIRED")
    try:
        await db.commit()
    except (Exception, asyncio.CancelledError) as error:
        raise CommandRejected("COMPLETION_UNKNOWN") from error
    receipt.committed = True
    receipt.values = {
        "skill_to_delete": None,
        "file_cleanup_pending": True,
        "cache_refresh_pending": True,
    }
    await _cleanup(db, actual, receipt)


async def _cleanup(
    db: AsyncSession, observed: SkillRemoval, receipt: PreferenceWriteReceipt
) -> None:
    try:
        cleaned = await cleanup_removal(db, observed)
        await db.commit()
        if receipt.values is not None:
            receipt.values["file_cleanup_pending"] = not cleaned
        await SkillsCache.invalidate_and_reload()
        if receipt.values is not None:
            receipt.values["cache_refresh_pending"] = False
    except (Exception, asyncio.CancelledError) as error:
        logger.warning("skill_removal_cleanup_pending", error_type=type(error).__name__)
