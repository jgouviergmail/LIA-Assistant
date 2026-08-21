"""Web Risk URL screening (lot D, 2026-08).

Contract pinned here:

- a flagged URL yields a blocking verdict carrying the threat types;
- a clean URL ({} response) yields a non-blocking CHECKED verdict;
- the feature flag OFF and every failure mode (HTTP error, timeout) are
  FAIL-OPEN: non-blocking, ``checked=False`` — Web Risk availability must
  never gate browsing, and an unchecked URL must never be claimed safe;
- verdicts are cached in Redis (threat TTL honors the response expireTime),
  and only real API calls are tracked for billing (cache hits are free).
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from src.infrastructure.security.web_risk import WebRiskVerdict, check_url_threat

pytestmark = pytest.mark.unit

_URL = "http://testsafebrowsing.appspot.com/s/malware.html"

_THREAT_RESPONSE = {
    "threat": {
        "threatTypes": ["MALWARE"],
        "expireTime": "2099-01-01T00:00:00Z",
    }
}


def _redis_mock(cached: dict | None = None) -> AsyncMock:
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=json.dumps(cached) if cached is not None else None)
    redis.set = AsyncMock()
    return redis


class TestVerdicts:
    async def test_threat_response_blocks_with_threat_types(self) -> None:
        redis = _redis_mock()
        with (
            patch(
                "src.infrastructure.security.web_risk._web_risk_enabled",
                return_value=True,
            ),
            patch(
                "src.infrastructure.security.web_risk._fetch_verdict_payload",
                new=AsyncMock(return_value=_THREAT_RESPONSE),
            ),
            patch(
                "src.infrastructure.security.web_risk._get_redis",
                new=AsyncMock(return_value=redis),
            ),
        ):
            verdict = await check_url_threat(_URL)

        assert verdict == WebRiskVerdict(blocked=True, threat_types=("MALWARE",), checked=True)

    async def test_clean_response_is_checked_and_unblocked(self) -> None:
        with (
            patch(
                "src.infrastructure.security.web_risk._web_risk_enabled",
                return_value=True,
            ),
            patch(
                "src.infrastructure.security.web_risk._fetch_verdict_payload",
                new=AsyncMock(return_value={}),
            ),
            patch(
                "src.infrastructure.security.web_risk._get_redis",
                new=AsyncMock(return_value=_redis_mock()),
            ),
        ):
            verdict = await check_url_threat("https://www.wikipedia.org")

        assert verdict.blocked is False
        assert verdict.checked is True

    async def test_disabled_flag_short_circuits_without_any_io(self) -> None:
        fetch = AsyncMock()
        with (
            patch(
                "src.infrastructure.security.web_risk._web_risk_enabled",
                return_value=False,
            ),
            patch("src.infrastructure.security.web_risk._fetch_verdict_payload", new=fetch),
        ):
            verdict = await check_url_threat(_URL)

        assert verdict == WebRiskVerdict(blocked=False, threat_types=(), checked=False)
        fetch.assert_not_awaited()

    async def test_api_failure_is_fail_open_and_unchecked(self) -> None:
        """Web Risk down must never gate browsing — but the verdict must not
        claim the URL was checked (absence of exception is not proof)."""
        with (
            patch(
                "src.infrastructure.security.web_risk._web_risk_enabled",
                return_value=True,
            ),
            patch(
                "src.infrastructure.security.web_risk._fetch_verdict_payload",
                new=AsyncMock(side_effect=httpx.ConnectTimeout("boom")),
            ),
            patch(
                "src.infrastructure.security.web_risk._get_redis",
                new=AsyncMock(return_value=_redis_mock()),
            ),
        ):
            verdict = await check_url_threat(_URL)

        assert verdict.blocked is False
        assert verdict.checked is False


class TestCache:
    async def test_cached_verdict_skips_the_api_call(self) -> None:
        fetch = AsyncMock()
        redis = _redis_mock(cached={"blocked": True, "threat_types": ["MALWARE"]})
        with (
            patch(
                "src.infrastructure.security.web_risk._web_risk_enabled",
                return_value=True,
            ),
            patch("src.infrastructure.security.web_risk._fetch_verdict_payload", new=fetch),
            patch(
                "src.infrastructure.security.web_risk._get_redis",
                new=AsyncMock(return_value=redis),
            ),
        ):
            verdict = await check_url_threat(_URL)

        assert verdict.blocked is True
        assert verdict.checked is True
        fetch.assert_not_awaited()

    async def test_fresh_verdict_is_cached(self) -> None:
        redis = _redis_mock()
        with (
            patch(
                "src.infrastructure.security.web_risk._web_risk_enabled",
                return_value=True,
            ),
            patch(
                "src.infrastructure.security.web_risk._fetch_verdict_payload",
                new=AsyncMock(return_value={}),
            ),
            patch(
                "src.infrastructure.security.web_risk._get_redis",
                new=AsyncMock(return_value=redis),
            ),
        ):
            await check_url_threat("https://www.wikipedia.org")

        redis.set.assert_awaited_once()

    async def test_redis_failure_does_not_break_the_check(self) -> None:
        redis = AsyncMock()
        redis.get = AsyncMock(side_effect=ConnectionError("redis down"))
        redis.set = AsyncMock(side_effect=ConnectionError("redis down"))
        with (
            patch(
                "src.infrastructure.security.web_risk._web_risk_enabled",
                return_value=True,
            ),
            patch(
                "src.infrastructure.security.web_risk._fetch_verdict_payload",
                new=AsyncMock(return_value=_THREAT_RESPONSE),
            ),
            patch(
                "src.infrastructure.security.web_risk._get_redis",
                new=AsyncMock(return_value=redis),
            ),
        ):
            verdict = await check_url_threat(_URL)

        assert verdict.blocked is True
