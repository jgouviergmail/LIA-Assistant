"""One safe gallery projection shared by the UI and native application tools."""

from typing import Any


def parsed_skill_metadata(
    skill: dict[str, Any], scope: str, *, enabled_for_user: bool = True
) -> dict[str, Any]:
    """Original safe upload/gallery projection; no instructions or disk paths."""
    return {
        "name": skill["name"],
        "description": skill["description"],
        "descriptions": skill.get("descriptions"),
        "scope": scope,
        "category": skill.get("category"),
        "priority": skill.get("priority", 50),
        "always_loaded": skill.get("always_loaded", False),
        "has_scripts": bool(skill.get("scripts")),
        "has_plan_template": bool(skill.get("plan_template")),
        "enabled_for_user": enabled_for_user,
        "dialogue": bool(skill.get("dialogue", False)),
        "outputs": skill.get("outputs"),
    }


def merge_skill_metadata(
    db_data: dict[str, Any],
    *,
    enabled_for_user: bool = True,
) -> dict[str, Any]:
    """Merge DB skill data with SkillsCache technical metadata for API response."""
    from src.domains.skills.cache import SkillsCache

    cached = SkillsCache.get_exact(db_data["name"], db_data.get("owner_id"))
    return {
        "name": db_data["name"],
        "description": db_data["description"],
        "descriptions": db_data.get("descriptions"),
        "scope": db_data["scope"],
        "category": cached.get("category") if cached else None,
        "priority": cached.get("priority", 50) if cached else 50,
        "always_loaded": cached.get("always_loaded", False) if cached else False,
        "has_scripts": bool(cached.get("scripts")) if cached else False,
        "has_plan_template": bool(cached.get("plan_template")) if cached else False,
        "enabled_for_user": enabled_for_user,
        "admin_enabled": db_data.get("admin_enabled", True),
        # UXR Lot 8 (A4): multi-turn dialogue flag (ADR-118) — feeds the
        # frontend slash-command registry (dialogue skills are conversational
        # commands).
        "dialogue": bool(cached.get("dialogue", False)) if cached else False,
        # UXR Lot 10 (B12): declared output channels (None ⇒ "text" default
        # in the gallery UI).
        "outputs": cached.get("outputs") if cached else None,
        # ADR-327: how the content arrived (a third-party skill is marked in the
        # gallery, and a library skill is updated from its source, never edited).
        "skill_id": db_data.get("skill_id"),
        "provenance": db_data.get("provenance"),
    }
