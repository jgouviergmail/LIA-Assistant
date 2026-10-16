"""Redis/CDP/SSRF failures expose facts above DEBUG, never their private text."""

import asyncio
from contextlib import contextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import structlog
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from redis.exceptions import ConnectionError as RedisConnectionError

from src.domains.agents.tools import browser_tools
from src.infrastructure.browser import accessibility, pool, security
from src.infrastructure.browser.models import BrowserSessionInfo
from src.infrastructure.browser.session import BrowserSession
from src.infrastructure.resilience import circuit_breaker
from tests.support.structlog_capture import fresh_module_logger

pytestmark = pytest.mark.unit
PRIVATE = "private mailbox body https://example.org/path?secret=yes"


@pytest.fixture(autouse=True)
def _independent_cdp_health(monkeypatch: pytest.MonkeyPatch) -> None:
    # Deliberate failures belong to this test, not the next test's service.
    breaker = circuit_breaker.CircuitBreaker("browser_cdp")
    monkeypatch.setattr(circuit_breaker, "get_circuit_breaker", lambda service: breaker)


@pytest.mark.parametrize("operation", ["reserve", "own", "recover", "update", "remove"])
@pytest.mark.parametrize("error_type", [OSError, RedisConnectionError])
async def test_a_redis_outage_keeps_its_fallback_and_no_private_log(
    operation: str, error_type: type[Exception]
) -> None:
    browser_pool = pool.BrowserPool()
    browser_pool._session_info["owner"] = BrowserSessionInfo(
        session_id="test-owner-token",
        user_id="owner",
        created_at=datetime.now(UTC),
        worker_pid=1,
    )
    with (
        contextmanager(fresh_module_logger)(pool),
        patch(
            "src.infrastructure.cache.redis.get_redis_cache",
            AsyncMock(side_effect=error_type(PRIVATE)),
        ),
        structlog.testing.capture_logs() as captured,
    ):
        if operation == "reserve":
            assert await browser_pool._reserve_session_redis("owner") is None
        elif operation == "own":
            assert await browser_pool._owns_session("owner") is True
        elif operation == "recover":
            assert await browser_pool._get_recovery_url("owner") is None
        elif operation == "update":
            await browser_pool.update_session_redis("owner", PRIVATE, PRIVATE)
        else:
            await browser_pool._remove_session_redis("owner")
    visible = [entry for entry in captured if entry["log_level"] != "debug"]
    assert len(visible) == 1
    assert visible[0]["error_type"] == error_type.__name__
    assert PRIVATE not in str(visible)


async def test_a_cdp_failure_detaches_and_does_not_log_the_page_text() -> None:
    cdp = MagicMock(send=AsyncMock(side_effect=RuntimeError(PRIVATE)), detach=AsyncMock())
    page = MagicMock()
    page.context.new_cdp_session = AsyncMock(return_value=cdp)
    with (
        contextmanager(fresh_module_logger)(accessibility),
        structlog.testing.capture_logs() as captured,
    ):
        with pytest.raises(RuntimeError, match="private mailbox"):
            await accessibility.AccessibilityTreeExtractor().extract(page)
    cdp.detach.assert_awaited_once()
    visible = [entry for entry in captured if entry["log_level"] != "debug"]
    failures = [
        entry for entry in visible if entry.get("event") == "browser_ax_tree_extraction_error"
    ]
    assert len(failures) == 1
    assert failures[0]["error_type"] == "RuntimeError"
    assert PRIVATE not in str(visible)


@pytest.mark.parametrize("operation", ["tree", "element"])
@pytest.mark.parametrize(
    "error_type", [RuntimeError, PlaywrightTimeoutError, asyncio.CancelledError]
)
async def test_detach_does_not_replace_the_primary_read_failure(
    operation: str, error_type: type[BaseException]
) -> None:
    primary = error_type("primary " + PRIVATE)
    cdp = MagicMock(
        send=AsyncMock(side_effect=primary), detach=AsyncMock(side_effect=OSError(PRIVATE))
    )
    page = MagicMock()
    page.context.new_cdp_session = AsyncMock(return_value=cdp)
    extractor = accessibility.AccessibilityTreeExtractor()
    if operation == "element":
        extractor.extract = AsyncMock(
            return_value=[
                accessibility.AXNode(
                    node_id="1", role="button", name="Button", backend_dom_node_id=99
                )
            ]
        )
    with (
        contextmanager(fresh_module_logger)(accessibility),
        structlog.testing.capture_logs() as captured,
    ):
        with pytest.raises(error_type) as raised:
            if operation == "tree":
                await extractor.extract(page)
            else:
                await extractor.find_element_by_ref(page, "E1")
    assert raised.value is primary
    cdp.detach.assert_awaited_once()
    visible = [entry for entry in captured if entry["log_level"] != "debug"]
    failures = [entry for entry in visible if entry.get("event") == "browser_cdp_detach_failed"]
    assert len(failures) == 1
    assert failures[0]["error_type"] == "OSError"
    assert PRIVATE not in str(visible)


async def test_an_interceptor_failure_still_aborts_without_logging_the_request() -> None:
    policy = security.BrowserSecurityPolicy()
    page = MagicMock(route=AsyncMock())
    await policy.create_request_interceptor(page)
    handler = page.route.call_args.args[1]
    request = MagicMock(url="https://example.org/path?secret=yes", resource_type="xhr")
    route = MagicMock(abort=AsyncMock(), continue_=AsyncMock(), request=request)
    with (
        contextmanager(fresh_module_logger)(security),
        patch.object(policy, "_host_is_reachable", AsyncMock(side_effect=RuntimeError(PRIVATE))),
        structlog.testing.capture_logs() as captured,
    ):
        await handler(route)
    route.abort.assert_awaited_once_with("blockedbyclient")
    route.continue_.assert_not_awaited()
    visible = [entry for entry in captured if entry["log_level"] != "debug"]
    assert len(visible) == 1
    assert visible[0]["error_type"] == "RuntimeError"
    assert "secret=yes" not in str(visible)
    assert PRIVATE not in str(visible)


@pytest.mark.parametrize("fails", [False, True], ids=["empty-page", "failed-read"])
async def test_a_failed_snapshot_is_distinct_from_a_successful_empty_page(fails: bool) -> None:
    cdp = MagicMock(
        send=AsyncMock(
            side_effect=RuntimeError(PRIVATE) if fails else None, return_value={"nodes": []}
        ),
        detach=AsyncMock(),
    )
    page = MagicMock(url="https://example.org", is_closed=MagicMock(return_value=False))
    page.title = AsyncMock(return_value="Empty page")
    page.context.new_cdp_session = AsyncMock(return_value=cdp)
    session = BrowserSession("owner", MagicMock(), MagicMock())
    session.page = page
    with (
        patch.object(
            browser_tools, "validate_runtime_config", return_value=SimpleNamespace(user_id="owner")
        ),
        patch.object(browser_tools, "_get_session", AsyncMock(return_value=(MagicMock(), session))),
        patch.object(browser_tools, "_emit_progressive_screenshot", AsyncMock()),
    ):
        result = await browser_tools.browser_snapshot_tool.coroutine()
    assert result.success is not fails
    if fails:
        assert result.error_code == "EXTERNAL_API_ERROR"
        assert PRIVATE not in result.message
    else:
        assert result.structured_data["interactive_count"] == 0
    cdp.detach.assert_awaited_once()
