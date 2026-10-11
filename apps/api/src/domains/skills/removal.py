"""Owned skill removal commits rows before cleanup and never removes a changed directory."""

import asyncio
import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.skills.archive import _root, create_skill_archive
from src.domains.skills.cache import SkillsCache
from src.domains.skills.lifecycle_lock import lock_skill_owner
from src.domains.skills.models import Skill, UserSkillState
from src.domains.skills.preference_service import SkillPreferenceService
from src.domains.skills.ui_projection import merge_skill_metadata


@dataclass(frozen=True)
class SkillRemoval:
    actor_id: UUID
    skill_id: UUID
    name: str
    directory: Path
    directory_identity: tuple[int, int] | None
    archive_digest: str | None
    metadata: dict[str, object]


async def observe_removal(
    db: AsyncSession, actor_id: UUID, skill_id: UUID, *, lock: bool = False
) -> SkillRemoval:
    statement = (
        select(Skill)
        .where(Skill.id == skill_id, Skill.owner_id == actor_id, Skill.is_system.is_(False))
        .execution_options(populate_existing=True)
    )
    if lock:
        statement = statement.with_for_update()
    row = await db.scalar(statement)
    if row is None or row.plugin_id is not None:
        raise ValueError("Owned removable skill unavailable")
    foreign_state = await db.scalar(
        select(UserSkillState.id)
        .where(UserSkillState.skill_id == skill_id, UserSkillState.user_id != actor_id)
        .limit(1)
    )
    if foreign_state is not None:
        raise ValueError("Skill state scope inconsistent")
    cached = SkillsCache.get_exact(row.name, str(actor_id))
    if cached is None or cached.get("owner_id") != str(actor_id) or cached.get("scope") != "user":
        raise ValueError("Skill cache scope unavailable")
    visible = await SkillPreferenceService(db).get_user_visible_skills(actor_id)
    data = next((item for item in visible if item["skill_id"] == str(skill_id)), None)
    if data is None:
        raise ValueError("Skill state unavailable")
    directory = _root(cached)
    try:
        before = directory.stat(follow_symlinks=False)
    except FileNotFoundError:
        return SkillRemoval(
            actor_id,
            skill_id,
            row.name,
            directory,
            None,
            None,
            merge_skill_metadata(data, enabled_for_user=data["is_active"]),
        )
    archive = await asyncio.to_thread(create_skill_archive, cached)
    after = directory.stat(follow_symlinks=False)
    if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
        raise ValueError("Skill directory replaced")
    return SkillRemoval(
        actor_id,
        skill_id,
        row.name,
        directory,
        (after.st_dev, after.st_ino),
        hashlib.sha256(archive).hexdigest(),
        merge_skill_metadata(data, enabled_for_user=data["is_active"]),
    )


async def stage_removal(db: AsyncSession, actor_id: UUID, observed: SkillRemoval) -> None:
    if observed.actor_id != actor_id:
        raise ValueError("Skill owner mismatch")
    await lock_skill_owner(db, actor_id)
    current = await observe_removal(db, actor_id, observed.skill_id, lock=True)
    if current != observed:
        raise ValueError("Skill changed before removal")
    await SkillPreferenceService(db).delete_skill(observed.skill_id)
    await db.flush()


def _cleanup_removal(observed: SkillRemoval) -> bool:
    cached = SkillsCache.get_exact(observed.name, str(observed.actor_id))
    if cached is None:
        return False
    directory = _root(cached)
    if observed.directory_identity is None:
        return directory == observed.directory and not directory.exists()
    current = directory.stat(follow_symlinks=False)
    if (
        directory != observed.directory
        or (current.st_dev, current.st_ino) != observed.directory_identity
    ):
        return False
    if hashlib.sha256(create_skill_archive(cached)).hexdigest() != observed.archive_digest:
        return False
    # Both resolved absolute paths must stay inside the configured account tree.
    from src.core.config import settings

    allowed = (Path(settings.skills_users_path) / str(observed.actor_id)).resolve()
    target = directory.resolve()
    if target == allowed or not target.is_relative_to(allowed):
        return False
    shutil.rmtree(target)
    return True


async def cleanup_removal(db: AsyncSession, observed: SkillRemoval) -> bool:
    """The caller supplies a NEW post-commit transaction; imports use this same owner lock."""
    await lock_skill_owner(db, observed.actor_id)
    replaced = await db.scalar(
        select(Skill.id).where(Skill.owner_id == observed.actor_id, Skill.name == observed.name)
    )
    if replaced is not None:
        return False
    try:
        return await asyncio.to_thread(_cleanup_removal, observed)
    except OSError, ValueError:
        return False
