"""Historical knowledge never substitutes for fresh native proof authority."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.domains.proactive_discussions.context_store.preparation import proof_of
from src.domains.proactive_discussions.run_types import RunClaim
from src.domains.shared.discussion_sources import DiscussionEvidence, SourceKey, source_snapshot
from src.infrastructure.proactive.discussion_proofs import hydrate_proofs, proof_request

pytestmark = pytest.mark.unit
NOW = datetime(2026, 10, 20, 12, tzinfo=UTC)
FACT = DiscussionEvidence(
    reference="calendar:old",
    source=SourceKey.CALENDAR,
    object_id="old",
    version="v1",
    occurred_at=NOW - timedelta(days=35),
    observed_at=NOW,
    excerpt="Fictional appointment",
    assertion="planned",
)


@pytest.mark.parametrize(
    "source",
    [
        SourceKey.MEMORIES,
        SourceKey.CONTACTS,
        SourceKey.PORTRAIT,
        SourceKey.INTERESTS,
        SourceKey.OPEN_LOOPS,
        SourceKey.HABITS,
    ],
)
def test_old_recording_date_does_not_expire_a_current_owned_object(source):
    retained = FACT.model_copy(
        update={
            "source": source,
            "reference": f"{source}:retained",
            "occurred_at": None,
            "recorded_at": NOW - timedelta(days=400),
        }
    )
    claim = RunClaim(
        owner_id=uuid4(),
        run_id=uuid4(),
        fence=1,
        policy_revision=1,
        context_epoch=0,
        lease_until=NOW + timedelta(minutes=5),
    )
    request = proof_request(claim, proof_of(retained, {}, now=NOW), now=NOW)
    assert request is not None and request.request.operation == (
        "recent" if source == SourceKey.PORTRAIT else "detail"
    )
    assert request.window_start < NOW < request.window_end


def test_an_old_calendar_occurrence_still_respects_the_research_horizon():
    old = FACT.model_copy(update={"occurred_at": NOW - timedelta(days=400)})
    claim = RunClaim(
        owner_id=uuid4(),
        run_id=uuid4(),
        fence=1,
        policy_revision=1,
        context_epoch=0,
        lease_until=NOW + timedelta(minutes=5),
    )
    assert proof_request(claim, proof_of(old, {}, now=NOW), now=NOW) is None


async def test_old_occurrence_is_refetched_in_its_own_window_without_reinterpretation():
    claim = RunClaim(
        owner_id=uuid4(),
        run_id=uuid4(),
        fence=1,
        policy_revision=1,
        context_epoch=0,
        lease_until=NOW + timedelta(minutes=5),
    )
    gateway = AsyncMock()
    gateway.read.side_effect = lambda request: source_snapshot(request, status="ok", items=(FACT,))
    result = await hydrate_proofs(claim, (proof_of(FACT, {}, now=NOW),), gateway, now=NOW)
    assert result[0].items == (FACT,)
    request = gateway.read.call_args.args[0]
    assert request.window_start < FACT.occurred_at < request.window_end
    assert request.request.operation == "history"


async def test_changed_or_removed_historical_proof_is_never_reused():
    claim = RunClaim(
        owner_id=uuid4(),
        run_id=uuid4(),
        fence=1,
        policy_revision=1,
        context_epoch=0,
        lease_until=NOW + timedelta(minutes=5),
    )
    gateway = AsyncMock()
    gateway.read.side_effect = lambda request: source_snapshot(
        request, status="ok", items=(FACT.model_copy(update={"version": "v2"}),)
    )
    assert await hydrate_proofs(claim, (proof_of(FACT, {}, now=NOW),), gateway, now=NOW) == ()


@pytest.mark.parametrize(
    ("assertion", "operation"), [("planned", "future"), ("observed", "recent")]
)
def test_a_weather_proof_is_read_again_where_it_can_be_found(assertion, operation):
    # A forecast is in no recent page: read there, a forecast-based item was dropped
    # at every run and the read was paid for nothing.
    point = FACT.model_copy(
        update={
            "source": SourceKey.WEATHER,
            "reference": "weather:place:forecast",
            "occurred_at": NOW + timedelta(hours=3),
            "expires_at": NOW + timedelta(minutes=30),
            "assertion": assertion,
            "required_sources": (SourceKey.LOCATION,),
        }
    )
    claim = RunClaim(
        owner_id=uuid4(),
        run_id=uuid4(),
        fence=1,
        policy_revision=1,
        context_epoch=0,
        lease_until=NOW + timedelta(minutes=5),
    )
    request = proof_request(claim, proof_of(point, {}, now=NOW), now=NOW)
    assert request is not None and request.request.operation == operation
    if operation == "future":
        assert request.request.start == request.window_start
        assert request.request.end == request.window_end
