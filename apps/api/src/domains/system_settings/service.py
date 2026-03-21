"""
System Settings Service.

Provides CRUD operations for system-wide settings with Redis caching.
Follows the same pattern as ConversationIdCache for consistency.

Architecture:
    Request → Redis Cache (fast path ~1ms) → setting value
                   ↓ (cache miss)
              PostgreSQL DB → Cache Set → setting value

Usage:
    # Get voice mode (cached)
    mode = await get_voice_tts_mode()  # "standard" or "hd"

    # Admin: Update voice mode
    service = SystemSettingsService(db)
    await service.set_voice_tts_mode("hd", admin_user_id, request)

Created: 2026-01-16
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast
from uuid import UUID

import structlog
from prometheus_client import Counter
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.config.voice import VoiceTTSMode
from src.core.constants import REDIS_KEY_VOICE_TTS_MODE
from src.domains.system_settings.models import SystemSetting, SystemSettingKey
from src.domains.system_settings.schemas import (
    DebugPanelEnabledResponse,
    DebugPanelEnabledUpdate,
    DebugPanelUserAccessResponse,
    DebugPanelUserAccessUpdate,
    VoiceTTSModeResponse,
    VoiceTTSModeUpdate,
)

if TYPE_CHECKING:
    import redis.asyncio as aioredis
    from fastapi import Request

logger = structlog.get_logger(__name__)


# ============================================================================
# PROMETHEUS METRICS
# ============================================================================

voice_tts_mode_cache_total = Counter(
    "voice_tts_mode_cache_total",
    "Total voice TTS mode cache operations",
    ["result"],  # "hit", "miss", "error"
)


# ============================================================================
# CACHE TTL
# ============================================================================

# Voice TTS mode doesn't change often, cache for 5 minutes
VOICE_TTS_MODE_CACHE_TTL_SECONDS = 300


# ============================================================================
# SERVICE
# ============================================================================


class SystemSettingsService:
    """
    Service for managing system-wide settings.

    Provides methods for getting and setting application configuration
    that affects all users (e.g., voice TTS mode).
    """

    def __init__(self, db: AsyncSession) -> None:
        """Initialize service with database session."""
        self.db = db

    async def get_voice_tts_mode(self) -> VoiceTTSModeResponse:
        """
        Get current voice TTS mode from database.

        Returns:
            VoiceTTSModeResponse with current mode and metadata.
        """
        stmt = select(SystemSetting).where(SystemSetting.key == SystemSettingKey.VOICE_TTS_MODE)
        result = await self.db.execute(stmt)
        setting = result.scalar_one_or_none()

        if setting:
            return VoiceTTSModeResponse(
                mode=setting.value,
                updated_by=setting.updated_by,
                updated_at=setting.updated_at,
                is_default=False,
            )

        # No DB setting: return default from environment
        return VoiceTTSModeResponse(
            mode=settings.voice_tts_default_mode,
            updated_by=None,
            updated_at=None,
            is_default=True,
        )

    async def set_voice_tts_mode(
        self,
        update: VoiceTTSModeUpdate,
        admin_user_id: UUID,
        request: Request,
    ) -> VoiceTTSModeResponse:
        """
        Set voice TTS mode (admin only).

        Creates or updates the setting in the database, creates an audit log,
        and invalidates the cache.

        Args:
            update: New mode and optional change reason
            admin_user_id: Admin user making the change
            request: FastAPI request for audit logging

        Returns:
            Updated VoiceTTSModeResponse
        """
        from src.domains.users.models import AdminAuditLog

        # Get or create setting
        stmt = select(SystemSetting).where(SystemSetting.key == SystemSettingKey.VOICE_TTS_MODE)
        result = await self.db.execute(stmt)
        setting = result.scalar_one_or_none()

        old_value = setting.value if setting else settings.voice_tts_default_mode

        if setting:
            # Update existing
            setting.value = update.mode
            setting.updated_by = admin_user_id
            setting.change_reason = update.change_reason
        else:
            # Create new
            setting = SystemSetting(
                key=SystemSettingKey.VOICE_TTS_MODE,
                value=update.mode,
                updated_by=admin_user_id,
                change_reason=update.change_reason,
            )
            self.db.add(setting)

        # Create audit log (setting.id is always set via default=uuid.uuid4)
        audit_entry = AdminAuditLog(
            admin_user_id=admin_user_id,
            action="voice_tts_mode_changed",
            resource_type="system_setting",
            resource_id=setting.id,
            details={
                "old_value": old_value,
                "new_value": update.mode,
                "change_reason": update.change_reason,
            },
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        self.db.add(audit_entry)

        await self.db.commit()
        await self.db.refresh(setting)

        # Invalidate cache
        await invalidate_voice_tts_mode_cache()

        logger.info(
            "voice_tts_mode_updated",
            old_value=old_value,
            new_value=update.mode,
            admin_user_id=str(admin_user_id),
            change_reason=update.change_reason,
        )

        return VoiceTTSModeResponse(
            mode=setting.value,
            updated_by=setting.updated_by,
            updated_at=setting.updated_at,
            is_default=False,
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
# CACHE FUNCTIONS
# ============================================================================


class VoiceTTSModeCache:
    """
    Cache service for voice TTS mode setting.

    Provides fast access to the current voice mode without DB queries.
    """

    def __init__(self, redis_client: aioredis.Redis) -> None:
        self.redis = redis_client
        self._key = REDIS_KEY_VOICE_TTS_MODE
        self._ttl_seconds = VOICE_TTS_MODE_CACHE_TTL_SECONDS

    async def get(self) -> VoiceTTSMode | None:
        """Get cached voice TTS mode."""
        result = await self.redis.get(self._key)

        if result:
            mode_str = result.decode() if isinstance(result, bytes) else str(result)
            logger.debug("voice_tts_mode_cache_hit", mode=mode_str)
            voice_tts_mode_cache_total.labels(result="hit").inc()
            return cast(VoiceTTSMode, mode_str)

        logger.debug("voice_tts_mode_cache_miss")
        voice_tts_mode_cache_total.labels(result="miss").inc()
        return None

    async def set(self, mode: VoiceTTSMode) -> None:
        """Set cached voice TTS mode with TTL."""
        await self.redis.setex(self._key, self._ttl_seconds, mode)
        logger.debug(
            "voice_tts_mode_cache_set",
            mode=mode,
            ttl_seconds=self._ttl_seconds,
        )

    async def invalidate(self) -> None:
        """Invalidate cached voice TTS mode."""
        await self.redis.delete(self._key)
        logger.debug("voice_tts_mode_cache_invalidated")


async def get_voice_tts_mode() -> VoiceTTSMode:
    """
    Get current voice TTS mode from cache or DB.

    Convenience function that handles Redis connection, cache miss fallback
    to database, and graceful error handling.

    Flow:
    1. Check Redis cache first (fast path, ~1ms)
    2. If cache miss, query DB and cache result
    3. If Redis error or DB has no setting, use default from environment
    4. Return mode: "standard" or "hd"

    Returns:
        VoiceTTSMode: "standard" or "hd"

    Example:
        >>> mode = await get_voice_tts_mode()
        >>> if mode == "hd":
        ...     # Use OpenAI/Gemini TTS
    """
    from src.infrastructure.cache.redis import get_redis_cache
    from src.infrastructure.database import get_db_context

    try:
        redis = await get_redis_cache()
        cache = VoiceTTSModeCache(redis)

        # Fast path: check cache
        cached = await cache.get()
        if cached:
            return cached

        # Cache miss: query DB
        async with get_db_context() as db:
            stmt = select(SystemSetting).where(SystemSetting.key == SystemSettingKey.VOICE_TTS_MODE)
            result = await db.execute(stmt)
            setting = result.scalar_one_or_none()

            if setting:
                mode = cast(VoiceTTSMode, setting.value)

                # Cache for future requests
                try:
                    await cache.set(mode)
                except RedisError as cache_err:
                    logger.warning(
                        "voice_tts_mode_cache_set_failed",
                        error=str(cache_err),
                    )

                return mode

            # No DB setting: use default from environment
            default_mode = settings.voice_tts_default_mode
            logger.debug(
                "voice_tts_mode_using_default",
                default_mode=default_mode,
            )
            return default_mode

    except RedisError as e:
        # Redis unavailable: fallback to DB or default
        logger.warning(
            "voice_tts_mode_cache_redis_error",
            error=str(e),
        )
        voice_tts_mode_cache_total.labels(result="error").inc()

        try:
            async with get_db_context() as db:
                stmt = select(SystemSetting).where(
                    SystemSetting.key == SystemSettingKey.VOICE_TTS_MODE
                )
                result = await db.execute(stmt)
                setting = result.scalar_one_or_none()
                return (
                    cast(VoiceTTSMode, setting.value)
                    if setting
                    else settings.voice_tts_default_mode
                )
        except Exception as db_err:
            logger.error(
                "voice_tts_mode_fallback_db_error",
                error=str(db_err),
            )
            return settings.voice_tts_default_mode

    except Exception as e:
        # Unexpected error: use default
        logger.error(
            "voice_tts_mode_cache_unexpected_error",
            error=str(e),
            error_type=type(e).__name__,
        )
        voice_tts_mode_cache_total.labels(result="error").inc()
        return settings.voice_tts_default_mode


async def invalidate_voice_tts_mode_cache() -> None:
    """
    Invalidate voice TTS mode cache.

    Call this when:
    - Admin changes the voice TTS mode
    - System settings are reset

    Example:
        >>> await invalidate_voice_tts_mode_cache()
    """
    from src.infrastructure.cache.redis import get_redis_cache

    try:
        redis = await get_redis_cache()
        cache = VoiceTTSModeCache(redis)
        await cache.invalidate()

    except RedisError as e:
        # Non-fatal: cache will expire naturally via TTL
        logger.warning(
            "voice_tts_mode_cache_invalidation_redis_error",
            error=str(e),
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
                    await redis.setex(
                        REDIS_KEY_DEBUG_PANEL_ENABLED,
                        DEBUG_PANEL_CACHE_TTL_SECONDS,
                        "true" if enabled else "false",
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
                    await redis.setex(
                        REDIS_KEY_DEBUG_PANEL_USER_ACCESS_ENABLED,
                        DEBUG_PANEL_USER_ACCESS_CACHE_TTL_SECONDS,
                        "true" if enabled else "false",
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
