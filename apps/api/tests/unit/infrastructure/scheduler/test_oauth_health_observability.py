"""A skipped OAuth-health notification must say so (defect 2026-07-30).

The dev instance logged ``oauth_health_check_completed checked=5 healthy=0
error=5 notified=0`` on 35 consecutive runs across three hours. Five connectors
were genuinely broken and nobody was told — and nothing in the logs said why.

Reconstructing the cause required reading the Redis keyspace across four
logical databases and doing arithmetic on a key's remaining TTL to date the one
notification that HAD fired (~12 h earlier, cooldown 12 h). That is an hour of
forensics for a fact one log line owns.

The cooldown is correct behaviour — an ERROR connector must not notify every
five minutes. What was wrong is that the correct behaviour was indistinguishable
from a broken one. ``notified=0`` now always has a companion line naming the
reason, and a counter that separates "suppressed by cooldown" from "user gone".
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.connectors.models import ConnectorStatus
from src.infrastructure.scheduler.oauth_health import _maybe_notify


def _connector() -> MagicMock:
    connector = MagicMock()
    connector.id = uuid4()
    connector.user_id = uuid4()
    connector.status = ConnectorStatus.ERROR
    connector.connector_type = MagicMock()
    connector.connector_type.value = "google_calendar"
    return connector


def _redis(*, cooldown_active: bool, ttl: int = 40000) -> AsyncMock:
    redis = AsyncMock()
    redis.exists = AsyncMock(side_effect=lambda key: 1 if cooldown_active else 0)
    redis.ttl = AsyncMock(return_value=ttl)
    redis.publish = AsyncMock()
    redis.set = AsyncMock()
    return redis


@pytest.mark.asyncio
async def test_cooldown_skip_is_logged_with_its_remaining_time(caplog):
    """The exact silence that cost an hour of forensics."""
    import logging

    with caplog.at_level(logging.INFO):
        sent = await _maybe_notify(
            connector=_connector(), redis=_redis(cooldown_active=True), db=AsyncMock()
        )

    assert sent is False
    emitted = " ".join(record.getMessage() for record in caplog.records)
    assert "oauth_health_notification_skipped" in emitted
    assert "cooldown" in emitted


@pytest.mark.asyncio
async def test_cooldown_skip_reports_the_seconds_left():
    """Remaining TTL is what dates the last notification — log it, don't infer it."""
    redis = _redis(cooldown_active=True, ttl=1234)

    with patch("src.infrastructure.scheduler.oauth_health.logger") as mock_logger:
        await _maybe_notify(connector=_connector(), redis=redis, db=AsyncMock())

    kwargs = mock_logger.info.call_args.kwargs
    assert kwargs["reason"] == "cooldown"
    assert kwargs["cooldown_remaining_seconds"] == 1234


@pytest.mark.asyncio
async def test_unknown_user_skip_is_logged_with_its_own_reason():
    """The other silent exit: a connector whose user is gone or deactivated."""
    user_repo = MagicMock()
    user_repo.get_by_id = AsyncMock(return_value=None)

    with (
        patch("src.domains.users.repository.UserRepository", return_value=user_repo),
        patch("src.infrastructure.scheduler.oauth_health.logger") as mock_logger,
    ):
        sent = await _maybe_notify(
            connector=_connector(), redis=_redis(cooldown_active=False), db=AsyncMock()
        )

    assert sent is False
    assert mock_logger.info.call_args.kwargs["reason"] == "user_unavailable"


@pytest.mark.asyncio
async def test_skips_are_counted_separately_by_reason():
    """A dashboard must distinguish "quiet on purpose" from "quiet by failure"."""
    with patch(
        "src.infrastructure.observability.metrics_registry.oauth_health_notification_skipped_total"
    ) as counter:
        await _maybe_notify(
            connector=_connector(), redis=_redis(cooldown_active=True), db=AsyncMock()
        )

    counter.labels.assert_called_once_with(reason="cooldown")
    counter.labels.return_value.inc.assert_called_once()
