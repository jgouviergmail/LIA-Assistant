"""Actual openings, rather than scheduled reads, reach the native register."""

import asyncio
from uuid import UUID

import pytest

from src.core.read_budget import mark_read_opened
from src.domains.agents.effects.treatments import treatment_collector
from src.domains.proactive_discussions.consultations import reads_requested_by_person
from src.domains.proactive_discussions.schemas import DiscussionPolicy
from src.domains.proactive_discussions.source_gateway import SourceGateway
from src.domains.shared.discussion_sources import SourceKey, SourceReadRequest, SourceSnapshot
from tests.unit.domains.proactive_discussions.test_source_authority import Port, request

pytestmark = pytest.mark.unit


async def allowed(owner: UUID) -> DiscussionPolicy:
    return DiscussionPolicy(enabled=True, sources=(SourceKey.SMS,), revision=1)


class NativePort:
    def __init__(self, *, cache: bool = False, failed: bool = False, cancel: bool = False) -> None:
        self.cache, self.failed, self.cancel = cache, failed, cancel

    async def read(self, scope: SourceReadRequest) -> SourceSnapshot:
        if not self.cache:
            mark_read_opened(scope.owner_id)
        if self.failed:
            raise ConnectionError("Fictional private source text")
        if self.cancel:
            raise asyncio.CancelledError
        return await Port().read(scope)


@pytest.mark.parametrize(
    "cache,failed,expected", [(False, False, 1), (True, False, 0), (False, True, 1)]
)
async def test_register_reflects_actual_source_opening(
    cache: bool, failed: bool, expected: int
) -> None:
    port = NativePort(cache=cache, failed=failed)
    with treatment_collector(run_id="discussion-test") as rows:
        await SourceGateway(dict.fromkeys(SourceKey, port), allowed).read(request(SourceKey.SMS))
    assert len(rows) == expected
    if rows:
        assert rows[0].tool_name == "discussion:sms"
        assert rows[0].source == "proactive"
        assert rows[0].outcome == ("failed" if failed else "ok")
        assert "Fictional private" not in repr(rows[0])


async def test_cancelled_opened_read_is_a_failed_consultation() -> None:
    with treatment_collector(run_id="discussion-cancel") as rows:
        with pytest.raises(asyncio.CancelledError):
            await SourceGateway(dict.fromkeys(SourceKey, NativePort(cancel=True)), allowed).read(
                request(SourceKey.SMS)
            )
    assert len(rows) == 1 and rows[0].outcome == "failed"


async def test_refused_read_never_reaches_consultation_register() -> None:
    async def refused(owner: UUID) -> DiscussionPolicy:
        return DiscussionPolicy(enabled=True, sources=(), revision=1)

    with treatment_collector(run_id="discussion-refused") as rows:
        await SourceGateway(dict.fromkeys(SourceKey, NativePort()), refused).read(
            request(SourceKey.SMS)
        )
    assert rows == []


async def test_a_rebuild_the_person_asked_for_is_filed_as_their_request() -> None:
    # ADR-263: who asked decides the authorship; a rebuild is the person's act, like
    # its spend, and its reads were dropped in silence before 2026-10-21.
    gateway = SourceGateway(dict.fromkeys(SourceKey, NativePort()), allowed)
    with treatment_collector(run_id="discussion-rebuild") as rows:
        with reads_requested_by_person(True):
            await gateway.read(request(SourceKey.SMS))
    assert len(rows) == 1
    assert (rows[0].tool_name, rows[0].source) == ("discussion_rebuild:sms", "user")
    # Outside the block, a read is LIA's initiative again.
    with treatment_collector(run_id="discussion-after") as rows:
        await gateway.read(request(SourceKey.SMS))
    assert (rows[0].tool_name, rows[0].source) == ("discussion:sms", "proactive")
