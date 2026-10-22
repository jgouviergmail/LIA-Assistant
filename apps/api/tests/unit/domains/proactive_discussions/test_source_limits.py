"""A provider cannot return a larger item than the caller budgeted."""

from datetime import timedelta
from uuid import UUID

import pytest

from src.domains.proactive_discussions.schemas import DiscussionPolicy
from src.domains.proactive_discussions.source_gateway import SourceGateway
from src.domains.shared.discussion_sources import ResearchRequest, SourceKey, SourceReadRequest
from tests.unit.domains.proactive_discussions.test_source_authority import Port, request

pytestmark = pytest.mark.unit


async def test_oversized_evidence_does_not_bypass_requested_budget() -> None:
    port = Port()

    async def policy(owner: UUID) -> DiscussionPolicy:
        return DiscussionPolicy(enabled=True, sources=(SourceKey.SMS,), revision=1)

    result = await SourceGateway(dict.fromkeys(SourceKey, port), policy).read(
        request(SourceKey.SMS).model_copy(update={"item_max_chars": 4})
    )
    assert result.status == "unavailable" and result.reason == "budget" and not result.items


def test_empty_read_window_is_refused_before_source_access() -> None:
    payload = request(SourceKey.SMS).model_dump()
    payload["window_end"] = payload["window_start"]
    with pytest.raises(ValueError, match="window"):
        SourceReadRequest.model_validate(payload)


def test_authorized_read_cannot_enlarge_research_window() -> None:
    scope = request(SourceKey.SMS)
    payload = scope.model_dump()
    payload["request"] = ResearchRequest(
        source=SourceKey.SMS,
        operation="history",
        start=scope.window_start + timedelta(hours=1),
        end=scope.now,
    ).model_dump()
    with pytest.raises(ValueError, match="window"):
        SourceReadRequest.model_validate(payload)


async def test_gateway_revalidates_a_modified_read_contract() -> None:
    port = Port()

    async def policy(owner: UUID) -> DiscussionPolicy:
        return DiscussionPolicy(enabled=True, sources=(SourceKey.SMS,), revision=1)

    with pytest.raises(ValueError):
        await SourceGateway(dict.fromkeys(SourceKey, port), policy).read(
            request(SourceKey.SMS).model_copy(update={"item_limit": 10000})
        )
    assert port.reads == 0
