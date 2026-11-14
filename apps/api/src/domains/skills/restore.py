"""Restore the previous version of a person's own skill (lot 14).

The composition of :mod:`src.domains.skills.previous_version` (what is kept,
where) with the import pipeline (how a version enters the live tree): kept
apart so the pipeline, which settles the slot after every commit, never imports
its own caller.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.skills.exceptions import raise_skill_previous_version_unavailable
from src.domains.skills.import_service import SkillImportService, parse_incoming_skill_name
from src.domains.skills.lifecycle_lock import lock_skill_owner
from src.domains.skills.models import Skill, SkillProvenance
from src.domains.skills.previous_version import keeps_previous, previous_slot
from src.domains.users.file_writers import account_file_write
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


def _holds_version(slot: Path, name: str) -> bool:
    """Whether the slot holds a skill package of that very name (blocking read).

    The pipeline names a skill after its frontmatter: a package of another
    name would be installed as ANOTHER skill, never restored as this one.
    """
    skill_md = slot / "SKILL.md"
    if slot.is_symlink() or not skill_md.is_file():
        return False
    found, error = parse_incoming_skill_name({"SKILL.md": skill_md.read_text("utf-8-sig")})
    return error is None and found == name


async def restore_previous(db: AsyncSession, owner_id: UUID, name: str) -> dict[str, Any]:
    """Put the previous version of the person's own skill back.

    A replacement like any other, through the import pipeline (every check,
    the atomic swap, the registration): the version it puts aside becomes the
    previous one, so the restoration can be undone in turn.

    Args:
        db: The request's session; the pipeline commits.
        owner_id: The person.
        name: The skill's name.

    Returns:
        The restored skill (safe subset), as an import returns it.

    Raises:
        ResourceNotFoundError: No skill of the person's own words by that name,
            or no previous version kept. Raised with the owner lock still held,
            as every refused import is: the caller's transaction ends it (the
            route's session rolls back).
    """
    async with account_file_write(db, owner_id):
        # The slot is read under the lock every replacement writes it under.
        await lock_skill_owner(db, owner_id)
        existing = await db.scalar(
            select(Skill.provenance).where(Skill.owner_id == owner_id, Skill.name == name)
        )
        if not keeps_previous(existing, SkillProvenance.AUTHORED):
            raise_skill_previous_version_unavailable(name)
        slot = previous_slot(settings.skills_users_path, owner_id, name)
        if not await asyncio.to_thread(_holds_version, slot, name):
            raise_skill_previous_version_unavailable(name)
        restored = await SkillImportService(db).import_directory(
            slot, owner_id=owner_id, provenance=SkillProvenance.AUTHORED
        )
    logger.info("skill_previous_version_restored", owner_id=str(owner_id))
    return restored
