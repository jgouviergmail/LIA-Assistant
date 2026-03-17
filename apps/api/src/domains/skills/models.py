"""
Skills domain models — normalized 2-table design.

Table ``skills`` is the skill registry (synced from disk).
Table ``user_skill_states`` stores per-user activation state.

Disk remains the source of truth for skill content (instructions, scripts,
resources, technical metadata). The DB is the source of truth for display
metadata (description, descriptions), admin visibility (admin_enabled),
and per-user activation (is_active).
"""

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models import BaseModel

if TYPE_CHECKING:
    from src.domains.auth.models import User


class Skill(BaseModel):
    """Registered skill (system or user-owned).

    Synced from disk on startup and when skills are imported/deleted/reloaded.
    The ``name`` matches the skill directory name on disk.
    """

    __tablename__ = "skills"

    name: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
        index=True,
        doc="Skill identifier, matches directory name on disk",
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
    description: Mapped[str] = mapped_column(
        String(1024),
        nullable=False,
        doc="English description (DB is source of truth for display)",
    )
    descriptions: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        doc="Translated descriptions keyed by language code: {fr, en, es, de, it, zh}",
    )

    # Relationships
    owner: Mapped["User | None"] = relationship(
        "User",
        foreign_keys=[owner_id],
        lazy="selectin",
    )
    user_skill_states: Mapped[list["UserSkillState"]] = relationship(
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

    # Relationships
    skill: Mapped["Skill"] = relationship(
        back_populates="user_skill_states",
        lazy="selectin",
    )
    user: Mapped["User"] = relationship(
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
