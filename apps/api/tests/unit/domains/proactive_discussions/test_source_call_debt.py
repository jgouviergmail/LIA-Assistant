"""Discarded content and interrupted readers must not erase known API work."""

import asyncio
from dataclasses import dataclass
from uuid import UUID

import pytest

from src.core.exceptions import ResourceConflictError
from src.core.read_budget import ReadCallBudget, ReadCallLimit, claim_read_call, read_call_budget
from src.domains.proactive_discussions.schemas import DiscussionPolicy
from src.domains.proactive_discussions.source_gateway import SourceGateway
from src.domains.shared.discussion_sources import SourceKey, SourceReadRequest, SourceSnapshot
from tests.unit.domains.proactive_discussions.test_source_authority import OWNER, Port, request

pytestmark = pytest.mark.unit


def test_independent_source_reads_share_one_run_physical_ceiling() -> None:
    parent = ReadCallBudget(owner=OWNER, limit=2)
    first = ReadCallBudget(owner=OWNER, limit=2, parent=parent)
    second = ReadCallBudget(owner=OWNER, limit=2, parent=parent)
    first.claim(OWNER)
    second.claim(OWNER)
    with pytest.raises(ReadCallLimit):
        first.claim(OWNER)
    assert parent.calls == 2 and first.calls == 1 and second.calls == 1


@dataclass
class CallingPort:
    cancel: bool = False
    foreign: bool = False

    async def read(self, scope: SourceReadRequest) -> SourceSnapshot:
        claim_read_call(scope.owner_id)
        if self.cancel:
            raise asyncio.CancelledError
        return await Port(foreign=self.foreign).read(scope)


async def policy(owner: UUID) -> DiscussionPolicy:
    return DiscussionPolicy(enabled=True, sources=(SourceKey.SMS,), revision=1)


@pytest.mark.parametrize("foreign", [False, True])
async def test_content_refusal_preserves_attempted_calls(foreign: bool) -> None:
    port = CallingPort(foreign=foreign)
    result = await SourceGateway(dict.fromkeys(SourceKey, port), policy).read(
        request(SourceKey.SMS)
    )
    assert result.physical_calls == 1
    assert result.status == ("unavailable" if foreign else "ok")


async def test_revocation_and_loader_failure_do_not_erase_reported_debt() -> None:
    calls = 0

    async def load(owner: UUID) -> DiscussionPolicy:
        nonlocal calls
        calls += 1
        if calls > 1:
            raise ConnectionError("private details are not logged")
        return await policy(owner)

    result = await SourceGateway(dict.fromkeys(SourceKey, CallingPort()), load).read(
        request(SourceKey.SMS)
    )
    assert result.status == "unavailable" and result.physical_calls == 1


async def test_cancelled_read_still_publishes_usage_to_run_collector() -> None:
    usages: list[int] = []
    gateway = SourceGateway(
        dict.fromkeys(SourceKey, CallingPort(cancel=True)),
        policy,
        usage_sink=lambda scope, calls: usages.append(calls),
    )
    with pytest.raises(asyncio.CancelledError):
        await gateway.read(request(SourceKey.SMS))
    assert usages == [1]


def test_bound_precedes_physical_call_and_is_owner_scoped() -> None:
    with read_call_budget(ReadCallBudget(owner=OWNER, limit=1)) as budget:
        claim_read_call(OWNER)
        with pytest.raises(ReadCallLimit):
            claim_read_call(OWNER)
        with pytest.raises(ReadCallLimit):
            claim_read_call(UUID(int=3))
        assert budget.calls == 1
    claim_read_call(OWNER)  # Existing callers remain outside this new bounded scope.


async def test_concurrent_tasks_keep_separate_owner_budgets() -> None:
    async def run(owner: UUID) -> int:
        with read_call_budget(ReadCallBudget(owner=owner, limit=1)) as budget:
            await asyncio.sleep(0)
            claim_read_call(owner)
            return budget.calls

    assert await asyncio.gather(run(OWNER), run(UUID(int=3))) == [1, 1]


@pytest.mark.parametrize(
    "code,reason", [("QUERY_TOO_BROAD", "budget"), ("STALE_CURSOR", "expired")]
)
async def test_broad_query_and_stale_cursor_are_different_failures(code: str, reason: str) -> None:
    class FailingPort:
        async def read(self, scope: SourceReadRequest) -> SourceSnapshot:
            claim_read_call(scope.owner_id)
            raise ResourceConflictError("sms_search", detail={"error_code": code})

    result = await SourceGateway(dict.fromkeys(SourceKey, FailingPort()), policy).read(
        request(SourceKey.SMS)
    )
    assert result.reason == reason and result.physical_calls == 1 and not result.items
