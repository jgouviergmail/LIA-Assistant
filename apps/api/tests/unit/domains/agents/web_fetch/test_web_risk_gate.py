"""Web Risk gate of the web-fetch tool (lot D, 2026-08).

The gate sits AFTER SSRF validation and BEFORE the actual fetch:
- flagged URL → localized failure, page never fetched;
- clean / unchecked (fail-open) verdicts → None, the fetch proceeds.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domains.agents.tools.url_screening import web_risk_gate as _web_risk_gate
from src.infrastructure.security.web_risk import WebRiskVerdict

pytestmark = pytest.mark.unit


def _patch_verdict(verdict: WebRiskVerdict) -> object:
    return patch(
        "src.domains.agents.tools.url_screening.check_url_threat",
        new=AsyncMock(return_value=verdict),
    )


def _patch_language() -> object:
    return patch(
        "src.domains.agents.tools.runtime_helpers.get_user_language_safe",
        new=AsyncMock(return_value="fr"),
    )


class TestWebRiskGate:
    async def test_flagged_url_returns_localized_failure(self) -> None:
        with (
            _patch_verdict(
                WebRiskVerdict(blocked=True, threat_types=("SOCIAL_ENGINEERING",), checked=True)
            ),
            _patch_language(),
        ):
            output = await _web_risk_gate("https://evil.example", MagicMock())

        assert output is not None
        assert output.success is False
        assert "dangereuse" in output.error_message
        assert output.metadata["threat_types"] == ["SOCIAL_ENGINEERING"]

    async def test_clean_verdict_lets_the_fetch_proceed(self) -> None:
        with _patch_verdict(WebRiskVerdict(blocked=False, checked=True)):
            assert await _web_risk_gate("https://ok.example", MagicMock()) is None

    async def test_fail_open_verdict_lets_the_fetch_proceed(self) -> None:
        """Web Risk down or disabled must never gate browsing."""
        with _patch_verdict(WebRiskVerdict(blocked=False, checked=False)):
            assert await _web_risk_gate("https://ok.example", MagicMock()) is None
