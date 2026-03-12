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
    def is_loaded(cls) -> bool:
        """Check if cache has been initialized."""
        return cls._loaded

    @classmethod
    def reset(cls) -> None:
        """Reset cache (for testing)."""
        cls._skills = {}
        cls._loaded = False
