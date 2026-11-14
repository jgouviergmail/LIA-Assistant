"""The ONE previous version a replaced skill keeps: the rule, the slot, its settlement (lot 14).

Replacing a skill — a new upload, an edit in the chat — used to destroy the
version it replaced: the import pipeline parks the old directory in its staging
area for a rollback and lets it go with the staging. A person who regretted a
change had no way back (ADR-165 amendment 2026-11-13).

What is kept: the version the LAST replacement replaced, and only when both
sides are the person's own words (``authored``). A third party's bytes — an
address, a library, a plugin, a peer — are never restored as the person's own:
that would launder the trust decision of ADR-327, and a managed skill changes
through its own channel only. Every other replacement leaves no previous
version, so the slot never outlives the incarnation it belongs to.

Where: ``<users>/<owner>/.lia-previous/<name>/``, beside the person's skills
under a reserved name no skill can take. The disk is the record (one fact, one
place): the listing reads the slots, and a slot's time is WHEN its version was
replaced. Every write happens inside the import's account fence and owner lock.

Restoring (``skills/restore.py``, which composes this module with the import
pipeline) is itself a replacement through that pipeline: the version it puts
aside becomes the previous one, so a restoration can be undone in turn.
"""

from __future__ import annotations

import asyncio
import os
import shutil
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import select

from src.core.config import settings
from src.core.constants import SKILLS_PREVIOUS_VERSIONS_DIR
from src.domains.skills.import_disk import finish_disk_step
from src.domains.skills.models import Skill, SkillProvenance
from src.infrastructure.observability.logging import get_logger

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)


def keeps_previous(existing: str | None, incoming: SkillProvenance | None) -> bool:
    """Whether a replacement keeps the version it replaces.

    Args:
        existing: The provenance of the person's skill being replaced, or None
            when nothing is replaced.
        incoming: The import's channel; None is a chat edit, which keeps the
            provenance of what it edits.

    Returns:
        True only when the person's own skill is replaced by their own words.
    """
    authored = SkillProvenance.AUTHORED.value
    return existing == authored and (incoming is None or incoming.value == authored)


def previous_slot(users_root: str, owner_id: UUID, name: str) -> Path:
    """Where the previous version of a person's skill lives.

    Args:
        users_root: ``SKILLS_USERS_PATH``.
        owner_id: The person.
        name: The skill's validated name.

    Returns:
        The slot's directory (it may not exist).
    """
    return Path(users_root) / str(owner_id) / SKILLS_PREVIOUS_VERSIONS_DIR / name


def settle_slot(backup_dir: Path, slot: Path, *, keep: bool) -> None:
    """After a committed replacement, make the slot hold what it replaced, or nothing.

    Called through a disk step (blocking I/O). The version parked by the swap
    moves into the slot, replacing the older one; a replacement that keeps
    nothing empties the slot, so an older version of another incarnation can
    never be offered.

    Args:
        backup_dir: Where the swap parked the replaced version (may not exist:
            a first import replaced nothing).
        slot: :func:`previous_slot` of the skill.
        keep: :func:`keeps_previous` for this replacement.
    """
    if slot.exists():
        shutil.rmtree(slot)
    if not keep or not backup_dir.is_dir():
        return
    slot.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(backup_dir), str(slot))
    # A moved tree keeps its files' times: stamp the slot with the replacement.
    os.utime(slot)


def discard_previous(users_root: str, owner_id: UUID, name: str) -> None:
    """Remove a skill's previous version (blocking): the skill itself is gone."""
    slot = previous_slot(users_root, owner_id, name)
    if slot.is_dir() and not slot.is_symlink():
        shutil.rmtree(slot)


async def replacement_keeps(
    db: AsyncSession, owner_id: UUID | None, name: str, incoming: SkillProvenance | None
) -> bool:
    """Whether the import about to commit keeps the version it replaces.

    Read under the import's owner lock, before its swap, from the row the
    replacement is about to overwrite.

    Args:
        db: The import's session.
        owner_id: The person, or None for a system import (never kept).
        name: The skill's validated name.
        incoming: The import's channel (None: a chat edit).

    Returns:
        :func:`keeps_previous` of the person's current skill of that name.
    """
    if owner_id is None:
        return False
    existing = await db.scalar(
        select(Skill.provenance).where(Skill.owner_id == owner_id, Skill.name == name)
    )
    return keeps_previous(existing, incoming)


async def settle_previous(
    backup_dir: Path, users_root: str, owner_id: UUID | None, name: str, *, keep: bool
) -> bool:
    """Settle the slot after a COMMITTED replacement; the import stays committed whatever happens.

    A disk failure here loses at most the way back, never the new version: it
    is logged with its facts and the import answers its success.

    Args:
        backup_dir: Where the swap parked the replaced version.
        users_root: ``SKILLS_USERS_PATH``.
        owner_id: The person, or None for a system import (nothing to settle).
        name: The skill's validated name.
        keep: :func:`replacement_keeps` for this replacement.

    Returns:
        Whether a cancellation arrived meanwhile — the caller propagates it once
        its own post-commit work is done.
    """
    if owner_id is None:
        return False
    slot = previous_slot(users_root, owner_id, name)
    try:
        return await finish_disk_step(partial(settle_slot, backup_dir, slot, keep=keep))
    except OSError as error:
        logger.warning(
            "skill_previous_version_unsettled",
            owner_id=str(owner_id),
            kept=keep,
            error_type=type(error).__name__,
        )
        current = asyncio.current_task()
        return current is not None and current.cancelling() > 0


async def forget_previous(owner_id: UUID, name: str) -> None:
    """Remove the previous version of a skill whose removal was just cleaned up.

    A leftover is invisible (no skill lists it) and the next import of that
    name empties the slot anyway: a failure is logged, never raised.
    """
    try:
        await asyncio.to_thread(discard_previous, settings.skills_users_path, owner_id, name)
    except OSError as error:
        logger.warning(
            "skill_previous_version_not_discarded",
            owner_id=str(owner_id),
            error_type=type(error).__name__,
        )


def restorable_at(listed: dict[str, Any], previous: dict[str, datetime]) -> datetime | None:
    """When a listed skill's previous version was replaced, if the person may restore it.

    Args:
        listed: One entry of ``SkillPreferenceService.get_user_visible_skills``.
        previous: :func:`previous_versions` of the person.

    Returns:
        The slot's time for the person's own skill of their own words, else None.
    """
    if listed["scope"] != "user" or not keeps_previous(
        listed["provenance"], SkillProvenance.AUTHORED
    ):
        return None
    return previous.get(listed["name"])


def previous_versions(users_root: str, owner_id: UUID) -> dict[str, datetime]:
    """The person's skills that have a previous version, with when it was replaced.

    Called through ``asyncio.to_thread`` (one directory read).

    Args:
        users_root: ``SKILLS_USERS_PATH``.
        owner_id: The person.

    Returns:
        Skill name → the instant its previous version was replaced (UTC).
    """
    root = Path(users_root) / str(owner_id) / SKILLS_PREVIOUS_VERSIONS_DIR
    if not root.is_dir():
        return {}
    found: dict[str, datetime] = {}
    with os.scandir(root) as entries:
        for entry in entries:
            if entry.is_dir(follow_symlinks=False) and Path(entry.path, "SKILL.md").is_file():
                stamp = entry.stat(follow_symlinks=False).st_mtime
                found[entry.name] = datetime.fromtimestamp(stamp, tz=UTC)
    return found
