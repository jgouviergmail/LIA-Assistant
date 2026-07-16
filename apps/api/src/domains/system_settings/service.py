"""
System Settings Service.

Provides CRUD operations for system-wide settings with Redis caching.
Follows the same pattern as ConversationIdCache for consistency.

Architecture:
    Request → Redis Cache (fast path ~1ms) → setting value
                   ↓ (cache miss)
              PostgreSQL DB → Cache Set → setting value

Usage:
    # Admin: enable the debug panel
    service = SystemSettingsService(db)
    await service.set_debug_panel_enabled(update, admin_user_id, request)

Created: 2026-01-16
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

import structlog
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.system_settings.models import SystemSetting, SystemSettingKey
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


class SystemSettingsService:
    """
    Service for managing system-wide settings.

    Provides methods for getting and setting application configuration
    that affects all users (e.g., debug panel visibility).
    """

    def __init__(self, db: AsyncSession) -> None:
        """Initialize service with database session."""
        self.db = db

    # =========================================================================
    # DEBUG PANEL SETTINGS
    # =========================================================================

    async def get_debug_panel_enabled(self) -> DebugPanelEnabledResponse:
        """
        Get current debug panel enabled status from database.

        Returns:
            DebugPanelEnabledResponse with current status and metadata.
        """
        stmt = select(SystemSetting).where(
            SystemSetting.key == SystemSettingKey.DEBUG_PANEL_ENABLED
        )
        result = await self.db.execute(stmt)
        setting = result.scalar_one_or_none()

        if setting:
            return DebugPanelEnabledResponse(
                enabled=setting.value.lower() == "true",
                updated_by=setting.updated_by,
                updated_at=setting.updated_at,
                is_default=False,
            )

        # No DB setting: return default (False)
        return DebugPanelEnabledResponse(
            enabled=False,
            updated_by=None,
            updated_at=None,
            is_default=True,
        )

    async def set_debug_panel_enabled(
        self,
        update: DebugPanelEnabledUpdate,
        admin_user_id: UUID,
        request: Request,
    ) -> DebugPanelEnabledResponse:
        """
        Set debug panel enabled status (admin only).

        Creates or updates the setting in the database, creates an audit log,
        and invalidates the cache.

        Args:
            update: New enabled status and optional change reason
            admin_user_id: Admin user making the change
            request: FastAPI request for audit logging

        Returns:
            Updated DebugPanelEnabledResponse
        """
        from src.domains.users.models import AdminAuditLog

        # Get or create setting
        stmt = select(SystemSetting).where(
            SystemSetting.key == SystemSettingKey.DEBUG_PANEL_ENABLED
        )
        result = await self.db.execute(stmt)
        setting = result.scalar_one_or_none()

        old_value = setting.value if setting else "false"
        new_value = "true" if update.enabled else "false"

        if setting:
            # Update existing
            setting.value = new_value
            setting.updated_by = admin_user_id
            setting.change_reason = update.change_reason
        else:
            # Create new
            setting = SystemSetting(
                key=SystemSettingKey.DEBUG_PANEL_ENABLED,
                value=new_value,
                updated_by=admin_user_id,
                change_reason=update.change_reason,
            )
            self.db.add(setting)

        # Create audit log
        audit_entry = AdminAuditLog(
            admin_user_id=admin_user_id,
            action="debug_panel_enabled_changed",
            resource_type="system_setting",
            resource_id=setting.id,
            details={
                "old_value": old_value,
                "new_value": new_value,
                "change_reason": update.change_reason,
            },
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        self.db.add(audit_entry)

        await self.db.commit()
        await self.db.refresh(setting)

        # Invalidate cache
        await invalidate_debug_panel_enabled_cache()

        logger.info(
            "debug_panel_enabled_updated",
            old_value=old_value,
            new_value=new_value,
            admin_user_id=str(admin_user_id),
            change_reason=update.change_reason,
        )

        return DebugPanelEnabledResponse(
            enabled=setting.value.lower() == "true",
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
        stmt = select(SystemSetting).where(
            SystemSetting.key == SystemSettingKey.DEBUG_PANEL_USER_ACCESS_ENABLED
        )
        result = await self.db.execute(stmt)
        setting = result.scalar_one_or_none()

        if setting:
            return DebugPanelUserAccessResponse(
                available=setting.value.lower() == "true",
                updated_by=setting.updated_by,
                updated_at=setting.updated_at,
                is_default=False,
            )

        # No DB setting: return default (False)
        return DebugPanelUserAccessResponse(
            available=False,
            updated_by=None,
            updated_at=None,
            is_default=True,
        )

    async def set_debug_panel_user_access(
        self,
        update: DebugPanelUserAccessUpdate,
        admin_user_id: UUID,
        request: Request,
    ) -> DebugPanelUserAccessResponse:
        """
        Set debug panel user access status (admin only).

        Creates or updates the setting in the database, creates an audit log,
        and invalidates the cache.

        Args:
            update: New availability status and optional change reason
            admin_user_id: Admin user making the change
            request: FastAPI request for audit logging

        Returns:
            Updated DebugPanelUserAccessResponse
        """
        from src.domains.users.models import AdminAuditLog

        # Get or create setting
        stmt = select(SystemSetting).where(
            SystemSetting.key == SystemSettingKey.DEBUG_PANEL_USER_ACCESS_ENABLED
        )
        result = await self.db.execute(stmt)
        setting = result.scalar_one_or_none()

        old_value = setting.value if setting else "false"
        new_value = "true" if update.available else "false"

        if setting:
            # Update existing
            setting.value = new_value
            setting.updated_by = admin_user_id
            setting.change_reason = update.change_reason
        else:
            # Create new
            setting = SystemSetting(
                key=SystemSettingKey.DEBUG_PANEL_USER_ACCESS_ENABLED,
                value=new_value,
                updated_by=admin_user_id,
                change_reason=update.change_reason,
            )
            self.db.add(setting)

        # Create audit log
        audit_entry = AdminAuditLog(
            admin_user_id=admin_user_id,
            action="debug_panel_user_access_changed",
            resource_type="system_setting",
            resource_id=setting.id,
            details={
                "old_value": old_value,
                "new_value": new_value,
                "change_reason": update.change_reason,
            },
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        self.db.add(audit_entry)

        await self.db.commit()
        await self.db.refresh(setting)

        # Invalidate cache
        await invalidate_debug_panel_user_access_cache()

        logger.info(
            "debug_panel_user_access_updated",
            old_value=old_value,
            new_value=new_value,
            admin_user_id=str(admin_user_id),
            change_reason=update.change_reason,
        )

        return DebugPanelUserAccessResponse(
            available=setting.value.lower() == "true",
            updated_by=setting.updated_by,
            updated_at=setting.updated_at,
            is_default=False,
        )


# ============================================================================
# DEBUG PANEL FUNCTIONS
# ============================================================================

# Default: debug panel is disabled
DEBUG_PANEL_ENABLED_DEFAULT = False
DEBUG_PANEL_CACHE_TTL_SECONDS = 300  # 5 minutes


async def get_debug_panel_enabled() -> bool:
    """
    Get current debug panel enabled status from cache or DB.

    Convenience function that handles Redis connection, cache miss fallback
    to database, and graceful error handling.

    Flow:
    1. Check Redis cache first (fast path, ~1ms)
    2. If cache miss, query DB and cache result
    3. If Redis error or DB has no setting, use default (False)
    4. Return: True or False

    Returns:
        bool: Whether debug panel is enabled

    Example:
        >>> enabled = await get_debug_panel_enabled()
        >>> if enabled:
        ...     # Include debug metrics in response
    """
    from src.core.constants import REDIS_KEY_DEBUG_PANEL_ENABLED
    from src.infrastructure.cache.redis import get_redis_cache
    from src.infrastructure.database import get_db_context

    try:
        redis = await get_redis_cache()

        # Fast path: check cache
        cached = await redis.get(REDIS_KEY_DEBUG_PANEL_ENABLED)
        if cached is not None:
            cached_str = cached.decode() if isinstance(cached, bytes) else str(cached)
            logger.debug("debug_panel_enabled_cache_hit", enabled=cached_str)
            return cached_str.lower() == "true"

        # Cache miss: query DB
        logger.debug("debug_panel_enabled_cache_miss")
        async with get_db_context() as db:
            stmt = select(SystemSetting).where(
                SystemSetting.key == SystemSettingKey.DEBUG_PANEL_ENABLED
            )
            result = await db.execute(stmt)
            setting = result.scalar_one_or_none()

            if setting:
                enabled = setting.value.lower() == "true"

                # Cache for future requests
                try:
                    await redis.set(
                        REDIS_KEY_DEBUG_PANEL_ENABLED,
                        "true" if enabled else "false",
                        ex=DEBUG_PANEL_CACHE_TTL_SECONDS,
                    )
                except RedisError as cache_err:
                    logger.warning(
                        "debug_panel_enabled_cache_set_failed",
                        error=str(cache_err),
                    )

                return enabled

            # No DB setting: use default
            logger.debug("debug_panel_enabled_using_default", default=DEBUG_PANEL_ENABLED_DEFAULT)
            return DEBUG_PANEL_ENABLED_DEFAULT

    except RedisError as e:
        # Redis unavailable: fallback to DB or default
        logger.warning("debug_panel_enabled_redis_error", error=str(e))

        try:
            async with get_db_context() as db:
                stmt = select(SystemSetting).where(
                    SystemSetting.key == SystemSettingKey.DEBUG_PANEL_ENABLED
                )
                result = await db.execute(stmt)
                setting = result.scalar_one_or_none()
                return setting.value.lower() == "true" if setting else DEBUG_PANEL_ENABLED_DEFAULT
        except Exception as db_err:
            logger.error("debug_panel_enabled_db_fallback_error", error=str(db_err))
            return DEBUG_PANEL_ENABLED_DEFAULT

    except Exception as e:
        # Unexpected error: use default
        logger.error("debug_panel_enabled_unexpected_error", error=str(e))
        return DEBUG_PANEL_ENABLED_DEFAULT


async def invalidate_debug_panel_enabled_cache() -> None:
    """
    Invalidate debug panel enabled cache.

    Call this when admin changes the setting.
    """
    from src.core.constants import REDIS_KEY_DEBUG_PANEL_ENABLED
    from src.infrastructure.cache.redis import get_redis_cache

    try:
        redis = await get_redis_cache()
        await redis.delete(REDIS_KEY_DEBUG_PANEL_ENABLED)
        logger.debug("debug_panel_enabled_cache_invalidated")

    except RedisError as e:
        # Non-fatal: cache will expire naturally via TTL
        logger.warning("debug_panel_enabled_cache_invalidation_error", error=str(e))


# ============================================================================
# DEBUG PANEL USER ACCESS FUNCTIONS
# ============================================================================

# Default: user access to debug panel is disabled
DEBUG_PANEL_USER_ACCESS_DEFAULT = False
DEBUG_PANEL_USER_ACCESS_CACHE_TTL_SECONDS = 300  # 5 minutes


async def get_debug_panel_user_access_enabled() -> bool:
    """
    Get current debug panel user access status from cache or DB.

    Flow:
    1. Check Redis cache first (fast path, ~1ms)
    2. If cache miss, query DB and cache result
    3. If Redis error or DB has no setting, use default (False)
    4. Return: True or False

    Returns:
        bool: Whether non-admin users can toggle their own debug panel
    """
    from src.core.constants import REDIS_KEY_DEBUG_PANEL_USER_ACCESS_ENABLED
    from src.infrastructure.cache.redis import get_redis_cache
    from src.infrastructure.database import get_db_context

    try:
        redis = await get_redis_cache()

        # Fast path: check cache
        cached = await redis.get(REDIS_KEY_DEBUG_PANEL_USER_ACCESS_ENABLED)
        if cached is not None:
            cached_str = cached.decode() if isinstance(cached, bytes) else str(cached)
            logger.debug("debug_panel_user_access_cache_hit", enabled=cached_str)
            return cached_str.lower() == "true"

        # Cache miss: query DB
        logger.debug("debug_panel_user_access_cache_miss")
        async with get_db_context() as db:
            stmt = select(SystemSetting).where(
                SystemSetting.key == SystemSettingKey.DEBUG_PANEL_USER_ACCESS_ENABLED
            )
            result = await db.execute(stmt)
            setting = result.scalar_one_or_none()

            if setting:
                enabled = setting.value.lower() == "true"

                # Cache for future requests
                try:
                    await redis.set(
                        REDIS_KEY_DEBUG_PANEL_USER_ACCESS_ENABLED,
                        "true" if enabled else "false",
                        ex=DEBUG_PANEL_USER_ACCESS_CACHE_TTL_SECONDS,
                    )
                except RedisError as cache_err:
                    logger.warning(
                        "debug_panel_user_access_cache_set_failed",
                        error=str(cache_err),
                    )

                return enabled

            # No DB setting: use default
            logger.debug(
                "debug_panel_user_access_using_default",
                default=DEBUG_PANEL_USER_ACCESS_DEFAULT,
            )
            return DEBUG_PANEL_USER_ACCESS_DEFAULT

    except RedisError as e:
        # Redis unavailable: fallback to DB or default
        logger.warning("debug_panel_user_access_redis_error", error=str(e))

        try:
            async with get_db_context() as db:
                stmt = select(SystemSetting).where(
                    SystemSetting.key == SystemSettingKey.DEBUG_PANEL_USER_ACCESS_ENABLED
                )
                result = await db.execute(stmt)
                setting = result.scalar_one_or_none()
                return (
                    setting.value.lower() == "true" if setting else DEBUG_PANEL_USER_ACCESS_DEFAULT
                )
        except Exception as db_err:
            logger.error("debug_panel_user_access_db_fallback_error", error=str(db_err))
            return DEBUG_PANEL_USER_ACCESS_DEFAULT

    except Exception as e:
        # Unexpected error: use default
        logger.error("debug_panel_user_access_unexpected_error", error=str(e))
        return DEBUG_PANEL_USER_ACCESS_DEFAULT


async def invalidate_debug_panel_user_access_cache() -> None:
    """
    Invalidate debug panel user access cache.

    Call this when admin changes the setting.
    """
    from src.core.constants import REDIS_KEY_DEBUG_PANEL_USER_ACCESS_ENABLED
    from src.infrastructure.cache.redis import get_redis_cache

    try:
        redis = await get_redis_cache()
        await redis.delete(REDIS_KEY_DEBUG_PANEL_USER_ACCESS_ENABLED)
        logger.debug("debug_panel_user_access_cache_invalidated")

    except RedisError as e:
        # Non-fatal: cache will expire naturally via TTL
        logger.warning("debug_panel_user_access_cache_invalidation_error", error=str(e))
