"""A run whose build stops still records what it had read and interpreted."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest

from src.domains.proactive_discussions.contextualization.outcome import ContextTally
from src.infrastructure.proactive import discussion_runner
from src.infrastructure.proactive.discussion_attention import InitiativeStopped

pytestmark = pytest.mark.unit


class NoGoogleCalls:
    def get_google_api_calls_breakdown(self) -> list[dict[str, object]]:
        return []


@asynccontextmanager
async def accounting(run_id: str, owner: UUID, session: str) -> AsyncIterator[NoGoogleCalls]:
    yield NoGoogleCalls()


@pytest.mark.parametrize("stop", [InitiativeStopped("evidence_changed"), RuntimeError("provider")])
async def test_a_stopped_build_keeps_its_counts_on_the_run(monkeypatch, stop):
    # Production 2026-10-21: five rebuilds stopped by a changed fact and four by a
    # refused answer all settled with no count at all.
    monkeypatch.setattr(discussion_runner, "out_of_turn_spend", accounting)
    tally = ContextTally(facts_read=3, facts_admitted=2, facts_offered=2, context_calls=1)
    act = SimpleNamespace(
        setup=SimpleNamespace(
            context_only=True, claim=SimpleNamespace(run_id=uuid4(), owner_id=uuid4())
        ),
        stats=None,
        context=SimpleNamespace(tally=tally),
        paid_weather_reads=0,
        permit=Mock(),
        build=AsyncMock(side_effect=stop),
    )
    with pytest.raises(type(stop)):
        await discussion_runner._act(act)
    assert act.stats == tally.as_dict()
    act.permit.external_receipt.assert_called_once_with(Decimal(0), uncertain=False)


async def test_counts_a_build_returned_are_never_replaced(monkeypatch):
    monkeypatch.setattr(discussion_runner, "out_of_turn_spend", accounting)
    result = SimpleNamespace(outcome="no_fact", stats={"facts_read": 0})
    act = SimpleNamespace(
        setup=SimpleNamespace(
            context_only=True, claim=SimpleNamespace(run_id=uuid4(), owner_id=uuid4())
        ),
        stats=None,
        reason=None,
        context=SimpleNamespace(tally=ContextTally(facts_read=9)),
        paid_weather_reads=0,
        permit=Mock(),
        build=AsyncMock(return_value=result),
        authority=SimpleNamespace(check=AsyncMock()),
        store=SimpleNamespace(complete_refresh=AsyncMock()),
    )
    assert await discussion_runner._act(act) is False
    assert act.stats == {"facts_read": 0}


@pytest.mark.parametrize("context_only", [True, False])
async def test_only_an_opening_reads_its_facts_again_around_each_call(monkeypatch, context_only):
    # Measured 2026-10-21: a rebuild re-reading every pass's facts before and after each
    # call spent the run's whole read budget; its stored proofs are read again before
    # any later use anyway.
    built: dict[str, object] = {}

    class Loop:
        def __init__(self, *args: object, **kwargs: object) -> None:
            built.update(kwargs)

        async def build(self) -> str:
            return "built"

    async def no_proofs(*args: object, **kwargs: object) -> tuple[()]:
        return ()

    monkeypatch.setattr(discussion_runner, "ContextLoop", Loop)
    monkeypatch.setattr(discussion_runner, "hydrate_proofs", no_proofs)
    act = SimpleNamespace(
        setup=SimpleNamespace(
            claim=SimpleNamespace(owner_id=uuid4(), run_id=uuid4()),
            controls=SimpleNamespace(text="rules"),
            language="en",
            context_only=context_only,
        ),
        store=SimpleNamespace(proof_candidates=AsyncMock(return_value=())),
        gateway=object(),
        policy=object(),
        model=object(),
        verify=object(),
        context_passes=3,
        context=None,
    )
    assert await discussion_runner.DiscussionAct._loop(act) == "built"
    assert (built["verify"] is None) is context_only
    assert built["cover_all"] is context_only


@pytest.mark.parametrize("context_only", [True, False])
async def test_a_run_past_its_deadline_stops_and_says_so(monkeypatch, context_only):
    # A rebuild cut by its deadline used to settle as a plain failure.
    monkeypatch.setattr(discussion_runner.settings, "discussion_run_deadline_seconds", 0.01)
    monkeypatch.setattr(discussion_runner.settings, "discussion_rebuild_deadline_seconds", 0.02)

    async def slow(act: object) -> bool:
        await asyncio.sleep(5)
        return True

    monkeypatch.setattr(discussion_runner, "_generate_and_publish", slow)
    act = SimpleNamespace(
        setup=SimpleNamespace(
            context_only=context_only, claim=SimpleNamespace(run_id=uuid4(), owner_id=uuid4())
        ),
        reason=None,
        retry_after=None,
    )
    assert await discussion_runner._attempt(act) == "skipped"
    assert act.reason == "deadline_reached"


async def test_a_timeout_inside_the_run_is_no_deadline(monkeypatch):
    async def timing_out(act: object) -> bool:
        raise TimeoutError

    monkeypatch.setattr(discussion_runner, "_generate_and_publish", timing_out)
    act = SimpleNamespace(
        setup=SimpleNamespace(
            context_only=True, claim=SimpleNamespace(run_id=uuid4(), owner_id=uuid4())
        ),
        reason=None,
        retry_after=None,
    )
    assert await discussion_runner._attempt(act) == "failed"
    assert act.reason == "failed"


async def test_a_usage_limit_reached_during_the_run_is_said_as_such(monkeypatch):
    # A model call the person's usage limit refuses answers a 429: read as a
    # provider's backoff, the run was filed « the provider asked to wait ».
    from src.core.exceptions import UsageLimitExceededError

    async def refused(act: object) -> bool:
        raise UsageLimitExceededError("monthly_cost", "Usage limit exceeded")

    monkeypatch.setattr(discussion_runner, "_generate_and_publish", refused)
    act = SimpleNamespace(
        setup=SimpleNamespace(
            context_only=False, claim=SimpleNamespace(run_id=uuid4(), owner_id=uuid4())
        ),
        reason=None,
        retry_after=None,
    )
    assert await discussion_runner._attempt(act) == "skipped"
    assert act.reason == "usage_limit_reached" and act.retry_after is None
