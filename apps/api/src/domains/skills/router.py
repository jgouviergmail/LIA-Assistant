"""Skills API router — list, import, delete, reload, toggle, download, description update.

SKILL.md files on disk + SkillsCache in-memory for content.
DB tables (skills, user_skill_states) for state + display metadata.
"""

from __future__ import annotations

import asyncio
import json
import shutil
from io import BytesIO
from pathlib import Path
from typing import Any
from uuid import UUID

import yaml
from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.constants import SKILL_PREVIEW_MAX_BYTES
from src.core.dependencies import get_db
from src.core.session_dependencies import (
    get_current_active_session,
    get_current_superuser_session,
)
from src.domains.feature_switches.guard import capability_dependencies
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.shared.capability_origins import capability_origins
from src.domains.shared.capability_shares import capability_shares
from src.domains.skills.archive import create_skill_archive as _create_skill_zip
from src.domains.skills.exceptions import (
    raise_admin_skill_delete_forbidden,
    raise_skill_invalid_format,
    raise_skill_locked_by_plugin,
    raise_skill_not_found,
    raise_skill_translation_failed,
    raise_skill_translation_invalid,
    raise_skill_write_failed,
)
from src.domains.skills.models import SkillProvenance
from src.domains.skills.ui_projection import merge_skill_metadata as _merge_with_cache
from src.domains.skills.ui_projection import parsed_skill_metadata as _skill_to_response
from src.domains.skills.url_rate_limit import (
    rate_limit_url_import as _url_import_rate_limit,
)
from src.domains.users.models import User
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

from src.domains.skills.description_translation import (  # noqa: E402
    _save_translations,
    _translate_description_all_langs,
)

router = APIRouter(
    prefix="/skills",
    tags=["Skills"],
    # Administrable capability: a switched-off feature refuses at the
    # door, not only in the planner catalogue.
    dependencies=capability_dependencies(PlatformCapability.SKILLS),
)


class SkillDescriptionUpdateRequest(BaseModel):
    """Request body for admin skill description update."""

    description: str = Field(..., min_length=10, max_length=1024)
    source_language: str = Field(..., pattern=r"^[a-z]{2}$")


class SkillUrlImportRequest(BaseModel):
    """Request body for URL-sourced skill import (UXR Lot 10, B12)."""

    url: str = Field(..., min_length=12, max_length=2048, description="https:// source URL")


# ---------------------------------------------------------------------------
# Shared helpers (disk operations — unchanged)
# ---------------------------------------------------------------------------


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
    skill_ids = [UUID(s["skill_id"]) for s in db_skills]
    origins = await capability_origins(db, user.id, "skill", skill_ids)
    shares = await capability_shares(db, user.id, "skill", skill_ids)
    for item, source in zip(items, db_skills, strict=True):
        origin = origins.get(UUID(source["skill_id"]))
        item["shared_origin"] = origin.model_dump(mode="json") if origin else None
        item["shared_with"] = [
            share.model_dump(mode="json") for share in shares.get(UUID(source["skill_id"]), [])
        ]
        item["is_third_party"] = source["is_third_party"]
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

    skill = SkillsCache.get_system_by_name(skill_name)
    if not skill:
        raise_skill_not_found(skill_name, scope="admin")

    # Offload directory read + zip compression off the event loop (CA-4).
    zip_bytes = await asyncio.to_thread(_create_skill_zip, skill)
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
    from src.domains.skills.repository import SkillRepository

    skill = SkillsCache.get_system_by_name(skill_name)
    if not skill:
        raise_skill_not_found(skill_name, scope="admin")

    # Delete from disk
    skill_dir = Path(skill["source_path"]).parent
    if skill_dir.exists():
        shutil.rmtree(skill_dir, ignore_errors=True)

    # Delete from DB (CASCADE deletes user_skill_states) — the SYSTEM row only.
    row = await SkillRepository(db).get_system(skill_name)
    if row is not None:
        await SkillPreferenceService(db).delete_skill(row.id)
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

    skill = SkillsCache.get_system_by_name(skill_name)
    if not skill:
        raise_skill_not_found(skill_name, scope="admin")

    invoke_config = enrich_config_with_node_metadata(None, "skill_description_translation")

    try:
        translations = await _translate_description_all_langs(body.description, invoke_config)
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning(
            "skill_description_translation_parse_error",
            skill_name=skill_name,
            error=str(exc),
        )
        raise_skill_translation_invalid(skill_name)
    except Exception as exc:
        logger.exception(
            "skill_description_translation_error", skill_name=skill_name, error=str(exc)
        )
        raise_skill_translation_failed(skill_name)

    english_desc = translations.get("en", body.description)
    skill_path = Path(skill["source_path"])
    skill_dir = skill_path.parent

    # Update disk (backward compat) — offload blocking read+write off the loop (CA-4).
    try:
        await asyncio.to_thread(_update_skill_file_description, skill_path, english_desc)
    except (OSError, ValueError) as exc:
        logger.error("skill_description_write_error", skill_name=skill_name, error=str(exc))
        raise_skill_write_failed(skill_name, "SKILL.md")

    try:
        await asyncio.to_thread(_save_translations, skill_dir, translations)
    except OSError as exc:
        logger.error("skill_translations_write_error", skill_name=skill_name, error=str(exc))
        raise_skill_write_failed(skill_name, "translations.json")

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
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Download an accessible skill (admin or own user skill) as a zip archive."""
    from src.domains.skills.cache import SkillsCache
    from src.domains.skills.preference_service import SkillPreferenceService

    user_id = str(user.id)
    visible = await SkillPreferenceService(db).get_user_visible_skills(user.id)
    selected = next((item for item in visible if item["name"] == skill_name), None)
    if selected is None:
        raise_skill_not_found(skill_name)
    skill = SkillsCache.get_exact(skill_name, selected.get("owner_id"))
    if not skill:
        raise_skill_not_found(skill_name)

    if skill.get("scope") == "user" and skill.get("owner_id") != user_id:
        # Hide existence — respond with the same 404 as missing skill.
        raise_skill_not_found(skill_name)

    # Offload directory read + zip compression off the event loop (CA-4).
    zip_bytes = await asyncio.to_thread(_create_skill_zip, skill)
    current = await SkillPreferenceService(db).get_user_visible_skills(user.id)
    if not any(item["skill_id"] == selected["skill_id"] for item in current):
        raise_skill_not_found(skill_name)
    return StreamingResponse(
        BytesIO(zip_bytes),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{skill_name}.zip"'},
    )


@router.get(
    "/{skill_name}/preview",
    summary="Skill gallery preview image",
    description=(
        "Stream the skill's bundled assets/preview.png (the ONLY asset ever "
        "served). 404 when the skill has none."
    ),
)
async def skill_preview(
    skill_name: str,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    """Serve ``assets/preview.png`` for the gallery detail view (UXR Lot 10).

    The strict skill-name pattern is the traversal guard: the served path is
    always ``<skill_dir>/assets/preview.png`` for a cache-resolved skill.
    Missing, oversized, non-file, or admin-disabled previews are an
    undifferentiated 404 (a system skill hidden by the admin must not leak
    its assets).
    """
    from src.domains.skills.cache import SkillsCache
    from src.domains.skills.loader import SKILL_NAME_PATTERN
    from src.domains.skills.repository import SkillRepository

    if not SKILL_NAME_PATTERN.match(skill_name):
        raise_skill_invalid_format("Invalid skill name")

    skill = SkillsCache.get_by_name_for_user(skill_name, str(user.id))
    if not skill:
        raise_skill_not_found(skill_name)

    db_skill = await SkillRepository(db).resolve_for_user(user.id, skill_name)
    if db_skill is not None and db_skill.is_system and not db_skill.admin_enabled:
        raise_skill_not_found(skill_name)

    preview_path = Path(skill["source_path"]).parent / "assets" / "preview.png"

    def _stat_ok() -> bool:
        return preview_path.is_file() and preview_path.stat().st_size <= SKILL_PREVIEW_MAX_BYTES

    if not await asyncio.to_thread(_stat_ok):
        raise_skill_not_found(skill_name)
    return FileResponse(preview_path, media_type="image/png")


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
    from src.domains.skills.import_service import SkillImportService

    content = await file.read()
    svc = SkillImportService(db)
    skill = await svc.import_upload(
        content,
        file.filename or "SKILL.md",
        owner_id=user.id,
        is_system=False,
    )
    logger.info("skill_imported", skill_name=skill["name"], user_id=str(user.id))
    return _skill_to_response(skill, "user")


@router.post(
    "/import-from-url",
    status_code=status.HTTP_201_CREATED,
    summary="Import a user skill from an https URL",
    description=(
        "Fetch a SKILL.md or .zip package from an https URL (SSRF-validated, "
        "no redirects, streamed size cap) and run it through the exact same "
        "hardened import pipeline as file upload."
    ),
)
async def import_skill_from_url(
    body: SkillUrlImportRequest,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
    _rate: None = Depends(_url_import_rate_limit),
) -> dict[str, Any]:
    """Import a user skill from a remote https URL (UXR Lot 10, B12)."""
    from src.domains.skills.import_service import SkillImportService
    from src.domains.skills.url_import import fetch_skill_from_url
    from src.infrastructure.observability.metrics_registry import (
        skill_url_imports_total,
    )

    if not settings.skills_url_import_enabled:
        raise_skill_invalid_format("URL import is disabled")

    try:
        content, filename = await fetch_skill_from_url(body.url)
    except HTTPException as exc:
        detail = str(exc.detail)
        outcome = (
            "blocked"
            if detail.startswith(("url_blocked", "url_not_https"))
            else (
                "too_large"
                if detail.startswith("url_too_large")
                else (
                    "invalid_content"
                    if detail.startswith("url_not_skill_content")
                    else "fetch_failed"
                )
            )
        )
        skill_url_imports_total.labels(outcome=outcome).inc()
        raise

    svc = SkillImportService(db)
    try:
        skill = await svc.import_upload(
            content,
            filename,
            owner_id=user.id,
            is_system=False,
            provenance=SkillProvenance.URL,
        )
    except HTTPException:
        skill_url_imports_total.labels(outcome="pipeline_rejected").inc()
        raise
    skill_url_imports_total.labels(outcome="ok").inc()
    logger.info(
        "skill_imported_from_url",
        skill_name=skill["name"],
        user_id=str(user.id),
        content_bytes=len(content),
    )
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
    from src.domains.skills.import_service import SkillImportService

    content = await file.read()
    svc = SkillImportService(db)
    skill = await svc.import_upload(
        content,
        file.filename or "SKILL.md",
        owner_id=None,
        is_system=True,
    )
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
    from src.domains.skills.removal import (
        cleanup_removal,
        observe_removal,
        stage_removal,
    )

    user_id = str(user.id)

    skill = SkillsCache.get_by_name_for_user(skill_name, user_id)
    if not skill:
        raise_skill_not_found(skill_name)

    if skill["scope"] == "admin":
        raise_admin_skill_delete_forbidden()

    if skill.get("owner_id") != user_id:
        # Hide existence — respond with the same 404 as missing skill.
        raise_skill_not_found(skill_name)

    # ADR-225 arbitrage F: a plugin's skill leaves through the plugin
    # uninstall, never through individual deletion (a silently amputated
    # plugin is the same anti-pattern as a false success).
    from src.domains.skills.repository import SkillRepository

    row = await SkillRepository(db).get_owned(user.id, skill_name)
    if row is not None and row.plugin_id is not None:
        raise_skill_locked_by_plugin(skill_name)

    if row is None:
        raise_skill_not_found(skill_name)
    observed = await observe_removal(db, user.id, row.id)
    await stage_removal(db, user.id, observed)
    # Disk remains untouched until this acknowledgement is certain.
    await db.commit()
    cleaned = await cleanup_removal(db, observed)
    await db.commit()
    await SkillsCache.invalidate_and_reload()
    if not cleaned:
        raise_skill_write_failed(skill_name, "post-commit cleanup pending")
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
    except ValueError:
        raise_skill_not_found(skill_name)
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
    db_skill = await skill_repo.get_system(skill_name)
    if not db_skill:
        raise_skill_not_found(skill_name, scope="admin")

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

    skill = SkillsCache.get_system_by_name(skill_name)
    if not skill:
        raise_skill_not_found(skill_name, scope="admin")

    invoke_config = enrich_config_with_node_metadata(None, "skill_description_translation")
    try:
        translations = await _translate_description_all_langs(skill["description"], invoke_config)
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning(
            "skill_description_translation_parse_error",
            skill_name=skill_name,
            error=str(exc),
        )
        raise_skill_translation_invalid(skill_name)
    except Exception as exc:
        logger.exception(
            "skill_description_translation_error", skill_name=skill_name, error=str(exc)
        )
        raise_skill_translation_failed(skill_name)

    # Save to disk
    skill_dir = Path(skill["source_path"]).parent
    try:
        _save_translations(skill_dir, translations)
    except OSError as exc:
        logger.error("skill_translations_write_error", skill_name=skill_name, error=str(exc))
        raise_skill_write_failed(skill_name, "translations.json")

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
