"""The real browser bounds reach the tools as typed refusals, never text markers."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.config import settings
from src.domains.agents.tools.browser_tools import _browser_failure
from src.infrastructure.browser.errors import BrowserRefusal
from src.infrastructure.browser.pool import BrowserPool
from src.infrastructure.browser.session import BrowserSession

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "verdict,code", [("full", "RATE_LIMIT_EXCEEDED"), ("unsupported", "DEPENDENCY_ERROR")]
)
async def test_an_unavailable_admission_refuses_before_creating_a_session(
    verdict: str, code: str
) -> None:
    redis = AsyncMock()
    redis.eval.return_value = [verdict, ""]
    pool = BrowserPool()
    with patch("src.infrastructure.cache.redis.get_redis_cache", AsyncMock(return_value=redis)):
        with pytest.raises(BrowserRefusal) as raised:
            await pool._reserve_session_redis("bounded-user")
    output = _browser_failure(raised.value, "browser_capacity_test")
    assert output.error_code == code
    if verdict == "full":
        assert "Maximum concurrent" in output.message
    redis.eval.assert_awaited_once()


async def test_the_navigation_cap_refuses_before_security_or_page_io() -> None:
    context = MagicMock(new_page=AsyncMock())
    security = MagicMock(validate_navigation_url=AsyncMock())
    session = BrowserSession("bounded-user", context, security)
    session.navigation_count = settings.browser_max_navigations_per_session
    with pytest.raises(BrowserRefusal) as raised:
        await session.navigate("https://example.org")
    assert (
        _browser_failure(raised.value, "browser_navigation_test").error_code
        == "RATE_LIMIT_EXCEEDED"
    )
    security.validate_navigation_url.assert_not_awaited()
    context.new_page.assert_not_awaited()


async def test_an_unhealthy_pool_has_no_session_to_lend() -> None:
    pool = BrowserPool()
    with pytest.raises(BrowserRefusal) as raised:
        await pool.acquire_session("bounded-user")
    assert _browser_failure(raised.value, "browser_pool_test").error_code == "DEPENDENCY_ERROR"


async def test_a_security_refusal_exposes_no_arbitrary_reason() -> None:
    security = MagicMock(
        validate_navigation_url=AsyncMock(return_value=(False, "private instruction"))
    )
    context = MagicMock(new_page=AsyncMock())
    session = BrowserSession("bounded-user", context, security)
    with pytest.raises(BrowserRefusal) as raised:
        await session.navigate("https://example.org")
    result = _browser_failure(raised.value, "browser_security_test")
    assert result.error_code == "INVALID_INPUT"
    assert "private instruction" not in result.message
    context.new_page.assert_not_awaited()
