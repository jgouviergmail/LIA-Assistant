"""
Skills preference service — business logic for skill state management.

Centralizes all DB operations for the skills and user_skill_states tables.
The SkillsCache remains the source of truth for skill content (instructions,
scripts, resources, technical metadata). This service manages display metadata
(descriptions), admin visibility (admin_enabled), and per-user activation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.skills.models import Skill, UserSkillState
from src.domains.skills.repository import SkillRepository, UserSkillStateRepository
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


@dataclass
class SyncResult:
    """Result of a disk-to-DB synchronization."""

    created: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)


class SkillPreferenceService:
    """Service layer for skill preferences (DB state management).

    Instantiated per-request with the current DB session.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.skill_repo = SkillRepository(db)
        self.state_repo = UserSkillStateRepository(db)

    # ------------------------------------------------------------------
    # Hot-path query (used per chat request by the agent flow)
    # ------------------------------------------------------------------

    async def get_active_skills_for_user(self, user_id: UUID) -> set[str]:
        """Get set of active skill names for a user.

        This is the single entry point replacing the old disabled_skills merge.
        Returns skill names where is_active=true AND (is_system=false OR admin_enabled=true).
        """
        return await self.state_repo.get_active_skill_names(user_id)

    # ------------------------------------------------------------------
    # User actions
    # ------------------------------------------------------------------

    async def toggle_user_skill(self, user_id: UUID, skill_name: str) -> bool:
        """Toggle a skill's is_active for a user. Returns the new is_active value.

        Raises ValueError if skill or state not found.
        """
        skill = await self.skill_repo.get_by_name(skill_name)
        if not skill:
            raise ValueError(f"Skill '{skill_name}' not found")

        new_value = await self.state_repo.toggle(user_id, skill.id)
        logger.info(
            "skill_toggled",
            skill_name=skill_name,
            user_id=str(user_id),
            is_active=new_value,
        )
        return new_value

    # ------------------------------------------------------------------
    # Admin actions
    # ------------------------------------------------------------------

    async def admin_toggle_skill(self, skill_name: str, *, enable: bool) -> None:
        """Admin enables/disables a system skill for all users.

        Updates skill.admin_enabled AND bulk-updates all user_skill_states.
        """
        skill = await self.skill_repo.get_by_name(skill_name)
        if not skill:
            raise ValueError(f"Skill '{skill_name}' not found")
        if not skill.is_system:
            raise ValueError(f"Skill '{skill_name}' is not a system skill")

        skill.admin_enabled = enable
        self.db.add(skill)

        count = await self.state_repo.set_all_for_skill(skill.id, is_active=enable)
        logger.info(
            "system_skill_toggled",
            skill_name=skill_name,
            admin_enabled=enable,
            users_updated=count,
        )

    async def admin_update_description(
        self,
        skill_name: str,
        description: str,
        descriptions: dict[str, str] | None = None,
    ) -> Skill:
        """Update a skill's description and translations in DB."""
        skill = await self.skill_repo.get_by_name(skill_name)
        if not skill:
            raise ValueError(f"Skill '{skill_name}' not found")

        skill.description = description
        if descriptions is not None:
            skill.descriptions = descriptions
        self.db.add(skill)

        logger.info(
            "skill_description_updated",
            skill_name=skill_name,
            languages=list(descriptions.keys()) if descriptions else [],
        )
        return skill

    # ------------------------------------------------------------------
    # Registration / provisioning
    # ------------------------------------------------------------------

    async def ensure_user_skills(self, user_id: UUID) -> int:
        """Create missing user_skill_states for a new or existing user.

        Inserts rows for all admin-enabled system skills the user doesn't
        have states for yet. Called on registration and OAuth user creation.
        Returns the number of rows created.
        """
        count = await self.state_repo.ensure_states_for_user(user_id)
        if count > 0:
            logger.info(
                "user_skills_provisioned",
                user_id=str(user_id),
                skills_created=count,
            )
        return count

    # ------------------------------------------------------------------
    # Import / delete
    # ------------------------------------------------------------------

    async def create_skill_for_import(
        self,
        name: str,
        description: str,
        *,
        is_system: bool,
        owner_id: UUID | None = None,
        descriptions: dict[str, str] | None = None,
    ) -> Skill:
        """Register a newly imported skill in DB and create user_skill_states.

        For system skills: creates states for ALL existing users.
        For user skills: creates a state for the owner only.
        """
        # Check if skill already exists (re-import case)
        existing = await self.skill_repo.get_by_name(name)
        if existing:
            existing.description = description
            existing.descriptions = descriptions
            self.db.add(existing)
            await self.db.flush()
            return existing

        skill = Skill(
            name=name,
            is_system=is_system,
            owner_id=owner_id,
            admin_enabled=True,
            description=description,
            descriptions=descriptions,
        )
        self.db.add(skill)
        await self.db.flush()  # Get skill.id

        if is_system:
            count = await self.state_repo.create_states_for_all_users(skill.id)
            logger.info(
                "system_skill_imported",
                skill_name=name,
                users_provisioned=count,
            )
        elif owner_id:
            state = UserSkillState(
                user_id=owner_id,
                skill_id=skill.id,
                is_active=True,
            )
            self.db.add(state)
            logger.info("user_skill_imported", skill_name=name, user_id=str(owner_id))

        return skill

    async def delete_skill(self, skill_name: str) -> None:
        """Delete a skill from DB (CASCADE deletes user_skill_states)."""
        await self.skill_repo.delete_by_name(skill_name)
        logger.info("skill_deleted_from_db", skill_name=skill_name)

    # ------------------------------------------------------------------
    # Disk ↔ DB sync
    # ------------------------------------------------------------------

    async def sync_from_disk(self) -> SyncResult:
        """Synchronize DB skills table with SkillsCache (loaded from disk).

        Creates new skills, removes orphans, updates descriptions.
        Also ensures all users have states for admin-enabled system skills.
        On first run after migration, reads _legacy_disabled_skills to preserve
        user preferences from the old disabled_skills JSONB column.
        """
        from sqlalchemy import select as sa_select

        from src.domains.auth.models import User
        from src.domains.skills.cache import SkillsCache

        result = SyncResult()
        cache_skills = SkillsCache.get_all()
        if not cache_skills:
            return result

        db_names = await self.skill_repo.get_all_names()
        cache_by_name: dict[str, dict[str, Any]] = {s["name"]: s for s in cache_skills}

        # 1. Create skills that exist on disk but not in DB
        for name, cached in cache_by_name.items():
            if name not in db_names:
                is_system = cached["scope"] == "admin"
                owner_id_str = cached.get("owner_id")
                skill = Skill(
                    name=name,
                    is_system=is_system,
                    owner_id=UUID(owner_id_str) if owner_id_str else None,
                    admin_enabled=True,
                    description=cached.get("description", name),
                    descriptions=cached.get("descriptions"),
                )
                self.db.add(skill)
                result.created.append(name)

        # Flush to get IDs for new skills
        if result.created:
            await self.db.flush()

        # 2. Remove DB skills that no longer exist on disk
        for db_name in db_names:
            if db_name not in cache_by_name:
                await self.skill_repo.delete_by_name(db_name)
                result.removed.append(db_name)

        # 3. Update descriptions from disk for existing skills
        for name in db_names & cache_by_name.keys():
            cached = cache_by_name[name]
            skill = await self.skill_repo.get_by_name(name)  # type: ignore[assignment]
            if skill:
                disk_desc = cached.get("description", "")
                disk_descs = cached.get("descriptions")
                updated = False
                # Only update if DB has no descriptions yet (disk seeds DB)
                if not skill.descriptions and disk_descs:
                    skill.descriptions = disk_descs
                    updated = True
                if skill.description != disk_desc and not skill.descriptions:
                    skill.description = disk_desc
                    updated = True
                if updated:
                    self.db.add(skill)
                    result.updated.append(name)

        # 4. Ensure all users have states for admin-enabled system skills
        user_ids_result = await self.db.execute(sa_select(User.id))
        for (uid,) in user_ids_result:
            await self.state_repo.ensure_states_for_user(uid)

        # 5. Migrate legacy disabled_skills preferences (one-time, post-migration)
        await self._apply_legacy_disabled_skills()

        logger.info(
            "skills_synced_from_disk",
            created=len(result.created),
            removed=len(result.removed),
            updated=len(result.updated),
        )
        return result

    async def _apply_legacy_disabled_skills(self) -> None:
        """Read legacy helper tables and restore user preferences.

        Reads _legacy_disabled_skills (per-user) and _legacy_system_disabled_skills
        (admin-level), created by the migration. Sets is_active=false / admin_enabled=false
        accordingly. Drops the helper tables after processing.
        """
        from sqlalchemy import text

        migrated_count = 0

        # --- Per-user disabled_skills ---
        check = await self.db.execute(text("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables
                    WHERE table_name = '_legacy_disabled_skills'
                )
            """))
        if check.scalar():
            rows = await self.db.execute(
                text("SELECT user_id, disabled_skills FROM _legacy_disabled_skills")
            )
            for user_id, disabled_list in rows:
                if not disabled_list:
                    continue
                for skill_name in disabled_list:
                    skill = await self.skill_repo.get_by_name(skill_name)
                    if not skill:
                        continue
                    state = await self.state_repo.get_state(user_id, skill.id)
                    if state and state.is_active:
                        state.is_active = False
                        self.db.add(state)
                        migrated_count += 1

            await self.db.execute(text("DROP TABLE _legacy_disabled_skills"))

        # --- Admin system_disabled_skills ---
        check2 = await self.db.execute(text("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables
                    WHERE table_name = '_legacy_system_disabled_skills'
                )
            """))
        if check2.scalar():
            rows2 = await self.db.execute(
                text(
                    "SELECT user_id, system_disabled_skills " "FROM _legacy_system_disabled_skills"
                )
            )
            system_disabled_names: set[str] = set()
            for _admin_id, sys_disabled_list in rows2:
                if sys_disabled_list:
                    system_disabled_names.update(sys_disabled_list)

            for skill_name in system_disabled_names:
                skill = await self.skill_repo.get_by_name(skill_name)
                if not skill or not skill.is_system:
                    continue
                skill.admin_enabled = False
                self.db.add(skill)
                count = await self.state_repo.set_all_for_skill(skill.id, is_active=False)
                migrated_count += count

            await self.db.execute(text("DROP TABLE _legacy_system_disabled_skills"))

        if migrated_count > 0:
            logger.info(
                "legacy_skills_preferences_migrated",
                preferences_restored=migrated_count,
            )

    # ------------------------------------------------------------------
    # Query helpers (for router)
    # ------------------------------------------------------------------

    async def get_user_visible_skills(self, user_id: UUID) -> list[dict[str, Any]]:
        """Get skills visible to a user for the settings UI.

        Returns dicts with DB fields + is_active state.
        System skills: only those with admin_enabled=true.
        User skills: all owned by this user.
        """
        states = await self.state_repo.get_states_for_user(user_id)
        items = []
        for state in states:
            skill = state.skill
            # System skills: hide if admin disabled
            if skill.is_system and not skill.admin_enabled:
                continue
            # User skills: only show owned ones
            if not skill.is_system and skill.owner_id != user_id:
                continue
            items.append(self._state_to_dict(state))
        return items

    async def get_admin_system_skills(self) -> list[dict[str, Any]]:
        """Get all system skills for admin management UI.

        Returns ALL system skills (including disabled) with admin_enabled state.
        """
        skills = await self.skill_repo.get_all_system(include_disabled=True)
        return [self._skill_to_admin_dict(s) for s in skills]

    @staticmethod
    def _state_to_dict(state: UserSkillState) -> dict[str, Any]:
        """Convert a UserSkillState (with joined Skill) to API response dict."""
        skill = state.skill
        return {
            "name": skill.name,
            "description": skill.description,
            "descriptions": skill.descriptions,
            "scope": "admin" if skill.is_system else "user",
            "is_active": state.is_active,
            "admin_enabled": skill.admin_enabled,
            "skill_id": str(skill.id),
        }

    @staticmethod
    def _skill_to_admin_dict(skill: Skill) -> dict[str, Any]:
        """Convert a Skill to admin management API response dict."""
        return {
            "name": skill.name,
            "description": skill.description,
            "descriptions": skill.descriptions,
            "scope": "admin",
            "admin_enabled": skill.admin_enabled,
            "skill_id": str(skill.id),
        }
