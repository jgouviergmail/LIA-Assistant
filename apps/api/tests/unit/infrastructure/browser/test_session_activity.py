"""An awaited navigation is work, not an idle browser session."""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.config import settings
from src.infrastructure.browser.pool import BrowserPool
from src.infrastructure.browser.session import BrowserSession


@pytest.mark.parametrize("cancel", [False, True])
async def test_idle_cleanup_retains_an_inflight_navigation_and_closes_after_it_becomes_idle(
    monkeypatch: pytest.MonkeyPatch, cancel: bool
) -> None:
    entered, finish = asyncio.Event(), asyncio.Event()

    async def goto(*args: object, **kwargs: object) -> None:
        entered.set()
        await finish.wait()

    page = MagicMock()
    page.is_closed.return_value = False
    page.goto = goto
    page.wait_for_load_state = AsyncMock()
    page.close = AsyncMock()
    context = MagicMock(close=AsyncMock())
    security = MagicMock(validate_navigation_url=AsyncMock(return_value=(True, "")))
    session = BrowserSession("user", context, security)
    session.page = page
    monkeypatch.setattr(session, "_dismiss_cookie_banner", AsyncMock())
    monkeypatch.setattr(session, "get_page_content", AsyncMock())
    pool = BrowserPool()
    pool._sessions["user"] = session
    monkeypatch.setattr(pool, "_owns_session", AsyncMock(return_value=True))
    monkeypatch.setattr(pool, "_remove_session_redis", AsyncMock())
    from src.infrastructure.browser.pool import browser_sessions_active

    browser_sessions_active.inc()
    navigation = asyncio.create_task(session.navigate("https://example.test"))
    await asyncio.wait_for(entered.wait(), 1)
    session.last_activity = time.monotonic() - settings.browser_session_timeout_seconds - 1
    try:
        await pool.cleanup_expired()
        closed_while_busy = context.close.await_count
    finally:
        if cancel:
            navigation.cancel()
            with pytest.raises(asyncio.CancelledError):
                await navigation
        else:
            finish.set()
            await navigation
        session.last_activity = time.monotonic() - settings.browser_session_timeout_seconds - 1
        await pool.cleanup_expired()

    assert closed_while_busy == 0, "idle cleanup closed a navigation still awaiting its page"
    context.close.assert_awaited_once()
    assert "user" not in pool._sessions
