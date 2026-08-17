"""Plugins API router — import (upload + URL), list, uninstall (ADR-225).

Thin composition over the already-hardened orchestrator: every import path
converges on ``PluginImportService.import_upload`` (zero bypass), the URL
path reuses the skills SSRF-hardened fetch verbatim (https-only, blocked
ranges, no redirects, streamed size cap) and its per-user rate limit — both
guard the same outbound-fetch resource, so they intentionally share a bucket.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.dependencies import get_db
from src.core.session_dependencies import get_current_active_session
from src.domains.plugins.exceptions import raise_plugin_invalid_package
from src.domains.plugins.schemas import (
    PluginImportReport,
    PluginListResponse,
    PluginResponse,
)
from src.domains.plugins.staging import zip_contains_plugin_manifest
from src.domains.skills.router import _url_import_rate_limit
from src.domains.users.models import User
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/plugins", tags=["plugins"])


class PluginUrlImportRequest(BaseModel):
    """Request body for the URL import endpoint."""

    url: str = Field(min_length=1, max_length=2048, description="https URL of a plugin .zip")


@router.post(
    "/import",
    status_code=status.HTTP_201_CREATED,
    summary="Install a plugin from a zip package",
    description=(
        "Install (or update) an Agent Plugins package (agent-plugins.org "
        "v1.0.0). Returns the full per-component report — installed, updated, "
        "skipped (with reasons) and removed components are never silent."
    ),
)
async def import_plugin(
    file: UploadFile,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> PluginImportReport:
    """Install or update a plugin from an uploaded zip package."""
    from src.domains.plugins.import_service import PluginImportService

    content = await file.read()
    svc = PluginImportService(db)
    report = await svc.import_upload(content, owner_id=user.id)
    logger.info(
        "plugin_imported",
        plugin_name=report.name,
        user_id=str(user.id),
        updated=report.updated,
    )
    return report


@router.post(
    "/import-from-url",
    status_code=status.HTTP_201_CREATED,
    summary="Install a plugin from an https URL",
    description=(
        "Fetch a plugin .zip from an https URL (SSRF-validated, no redirects, "
        "streamed size cap — the exact skills URL-import hardening) and run "
        "it through the same import pipeline as file upload."
    ),
)
async def import_plugin_from_url(
    body: PluginUrlImportRequest,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
    _rate: None = Depends(_url_import_rate_limit),
) -> PluginImportReport:
    """Install or update a plugin fetched from a remote https URL."""
    from src.domains.plugins.import_service import PluginImportService
    from src.domains.skills.url_import import fetch_skill_from_url

    if not settings.skills_url_import_enabled:
        raise_plugin_invalid_package("URL import is disabled")

    content, _filename = await fetch_skill_from_url(body.url)
    if not zip_contains_plugin_manifest(content):
        raise_plugin_invalid_package(
            "the fetched content is not an Agent Plugins package (no plugin.json)"
        )

    svc = PluginImportService(db)
    report = await svc.import_upload(content, owner_id=user.id)
    logger.info(
        "plugin_imported_from_url",
        plugin_name=report.name,
        user_id=str(user.id),
        updated=report.updated,
        content_bytes=len(content),
    )
    return report


@router.get(
    "",
    summary="List installed plugins",
    description="List the user's installed plugins with their components.",
)
async def list_plugins(
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> PluginListResponse:
    """List installed plugins with their component names."""
    from src.domains.plugins.import_service import PluginImportService
    from src.domains.skills.repository import SkillRepository
    from src.domains.user_mcp.repository import UserMCPServerRepository

    svc = PluginImportService(db)
    skill_repo = SkillRepository(db)
    mcp_repo = UserMCPServerRepository(db)

    items: list[PluginResponse] = []
    for row in await svc.list_plugins(user.id):
        skills = await skill_repo.get_by_plugin_id(row.id)
        servers = await mcp_repo.get_by_plugin_id(row.id)
        items.append(
            PluginResponse(
                id=row.id,
                name=row.name,
                version=row.version,
                description=row.description,
                spec_version=row.spec_version,
                skill_names=[s.name for s in skills],
                server_names=[s.name for s in servers],
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
        )
    return PluginListResponse(plugins=items, total=len(items))


@router.delete(
    "/{plugin_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Uninstall a plugin",
    description=(
        "Uninstall a plugin and every component it installed (skills and MCP "
        "servers, rows and files). This is the only way plugin components "
        "leave — individual component deletion is refused."
    ),
)
async def delete_plugin(
    plugin_id: UUID,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Uninstall a plugin and its components (group removal, arbitrage F)."""
    from src.domains.plugins.import_service import PluginImportService

    svc = PluginImportService(db)
    await svc.uninstall(plugin_id, owner_id=user.id)
