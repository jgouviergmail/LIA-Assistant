"""An expanded recurring occurrence is revalidated as that occurrence, never its master."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from src.domains.proactive_discussions.contextualization.loop import ContextResult
from src.domains.proactive_discussions.run_types import RunClaim
from src.domains.shared.discussion_sources import DiscussionEvidence, SourceKey, SourceSnapshot
from src.infrastructure.proactive.discussion_attention import InitiativeStopped
from src.infrastructure.proactive.discussion_revalidation import revalidate_evidence

pytestmark = pytest.mark.unit
NOW = datetime(2026, 10, 20, 12, tzinfo=UTC)
OWNER = uuid4()
FACT = DiscussionEvidence(
    reference="calendar:expanded",
    source=SourceKey.CALENDAR,
    object_id="series",
    series_id="series",
    original_start=NOW,
    version="v1",
    observed_at=NOW,
    excerpt="Fictional monthly appointment",
    sensitive_topics=("health",),
)
PAGE = SourceSnapshot(
    source=SourceKey.CALENDAR,
    owner_id=OWNER,
    status="ok",
    read_at=NOW,
    window_start=NOW - timedelta(days=7),
    window_end=NOW + timedelta(days=7),
    complete=False,
    items=(FACT,),
)
CLAIM = RunClaim(
    owner_id=OWNER,
    run_id=uuid4(),
    fence=1,
    policy_revision=1,
    context_epoch=0,
    lease_until=NOW + timedelta(minutes=5),
)


class Reader:
    def __init__(self, deleted=False):
        self.requests = []
        self.deleted = deleted

    async def read(self, request):
        self.requests.append(request)
        if self.deleted:
            return PAGE.model_copy(update={"status": "empty", "items": ()})
        fact = FACT.model_copy(update={"sensitive_topics": ()})
        if request.request.operation == "detail":
            fact = fact.model_copy(update={"reference": "calendar:master", "original_start": None})
        return PAGE.model_copy(update={"items": (fact,)})


@pytest.mark.asyncio
async def test_expanded_calendar_identity_survives_revalidation_and_topic_restrictions():
    reader = Reader()
    result = await revalidate_evidence(CLAIM, ContextResult(True, (FACT,), (), (PAGE,)), reader)
    assert reader.requests[0].request.operation != "detail"
    assert result[0].items[0].original_start == NOW
    assert result[0].items[0].sensitive_topics == ("health",)


@pytest.mark.asyncio
async def test_deleted_native_object_is_not_served_from_derived_context():
    with pytest.raises(InitiativeStopped, match="evidence_changed"):
        await revalidate_evidence(
            CLAIM, ContextResult(True, (FACT,), (), (PAGE,)), Reader(deleted=True)
        )


@pytest.mark.parametrize(
    ("assertion", "operation"), [("planned", "future"), ("observed", "recent")]
)
async def test_a_weather_fact_is_read_again_where_it_was_found(assertion, operation):
    fact = DiscussionEvidence(
        reference="weather:place:current",
        source=SourceKey.WEATHER,
        object_id="current",
        version="v1",
        observed_at=NOW,
        occurred_at=NOW + timedelta(seconds=46),
        excerpt="Overcast",
        assertion=assertion,
        required_sources=(SourceKey.LOCATION,),
    )
    page = PAGE.model_copy(update={"source": SourceKey.WEATHER, "items": (fact,)})

    class Same:
        def __init__(self):
            self.requests = []

        async def read(self, request):
            self.requests.append(request)
            # The provider stamps a new instant; the object and its version hold.
            later = fact.model_copy(update={"occurred_at": NOW + timedelta(seconds=92)})
            return page.model_copy(update={"items": (later,)})

    reader = Same()
    pages = await revalidate_evidence(CLAIM, ContextResult(True, (fact,), (), (page,)), reader)
    assert pages[0].items[0].version == "v1"
    (asked,) = reader.requests
    assert asked.request.operation == operation
    if operation == "future":
        assert (asked.request.start, asked.request.end) == (page.window_start, page.window_end)


async def test_facts_of_one_page_are_read_again_once():
    # Measured 2026-10-21: one read per fact spent a run's whole read budget on three
    # passes, and its last re-read came back closed.
    second = FACT.model_copy(
        update={"reference": "calendar:second", "object_id": "second", "series_id": None}
    )
    page = PAGE.model_copy(update={"items": (FACT, second)})

    class Counting:
        def __init__(self):
            self.reads = 0

        async def read(self, request):
            self.reads += 1
            return page

    reader = Counting()
    fresh = await revalidate_evidence(
        CLAIM, ContextResult(True, (FACT, second), (), (page,)), reader
    )
    assert reader.reads == 1
    assert [item.items[0].reference for item in fresh] == [FACT.reference, second.reference]


OLDER = DiscussionEvidence(
    reference="conversations:older",
    source=SourceKey.CONVERSATIONS,
    object_id="older",
    version="v1",
    observed_at=NOW,
    recorded_at=NOW - timedelta(days=60),
    excerpt="Fictional words the person wrote two months ago",
)
NEWER = OLDER.model_copy(update={"reference": "conversations:newer", "object_id": "newer"})
WIDE = PAGE.model_copy(
    update={
        "source": SourceKey.CONVERSATIONS,
        "window_start": NOW - timedelta(days=90),
        "window_end": NOW,
        "items": (OLDER,),
    }
)


class BusyWindow:
    """A window holding more newer messages than one re-read page returns."""

    def __init__(self, *, found_around_instant: bool) -> None:
        self.requests = []
        self.found = found_around_instant

    async def read(self, request):
        self.requests.append(request)
        if request.window_start == WIDE.window_start:
            return WIDE.model_copy(update={"status": "truncated", "items": (NEWER,)})
        items = (OLDER,) if self.found else (NEWER,)
        return WIDE.model_copy(
            update={
                "status": "ok" if self.found else "truncated",
                "window_start": request.window_start,
                "window_end": request.window_end,
                "items": items,
            }
        )


async def test_a_fact_a_truncated_page_stopped_before_is_read_again_around_its_instant():
    # A search found the fact two months back; the re-read of that wide window stops
    # at newer messages, which proves nothing about the fact itself.
    reader = BusyWindow(found_around_instant=True)
    pages = await revalidate_evidence(CLAIM, ContextResult(True, (OLDER,), (), (WIDE,)), reader)
    assert pages[0].items[0].reference == OLDER.reference
    first, around = reader.requests
    assert around.window_start <= OLDER.recorded_at <= around.window_end
    assert around.window_end - around.window_start < WIDE.window_end - WIDE.window_start


async def test_a_fact_no_page_reached_is_never_read_as_a_changed_fact():
    with pytest.raises(InitiativeStopped) as stopped:
        await revalidate_evidence(
            CLAIM,
            ContextResult(True, (OLDER,), (), (WIDE,)),
            BusyWindow(found_around_instant=False),
        )
    assert stopped.value.reason == "evidence_page_missing"


@pytest.mark.parametrize(
    ("status", "reason", "stop"),
    [
        ("unavailable", "budget", "read_budget_exhausted"),
        ("disabled", "consent", "evidence_refused"),
        ("unavailable", "provider", "evidence_page_missing"),
        ("unavailable", "timeout", "evidence_page_missing"),
    ],
)
async def test_a_re_read_that_was_not_made_never_reads_as_a_changed_fact(status, reason, stop):
    class Closed:
        async def read(self, request):
            return PAGE.model_copy(update={"status": status, "reason": reason, "items": ()})

    with pytest.raises(InitiativeStopped) as stopped:
        await revalidate_evidence(CLAIM, ContextResult(True, (FACT,), (), (PAGE,)), Closed())
    assert stopped.value.reason == stop
