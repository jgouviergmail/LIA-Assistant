"""
Unit tests for browser session pool.

Phase: evolution F7 — Browser Control (Playwright)
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from prometheus_client import REGISTRY

from src.core.config import settings
from src.infrastructure.browser.pool import BrowserPool

_ERRORS = "browser_errors_total"
_LAUNCH_FAILED = {"error_type": "launch_failed"}


class _Browser:
    """What Playwright hands back from a successful launch."""

    version = "154.0.8037.92"

    async def close(self) -> None:
        """Nothing to release."""


class _Chromium:
    """Records each launch; raises like Playwright when the binary is missing."""

    def __init__(self, *, fails: bool) -> None:
        self.launches: list[dict[str, object]] = []
        self._fails = fails

    async def launch(self, **options: object) -> _Browser:
        self.launches.append(options)
        if self._fails:
            raise RuntimeError("Executable doesn't exist at /usr/bin/chromium")
        return _Browser()


class _Playwright:
    """The started driver: one browser type, and a stop the pool must call."""

    def __init__(self, *, fails: bool) -> None:
        self.chromium = _Chromium(fails=fails)
        self.stopped = False

    async def stop(self) -> None:
        self.stopped = True


class _Starter:
    """``async_playwright()``: an object whose ``start()`` yields the driver."""

    def __init__(self, driver: _Playwright) -> None:
        self._driver = driver

    async def start(self) -> _Playwright:
        return self._driver


@contextmanager
def _driver(*, fails: bool = False) -> Iterator[_Playwright]:
    """Replace Playwright's entry point with a recording driver."""
    driver = _Playwright(fails=fails)
    with patch("playwright.async_api.async_playwright", lambda: _Starter(driver)):
        yield driver


class TestBrowserPool:
    """Tests for BrowserPool."""

    def test_pool_init_not_healthy(self):
        """Pool starts as not healthy before initialize()."""
        pool = BrowserPool()
        assert not pool.is_healthy


class TestBrowserPoolLaunch:
    """The pool launches the Chromium the deployment declares (ADR-059 amendment)."""

    @pytest.mark.parametrize("declared", ["/usr/bin/chromium", None])
    async def test_the_declared_executable_is_the_one_launched(
        self, monkeypatch: pytest.MonkeyPatch, declared: str | None
    ) -> None:
        monkeypatch.setattr(settings, "browser_chromium_executable", declared)
        pool = BrowserPool()

        with _driver() as driver:
            await pool.initialize()

        assert pool.is_healthy
        (launch,) = driver.chromium.launches
        assert launch["executable_path"] == declared
        assert launch["headless"] is True
        # Docker has no user namespace for Chromium's own sandbox (ADR-059).
        assert "--no-sandbox" in launch["args"]  # type: ignore[operator]

    async def test_a_failed_launch_is_counted_and_releases_the_driver(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "browser_chromium_executable", "/usr/bin/chromium")
        before = REGISTRY.get_sample_value(_ERRORS, _LAUNCH_FAILED) or 0.0
        pool = BrowserPool()

        with _driver(fails=True) as driver:
            await pool.initialize()

        assert not pool.is_healthy
        # The engine moves with every image build: a launch the driver can no
        # longer make must reach the browser dashboard, not a log line alone.
        assert REGISTRY.get_sample_value(_ERRORS, _LAUNCH_FAILED) == before + 1
        # The driver process was started for nothing; it must not live on.
        assert driver.stopped
        with pytest.raises(ValueError, match="not healthy"):
            await pool.acquire_session("user123")


class TestBrowserPoolSessionLimit:
    """Tests for global session coordination."""

    @pytest.mark.asyncio
    async def test_pool_unhealthy_raises(self):
        """Acquiring session on unhealthy pool raises ValueError."""
        pool = BrowserPool()
        with pytest.raises(ValueError, match="not healthy"):
            await pool.acquire_session("user123")


@pytest.mark.parametrize("cancelled", [False, True])
@pytest.mark.parametrize("cleanup_fails", [False, True])
@pytest.mark.parametrize("redis_cleanup_fails", [False, True])
async def test_an_uninitialized_context_is_closed_without_losing_the_primary_failure(
    monkeypatch: pytest.MonkeyPatch, cancelled: bool, cleanup_fails: bool, redis_cleanup_fails: bool
) -> None:
    """Playwright owns a context even when installing its initial script fails."""
    failure = asyncio.CancelledError() if cancelled else RuntimeError("initialization failed")
    context = MagicMock()
    context.add_init_script = AsyncMock(side_effect=failure)
    context.close = AsyncMock(side_effect=OSError("cleanup failed") if cleanup_fails else None)
    browser = MagicMock()
    browser.new_context = AsyncMock(return_value=context)
    pool = BrowserPool()
    pool._browser = browser
    pool._healthy = True
    monkeypatch.setattr(pool, "_reserve_session_redis", AsyncMock(return_value=None))
    monkeypatch.setattr(
        pool,
        "_remove_session_redis",
        AsyncMock(
            side_effect=(
                RuntimeError("secondary Redis protocol failure") if redis_cleanup_fails else None
            )
        ),
    )
    before = REGISTRY.get_sample_value("browser_sessions_active")

    with pytest.raises(type(failure)) as caught:
        await pool.acquire_session("new-user")

    assert caught.value is failure
    context.close.assert_awaited_once()
    assert "new-user" not in pool._sessions
    assert REGISTRY.get_sample_value("browser_sessions_active") == before
