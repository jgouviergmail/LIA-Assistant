"""
Skills repositories — data access for skills and user_skill_states tables.

SkillRepository extends BaseRepository for CRUD on the ``skills`` table.
UserSkillStateRepository does NOT extend BaseRepository because
BaseRepository auto-filters by ``is_active`` (soft-delete semantics),
which conflicts with ``UserSkillState.is_active`` (business toggle).
"""

from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.repository import BaseRepository
from src.domains.skills.models import Skill, UserSkillState


class SkillRepository(BaseRepository[Skill]):
    """Repository for the skills registry table.

    Uses BaseRepository because Skill has no ``is_active`` column
    (admin_enabled is a separate concept, not soft-delete).
    """

    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db, Skill)

    async def get_by_name(self, name: str) -> Skill | None:
        """Get a skill by its unique name."""
        stmt = select(Skill).where(Skill.name == name)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all_system(self, include_disabled: bool = False) -> list[Skill]:
        """Get all system (admin) skills, ordered by name."""
        stmt = select(Skill).where(Skill.is_system.is_(True)).order_by(Skill.name)
        if not include_disabled:
            stmt = stmt.where(Skill.admin_enabled.is_(True))
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_user_skills(self, user_id: UUID) -> list[Skill]:
        """Get all user-imported skills for a specific user."""
        stmt = (
            select(Skill)
            .where(Skill.is_system.is_(False))
            .where(Skill.owner_id == user_id)
            .order_by(Skill.name)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_all_names(self) -> set[str]:
        """Get all registered skill names."""
        stmt = select(Skill.name)
        result = await self.db.execute(stmt)
        return {row[0] for row in result}

    async def delete_by_name(self, name: str) -> None:
        """Delete a skill by name (CASCADE deletes user_skill_states)."""
        stmt = delete(Skill).where(Skill.name == name)
        await self.db.execute(stmt)


class UserSkillStateRepository:
    """Repository for per-user skill activation states.

    Does NOT extend BaseRepository: ``is_active`` here is a business toggle
    (user preference), not a soft-delete flag. BaseRepository would
    auto-filter by ``is_active=True``, silently hiding disabled skills.

    All methods require the caller to commit/flush the session.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_active_skill_names(self, user_id: UUID) -> set[str]:
        """Get names of all active skills for a user (the hot-path query).

        Returns skill names where:
        - user_skill_states.is_active = true
        - For system skills: skill.admin_enabled = true
        - For user skills: always included if is_active = true
        """
        stmt = (
            select(Skill.name)
            .join(UserSkillState, UserSkillState.skill_id == Skill.id)
            .where(UserSkillState.user_id == user_id)
            .where(UserSkillState.is_active.is_(True))
            .where(
                # System skills require admin_enabled, user skills always pass
                (Skill.is_system.is_(False))
                | (Skill.admin_enabled.is_(True))
            )
        )
        result = await self.db.execute(stmt)
        return {row[0] for row in result}

    async def get_states_for_user(
        self,
        user_id: UUID,
        *,
        system_only: bool = False,
        user_only: bool = False,
    ) -> list[UserSkillState]:
        """Get all skill states for a user (with joined skill data)."""
        stmt = (
            select(UserSkillState)
            .join(Skill, UserSkillState.skill_id == Skill.id)
            .where(UserSkillState.user_id == user_id)
            .order_by(Skill.name)
        )
        if system_only:
            stmt = stmt.where(Skill.is_system.is_(True))
        elif user_only:
            stmt = stmt.where(Skill.is_system.is_(False))
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_state(self, user_id: UUID, skill_id: UUID) -> UserSkillState | None:
        """Get a specific user-skill state."""
        stmt = (
            select(UserSkillState)
            .where(UserSkillState.user_id == user_id)
            .where(UserSkillState.skill_id == skill_id)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def toggle(self, user_id: UUID, skill_id: UUID) -> bool:
        """Toggle is_active for a user-skill pair. Returns the new value."""
        state = await self.get_state(user_id, skill_id)
        if not state:
            raise ValueError(f"No state found for user={user_id}, skill={skill_id}")
        state.is_active = not state.is_active
        self.db.add(state)
        return state.is_active

    async def set_all_for_skill(self, skill_id: UUID, *, is_active: bool) -> int:
        """Bulk-update is_active for all users for a given skill.

        Used when admin toggles a system skill on/off.
        Returns the number of rows updated.
        """
        stmt = (
            update(UserSkillState)
            .where(UserSkillState.skill_id == skill_id)
            .values(is_active=is_active)
        )
        result = await self.db.execute(stmt)
        return result.rowcount  # type: ignore[no-any-return,attr-defined]

    async def ensure_states_for_user(self, user_id: UUID) -> int:
        """Create missing user_skill_states for a user.

        Inserts rows for all admin-enabled system skills that the user
        doesn't have a state for yet. Used on user registration and startup sync.
        Handles concurrent inserts gracefully via unique constraint.
        Returns the number of rows created.
        """
        from sqlalchemy.exc import IntegrityError

        # Find system skills that this user doesn't have states for
        existing_skill_ids = select(UserSkillState.skill_id).where(
            UserSkillState.user_id == user_id
        )
        missing_skills_stmt = (
            select(Skill.id)
            .where(Skill.is_system.is_(True))
            .where(Skill.admin_enabled.is_(True))
            .where(Skill.id.not_in(existing_skill_ids))
        )
        result = await self.db.execute(missing_skills_stmt)
        missing_ids = [row[0] for row in result]

        if not missing_ids:
            return 0

        created = 0
        for skill_id in missing_ids:
            try:
                async with self.db.begin_nested():
                    state = UserSkillState(user_id=user_id, skill_id=skill_id, is_active=True)
                    self.db.add(state)
                    await self.db.flush()
                    created += 1
            except IntegrityError:
                # Concurrent insert created the same row — savepoint rolls back,
                # outer transaction continues safely.
                pass

        return created

    async def create_states_for_all_users(self, skill_id: UUID) -> int:
        """Create user_skill_states for all existing users for a new skill.

        Used when admin imports a new system skill.
        Returns the number of rows created.
        """
        from src.domains.auth.models import User

        # Get all user IDs that don't already have a state for this skill
        existing_users = select(UserSkillState.user_id).where(UserSkillState.skill_id == skill_id)
        stmt = select(User.id).where(User.id.not_in(existing_users))
        result = await self.db.execute(stmt)
        user_ids = [row[0] for row in result]

        if not user_ids:
            return 0

        from sqlalchemy.exc import IntegrityError

        created = 0
        for uid in user_ids:
            try:
                async with self.db.begin_nested():
                    state = UserSkillState(user_id=uid, skill_id=skill_id, is_active=True)
                    self.db.add(state)
                    await self.db.flush()
                    created += 1
            except IntegrityError:
                pass

        return created

    async def count_for_user(self, user_id: UUID) -> int:
        """Count skill states for a user."""
        stmt = (
            select(func.count())
            .select_from(UserSkillState)
            .where(UserSkillState.user_id == user_id)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one()
