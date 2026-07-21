"""Skills In-Memory Cache.

Pattern: LLMConfigOverrideCache (domains/llm_config/cache.py).
Loaded from SKILL.md files at startup. No DB, no async.
"""

from pathlib import Path
from typing import Any

from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


class SkillsCache:
    """Singleton in-memory cache for skills loaded from SKILL.md files."""

    _skills: dict[str, dict[str, Any]] = {}
    _loaded: bool = False

    @classmethod
    def load_from_disk(cls, system_path: str, users_path: str) -> None:
        """Load all skills from disk into memory. Atomic swap."""
        from src.domains.skills.loader import scan_skills_directory

        skills: dict[str, dict[str, Any]] = {}

        # System (admin) skills
        for skill in scan_skills_directory(Path(system_path), scope="admin"):
            skills[skill["id"]] = skill

        # User skills (per-user subdirectories)
        users_dir = Path(users_path)
        if users_dir.exists():
            for user_dir in users_dir.iterdir():
                if user_dir.is_dir():
                    user_id = user_dir.name
                    for skill in scan_skills_directory(
                        user_dir,
                        scope="user",
                        owner_id=user_id,
                    ):
                        skills[skill["id"]] = skill

        cls._skills = skills
        cls._loaded = True
        logger.info("skills_cache_loaded", count=len(skills))

    @classmethod
    def get_all(cls) -> list[dict[str, Any]]:
        """Return all loaded skills."""
        return list(cls._skills.values())

    @staticmethod
    def entry_is_system(entry: dict[str, Any]) -> bool:
        """Return True when a cache entry describes a system (admin-curated) skill.

        Cache entries carry ``scope`` ("admin" | "user"), stamped by
        ``scan_skills_directory`` — they never carry the DB column
        ``is_system``, which only exists on the ``skills`` table. Reading
        ``entry.get("is_system")`` on a cache entry therefore matches nothing:
        that exact confusion shipped once (2026-07-21) and silently demoted
        every rehydrated widget, and once with a permissive ``True`` default
        that would have granted user skills system-frame privileges. Every
        system-ness decision on a cache entry MUST go through this predicate.

        Args:
            entry: A skill dict as produced by the loader.

        Returns:
            True for admin-scope (system) skills, False otherwise.
        """
        return entry.get("scope") == "admin"

    @classmethod
    def get_system_skill_names(cls, user_id: str) -> frozenset[str]:
        """Return the skill names that resolve to a SYSTEM skill for this user.

        Used by the history read path to recompute ``is_system_skill`` on
        rehydrated widgets (ADR-137): the flag grants frame privileges and is
        never trusted from a persisted payload.

        User-scoped on purpose, with the same override semantics as the write
        path (``get_by_name_for_user``): a user skill shadowing a system name
        makes that name resolve to the USER skill, so it must not be treated
        as system here — a global name-based set would re-grant system frame
        privileges (``credentialless`` + ``allow-same-origin``) to a widget
        produced by user-owned code.

        Args:
            user_id: The user whose skill resolution applies.

        Returns:
            Frozen set of system skill names for that user; empty when the
            cache is empty.
        """
        return frozenset(
            str(s["name"])
            for s in cls.get_for_user(user_id)
            if cls.entry_is_system(s) and s.get("name")
        )

    @classmethod
    def get_for_user(cls, user_id: str) -> list[dict[str, Any]]:
        """Admin skills + user's own skills, with override semantics.

        Per agentskills.io: user skills override admin skills with same name.
        """
        by_name: dict[str, dict[str, Any]] = {}
        for s in cls._skills.values():
            if s["scope"] == "admin":
                by_name.setdefault(s["name"], s)
            elif s.get("owner_id") == user_id:
                by_name[s["name"]] = s  # User overrides admin (last-one-wins)
        return list(by_name.values())

    @classmethod
    def get_by_name(cls, name: str) -> dict[str, Any] | None:
        """Find a skill by name (first match, any scope)."""
        for skill in cls._skills.values():
            if skill["name"] == name:
                return skill
        return None

    @classmethod
    def get_by_name_for_user(cls, name: str, user_id: str) -> dict[str, Any] | None:
        """Find a skill by name with user override semantics.

        If both admin and user skill exist with the same name,
        the user's version wins (per agentskills.io standard).
        """
        admin_match: dict[str, Any] | None = None
        for skill in cls._skills.values():
            if skill["name"] != name:
                continue
            if skill["scope"] == "user" and skill.get("owner_id") == user_id:
                return skill  # User skill takes priority
            if skill["scope"] == "admin":
                admin_match = skill
        return admin_match

    @classmethod
    def get_always_loaded(cls, user_id: str | None = None) -> list[dict[str, Any]]:
        """Return skills marked as always_loaded for injection."""
        return [
            s
            for s in cls._skills.values()
            if s.get("always_loaded") and (s["scope"] == "admin" or s.get("owner_id") == user_id)
        ]

    @classmethod
    async def invalidate_and_reload(cls) -> None:
        """Reload skills from disk and notify all workers.

        Called by router endpoints after skill modifications.
        Publishes cross-worker invalidation via Redis Pub/Sub (ADR-063).
        """
        from src.core.config import settings
        from src.core.constants import CACHE_NAME_SKILLS
        from src.infrastructure.cache.invalidation import publish_cache_invalidation

        cls.load_from_disk(settings.skills_system_path, settings.skills_users_path)
        await publish_cache_invalidation(CACHE_NAME_SKILLS)

    @classmethod
    def is_loaded(cls) -> bool:
        """Check if cache has been initialized."""
        return cls._loaded

    @classmethod
    def reset(cls) -> None:
        """Reset cache (for testing)."""
        cls._skills = {}
        cls._loaded = False
