"""
Skills domain models — normalized 2-table design.

Table ``skills`` is the skill registry (synced from disk).
Table ``user_skill_states`` stores per-user activation state.

Disk remains the source of truth for skill content (instructions, scripts,
resources, technical metadata). The DB is the source of truth for display
metadata (description, descriptions), admin visibility (admin_enabled),
per-user activation (is_active) and per-user use (use_count, last_used_at,
counted since usage_counted_since).
"""

from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Final
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models import BaseModel

if TYPE_CHECKING:
    from src.domains.users.models import User


class SkillProvenance(StrEnum):
    """How a skill's content arrived — the basis of what it may do (ADR-327).

    Recorded at every import by the CHANNEL that brought it, never guessed
    from the content. ``url``, ``plugin`` and ``library`` are THIRD-PARTY: LIA
    fetched them from someone else, so their instructions never drive a model
    holding the person's tools, and their outputs are neutralised.
    """

    #: Shipped with the instance or imported by the administrator.
    SYSTEM = "system"
    #: Uploaded by the person, or generated with them in chat.
    AUTHORED = "authored"
    #: Explicit peer transfer; disabled on receipt, authored-equivalent on activation.
    PEER = "peer"
    #: Fetched by LIA from an https address the person gave.
    URL = "url"
    #: Installed by an Agent Plugins package (ADR-225).
    PLUGIN = "plugin"
    #: Installed from a skill library (ADR-327).
    LIBRARY = "library"


#: Written elsewhere and fetched by LIA: restricted at run time (ADR-327).
THIRD_PARTY_PROVENANCES: Final = frozenset(
    {SkillProvenance.URL, SkillProvenance.PLUGIN, SkillProvenance.LIBRARY}
)
#: Owned by the channel that installed them: only that channel replaces them
#: (a plugin update, a library update) — never an upload or a chat edit.
MANAGED_PROVENANCES: Final = frozenset({SkillProvenance.PLUGIN, SkillProvenance.LIBRARY})


def skill_is_third_party(provenance: str, *, peer_authored: bool) -> bool:
    return provenance in THIRD_PARTY_PROVENANCES and not peer_authored


class Skill(BaseModel):
    """Registered skill (system or user-owned).

    Synced from disk on startup and when skills are imported/deleted/reloaded.
    The ``name`` matches the skill directory name on disk.
    """

    __tablename__ = "skills"

    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        doc=(
            "Skill identifier, matches directory name on disk. Unique per SCOPE "
            "(ADR-327): among system skills, and among one owner's skills."
        ),
    )
    is_system: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        doc="True = system (admin-managed) skill, False = user-imported skill",
    )
    owner_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        doc="NULL for system skills, user_id for user-imported skills",
    )
    admin_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
        doc="Admin visibility toggle. When False, skill is hidden from all non-superusers.",
    )
    plugin_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("user_plugins.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Agent Plugins provenance (ADR-225); NULL = manually imported",
        doc=(
            "Provenance link to the Agent Plugins package that installed this "
            "skill (ADR-225). NULL = manually imported. SET NULL on raw plugin "
            "deletion turns it back into an ordinary user skill; the clean "
            "group uninstall is service-driven."
        ),
    )
    provenance: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=SkillProvenance.AUTHORED.value,
        server_default=SkillProvenance.AUTHORED.value,
        comment=(
            "How the content arrived: system | authored | url | plugin | library "
            "(ADR-327). url, plugin and library are third-party."
        ),
    )
    description: Mapped[str] = mapped_column(
        String(1024),
        nullable=False,
        doc="English description (DB is source of truth for display)",
    )
    peer_authored: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        doc="Server-written execution grant for a peer-delivered plugin child; never frontmatter.",
    )
    descriptions: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        doc="Translated descriptions keyed by language code: {fr, en, es, de, it, zh}",
    )

    # Relationships
    owner: Mapped[User | None] = relationship(
        "User",
        foreign_keys=[owner_id],
        lazy="selectin",
    )
    user_skill_states: Mapped[list[UserSkillState]] = relationship(
        back_populates="skill",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index(
            "ix_skills_system_enabled",
            "is_system",
            "admin_enabled",
            postgresql_where="is_system = true",
        ),
        # ADR-327: a name is unique per scope. Two people may each keep a
        # ``pdf``; a system name stays unique among system skills.
        Index(
            "uq_skills_system_name",
            "name",
            unique=True,
            postgresql_where="owner_id IS NULL",
        ),
        Index(
            "uq_skills_owner_name",
            "owner_id",
            "name",
            unique=True,
            postgresql_where="owner_id IS NOT NULL",
        ),
        # What the two indexes above rely on: a system skill has no owner and a
        # person's skill has one. The owner FK CASCADEs (the row goes with its
        # owner), so no foreign-key action can leave a row between the two.
        CheckConstraint(
            "is_system = (owner_id IS NULL)",
            name="ck_skills_system_has_no_owner",
        ),
        # ADR-327: the provenance vocabulary, and a system skill is the only
        # one of system provenance (the owner FK cascades, so no FK action
        # moves a row between the two).
        CheckConstraint(
            "provenance IN ('system', 'authored', 'url', 'plugin', 'library', 'peer') "
            "AND (provenance = 'system') = is_system",
            name="ck_skills_provenance",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<Skill(id={self.id}, name='{self.name}', "
            f"is_system={self.is_system}, admin_enabled={self.admin_enabled})>"
        )


class UserSkillState(BaseModel):
    """Per-user activation state for a skill.

    One row per (user, skill) pair. ``is_active`` is the user's personal toggle.
    Created automatically when:
    - A system skill is imported by admin (for all existing users)
    - A user imports their own skill
    - A new user registers (for all admin-enabled system skills)
    """

    __tablename__ = "user_skill_states"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="User this state belongs to",
    )
    skill_id: Mapped[UUID] = mapped_column(
        ForeignKey("skills.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="Skill this state refers to",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
        doc="True = skill is active for this user",
    )
    # Lot 14 (skills/usage.py). The comments are the migration's, word for word.
    use_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="Runs in which this skill was used for this user, one per run.",
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When a run last used this skill for this user; NULL = never.",
    )
    last_used_run_id: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="The run last counted, so one run counts once.",
    )
    usage_counted_since: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        comment="When counting began: this migration for an existing state, creation after.",
    )
    dormancy_kept_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When the person last kept this skill after the unused-skill proposal.",
    )

    # Relationships
    skill: Mapped[Skill] = relationship(
        back_populates="user_skill_states",
        lazy="selectin",
    )
    user: Mapped[User] = relationship(
        "User",
        foreign_keys=[user_id],
        back_populates="skill_states",
        lazy="selectin",
    )

    __table_args__ = (
        Index(
            "ix_user_skill_states_user_skill",
            "user_id",
            "skill_id",
            unique=True,
        ),
        Index(
            "ix_user_skill_states_active",
            "user_id",
            postgresql_where="is_active = true",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<UserSkillState(user_id={self.user_id}, "
            f"skill_id={self.skill_id}, is_active={self.is_active})>"
        )
