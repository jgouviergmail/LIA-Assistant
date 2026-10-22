"""A provider refusal schedules a later evaluation, never an immediate retry."""

from datetime import timedelta

import pytest

from src.core.config import settings
from src.core.exceptions import ConnectorAPIError
from src.core.read_budget import claim_read_call
from src.domains.proactive_discussions.backoff import DiscussionBackoff, retry_deadline
from src.domains.proactive_discussions.source_gateway import SourceGateway
from src.domains.shared.discussion_sources import SourceKey
from tests.unit.domains.proactive_discussions.test_source_authority import NOW, request
from tests.unit.domains.proactive_discussions.test_source_call_debt import policy

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_provider_backoff_preserves_debt_and_exits_before_another_read():
    class Limited:
        async def read(self, scope):
            claim_read_call(scope.owner_id)
            raise ConnectorAPIError(
                "fictional", 429, "rate limited", headers={"Retry-After": "7200"}
            )

    debt = []
    gateway = SourceGateway(
        dict.fromkeys(SourceKey, Limited()),
        policy,
        usage_sink=lambda scope, calls: debt.append(calls),
    )
    with pytest.raises(DiscussionBackoff) as error:
        await gateway.read(request(SourceKey.SMS))
    assert error.value.until == NOW + timedelta(hours=2)
    assert debt == [1]


def test_retry_after_http_date_and_missing_header_are_bounded():
    error = ConnectorAPIError(
        "fictional", 429, "rate limited", headers={"Retry-After": "Tue, 20 Oct 2026 11:00:00 GMT"}
    )
    assert retry_deadline(error, now=NOW) == NOW + timedelta(hours=1)
    assert retry_deadline(
        ConnectorAPIError("fictional", 429, "rate limited"), now=NOW
    ) == NOW + timedelta(minutes=15)
    assert retry_deadline(ValueError("not a provider refusal"), now=NOW) is None


def test_a_refusal_stating_no_delay_defers_by_the_configured_backoff(monkeypatch):
    monkeypatch.setattr(settings, "discussion_backoff_minutes", 40)
    assert retry_deadline(
        ConnectorAPIError("fictional", 429, "rate limited"), now=NOW
    ) == NOW + timedelta(minutes=40)
