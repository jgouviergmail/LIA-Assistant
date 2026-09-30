"""Where a skill installed from a library came from (ADR-327).

One row per installed skill, 1:1 with ``skills`` and cascading with it: the
repository and the folder it was read from, the ref it follows and the commit
it was installed at. The folder's git tree SHA is what an update check
compares — two commits that leave the folder untouched are the same skill.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models import BaseModel

#: Column comments, shared with the migration — the replay check compares them.
PORTAL_COMMENT = "The library it was found on (a declared portal key); NULL = a repository address."
ORIGIN_COMMENT = "Where its content was read (a declared origin key, e.g. github)."
REPOSITORY_COMMENT = "The repository the folder lives in, as the origin names it (owner/repo)."
REF_COMMENT = "The ref an update follows: HEAD, or the branch or tag the person gave."
PATH_COMMENT = "The skill's folder inside the repository ('' = the repository root)."
REGISTRY_ID_COMMENT = "The portal's own identifier of the skill, when it came from a portal."
COMMIT_SHA_COMMENT = "The commit the installed content was read at."
TREE_SHA_COMMENT = "The folder's git tree SHA at that commit — what an update check compares."


class SkillLibrarySource(BaseModel):
    """The provenance of one skill installed from a library."""

    __tablename__ = "skill_library_sources"

    skill_id: Mapped[UUID] = mapped_column(
        ForeignKey("skills.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
        doc="The installed skill; the row goes with it.",
    )
    portal: Mapped[str | None] = mapped_column(String(40), nullable=True, comment=PORTAL_COMMENT)
    origin: Mapped[str] = mapped_column(String(20), nullable=False, comment=ORIGIN_COMMENT)
    repository: Mapped[str] = mapped_column(String(200), nullable=False, comment=REPOSITORY_COMMENT)
    ref: Mapped[str] = mapped_column(String(200), nullable=False, comment=REF_COMMENT)
    path: Mapped[str] = mapped_column(String(500), nullable=False, comment=PATH_COMMENT)
    registry_id: Mapped[str | None] = mapped_column(
        String(300), nullable=True, comment=REGISTRY_ID_COMMENT
    )
    commit_sha: Mapped[str] = mapped_column(String(64), nullable=False, comment=COMMIT_SHA_COMMENT)
    tree_sha: Mapped[str] = mapped_column(String(64), nullable=False, comment=TREE_SHA_COMMENT)

    def __repr__(self) -> str:
        return (
            f"<SkillLibrarySource(skill_id={self.skill_id}, origin='{self.origin}', "
            f"repository='{self.repository}', path='{self.path}')>"
        )
