"""
Browser session pool with cross-worker recovery via Redis.

Manages Playwright browser instances and sessions with:
- Module-level singleton (pattern: infrastructure/cache/redis.py)
- Atomic logical-session coordination and ownership fencing via Redis
- Cross-worker session recovery via Redis metadata
- Bounded logical/local session counts and recovery metadata
- Worker-owned idle session cleanup

Phase: evolution F7 — Browser Control (Playwright)
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from contextlib import suppress
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import structlog

from src.core.config import settings
from src.core.constants import (
    BROWSER_COORDINATION_TIMEOUT_SECONDS,
    BROWSER_RECOVERY_TITLE_MAX_CHARS,
    BROWSER_RECOVERY_URL_MAX_CHARS,
    BROWSER_SESSION_MAINTENANCE_INTERVAL_SECONDS,
    DEFAULT_USER_DISPLAY_TIMEZONE,
    REDIS_KEY_BROWSER_SESSION_PREFIX,
)
from src.core.i18n import get_locale_for_language
from src.infrastructure.browser import coordination
from src.infrastructure.browser.coordination import BrowserCoordinationUnavailable
from src.infrastructure.browser.errors import BrowserRefusal, BrowserRefusalReason
from src.infrastructure.browser.models import BrowserSessionInfo
from src.infrastructure.browser.security import BrowserSecurityPolicy
from src.infrastructure.observability.log_facts import url_host
from src.infrastructure.observability.metrics_browser import (
    browser_errors_total,
    browser_sessions_active,
)

if TYPE_CHECKING:
    from playwright.async_api import Browser, Playwright

    from src.infrastructure.browser.session import BrowserSession

logger = structlog.get_logger(__name__)

# Module-level singleton (pattern: infrastructure/cache/redis.py)
_browser_pool: BrowserPool | None = None
_browser_pool_start: asyncio.Task[None] | None = None
_browser_pool_lock = asyncio.Lock()


async def get_browser_pool() -> BrowserPool:
    """Return the browser pool singleton, created and launched on the first call.

    Returns:
        The pool. A launch that failed leaves it unhealthy — every session
        acquisition then refuses — until the process restarts.
    """
    global _browser_pool, _browser_pool_start
    async with _browser_pool_lock:
        if _browser_pool is None:
            _browser_pool = BrowserPool()
            _browser_pool_start = asyncio.create_task(_browser_pool.initialize())
        if _browser_pool_start is not None:
            # A request owns its wait, not the process-wide driver startup.
            await asyncio.shield(_browser_pool_start)
        return _browser_pool


async def close_browser_pool() -> None:
    """Shut down the browser pool and release all resources."""
    global _browser_pool, _browser_pool_start
    async with _browser_pool_lock:
        if _browser_pool_start is not None:
            await asyncio.shield(_browser_pool_start)
        if _browser_pool is not None:
            try:
                await _browser_pool.close()
            finally:
                _browser_pool = None
                _browser_pool_start = None


async def cleanup_browser_sessions() -> None:
    """Cleanup expired browser sessions if pool is initialized.

    Safe to call even when pool is not yet initialized (no-op).
    Registered as APScheduler job at startup — the leader election pattern
    requires all workers to have the job registered, but the pool may only
    be initialized on the worker that handles the first browser request.
    """
    if _browser_pool is not None and _browser_pool.is_healthy:
        await _browser_pool.cleanup_expired()


class BrowserPool:
    """Manages Playwright browser instances and sessions.

    Provides session acquisition with global coordination via Redis,
    cross-worker recovery and idle cleanup.
    """

    def __init__(self) -> None:
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._sessions: dict[str, BrowserSession] = {}
        self._session_info: dict[str, BrowserSessionInfo] = {}
        self._maintenance_task: asyncio.Task[None] | None = None
        self._coordination_down = False
        self._lock = asyncio.Lock()
        self._healthy = False
        self._security = BrowserSecurityPolicy()
        self._pid = os.getpid()

    @property
    def is_healthy(self) -> bool:
        """Whether the browser pool is initialized and healthy."""
        return self._healthy

    async def initialize(self) -> None:
        """Start Playwright and launch the Chromium the deployment declares.

        ``browser_chromium_executable`` names the binary — the images' Debian
        package (ADR-059 amendment 2026-10-02); unset, Playwright starts its
        bundled build. A launch that fails never crashes the caller: it stops
        the driver it started, is counted on the browser dashboard
        (``browser_errors_total{error_type="launch_failed"}``) and leaves the
        pool unhealthy.
        """
        executable = settings.browser_chromium_executable
        try:
            # Lazy import — Playwright may not be installed
            from playwright.async_api import async_playwright

            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=True,
                executable_path=executable,
                args=[
                    "--disable-gpu",
                    "--disable-dev-shm-usage",
                    "--no-sandbox",  # Docker gives Chromium no user namespace (ADR-059)
                    "--disable-extensions",
                    # Anti-detection: reduce headless browser fingerprint
                    "--disable-blink-features=AutomationControlled",
                    "--disable-infobars",
                    "--window-size=1280,720",
                ],
            )
            self._healthy = True
            logger.info(
                "browser_pool_initialized",
                pid=self._pid,
                chromium=self._browser.version,
                executable=executable or "bundled",
            )
        except asyncio.CancelledError:
            self._healthy = False
            await self._stop_driver()
            raise
        except Exception as e:
            self._healthy = False
            await self._stop_driver()
            browser_errors_total.labels(error_type="launch_failed").inc()
            logger.warning(
                "browser_pool_initialization_failed",
                error_type=type(e).__name__,
                pid=self._pid,
                executable=executable or "bundled",
            )
            logger.debug("browser_error_detail", error=str(e))

    async def _stop_driver(self) -> None:
        """Stop the Playwright driver a failed launch started.

        Its process would otherwise live as long as the worker, serving nothing.
        """
        if self._playwright is None:
            return
        try:
            await self._playwright.stop()
        except Exception as stop_error:
            # The launch failure is the signal already logged; a stop that fails
            # too must not mask it.
            logger.debug("browser_driver_stop_failed", error_type=type(stop_error).__name__)
        self._playwright = None

    async def acquire_session(
        self,
        user_id: str,
        user_language: str | None = None,
        user_timezone: str = DEFAULT_USER_DISPLAY_TIMEZONE,
    ) -> BrowserSession:
        """Acquire or create a browser session for the given user.

        Checks for existing local session first (fast path), then attempts
        cross-worker recovery via Redis metadata, or creates a new session.

        Global session count is coordinated via Redis to respect
        browser_max_concurrent_sessions across all workers.

        Args:
            user_id: The user requesting a browser session.
            user_language: User's language code (e.g., "fr", "en", "de"); the
                declared language when absent (ADR-323).
            user_timezone: User's timezone (e.g., "Europe/Paris").

        Returns:
            BrowserSession instance ready for use.

        Raises:
            ValueError: If global max sessions reached or pool unhealthy.
        """
        async with self._lock:
            if not self._healthy or not self._browser:
                raise BrowserRefusal(BrowserRefusalReason.UNHEALTHY)
            # Fast path: reuse existing local session
            if user_id in self._sessions:
                if await self._owns_session(user_id):
                    session = self._sessions[user_id]
                    session.last_activity = time.monotonic()
                    return session
                await self._release_locked(user_id)

            # Redis fail-open retains availability, never an unbounded local pool.
            if len(self._sessions) >= settings.browser_max_concurrent_sessions:
                raise BrowserRefusal(BrowserRefusalReason.CAPACITY)

            # Claim BEFORE the awaited context allocation. The same-user transfer
            # preserves the logical-session contract and fences the previous owner.
            recovery_url = await self._reserve_session_redis(user_id)

            # Create new session
            # Lazy import to avoid ModuleNotFoundError when browser_enabled=False
            from src.infrastructure.browser.session import BrowserSession

            # The browser speaks the person's locale ("fr" → "fr-FR"): the one
            # display-locale table, never a copy of it (ADR-323).
            browser_locale = get_locale_for_language(user_language)
            base_lang = browser_locale.split("-")[0]
            accept_lang = f"{browser_locale},{base_lang};q=0.9,en-US;q=0.8,en;q=0.7"

            try:
                context = await self._browser.new_context(
                    user_agent=settings.browser_user_agent,
                    viewport={"width": 1280, "height": 720},
                    locale=browser_locale,
                    timezone_id=user_timezone,
                    color_scheme="light",
                    java_script_enabled=True,
                    extra_http_headers={"Accept-Language": accept_lang},
                )
            except BaseException:
                await self._discard_reservation(user_id)
                raise
            try:
                # Remove navigator.webdriver flag (primary bot detection signal)
                await context.add_init_script(
                    "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
                )
                if not await self._owns_session(user_id):
                    raise BrowserRefusal(BrowserRefusalReason.SESSION_MOVED)
            except BaseException:
                # Ownership has not reached a session yet. Even a cancelled
                # initialization must close the context it already allocated.
                try:
                    await context.close()
                except BaseException as cleanup_error:
                    logger.warning(
                        "browser_uninitialized_context_cleanup_failed",
                        error_type=type(cleanup_error).__name__,
                    )
                    logger.debug("browser_error_detail", error=str(cleanup_error))
                await self._discard_reservation(user_id)
                raise

            session = BrowserSession(
                user_id=user_id,
                context=context,
                security=self._security,
            )
            self._sessions[user_id] = session

            browser_sessions_active.inc()
            self._ensure_maintenance()

            # If recovery URL exists, auto-navigate
            if recovery_url:
                try:
                    await session.navigate(recovery_url)
                    logger.info(
                        "browser_session_recovered",
                        user_id=user_id[:8],
                        url_host=url_host(recovery_url),
                    )
                except Exception as e:
                    logger.warning(
                        "browser_session_recovery_failed",
                        user_id=user_id[:8],
                        url_host=url_host(recovery_url),
                        error_type=type(e).__name__,
                    )
                    logger.debug("browser_error_detail", error=str(e))

            return session

    async def release_session(self, user_id: str) -> None:
        """Release and close a user's browser session.

        Args:
            user_id: The user whose session to release.
        """
        async with self._lock:
            await self._release_locked(user_id)

    async def _release_locked(self, user_id: str) -> None:
        session = self._sessions.pop(user_id, None)
        if session is None:
            return
        try:
            try:
                await session.close()
            except BaseException:
                await self._discard_reservation(user_id)
                raise
            else:
                await self._remove_session_redis(user_id)
        finally:
            self._session_info.pop(user_id, None)
            browser_sessions_active.dec()
        logger.info("browser_session_released", user_id=user_id[:8])

    async def cleanup_expired(self) -> None:
        """Close sessions that have been idle longer than the timeout.

        Called periodically by APScheduler (AsyncIOScheduler).
        """
        timeout = settings.browser_session_timeout_seconds
        async with self._lock:
            for user_id, session in list(self._sessions.items()):
                # Recheck under the same lock as acquire: an earlier idle
                # snapshot must not close a session somebody just refreshed.
                idle = not session.is_busy and time.monotonic() - session.last_activity > timeout
                if idle or not await self._owns_session(user_id):
                    await self._release_locked(user_id)
                    logger.info("browser_session_retired", user_id=user_id[:8], idle=idle)

    def _ensure_maintenance(self) -> None:
        if not self._healthy:
            return
        if self._maintenance_task is None or self._maintenance_task.done():
            self._maintenance_task = asyncio.create_task(self._maintain())

    async def _maintain(self) -> None:
        """Every worker retires its own idle or superseded contexts, leader or not."""
        try:
            while self._sessions:
                await asyncio.sleep(
                    min(
                        BROWSER_SESSION_MAINTENANCE_INTERVAL_SECONDS,
                        settings.browser_session_timeout_seconds / 3,
                    )
                )
                try:
                    await self.cleanup_expired()
                except Exception as exc:
                    logger.warning("browser_pool_maintenance_failed", error_type=type(exc).__name__)
        finally:
            if self._maintenance_task is asyncio.current_task():
                self._maintenance_task = None

    async def close(self) -> None:
        """Shut down all sessions, the browser, and Playwright."""
        self._healthy = False
        task, self._maintenance_task = self._maintenance_task, None
        if task is not None and task is not asyncio.current_task():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        # Wait for an allocation already inside the lock, then drain its result
        # too. A snapshot taken before that allocation finished leaked a context.
        async with self._lock:
            failures: list[Exception] = []
            for user_id in list(self._sessions):
                try:
                    await self._release_locked(user_id)
                except Exception as exc:
                    failures.append(exc)
                    logger.warning("browser_session_close_failed", error_type=type(exc).__name__)
            if self._browser:
                browser = self._browser
                self._browser = None
                try:
                    await browser.close()
                except Exception as exc:
                    failures.append(exc)
                    logger.warning("browser_close_failed", error_type=type(exc).__name__)
            if self._playwright:
                playwright = self._playwright
                self._playwright = None
                try:
                    await playwright.stop()
                except Exception as exc:
                    failures.append(exc)
                    logger.warning("browser_driver_close_failed", error_type=type(exc).__name__)
            if failures:
                raise failures[0]
        logger.info("browser_pool_closed", pid=self._pid)

    # ========================================================================
    # Redis coordination (private methods)
    # ========================================================================

    def _coordination_failed(self, error: BrowserCoordinationUnavailable) -> None:
        if not self._coordination_down:
            self._coordination_down = True
            logger.warning(
                "browser_redis_coordination_failed",
                error_type=type(error.__cause__ or error).__name__,
            )
        logger.debug("browser_error_detail", error=str(error.__cause__ or error))

    async def _owns_session(self, user_id: str) -> bool:
        info = self._session_info.get(user_id)
        if info is None:
            return False
        try:
            owned = await coordination.renew(user_id, info.session_id)
        except BrowserCoordinationUnavailable as exc:
            self._coordination_failed(exc)
            return True  # Intentional availability fallback, within the local cap.
        self._coordination_down = False
        return owned

    async def _discard_reservation(self, user_id: str) -> None:
        """Clean up an aborted admission without replacing its primary failure."""
        try:
            await self._remove_session_redis(user_id)
        except BaseException as exc:
            logger.warning("browser_reservation_cleanup_failed", error_type=type(exc).__name__)
        finally:
            self._session_info.pop(user_id, None)

    async def _get_recovery_url(self, user_id: str) -> str | None:
        """Check Redis for an existing session on another worker.

        Args:
            user_id: The user to check for.

        Returns:
            The URL to recover to, or None if no existing session.
        """
        try:
            from src.infrastructure.cache.redis import get_redis_cache

            async with asyncio.timeout(BROWSER_COORDINATION_TIMEOUT_SECONDS):
                redis = await get_redis_cache()
                key = f"{REDIS_KEY_BROWSER_SESSION_PREFIX}{user_id}"
                data = await redis.get(key)
            if data:
                info = json.loads(data)
                # No local session exists here. A restarted worker can reuse the
                # old PID, so PID equality says nothing about context ownership.
                url = info.get("current_url")
                return (
                    url
                    if isinstance(url, str) and len(url) <= BROWSER_RECOVERY_URL_MAX_CHARS
                    else None
                )
        except Exception as e:
            logger.warning("browser_redis_recovery_check_failed", error_type=type(e).__name__)
            logger.debug("browser_error_detail", error=str(e))
        return None

    async def _reserve_session_redis(self, user_id: str) -> str | None:
        """Claim logical capacity before allocating a context, retaining a unique owner."""
        info = BrowserSessionInfo(
            session_id=str(uuid.uuid4()),
            user_id=user_id,
            created_at=datetime.now(UTC),
            current_url=None,
            page_title=None,
            worker_pid=self._pid,
            navigation_count=0,
        )
        self._session_info[user_id] = info
        try:
            previous = await coordination.reserve(user_id, info)
        except BrowserCoordinationUnavailable as exc:
            self._coordination_failed(exc)
            previous = None
        except BrowserRefusal:
            self._session_info.pop(user_id, None)
            raise
        except BaseException:
            await self._discard_reservation(user_id)
            raise
        else:
            self._coordination_down = False
        if previous is not None:
            info.current_url, info.page_title = previous.current_url, previous.page_title
        elif not self._coordination_down:
            try:
                info.current_url = await self._get_recovery_url(user_id)
            except asyncio.CancelledError:
                await self._discard_reservation(user_id)
                raise
        return info.current_url

    async def update_session_redis(self, user_id: str, url: str, title: str) -> None:
        """Update session metadata in Redis after navigation.

        Args:
            user_id: The session owner.
            url: The current page URL.
            title: The current page title.
        """
        async with self._lock:
            info = self._session_info.get(user_id)
            if info is None:
                return
            session = self._sessions.get(user_id)
            updated = info.model_copy(
                update={
                    # A cut signed URL is a different request: omit recovery
                    # rather than silently navigating a truncated destination.
                    "current_url": url if len(url) <= BROWSER_RECOVERY_URL_MAX_CHARS else None,
                    "page_title": title[:BROWSER_RECOVERY_TITLE_MAX_CHARS],
                    "navigation_count": (
                        session.navigation_count if session is not None else info.navigation_count
                    ),
                }
            )
            try:
                owned = await coordination.update(user_id, updated)
            except BrowserCoordinationUnavailable as exc:
                self._coordination_failed(exc)
                return
            self._coordination_down = False
            if owned:
                self._session_info[user_id] = updated
            else:
                # The navigation already happened. Retire the stale context;
                # never replace the newer owner's facts or retry the action.
                await self._release_locked(user_id)

    async def _remove_session_redis(self, user_id: str) -> None:
        """Remove session metadata from Redis.

        Args:
            user_id: The session owner.
        """
        info = self._session_info.get(user_id)
        if info is None:
            return
        try:
            await coordination.release(user_id, info.session_id)
        except BrowserCoordinationUnavailable as exc:
            self._coordination_failed(exc)
