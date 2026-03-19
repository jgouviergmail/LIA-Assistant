"""
Browser session pool with cross-worker recovery via Redis.

Manages Playwright browser instances and sessions with:
- Module-level singleton (pattern: infrastructure/cache/redis.py)
- Global session coordination via Redis key counting
- Cross-worker session recovery via Redis metadata
- Memory monitoring and resource limits
- APScheduler-based idle session cleanup

Phase: evolution F7 — Browser Control (Playwright)
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import structlog

from src.core.config import settings
from src.core.constants import REDIS_KEY_BROWSER_SESSION_PREFIX
from src.infrastructure.browser.models import BrowserSessionInfo
from src.infrastructure.browser.security import BrowserSecurityPolicy
from src.infrastructure.observability.metrics_browser import (
    browser_memory_bytes,
    browser_sessions_active,
)

if TYPE_CHECKING:
    from playwright.async_api import Browser, Playwright

logger = structlog.get_logger(__name__)

# Module-level singleton (pattern: infrastructure/cache/redis.py)
_browser_pool: BrowserPool | None = None


async def get_browser_pool() -> BrowserPool | None:
    """Return the browser pool singleton, or None if not initialized.

    Returns:
        BrowserPool instance if initialized and healthy, None otherwise.
    """
    global _browser_pool
    if _browser_pool is None:
        _browser_pool = BrowserPool()
        await _browser_pool.initialize()
    return _browser_pool


async def close_browser_pool() -> None:
    """Shut down the browser pool and release all resources."""
    global _browser_pool
    if _browser_pool:
        await _browser_pool.close()
        _browser_pool = None


class BrowserPool:
    """Manages Playwright browser instances and sessions.

    Provides session acquisition with global coordination via Redis,
    cross-worker recovery, memory monitoring, and idle cleanup.
    """

    def __init__(self) -> None:
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._sessions: dict[str, Any] = {}  # user_id -> BrowserSession
        self._lock = asyncio.Lock()
        self._healthy = False
        self._security = BrowserSecurityPolicy()
        self._pid = os.getpid()

    @property
    def is_healthy(self) -> bool:
        """Whether the browser pool is initialized and healthy."""
        return self._healthy

    async def initialize(self) -> None:
        """Initialize Playwright and launch Chromium.

        If Chromium binary is not available, logs a warning and sets
        is_healthy=False (does not crash).
        """
        try:
            # Lazy import — Playwright may not be installed
            from playwright.async_api import async_playwright

            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=True,
                args=[
                    "--disable-gpu",
                    "--disable-dev-shm-usage",
                    "--no-sandbox",  # Required in Docker (see ADR-056)
                    "--disable-extensions",
                    # Anti-detection: reduce headless browser fingerprint
                    "--disable-blink-features=AutomationControlled",
                    "--disable-infobars",
                    "--window-size=1280,720",
                ],
            )
            self._healthy = True
            logger.info("browser_pool_initialized", pid=self._pid)
        except Exception as e:
            self._healthy = False
            logger.warning(
                "browser_pool_initialization_failed",
                error=str(e),
                pid=self._pid,
            )

    async def acquire_session(
        self,
        user_id: str,
        user_language: str = "fr",
        user_timezone: str = "Europe/Paris",
    ) -> Any:
        """Acquire or create a browser session for the given user.

        Checks for existing local session first (fast path), then attempts
        cross-worker recovery via Redis metadata, or creates a new session.

        Global session count is coordinated via Redis to respect
        browser_max_concurrent_sessions across all workers.

        Args:
            user_id: The user requesting a browser session.
            user_language: User's language code (e.g., "fr", "en", "de").
            user_timezone: User's timezone (e.g., "Europe/Paris").

        Returns:
            BrowserSession instance ready for use.

        Raises:
            ValueError: If global max sessions reached or pool unhealthy.
        """
        if not self._healthy or not self._browser:
            raise ValueError("Browser pool is not healthy")

        async with self._lock:
            # Fast path: reuse existing local session
            if user_id in self._sessions:
                session = self._sessions[user_id]
                session.last_activity = time.monotonic()
                return session

            # Check global session count via Redis
            # Exclude current user's own session (recovery replaces, doesn't add)
            await self._check_global_session_limit(exclude_user_id=user_id)

            # Check for cross-worker recovery (Redis metadata)
            recovery_url = await self._get_recovery_url(user_id)

            # Create new session
            # Lazy import to avoid ModuleNotFoundError when browser_enabled=False
            from src.infrastructure.browser.session import BrowserSession

            # Build locale from user language (e.g., "fr" → "fr-FR", "en" → "en-US")
            lang = user_language.lower().split("-")[0]  # Normalize "zh-CN" → "zh"
            locale_map = {
                "fr": "fr-FR",
                "en": "en-US",
                "de": "de-DE",
                "es": "es-ES",
                "it": "it-IT",
                "zh": "zh-CN",
            }
            browser_locale = locale_map.get(lang, "en-US")
            accept_lang = f"{browser_locale},{lang};q=0.9,en-US;q=0.8,en;q=0.7"

            context = await self._browser.new_context(
                user_agent=settings.browser_user_agent,
                viewport={"width": 1280, "height": 720},
                # Anti-detection: realistic browser context with user preferences
                locale=browser_locale,
                timezone_id=user_timezone,
                color_scheme="light",
                java_script_enabled=True,
                extra_http_headers={
                    "Accept-Language": accept_lang,
                },
            )
            # Remove navigator.webdriver flag (primary bot detection signal)
            await context.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )

            session = BrowserSession(
                user_id=user_id,
                context=context,
                security=self._security,
            )
            self._sessions[user_id] = session

            # Register in Redis for cross-worker coordination
            await self._register_session_redis(user_id, session)
            browser_sessions_active.inc()

            # If recovery URL exists, auto-navigate
            if recovery_url:
                try:
                    await session.navigate(recovery_url)
                    logger.info(
                        "browser_session_recovered",
                        user_id=user_id[:8],
                        url=recovery_url[:100],
                    )
                except Exception as e:
                    logger.warning(
                        "browser_session_recovery_failed",
                        user_id=user_id[:8],
                        url=recovery_url[:100],
                        error=str(e),
                    )

            return session

    async def release_session(self, user_id: str) -> None:
        """Release and close a user's browser session.

        Args:
            user_id: The user whose session to release.
        """
        async with self._lock:
            session = self._sessions.pop(user_id, None)
            if session:
                await session.close()
                await self._remove_session_redis(user_id)
                browser_sessions_active.dec()
                logger.info("browser_session_released", user_id=user_id[:8])

    async def cleanup_expired(self) -> None:
        """Close sessions that have been idle longer than the timeout.

        Called periodically by APScheduler (AsyncIOScheduler).
        """
        timeout = settings.browser_session_timeout_seconds
        now = time.monotonic()
        expired_users: list[str] = []

        async with self._lock:
            for user_id, session in self._sessions.items():
                if now - session.last_activity > timeout:
                    expired_users.append(user_id)

        for user_id in expired_users:
            await self.release_session(user_id)
            logger.info("browser_session_expired_cleanup", user_id=user_id[:8])

    def get_memory_usage_mb(self) -> float | None:
        """Get current process memory usage in MB.

        Uses /proc/{pid}/status on Linux (production RPi5).
        Returns None if unavailable (Windows, macOS).

        Returns:
            Memory usage in MB, or None if not available.
        """
        try:
            pid = os.getpid()
            with open(f"/proc/{pid}/status") as f:
                for line in f:
                    if line.startswith("VmRSS:"):
                        # VmRSS is in kB
                        kb = int(line.split()[1])
                        mb = kb / 1024.0
                        browser_memory_bytes.set(kb * 1024)  # Convert kB → bytes
                        return mb
        except (FileNotFoundError, OSError, ValueError):
            pass
        return None

    async def close(self) -> None:
        """Shut down all sessions, the browser, and Playwright."""
        # Close all sessions
        user_ids = list(self._sessions.keys())
        for user_id in user_ids:
            await self.release_session(user_id)

        # Close browser
        if self._browser:
            await self._browser.close()
            self._browser = None

        # Stop Playwright
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

        self._healthy = False
        logger.info("browser_pool_closed", pid=self._pid)

    # ========================================================================
    # Redis coordination (private methods)
    # ========================================================================

    async def _check_global_session_limit(self, exclude_user_id: str | None = None) -> None:
        """Check if global session count allows a new session.

        Args:
            exclude_user_id: Don't count this user's existing session (recovery case).

        Raises:
            ValueError: If max concurrent sessions reached globally.
        """
        try:
            from src.infrastructure.cache.redis import get_redis_cache

            redis = await get_redis_cache()
            # Count active browser session keys
            keys = await redis.keys(f"{REDIS_KEY_BROWSER_SESSION_PREFIX}*")

            # Exclude current user's own key (recovery doesn't add a new session)
            if exclude_user_id:
                own_key = f"{REDIS_KEY_BROWSER_SESSION_PREFIX}{exclude_user_id}"
                keys = [k for k in keys if k != own_key and k != own_key.encode()]

            active_count = len(keys)

            if active_count >= settings.browser_max_concurrent_sessions:
                raise ValueError(
                    f"Maximum concurrent browser sessions reached "
                    f"({active_count}/{settings.browser_max_concurrent_sessions})"
                )
        except ValueError:
            raise
        except Exception as e:
            # Redis unavailable — allow session (fail open for availability)
            logger.warning("browser_redis_check_failed", error=str(e))

    async def _get_recovery_url(self, user_id: str) -> str | None:
        """Check Redis for an existing session on another worker.

        Args:
            user_id: The user to check for.

        Returns:
            The URL to recover to, or None if no existing session.
        """
        try:
            from src.infrastructure.cache.redis import get_redis_cache

            redis = await get_redis_cache()
            key = f"{REDIS_KEY_BROWSER_SESSION_PREFIX}{user_id}"
            data = await redis.get(key)
            if data:
                info = json.loads(data)
                # Only recover if the session was on a DIFFERENT worker
                if info.get("worker_pid") != self._pid:
                    return info.get("current_url")
        except Exception as e:
            logger.warning("browser_redis_recovery_check_failed", error=str(e))
        return None

    async def _register_session_redis(self, user_id: str, session: Any) -> None:
        """Register session metadata in Redis for cross-worker recovery.

        Args:
            user_id: The session owner.
            session: The BrowserSession instance.
        """
        try:
            from src.infrastructure.cache.redis import get_redis_cache

            redis = await get_redis_cache()
            key = f"{REDIS_KEY_BROWSER_SESSION_PREFIX}{user_id}"
            info = BrowserSessionInfo(
                session_id=str(uuid.uuid4()),
                user_id=user_id,
                created_at=datetime.now(UTC),
                current_url=None,
                page_title=None,
                worker_pid=self._pid,
                navigation_count=0,
            )
            await redis.setex(
                key,
                settings.browser_session_timeout_seconds,
                info.model_dump_json(),
            )
        except Exception as e:
            logger.warning("browser_redis_register_failed", error=str(e))

    async def update_session_redis(self, user_id: str, url: str, title: str) -> None:
        """Update session metadata in Redis after navigation.

        Args:
            user_id: The session owner.
            url: The current page URL.
            title: The current page title.
        """
        try:
            from src.infrastructure.cache.redis import get_redis_cache

            redis = await get_redis_cache()
            key = f"{REDIS_KEY_BROWSER_SESSION_PREFIX}{user_id}"
            data = await redis.get(key)
            if data:
                info_dict = json.loads(data)
                info_dict["current_url"] = url
                info_dict["page_title"] = title
                info_dict["worker_pid"] = self._pid
                await redis.setex(
                    key,
                    settings.browser_session_timeout_seconds,
                    json.dumps(info_dict),
                )
        except Exception as e:
            logger.warning("browser_redis_update_failed", error=str(e))

    async def _remove_session_redis(self, user_id: str) -> None:
        """Remove session metadata from Redis.

        Args:
            user_id: The session owner.
        """
        try:
            from src.infrastructure.cache.redis import get_redis_cache

            redis = await get_redis_cache()
            key = f"{REDIS_KEY_BROWSER_SESSION_PREFIX}{user_id}"
            await redis.delete(key)
        except Exception as e:
            logger.warning("browser_redis_remove_failed", error=str(e))
