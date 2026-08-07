"""
System Settings Service.

Administrator-facing CRUD over the settings store, plus the convenience
readers used on the request path.

Architecture:
    Admin read/write  → PostgreSQL (the truth, with metadata) → cache invalidation
    Request-path read → registry.read_setting → Redis → PostgreSQL → default

Every key is DECLARED ONCE in ``registry.py`` (codec, default, cache); this
module only adds what an administrator needs on top: metadata, an audit
trail, and the response schemas. Adding a setting therefore means adding a
spec — not another copy of the cache/fallback/invalidate block.

Usage:
    # Admin: enable the debug panel
    service = SystemSettingsService(db)
    await service.set_debug_panel_enabled(update, admin_user_id, request)

Created: 2026-01-16
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.system_settings.models import SystemSetting, SystemSettingKey
from src.domains.system_settings.registry import (
    get_setting_spec,
    invalidate_setting_cache,
    read_setting,
)
from src.domains.system_settings.schemas import (
    DebugPanelEnabledResponse,
    DebugPanelEnabledUpdate,
    DebugPanelUserAccessResponse,
    DebugPanelUserAccessUpdate,
)

if TYPE_CHECKING:
    from fastapi import Request

logger = structlog.get_logger(__name__)


# ============================================================================
# SERVICE
# ============================================================================


async def read_setting_with_metadata(
    db: AsyncSession, key: SystemSettingKey
) -> tuple[Any, SystemSetting | None]:
    """Return the decoded stored value (or its default) and the backing row.

    Admin reads go to the DATABASE on purpose: a panel must show what is
    stored — including "nothing is stored" — not a cached echo.

    Any domain owning a setting calls this rather than re-implementing the
    decode/default dance. The dependency only ever points THIS way: this
    module knows nothing about the domains that store settings in it.

    Args:
        db: Async session.
        key: Setting to read.

    Returns:
        The typed value and the row it came from (None when unset).
    """
    result = await db.execute(select(SystemSetting).where(SystemSetting.key == key))
    setting: SystemSetting | None = result.scalar_one_or_none()
    spec = get_setting_spec(key)
    if setting is None:
        return spec.default, None
    return spec.decode(setting.value), setting


async def write_setting(
    db: AsyncSession,
    key: SystemSettingKey,
    value: Any,
    *,
    action: str,
    admin_user_id: UUID,
    request: Request,
    change_reason: str | None,
) -> SystemSetting:
    """Persist a setting, audit the change, commit, invalidate its cache.

    Args:
        db: Async session.
        key: Setting to write.
        value: Typed value; serialized through the key's spec.
        action: Audit action name.
        admin_user_id: Admin making the change.
        request: FastAPI request, for the audit trail.
        change_reason: Optional operator justification.

    Returns:
        The persisted row, refreshed.
    """
    from src.domains.users.models import AdminAuditLog

    spec = get_setting_spec(key)
    new_value = spec.serialize(value)
    result = await db.execute(select(SystemSetting).where(SystemSetting.key == key))
    setting: SystemSetting | None = result.scalar_one_or_none()
    old_value = setting.value if setting else spec.serialize(spec.default)

    if setting:
        setting.value = new_value
        setting.updated_by = admin_user_id
        setting.change_reason = change_reason
    else:
        setting = SystemSetting(
            key=key,
            value=new_value,
            updated_by=admin_user_id,
            change_reason=change_reason,
        )
        db.add(setting)

    db.add(
        AdminAuditLog(
            admin_user_id=admin_user_id,
            action=action,
            resource_type="system_setting",
            resource_id=setting.id,
            details={
                "old_value": old_value,
                "new_value": new_value,
                "change_reason": change_reason,
            },
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    )

    await db.commit()
    await db.refresh(setting)
    await invalidate_setting_cache(key)

    logger.info(
        "system_setting_updated",
        setting=key.value,
        old_value=old_value,
        new_value=new_value,
        admin_user_id=str(admin_user_id),
        change_reason=change_reason,
    )
    return setting


class SystemSettingsService:
    """
    Service for managing system-wide settings.

    Provides methods for getting and setting application configuration
    that affects all users (e.g., debug panel visibility, spend ceiling).
    """

    def __init__(self, db: AsyncSession) -> None:
        """Initialize service with database session."""
        self.db = db

    # =========================================================================
    # GENERIC PLUMBING
    # =========================================================================

    async def _read_typed(self, key: SystemSettingKey) -> tuple[Any, SystemSetting | None]:
        """Read one setting with its metadata (see ``read_setting_with_metadata``)."""
        return await read_setting_with_metadata(self.db, key)

    async def _write(
        self,
        key: SystemSettingKey,
        value: Any,
        *,
        action: str,
        admin_user_id: UUID,
        request: Request,
        change_reason: str | None,
    ) -> SystemSetting:
        """Write one setting with audit and invalidation (see ``write_setting``)."""
        return await write_setting(
            self.db,
            key,
            value,
            action=action,
            admin_user_id=admin_user_id,
            request=request,
            change_reason=change_reason,
        )

    # =========================================================================
    # DEBUG PANEL SETTINGS
    # =========================================================================

    async def get_debug_panel_enabled(self) -> DebugPanelEnabledResponse:
        """
        Get current debug panel enabled status from database.

        Returns:
            DebugPanelEnabledResponse with current status and metadata.
        """
        enabled, setting = await self._read_typed(SystemSettingKey.DEBUG_PANEL_ENABLED)
        return DebugPanelEnabledResponse(
            enabled=enabled,
            updated_by=setting.updated_by if setting else None,
            updated_at=setting.updated_at if setting else None,
            is_default=setting is None,
        )

    async def set_debug_panel_enabled(
        self,
        update: DebugPanelEnabledUpdate,
        admin_user_id: UUID,
        request: Request,
    ) -> DebugPanelEnabledResponse:
        """
        Set debug panel enabled status (admin only).

        Args:
            update: New enabled status and optional change reason
            admin_user_id: Admin user making the change
            request: FastAPI request for audit logging

        Returns:
            Updated DebugPanelEnabledResponse
        """
        setting = await self._write(
            SystemSettingKey.DEBUG_PANEL_ENABLED,
            update.enabled,
            action="debug_panel_enabled_changed",
            admin_user_id=admin_user_id,
            request=request,
            change_reason=update.change_reason,
        )
        return DebugPanelEnabledResponse(
            enabled=update.enabled,
            updated_by=setting.updated_by,
            updated_at=setting.updated_at,
            is_default=False,
        )

    # =========================================================================
    # DEBUG PANEL USER ACCESS SETTINGS
    # =========================================================================

    async def get_debug_panel_user_access(self) -> DebugPanelUserAccessResponse:
        """
        Get current debug panel user access status from database.

        Returns:
            DebugPanelUserAccessResponse with current status and metadata.
        """
        available, setting = await self._read_typed(
            SystemSettingKey.DEBUG_PANEL_USER_ACCESS_ENABLED
        )
        return DebugPanelUserAccessResponse(
            available=available,
            updated_by=setting.updated_by if setting else None,
            updated_at=setting.updated_at if setting else None,
            is_default=setting is None,
        )

    async def set_debug_panel_user_access(
        self,
        update: DebugPanelUserAccessUpdate,
        admin_user_id: UUID,
        request: Request,
    ) -> DebugPanelUserAccessResponse:
        """
        Set debug panel user access status (admin only).

        Args:
            update: New availability status and optional change reason
            admin_user_id: Admin user making the change
            request: FastAPI request for audit logging

        Returns:
            Updated DebugPanelUserAccessResponse
        """
        setting = await self._write(
            SystemSettingKey.DEBUG_PANEL_USER_ACCESS_ENABLED,
            update.available,
            action="debug_panel_user_access_changed",
            admin_user_id=admin_user_id,
            request=request,
            change_reason=update.change_reason,
        )
        return DebugPanelUserAccessResponse(
            available=update.available,
            updated_by=setting.updated_by,
            updated_at=setting.updated_at,
            is_default=False,
        )


# ============================================================================
# REQUEST-PATH READERS
# ============================================================================
# Thin adapters over the typed registry. They keep their historical import
# address because production code and tests patch them there.


async def get_debug_panel_enabled() -> bool:
    """Whether the debug panel is enabled (cache → DB → default False)."""
    enabled: bool = await read_setting(SystemSettingKey.DEBUG_PANEL_ENABLED)
    return enabled


async def get_debug_panel_user_access_enabled() -> bool:
    """Whether non-admin users may toggle their own debug panel."""
    enabled: bool = await read_setting(SystemSettingKey.DEBUG_PANEL_USER_ACCESS_ENABLED)
    return enabled


async def get_instance_daily_budget_eur() -> Decimal | None:
    """The operator daily spend ceiling, or None when unset.

    This is only the operator half: the enforced ceiling is the smallest of
    this value and the deployment bound (``settings.instance_daily_budget_eur``).
    Resolve both through ``InstanceBudgetService.resolve_ceiling``.
    """
    ceiling: Decimal | None = await read_setting(SystemSettingKey.INSTANCE_DAILY_BUDGET_EUR)
    return ceiling


async def invalidate_debug_panel_enabled_cache() -> None:
    """Invalidate debug panel enabled cache (call after an admin change)."""
    await invalidate_setting_cache(SystemSettingKey.DEBUG_PANEL_ENABLED)


async def invalidate_debug_panel_user_access_cache() -> None:
    """Invalidate debug panel user access cache (call after an admin change)."""
    await invalidate_setting_cache(SystemSettingKey.DEBUG_PANEL_USER_ACCESS_ENABLED)
