"""Original durable approval precedes putting back exactly the version a person's skill replaced.

The proposal seals the person's own skill and a private witness of the version put aside (every
file of its slot, digested, and the instant it was put aside). The confirmation observes them again
under the account's file lock and the owner's row lock — the order the restoration itself takes
them — and only then goes through the settings' own door (``skills.restore.restore_previous``):
the import pipeline's checks, its atomic swap, its registration. The version it puts aside
becomes restorable in turn (lot 14). Nothing of a version's words enters the proposal.
"""

import asyncio
import hashlib
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import BaseAPIException
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.authorization import authorize_actor
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.skill_read import observe_visible_skill, require_skill_access
from src.domains.agents.application.skill_restore_schemas import (
    SkillRestoreInput,
    SkillRestorePatch,
    SkillRestoreSnapshot,
    canonical_skill_restore,
)
from src.domains.agents.application.skill_restore_spec import SKILL_RESTORE_OPERATION
from src.domains.agents.effects.digest import payload_digest
from src.domains.skills.lifecycle_lock import lock_skill_owner
from src.domains.skills.models import SkillProvenance
from src.domains.skills.previous_version import keeps_previous, previous_slot
from src.domains.skills.restore import restore_previous
from src.domains.users.file_writers import account_file_write
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.domains.users.repository import UserRepository
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


def _slot_witness(slot: Path) -> tuple[datetime, str] | None:
    """When a slot's version was put aside, and a digest of every file it holds (blocking).

    ``None`` for no version: no slot, a link, or no ``SKILL.md``. Links inside are never
    followed, and their target is never read.
    """
    if slot.is_symlink() or not (slot / "SKILL.md").is_file():
        return None
    files: list[tuple[str, str]] = []
    for directory, _dirs, names in os.walk(slot, followlinks=False):
        for name in names:
            path = Path(directory, name)
            if path.is_symlink() or not path.is_file():
                continue
            files.append(
                (path.relative_to(slot).as_posix(), hashlib.sha256(path.read_bytes()).hexdigest())
            )
    put_aside_at = datetime.fromtimestamp(slot.stat(follow_symlinks=False).st_mtime, tz=UTC)
    return put_aside_at, payload_digest(sorted(files))


async def _observe(db: AsyncSession, actor_id: UUID, skill_id: UUID) -> SkillRestoreSnapshot:
    """The person's own skill and the version that would come back, as they stand now."""
    skill = await observe_visible_skill(db, actor_id, skill_id)
    if skill.scope != "user" or not keeps_previous(skill.provenance, SkillProvenance.AUTHORED):
        raise CommandRejected("NOT_FOUND_OR_UNAUTHORIZED")
    slot = previous_slot(settings.skills_users_path, actor_id, skill.name)
    witness = await asyncio.to_thread(_slot_witness, slot)
    if witness is None:
        raise CommandRejected("NOT_FOUND_OR_UNAUTHORIZED")
    put_aside_at, files = witness
    return SkillRestoreSnapshot(
        request=SkillRestoreInput(skill_id=skill_id),
        skill=skill,
        previous_version_at=put_aside_at,
        state_digest=payload_digest({"skill": skill.model_dump(mode="json"), "files": files}),
    )


def restore_draft(
    actor_id: UUID, selected: SkillRestoreSnapshot, *, command_id: UUID | None = None
) -> ApplicationActionDraftContent:
    """The exact proposal: the skill as it stands, then the version that comes back."""
    return build_action_content(
        actor_id,
        SKILL_RESTORE_OPERATION,
        SkillRestorePatch(skill_to_restore=selected),
        {"skill_to_restore": selected.public_scope()},
        {"skill_to_restore": selected.restored_scope()},
        command_id=command_id,
    )


async def prepare_skill_restore(
    db: AsyncSession, actor_id: UUID, request: SkillRestoreInput, *, command_id: UUID | None = None
) -> ApplicationActionDraftContent:
    desired = SkillRestoreInput.model_validate(request.model_dump())
    await require_skill_access(db, actor_id)
    selected = await _observe(db, actor_id, desired.skill_id)
    await require_skill_access(db, actor_id)
    return restore_draft(actor_id, selected, command_id=command_id)


async def execute_skill_restore(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    if draft.actor_id != actor_id or draft.operation_id != SKILL_RESTORE_OPERATION.operation_id:
        raise CommandRejected("FORBIDDEN")
    if not canonical_skill_restore(draft):
        raise CommandRejected("INVALID_INPUT")
    expected = SkillRestorePatch.model_validate(draft.intent).skill_to_restore
    await require_skill_access(db, actor_id)
    async with account_file_write(db, actor_id):
        # The restoration's own order: the account's file lock, then the owner's row.
        await lock_skill_owner(db, actor_id)
        authorize_actor(await UserRepository(db).get_by_id_for_preference_update(actor_id))
        if await _observe(db, actor_id, expected.request.skill_id) != expected:
            raise CommandRejected("STALE_STATE")
        await require_skill_access(db, actor_id)
        if datetime.now(UTC) >= draft.expires_at:
            raise CommandRejected("EXPIRED")
        try:
            await restore_previous(db, actor_id, expected.skill.name)
        except BaseAPIException as refused:
            # The pipeline refused the version before its swap: nothing changed.
            raise CommandRejected("CONSTRAINT_VIOLATION") from refused
        except (Exception, asyncio.CancelledError) as error:
            # The pipeline commits: past its swap, the outcome is not known.
            raise CommandRejected("COMPLETION_UNKNOWN") from error
    receipt.committed = True
    receipt.values = {"skill_to_restore": expected.restored_scope()}
    logger.info("application_skill_restored", actor_id=str(actor_id))
