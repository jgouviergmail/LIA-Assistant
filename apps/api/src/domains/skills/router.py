"""Skills API router — list, import, delete, reload, toggle, download, description update.

SKILL.md files on disk + SkillsCache in-memory for content.
DB tables (skills, user_skill_states) for state + display metadata.
"""

from __future__ import annotations

import json
import shutil
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import get_db
from src.core.session_dependencies import (
    get_current_active_session,
    get_current_superuser_session,
)
from src.domains.auth.models import User
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/skills", tags=["Skills"])


class SkillDescriptionUpdateRequest(BaseModel):
    """Request body for admin skill description update."""

    description: str = Field(..., min_length=10, max_length=1024)
    source_language: str = Field(..., pattern=r"^[a-z]{2}$")


# ---------------------------------------------------------------------------
# Shared helpers (disk operations — unchanged)
# ---------------------------------------------------------------------------


def _merge_with_cache(
    db_data: dict[str, Any],
    *,
    enabled_for_user: bool = True,
) -> dict[str, Any]:
    """Merge DB skill data with SkillsCache technical metadata for API response."""
    from src.domains.skills.cache import SkillsCache

    cached = SkillsCache.get_by_name(db_data["name"])
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
    }


def _skill_to_response(
    skill: dict[str, Any],
    scope: str,
    *,
    enabled_for_user: bool = True,
) -> dict[str, Any]:
    """Build a safe API response dict from a parsed cache skill (no instructions)."""
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
    }


def _extract_skill_to_dir(content: bytes, filename: str, base_dir: Path) -> Path:
    """Extract a SKILL.md or .zip package to a target directory.

    Returns the target directory containing SKILL.md.
    Raises HTTPException on validation errors.
    """
    from src.core.constants import SKILLS_MAX_FILE_SIZE_KB

    if len(content) > SKILLS_MAX_FILE_SIZE_KB * 1024:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds {SKILLS_MAX_FILE_SIZE_KB}KB limit",
        )

    if filename.endswith(".zip"):
        return _extract_zip(content, base_dir)
    return _extract_single_md(content, base_dir)


def _extract_zip(content: bytes, base_dir: Path) -> Path:
    """Extract a .zip skill package with Zip Slip protection.

    Handles two zip layouts:
    - Nested: my-skill/SKILL.md (standard) → extract to base_dir, target = base_dir/my-skill
    - Flat: SKILL.md at root → extract to base_dir/imported-skill, parse name from frontmatter
    """
    try:
        with zipfile.ZipFile(BytesIO(content)) as zf:
            skill_files = [n for n in zf.namelist() if n.endswith("SKILL.md")]
            if not skill_files:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No SKILL.md found in zip",
                )
            skill_md_path = skill_files[0]
            parent = Path(skill_md_path).parent

            if parent == Path(".") or parent == Path(""):
                target_dir = base_dir / "imported-skill"
                target_dir.mkdir(parents=True, exist_ok=True)
            else:
                target_dir = base_dir / parent.parts[0]
                target_dir.mkdir(parents=True, exist_ok=True)

            extract_to = (
                target_dir.parent if parent != Path(".") and parent != Path("") else target_dir
            )
            extract_to_resolved = extract_to.resolve()
            for member in zf.namelist():
                member_path = (extract_to / member).resolve()
                try:
                    member_path.relative_to(extract_to_resolved)
                except ValueError:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Zip contains path traversal entries",
                    ) from None

            if parent == Path(".") or parent == Path(""):
                zf.extractall(str(target_dir))
            else:
                zf.extractall(str(base_dir))
    except zipfile.BadZipFile as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid zip file",
        ) from exc
    return target_dir


def _extract_single_md(content: bytes, base_dir: Path) -> Path:
    """Extract a single SKILL.md file to a named directory."""
    if content.startswith(b"\xef\xbb\xbf"):
        content = content[3:]

    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        logger.warning("skill_file_decode_error", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="SKILL.md must be a valid UTF-8 text file",
        ) from exc

    if not text.startswith("---"):
        logger.warning("skill_file_no_frontmatter_import", preview=text[:80])
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="SKILL.md must start with YAML frontmatter (---)",
        )
    parts = text.split("---", 2)
    if len(parts) < 3:
        logger.warning("skill_file_bad_frontmatter_import")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid YAML frontmatter (missing closing ---)",
        )
    try:
        meta = yaml.safe_load(parts[1])
    except yaml.YAMLError as exc:
        logger.warning("skill_file_yaml_error_import", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid YAML in frontmatter: {exc}",
        ) from exc

    if not isinstance(meta, dict):
        logger.warning("skill_file_invalid_meta_import", meta_type=type(meta).__name__)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="YAML frontmatter must be a mapping (key: value pairs)",
        )

    skill_name: str = meta.get("name", "imported-skill")
    target_dir = base_dir / skill_name
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / "SKILL.md").write_text(text, encoding="utf-8")
    return target_dir


def _create_skill_zip(skill: dict[str, Any]) -> bytes:
    """Build a zip archive for a skill directory (SKILL.md + all bundled resources)."""
    skill_dir = Path(skill["source_path"]).parent
    buf = BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file_path in sorted(skill_dir.rglob("*")):
            if file_path.is_file():
                arcname = Path(skill["name"]) / file_path.relative_to(skill_dir)
                zf.write(file_path, arcname)
    return buf.getvalue()


def _update_skill_file_description(skill_path: Path, new_description: str) -> None:
    """Overwrite the `description` field in SKILL.md frontmatter and rewrite the file."""
    content = skill_path.read_text(encoding="utf-8")
    parts = content.split("---", 2)
    if len(parts) < 3:
        raise ValueError("Invalid SKILL.md: missing frontmatter delimiters")
    meta = yaml.safe_load(parts[1])
    if not isinstance(meta, dict):
        raise ValueError("Invalid SKILL.md: frontmatter is not a mapping")
    meta["description"] = new_description
    new_yaml = yaml.dump(
        meta,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
        width=2000,
    )
    skill_path.write_text(f"---\n{new_yaml}---\n{parts[2]}", encoding="utf-8")


async def _translate_description_all_langs(
    description: str,
    invoke_config: Any,
) -> dict[str, str]:
    """Call LLM to translate a skill description into all 6 supported languages."""
    from langchain_core.messages import HumanMessage, SystemMessage

    from src.domains.agents.prompts import load_prompt
    from src.infrastructure.llm.factory import get_llm

    system_prompt = load_prompt("skill_description_translation_prompt", version="v1")
    llm = get_llm("skill_description_translator")
    response = await llm.ainvoke(
        [SystemMessage(content=system_prompt), HumanMessage(content=description)],
        config=invoke_config,
    )
    content = response.content if hasattr(response, "content") else str(response)
    raw = str(content).strip()
    if raw.startswith("```"):
        lines = raw.splitlines()
        raw = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    translations: dict[str, str] = json.loads(raw)
    if not isinstance(translations, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in translations.items()
    ):
        raise ValueError("LLM returned invalid translation format")
    return translations


def _save_translations(skill_dir: Path, translations: dict[str, str]) -> None:
    """Write (or overwrite) translations.json next to SKILL.md."""
    (skill_dir / "translations.json").write_text(
        json.dumps(translations, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _validate_skill(target_dir: Path) -> dict[str, Any]:
    """Parse and validate SKILL.md in target_dir, clean up on failure.

    Does NOT reload cache — caller is responsible for calling
    ``await SkillsCache.invalidate_and_reload()`` after DB commit (ADR-063).
    """
    from src.domains.skills.loader import parse_skill_file

    skill_file = target_dir / "SKILL.md"
    skill = parse_skill_file(skill_file)
    if not skill:
        shutil.rmtree(target_dir, ignore_errors=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="SKILL.md validation failed (missing description or invalid format)",
        )

    return skill


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "",
    summary="List available skills",
    description="List system skills (admin-enabled) + user's own skills with activation state.",
)
async def list_skills(
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """List available skills for the user-facing settings (Compétences LIA).

    System skills with admin_enabled=false are excluded.
    User skills always shown regardless of is_active state.
    """
    from src.domains.skills.preference_service import SkillPreferenceService

    svc = SkillPreferenceService(db)
    db_skills = await svc.get_user_visible_skills(user.id)

    items = [_merge_with_cache(s, enabled_for_user=s["is_active"]) for s in db_skills]
    return {"skills": items, "total": len(items)}


@router.get(
    "/admin/list",
    summary="List all admin skills with system toggle state (superuser)",
    description="Returns all system skills with admin_enabled flag for admin management panel.",
)
async def list_admin_skills(
    user: User = Depends(get_current_superuser_session),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """List all admin skills for the admin management panel.

    Returns ALL system skills (including disabled) with admin_enabled flag.
    """
    from src.domains.skills.preference_service import SkillPreferenceService

    svc = SkillPreferenceService(db)
    db_skills = await svc.get_admin_system_skills()

    items = [_merge_with_cache(s, enabled_for_user=True) for s in db_skills]
    return {"skills": items, "total": len(items)}


@router.get(
    "/admin/{skill_name}/download",
    summary="Download an admin skill as zip (superuser)",
)
async def download_admin_skill(
    skill_name: str,
    user: User = Depends(get_current_superuser_session),
) -> StreamingResponse:
    """Download a system (admin) skill directory as a zip archive."""
    from src.domains.skills.cache import SkillsCache

    skill = SkillsCache.get_by_name(skill_name)
    if not skill or skill.get("scope") != "admin":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Admin skill '{skill_name}' not found"
        )

    zip_bytes = _create_skill_zip(skill)
    return StreamingResponse(
        BytesIO(zip_bytes),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{skill_name}.zip"'},
    )


@router.delete(
    "/admin/{skill_name}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an admin skill (superuser)",
)
async def delete_admin_skill(
    skill_name: str,
    user: User = Depends(get_current_superuser_session),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a system skill from disk + DB and reload the cache."""
    from src.domains.skills.cache import SkillsCache
    from src.domains.skills.preference_service import SkillPreferenceService

    skill = SkillsCache.get_by_name(skill_name)
    if not skill or skill.get("scope") != "admin":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Admin skill '{skill_name}' not found"
        )

    # Delete from disk
    skill_dir = Path(skill["source_path"]).parent
    if skill_dir.exists():
        shutil.rmtree(skill_dir, ignore_errors=True)

    # Delete from DB (CASCADE deletes user_skill_states)
    svc = SkillPreferenceService(db)
    await svc.delete_skill(skill_name)
    await db.commit()
    await SkillsCache.invalidate_and_reload()

    logger.info("admin_skill_deleted", skill_name=skill_name, user_id=str(user.id))


@router.patch(
    "/admin/{skill_name}/description",
    summary="Update admin skill description (superuser)",
    description=(
        "Update the description of an admin skill in any language. "
        "Translates to English (stored in SKILL.md) and all 6 languages (stored in DB + disk)."
    ),
)
async def update_admin_skill_description(
    skill_name: str,
    body: SkillDescriptionUpdateRequest,
    user: User = Depends(get_current_superuser_session),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Update description → translate to EN (SKILL.md) + all 6 langs (DB + disk) → reload."""
    from src.domains.skills.cache import SkillsCache
    from src.domains.skills.preference_service import SkillPreferenceService
    from src.infrastructure.llm.invoke_helpers import enrich_config_with_node_metadata

    skill = SkillsCache.get_by_name(skill_name)
    if not skill or skill.get("scope") != "admin":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Admin skill '{skill_name}' not found"
        )

    invoke_config = enrich_config_with_node_metadata(None, "skill_description_translation")

    try:
        translations = await _translate_description_all_langs(body.description, invoke_config)
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning(
            "skill_description_translation_parse_error", skill_name=skill_name, error=str(exc)
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="LLM returned invalid JSON for translations",
        ) from exc
    except Exception as exc:
        logger.error("skill_description_translation_error", skill_name=skill_name, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Translation failed"
        ) from exc

    english_desc = translations.get("en", body.description)
    skill_path = Path(skill["source_path"])
    skill_dir = skill_path.parent

    # Update disk (backward compat)
    try:
        _update_skill_file_description(skill_path, english_desc)
    except (OSError, ValueError) as exc:
        logger.error("skill_description_write_error", skill_name=skill_name, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update SKILL.md",
        ) from exc

    try:
        _save_translations(skill_dir, translations)
    except OSError as exc:
        logger.error("skill_translations_write_error", skill_name=skill_name, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to write translations.json",
        ) from exc

    # Update DB
    svc = SkillPreferenceService(db)
    await svc.admin_update_description(skill_name, english_desc, translations)
    await db.commit()

    await SkillsCache.invalidate_and_reload()

    logger.info(
        "admin_skill_description_updated",
        skill_name=skill_name,
        languages=list(translations.keys()),
        user_id=str(user.id),
    )
    return {"skill_name": skill_name, "descriptions": translations}


@router.get(
    "/{skill_name}/download",
    summary="Download a skill as zip",
)
async def download_skill(
    skill_name: str,
    user: User = Depends(get_current_active_session),
) -> StreamingResponse:
    """Download an accessible skill (admin or own user skill) as a zip archive."""
    from src.domains.skills.cache import SkillsCache

    user_id = str(user.id)
    skill = SkillsCache.get_by_name_for_user(skill_name, user_id)
    if not skill:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Skill '{skill_name}' not found"
        )

    if skill.get("scope") == "user" and skill.get("owner_id") != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Skill '{skill_name}' not found"
        )

    zip_bytes = _create_skill_zip(skill)
    return StreamingResponse(
        BytesIO(zip_bytes),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{skill_name}.zip"'},
    )


@router.post(
    "/import",
    status_code=status.HTTP_201_CREATED,
    summary="Import a user skill",
    description="Import a SKILL.md file or .zip package to user skills directory.",
)
async def import_skill(
    file: UploadFile,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Import a SKILL.md file or .zip package (user scope)."""
    from src.core.config import get_settings
    from src.domains.skills.cache import SkillsCache
    from src.domains.skills.preference_service import SkillPreferenceService

    settings = get_settings()
    user_id = str(user.id)

    # Check per-user limit
    user_skills = [s for s in SkillsCache.get_all() if s.get("owner_id") == user_id]
    if len(user_skills) >= settings.skills_max_per_user:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Maximum {settings.skills_max_per_user} skills per user",
        )

    content = await file.read()
    base_dir = Path(settings.skills_users_path) / user_id
    target_dir = _extract_skill_to_dir(content, file.filename or "SKILL.md", base_dir)
    skill = _validate_skill(target_dir)

    # Register in DB
    svc = SkillPreferenceService(db)
    await svc.create_skill_for_import(
        name=skill["name"],
        description=skill.get("description", skill["name"]),
        is_system=False,
        owner_id=user.id,
        descriptions=skill.get("descriptions"),
    )
    await db.commit()
    await SkillsCache.invalidate_and_reload()

    logger.info("skill_imported", skill_name=skill["name"], user_id=user_id)
    return _skill_to_response(skill, "user")


@router.post(
    "/admin/import",
    status_code=status.HTTP_201_CREATED,
    summary="Import an admin skill (superuser)",
    description="Import a SKILL.md file or .zip package to system skills directory.",
)
async def import_admin_skill(
    file: UploadFile,
    user: User = Depends(get_current_superuser_session),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Import a skill to the system (admin) directory."""
    from src.core.config import get_settings
    from src.domains.skills.cache import SkillsCache
    from src.domains.skills.preference_service import SkillPreferenceService

    settings = get_settings()
    system_base = Path(settings.skills_system_path)
    system_base.mkdir(parents=True, exist_ok=True)

    content = await file.read()
    target_dir = _extract_skill_to_dir(content, file.filename or "SKILL.md", system_base)
    skill = _validate_skill(target_dir)

    # Register in DB + create states for all users
    svc = SkillPreferenceService(db)
    await svc.create_skill_for_import(
        name=skill["name"],
        description=skill.get("description", skill["name"]),
        is_system=True,
        descriptions=skill.get("descriptions"),
    )
    await db.commit()
    await SkillsCache.invalidate_and_reload()

    logger.info("admin_skill_imported", skill_name=skill["name"], user_id=str(user.id))
    return _skill_to_response(skill, "admin")


@router.delete(
    "/{skill_name}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a user skill",
    description="Delete a user-imported skill (cannot delete admin skills).",
)
async def delete_skill(
    skill_name: str,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a user skill (cannot delete admin skills)."""
    from src.domains.skills.cache import SkillsCache
    from src.domains.skills.preference_service import SkillPreferenceService

    user_id = str(user.id)

    skill = SkillsCache.get_by_name_for_user(skill_name, user_id)
    if not skill:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Skill '{skill_name}' not found",
        )

    if skill["scope"] == "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot delete admin skills",
        )

    if skill.get("owner_id") != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Skill '{skill_name}' not found",
        )

    # Delete from disk
    skill_dir = Path(skill["source_path"]).parent
    if skill_dir.exists():
        shutil.rmtree(skill_dir, ignore_errors=True)

    # Delete from DB
    svc = SkillPreferenceService(db)
    await svc.delete_skill(skill_name)
    await db.commit()

    await SkillsCache.invalidate_and_reload()
    logger.info("skill_deleted", skill_name=skill_name, user_id=user_id)


@router.patch(
    "/{skill_name}/toggle",
    summary="Toggle a skill on/off",
    description="Enable or disable a skill for the current user.",
)
async def toggle_skill(
    skill_name: str,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Toggle a skill on/off for the current user.

    Updates is_active in user_skill_states table.
    """
    from src.domains.skills.preference_service import SkillPreferenceService

    svc = SkillPreferenceService(db)
    try:
        new_state = await svc.toggle_user_skill(user.id, skill_name)
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Skill '{skill_name}' not found",
        ) from err
    await db.commit()

    return {"skill_name": skill_name, "enabled_for_user": new_state}


@router.patch(
    "/admin/{skill_name}/system-toggle",
    summary="Toggle a system skill on/off for all users (admin)",
    description="System-level enable/disable. Disabled skills are hidden from non-superusers.",
)
async def admin_system_toggle_skill(
    skill_name: str,
    user: User = Depends(get_current_superuser_session),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Toggle a system skill on/off for all users.

    Updates admin_enabled on skills table + is_active on all user_skill_states.
    """
    from src.domains.skills.preference_service import SkillPreferenceService
    from src.domains.skills.repository import SkillRepository

    skill_repo = SkillRepository(db)
    db_skill = await skill_repo.get_by_name(skill_name)
    if not db_skill or not db_skill.is_system:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"System skill '{skill_name}' not found",
        )

    new_state = not db_skill.admin_enabled
    svc = SkillPreferenceService(db)
    await svc.admin_toggle_skill(skill_name, enable=new_state)
    await db.commit()

    logger.info(
        "system_skill_toggled",
        skill_name=skill_name,
        admin_id=str(user.id),
        admin_enabled=new_state,
    )
    return {"skill_name": skill_name, "admin_enabled": new_state}


@router.post(
    "/admin/{skill_name}/translate-description",
    summary="Translate a skill description (admin)",
    description=(
        "Generate LLM translations of a skill description to all 6 supported languages "
        "(fr, en, es, de, it, zh) and persist them in DB + translations.json."
    ),
)
async def translate_skill_description(
    skill_name: str,
    user: User = Depends(get_current_superuser_session),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Translate a system skill description to all 6 languages via LLM."""
    from src.domains.skills.cache import SkillsCache
    from src.domains.skills.preference_service import SkillPreferenceService
    from src.infrastructure.llm.invoke_helpers import enrich_config_with_node_metadata

    skill = SkillsCache.get_by_name(skill_name)
    if not skill:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Skill '{skill_name}' not found"
        )
    if skill.get("scope") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admin (system) skills can be translated via this endpoint",
        )

    invoke_config = enrich_config_with_node_metadata(None, "skill_description_translation")
    try:
        translations = await _translate_description_all_langs(skill["description"], invoke_config)
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning(
            "skill_description_translation_parse_error", skill_name=skill_name, error=str(exc)
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="LLM returned invalid JSON for translations",
        ) from exc
    except Exception as exc:
        logger.error("skill_description_translation_error", skill_name=skill_name, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Translation failed"
        ) from exc

    # Save to disk
    skill_dir = Path(skill["source_path"]).parent
    try:
        _save_translations(skill_dir, translations)
    except OSError as exc:
        logger.error("skill_translations_write_error", skill_name=skill_name, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to write translations.json",
        ) from exc

    # Save to DB
    svc = SkillPreferenceService(db)
    await svc.admin_update_description(skill_name, skill["description"], translations)
    await db.commit()

    await SkillsCache.invalidate_and_reload()

    logger.info(
        "skill_description_translated",
        skill_name=skill_name,
        languages=list(translations.keys()),
        user_id=str(user.id),
    )
    return {"skill_name": skill_name, "descriptions": translations}


@router.post(
    "/reload",
    summary="Reload skills cache (admin)",
    description="Force reload all skills from disk and sync with DB.",
)
async def reload_skills(
    user: User = Depends(get_current_superuser_session),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Admin: force reload all skills from disk and sync DB."""
    from src.core.config import get_settings
    from src.domains.skills.cache import SkillsCache
    from src.domains.skills.preference_service import SkillPreferenceService

    settings = get_settings()
    # Local reload first — sync_from_disk() needs fresh cache to compare disk vs DB
    SkillsCache.load_from_disk(settings.skills_system_path, settings.skills_users_path)

    # Sync DB with disk
    svc = SkillPreferenceService(db)
    sync_result = await svc.sync_from_disk()
    await db.commit()

    # Notify other workers after commit (ADR-063)
    from src.core.constants import CACHE_NAME_SKILLS
    from src.infrastructure.cache.invalidation import publish_cache_invalidation

    await publish_cache_invalidation(CACHE_NAME_SKILLS)

    skills = SkillsCache.get_all()
    logger.info(
        "skills_reloaded",
        count=len(skills),
        created=len(sync_result.created),
        removed=len(sync_result.removed),
        user_id=str(user.id),
    )
    return {
        "status": "reloaded",
        "count": len(skills),
        "admin_count": len([s for s in skills if s["scope"] == "admin"]),
        "user_count": len([s for s in skills if s["scope"] == "user"]),
    }
