"""Pool startup and shutdown remain owned when a requesting task disappears."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from prometheus_client import REGISTRY

from src.infrastructure.browser import pool as module
from src.infrastructure.browser.models import BrowserSessionInfo


@pytest.mark.parametrize("cancel_first", [False, True])
async def test_first_request_never_exposes_partial_startup(
    monkeypatch: pytest.MonkeyPatch, cancel_first: bool
) -> None:
    monkeypatch.setattr(module, "_browser_pool", None)
    monkeypatch.setattr(module, "_browser_pool_start", None, raising=False)
    monkeypatch.setattr(module, "_browser_pool_lock", asyncio.Lock(), raising=False)
    entered, finish = asyncio.Event(), asyncio.Event()
    calls = 0

    async def initialize(pool: module.BrowserPool) -> None:
        nonlocal calls
        calls += 1
        entered.set()
        await finish.wait()
        pool._healthy = True

    monkeypatch.setattr(module.BrowserPool, "initialize", initialize)
    first = asyncio.create_task(module.get_browser_pool())
    await asyncio.wait_for(entered.wait(), 1)
    if cancel_first:
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
    second = asyncio.create_task(module.get_browser_pool())
    await asyncio.sleep(0)
    exposed_partial = second.done()
    finish.set()
    try:
        pool = await asyncio.wait_for(second, 1)
        if not cancel_first:
            assert await first is pool
        assert not exposed_partial, "a caller received the pool before initialization completed"
        assert pool.is_healthy
        assert calls == 1
    finally:
        await module.close_browser_pool()


async def test_cancelled_launch_stops_the_started_driver(monkeypatch: pytest.MonkeyPatch) -> None:
    entered = asyncio.Event()
    driver = MagicMock()

    async def launch(**options: object) -> None:
        entered.set()
        await asyncio.Event().wait()

    driver.chromium.launch = launch
    driver.stop = AsyncMock()
    starter = MagicMock(start=AsyncMock(return_value=driver))
    monkeypatch.setattr("playwright.async_api.async_playwright", lambda: starter)
    pool = module.BrowserPool()
    starting = asyncio.create_task(pool.initialize())
    await asyncio.wait_for(entered.wait(), 1)
    starting.cancel()
    with pytest.raises(asyncio.CancelledError):
        await starting

    driver.stop.assert_awaited_once()
    assert not pool.is_healthy


async def test_shutdown_continues_past_context_and_browser_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool = module.BrowserPool()
    first_failure = OSError("context could not close")
    first = MagicMock(close=AsyncMock(side_effect=first_failure))
    second = MagicMock(close=AsyncMock())
    browser = MagicMock(close=AsyncMock(side_effect=OSError("browser disconnected")))
    driver = MagicMock(stop=AsyncMock())
    pool._browser = browser
    pool._playwright = driver
    pool._healthy = True
    pool._sessions = {"first": first, "second": second}
    pool._session_info = {"first": MagicMock(spec=BrowserSessionInfo)}
    remove = AsyncMock()
    monkeypatch.setattr(pool, "_remove_session_redis", remove)
    before = REGISTRY.get_sample_value("browser_sessions_active") or 0
    module.browser_sessions_active.inc(2)

    with pytest.raises(OSError) as caught:
        await pool.close()

    assert caught.value is first_failure
    first.close.assert_awaited_once()
    second.close.assert_awaited_once()
    browser.close.assert_awaited_once()
    driver.stop.assert_awaited_once()
    assert not pool._sessions
    assert not pool._session_info
    assert not pool.is_healthy
    assert pool._browser is None
    assert pool._playwright is None
    assert REGISTRY.get_sample_value("browser_sessions_active") == before


async def test_context_close_failure_reaches_the_pool_after_page_cleanup() -> None:
    from src.infrastructure.browser.session import BrowserSession

    failure = OSError("context disconnected")
    context = MagicMock(close=AsyncMock(side_effect=failure))
    page = MagicMock(close=AsyncMock(side_effect=OSError("page disconnected")))
    page.is_closed.return_value = False
    session = BrowserSession("user", context, MagicMock())
    session.page = page

    with pytest.raises(OSError) as caught:
        await session.close()

    assert caught.value is failure
    page.close.assert_awaited_once()
    context.close.assert_awaited_once()
    assert session.page is None
