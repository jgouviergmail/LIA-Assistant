"""Where the skills a person installed from a library came from (ADR-327).

Every read is the CALLER's: a source row is reached through the skill it
belongs to, filtered on the skill's owner, so another account's installation
reads as absent. The writes happen inside the import's own transaction
(``after_register``), so a skill and its provenance are committed together or
not at all.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.skill_library.models import SkillLibrarySource
from src.domains.skills.models import Skill, SkillProvenance


@dataclass(frozen=True)
class InstalledSkill:
    """One skill the person installed from a library, with where it came from."""

    skill_id: UUID
    name: str
    portal: str | None
    repository: str
    ref: str
    path: str
    registry_id: str | None
    commit_sha: str
    tree_sha: str


@dataclass(frozen=True)
class SourceRecord:
    """What an install records beside the skill it registered."""

    portal: str | None
    origin: str
    repository: str
    ref: str
    path: str
    registry_id: str | None
    commit_sha: str
    tree_sha: str


def _installed_statement(owner_id: UUID) -> Select[tuple[UUID, str, SkillLibrarySource]]:
    return (
        select(Skill.id, Skill.name, SkillLibrarySource)
        .join(SkillLibrarySource, SkillLibrarySource.skill_id == Skill.id)
        .where(Skill.owner_id == owner_id)
        .where(Skill.provenance == SkillProvenance.LIBRARY.value)
        .order_by(Skill.name, Skill.id)
    )


def _installed(skill_id: UUID, name: str, source: SkillLibrarySource) -> InstalledSkill:
    return InstalledSkill(
        skill_id=skill_id,
        name=name,
        portal=source.portal,
        repository=source.repository,
        ref=source.ref,
        path=source.path,
        registry_id=source.registry_id,
        commit_sha=source.commit_sha,
        tree_sha=source.tree_sha,
    )


class SkillLibraryRepository:
    """The installed skills of one account, and the provenance an install writes."""

    def __init__(self, db: AsyncSession) -> None:
        """Bind the repository to a session."""
        self.db = db

    async def installed(self, owner_id: UUID) -> list[InstalledSkill]:
        """Every skill ``owner_id`` installed from a library, by name."""
        rows = (await self.db.execute(_installed_statement(owner_id))).all()
        return [_installed(skill_id, name, source) for skill_id, name, source in rows]

    async def installed_skill(self, owner_id: UUID, skill_id: UUID) -> InstalledSkill | None:
        """One of them, or None when it is not ``owner_id``'s library skill."""
        statement = _installed_statement(owner_id).where(Skill.id == skill_id)
        row = (await self.db.execute(statement)).first()
        return _installed(row[0], row[1], row[2]) if row else None

    async def record(self, skill_id: UUID, source: SourceRecord) -> None:
        """Write or replace the provenance of ``skill_id`` (one row per skill)."""
        values = {
            "skill_id": skill_id,
            "portal": source.portal,
            "origin": source.origin,
            "repository": source.repository,
            "ref": source.ref,
            "path": source.path,
            "registry_id": source.registry_id,
            "commit_sha": source.commit_sha,
            "tree_sha": source.tree_sha,
        }
        statement = pg_insert(SkillLibrarySource).values(**values)
        statement = statement.on_conflict_do_update(
            index_elements=[SkillLibrarySource.skill_id],
            set_={
                **{k: statement.excluded[k] for k in values if k != "skill_id"},
                "updated_at": datetime.now(UTC),
            },
        )
        await self.db.execute(statement)
