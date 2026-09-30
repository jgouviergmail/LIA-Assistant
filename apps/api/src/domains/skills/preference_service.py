"""
Skills preference service — business logic for skill state management.

Centralizes all DB operations for the skills and user_skill_states tables.
The SkillsCache remains the source of truth for skill content (instructions,
scripts, resources, technical metadata). This service manages display metadata
(descriptions), admin visibility (admin_enabled), and per-user activation.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.skills.models import (
    MANAGED_PROVENANCES,
    Skill,
    SkillProvenance,
    UserSkillState,
)
from src.domains.skills.repository import (
    RequestSkillState,
    SkillRepository,
    UserSkillStateRepository,
)
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


def _disk_identity(entry: dict[str, Any]) -> tuple[UUID | None, str] | None:
    """The (owner or None, name) identity of a cache entry, None when unreadable.

    A user skill lives under ``users/<owner id>/``: a folder there whose name
    is not an id is not a person's, and is skipped rather than allowed to
    abort the whole sync on a ``ValueError``.
    """
    owner = entry.get("owner_id")
    if owner is None:
        return None, entry["name"]
    try:
        return UUID(str(owner)), entry["name"]
    except ValueError:
        logger.warning("skill_sync_owner_unreadable")
        return None


def captures_managed(existing: str, incoming: SkillProvenance | None) -> bool:
    """Whether an import through ``incoming`` would capture a managed skill, or be one.

    A plugin's or a library's skill is replaced by its own channel only; and a
    managed channel never captures a skill of another provenance (ADR-327, the
    plugin rule of ADR-225 generalised). ``None`` is a chat edit.

    Args:
        existing: The provenance of the person's skill of that name.
        incoming: The channel of the import (None: a chat edit).

    Returns:
        True when the import must be refused.
    """
    managed = {p.value for p in MANAGED_PROVENANCES}
    incoming_value = incoming.value if incoming is not None else None
    if existing == incoming_value:
        return False
    return existing in managed or incoming_value in managed


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

    async def get_request_skill_state(self, user_id: UUID) -> RequestSkillState:
        """The person's active and third-party skill names for one request (ADR-327)."""
        return await self.state_repo.get_request_skill_state(user_id)

    # ------------------------------------------------------------------
    # User actions
    # ------------------------------------------------------------------

    async def toggle_user_skill(self, user_id: UUID, skill_name: str) -> bool:
        """Toggle a skill's is_active for a user. Returns the new is_active value.

        The name resolves the way the person reaches it: their own skill, else
        the system one (ADR-327).

        Raises ValueError if skill or state not found.
        """
        skill = await self.skill_repo.resolve_for_user(user_id, skill_name)
        if not skill:
            raise ValueError(f"Skill '{skill_name}' not found")

        is_active = await self.state_repo.toggle(user_id, skill.id)
        logger.info(
            "skill_toggled",
            skill_name=skill_name,
            user_id=str(user_id),
            is_active=is_active,
        )
        return is_active

    # ------------------------------------------------------------------
    # Admin actions
    # ------------------------------------------------------------------

    async def admin_toggle_skill(self, skill_name: str, *, enable: bool) -> None:
        """Admin enables/disables a system skill for all users.

        Updates skill.admin_enabled AND bulk-updates all user_skill_states.
        """
        skill = await self.skill_repo.get_system(skill_name)
        if not skill:
            raise ValueError(f"System skill '{skill_name}' not found")

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
        """Update a SYSTEM skill's description and translations in DB."""
        skill = await self.skill_repo.get_system(skill_name)
        if not skill:
            raise ValueError(f"System skill '{skill_name}' not found")

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
        plugin_id: UUID | None = None,
        provenance: SkillProvenance | None = None,
    ) -> Skill:
        """Register a newly imported skill in DB and create user_skill_states.

        For system skills: creates states for ALL existing users.
        For user skills: creates a state for the owner only.

        The re-import case is looked up in the importer's OWN scope (ADR-327):
        a name is unique per account, so another person's skill of that name,
        or a system one, is a different skill and never an upsert target.

        ``provenance`` is the channel of THIS import (ADR-327). A system import
        is always ``system``; ``None`` is a chat edit, which keeps what it edits
        (``authored`` for a new skill): rewriting a third-party skill in
        conversation must not launder it into the person's own. A managed
        skill (plugin, library) is replaced by its own channel only.

        Raises:
            ValueError: when a user skill of that name is registered under a
                different Agent Plugins provenance (ADR-225: a plugin never
                captures a manual skill and vice versa) or a different managed
                channel (ADR-327), or when a user import names no owner. The
                import pipeline rejects the first two with a 409 before
                reaching this point (ADR-118) — this guard is defense-in-depth
                against races and future callers.
        """
        # Re-import case: the same identity (scope, name) already registered.
        if is_system:
            existing = await self.skill_repo.get_system(name)
        elif owner_id is None:
            raise ValueError(f"User skill '{name}' needs an owner")
        else:
            existing = await self.skill_repo.get_owned(owner_id, name)
        if existing:
            if existing.plugin_id != plugin_id:
                raise ValueError(
                    f"Skill '{name}' is already registered with a different plugin provenance"
                )
            if captures_managed(existing.provenance, provenance):
                raise ValueError(f"Skill '{name}' is managed by another channel")
            if provenance is not None and not is_system:
                existing.provenance = provenance.value
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
            plugin_id=plugin_id,
            provenance=(
                SkillProvenance.SYSTEM if is_system else provenance or SkillProvenance.AUTHORED
            ).value,
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

    async def delete_skill(self, skill_id: UUID) -> None:
        """Delete ONE skill from DB by id (CASCADE deletes user_skill_states)."""
        await self.skill_repo.delete_by_id(skill_id)
        logger.info("skill_deleted_from_db", skill_id=str(skill_id))

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

        from src.domains.skills.cache import SkillsCache

        result = SyncResult()
        cache_skills = SkillsCache.get_all()
        if not cache_skills:
            return result

        # Keyed on the IDENTITY (owner or None, name), never the name alone:
        # a name is unique per account (ADR-327).
        db_rows = await self.skill_repo.get_identities()
        on_disk: dict[tuple[UUID | None, str], dict[str, Any]] = {}
        for entry in cache_skills:
            identity = _disk_identity(entry)
            if identity is not None:
                on_disk[identity] = entry

        # 1. Create skills that exist on disk but not in DB.
        result.created.extend(await self._register_recovered(on_disk, db_rows))

        # 2. Remove DB skills that no longer exist on disk
        for identity, row in db_rows.items():
            if identity not in on_disk:
                await self.skill_repo.delete_by_id(row.id)
                result.removed.append(row.name)

        # 3. Update descriptions from disk for existing skills
        for identity, row in db_rows.items():
            disk_entry = on_disk.get(identity)
            if disk_entry is not None and self._seed_description(row, disk_entry):
                self.db.add(row)
                result.updated.append(row.name)

        # 4. Ensure all users have states for admin-enabled system skills — one
        # set-based bulk upsert over the users × system-skills cross join instead
        # of an O(users × skills) per-user savepoint loop (audit F018). Timed and
        # counted so the cost is observable regardless of user/skill volume.
        _states_start = time.perf_counter()
        states_provisioned = await self.state_repo.ensure_states_for_all_system_skills()
        states_provision_ms = round((time.perf_counter() - _states_start) * 1000, 1)

        # 5. Migrate legacy disabled_skills preferences (one-time, post-migration)
        await self._apply_legacy_disabled_skills()

        logger.info(
            "skills_synced_from_disk",
            created=len(result.created),
            removed=len(result.removed),
            updated=len(result.updated),
            states_provisioned=states_provisioned,
            states_provision_ms=states_provision_ms,
        )
        return result

    async def _register_recovered(
        self,
        on_disk: dict[tuple[UUID | None, str], dict[str, Any]],
        db_rows: dict[tuple[UUID | None, str], Skill],
    ) -> list[str]:
        """Register the skills found on disk with no row, and give a person's its state.

        A person's skill gets that person's state, or it would be registered and
        invisible; a folder whose owner no longer exists is left alone (its row
        would violate the owner foreign key and abort the whole sync). A folder
        with no row was written by LIA's importer or by someone with the server's
        filesystem, who is trusted already: it comes back as the person's own
        (the channel was never on disk).

        Args:
            on_disk: The cache's skills, by identity.
            db_rows: The registered skills, by identity.

        Returns:
            The names registered.
        """
        living_owners = await self._existing_users({o for o, _ in on_disk if o is not None})
        created: list[Skill] = []
        for (owner, name), cached in on_disk.items():
            if (owner, name) in db_rows or (owner is not None and owner not in living_owners):
                continue
            skill = Skill(
                name=name,
                is_system=owner is None,
                owner_id=owner,
                admin_enabled=True,
                description=cached.get("description", name),
                descriptions=cached.get("descriptions"),
                provenance=(
                    SkillProvenance.SYSTEM if owner is None else SkillProvenance.AUTHORED
                ).value,
            )
            self.db.add(skill)
            created.append(skill)
        if created:
            await self.db.flush()  # ids for the owners' states
            for skill in created:
                if skill.owner_id is not None:
                    self.db.add(UserSkillState(user_id=skill.owner_id, skill_id=skill.id))
        return [skill.name for skill in created]

    async def _existing_users(self, candidates: set[UUID]) -> set[UUID]:
        """Which of these ids are accounts that still exist (one query)."""
        if not candidates:
            return set()
        from sqlalchemy import select

        from src.domains.users.models import User

        rows = await self.db.execute(select(User.id).where(User.id.in_(candidates)))
        return {row[0] for row in rows}

    @staticmethod
    def _seed_description(row: Skill, cached: dict[str, Any]) -> bool:
        """Let the disk seed a row's descriptions while the DB holds none.

        Returns:
            True when the row changed.
        """
        disk_desc = cached.get("description", "")
        disk_descs = cached.get("descriptions")
        updated = False
        if not row.descriptions and disk_descs:
            row.descriptions = disk_descs
            updated = True
        if row.description != disk_desc and not row.descriptions:
            row.description = disk_desc
            updated = True
        return updated

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
                    skill = await self.skill_repo.resolve_for_user(user_id, skill_name)
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
                skill = await self.skill_repo.get_system(skill_name)
                if not skill:
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
        System skills: only those with admin_enabled=true, and none the
        person's own skill of the same name shadows (ADR-327: the listing shows
        the skill the name resolves to, so a name reaches ONE card).
        User skills: all owned by this user.
        """
        states = await self.state_repo.get_states_for_user(user_id)
        own_names = {
            state.skill.name
            for state in states
            if not state.skill.is_system and state.skill.owner_id == user_id
        }
        items = []
        for state in states:
            skill = state.skill
            if skill.is_system and (not skill.admin_enabled or skill.name in own_names):
                continue
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
            "owner_id": str(skill.owner_id) if skill.owner_id else None,
            "is_active": state.is_active,
            "admin_enabled": skill.admin_enabled,
            "skill_id": str(skill.id),
            "provenance": skill.provenance,
        }

    @staticmethod
    def _skill_to_admin_dict(skill: Skill) -> dict[str, Any]:
        """Convert a Skill to admin management API response dict."""
        return {
            "name": skill.name,
            "description": skill.description,
            "descriptions": skill.descriptions,
            "scope": "admin",
            "owner_id": None,
            "admin_enabled": skill.admin_enabled,
            "skill_id": str(skill.id),
            "provenance": skill.provenance,
        }
