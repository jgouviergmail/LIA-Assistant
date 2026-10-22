"""Expected outcomes stay distinguishable from failed operations in operator logs."""

import logging
from unittest.mock import AsyncMock

import pytest

from src.core.config import settings
from src.domains.agents.domain_schemas import RouterOutput
from src.domains.agents.graph import route_from_router
from src.domains.agents.models import MessagesState
from src.domains.agents.tools.web_fetch_tools import _html_to_markdown
from src.infrastructure.security import web_risk

pytestmark = pytest.mark.unit


def test_successful_readability_recovery_returns_content_without_a_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING):
        _, content = _html_to_markdown(
            "<html><body><p>Available content.</p></body></html>", "article"
        )

    assert "Available content." in content
    assert not any("readability_fallback_to_full" in record.message for record in caplog.records)


def test_valid_medium_confidence_route_is_observable_without_a_warning(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "router_confidence_high", 0.8)
    monkeypatch.setattr(settings, "router_confidence_medium", 0.6)
    monkeypatch.setattr(settings, "router_confidence_low", 0.4)
    state: MessagesState = {
        "messages": [],
        "routing_history": [
            RouterOutput(
                intention="conversation",
                confidence=0.7,
                context_label="general",
                next_node="response",
            )
        ],
    }

    with caplog.at_level(logging.INFO):
        assert route_from_router(state) == "response"

    records = [record for record in caplog.records if "router_medium_confidence" in record.message]
    assert len(records) == 1
    assert records[0].levelno == logging.INFO


async def test_empty_transport_errors_retain_their_type_and_never_claim_a_checked_url(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(web_risk, "_web_risk_enabled", lambda: True)
    redis = AsyncMock()
    redis.get.return_value = None
    monkeypatch.setattr(web_risk, "_get_redis", AsyncMock(return_value=redis))
    monkeypatch.setattr(web_risk, "_fetch_verdict_payload", AsyncMock(side_effect=TimeoutError()))

    with caplog.at_level(logging.WARNING):
        verdict = await web_risk.check_url_threat("https://example.test/private-page")

    assert not verdict.checked
    assert not verdict.blocked
    records = [
        record.message for record in caplog.records if "web_risk_check_failed" in record.message
    ]
    assert len(records) == 1
    assert "TimeoutError" in records[0]
    assert "error_type" in records[0]
    assert "private-page" not in records[0]
