"""Every published source has a real port, and opt-out stops before its native reader."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from src.domains.proactive_discussions.schemas import DiscussionPolicy
from src.domains.proactive_discussions.source_gateway import SourceGateway
from src.domains.shared.discussion_catalogue import SOURCE_REGISTRY
from src.domains.shared.discussion_sources import ResearchRequest, SourceKey, SourceReadRequest
from src.infrastructure.proactive.discussion_sources import discussion_readers

pytestmark = pytest.mark.unit


async def test_all_native_ports_are_present_and_refused_before_any_reader_opens() -> None:
    readers = discussion_readers()
    assert frozenset(readers) == frozenset(SourceKey)
    owner, now = UUID(int=1), datetime.now(UTC)

    async def policy(_owner):
        return DiscussionPolicy(enabled=True, sources=(), revision=0)

    gateway = SourceGateway(readers, policy)
    requests = tuple(
        SourceReadRequest(
            owner_id=owner,
            run_id=UUID(int=2),
            policy_revision=0,
            request=ResearchRequest(
                source=source,
                operation=SOURCE_REGISTRY[source].operations[0],
                query="Fictional" if SOURCE_REGISTRY[source].operations[0] == "search" else None,
            ),
            now=now,
            window_start=now - timedelta(days=3),
            window_end=now + timedelta(days=7),
            item_limit=2,
            call_limit=1,
            timeout_seconds=1,
        )
        for source in SourceKey
    )
    results = await asyncio.gather(*(gateway.read(request) for request in requests))
    assert all(
        result.status == "disabled" and not result.items and result.physical_calls == 0
        for result in results
    )
