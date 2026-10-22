"""Owner-neutral read ports for personal conversation context.

Provider domains implement this contract without importing the discussion engine
or agents. The composition root installs their readers; these types perform no IO.

SourceKey and ResearchRequest are MODEL-FACING: they are part of the context and
rule-compiler schemas and of the discussion tools' parameters, so they carry
comments, never docstrings (a docstring becomes schema text a model reads).
"""

import json
from datetime import UTC, date
from enum import StrEnum
from hashlib import sha256
from typing import Annotated, Literal, Protocol, Self
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    model_validator,
)

from src.core.constants import (
    DISCUSSION_FULL_EXCERPT_CHARS,
    DISCUSSION_READ_CALL_LIMIT_MAX,
    DISCUSSION_READ_TIMEOUT_SECONDS_MAX,
    DISCUSSION_RESEARCH_ITEM_MAX_CHARS_DEFAULT,
)
from src.core.recurrence import RecurrenceSpec

RESEARCH_HISTORY_DAYS_MAX = 183
RESEARCH_FUTURE_DAYS_MAX = 30


# MODEL-FACING (context, rule compiler, discussion tools): the readable sources.
class SourceKey(StrEnum):
    CALENDAR = "calendar"
    EMAILS = "emails"
    CONTACTS = "contacts"
    TASKS = "tasks"
    WEATHER = "weather"
    LOCATION = "location"
    MEMORIES = "memories"
    JOURNALS = "journals"
    PORTRAIT = "portrait"
    OPEN_LOOPS = "open_loops"
    HABITS = "habits"
    RELATIONS = "relations"
    HEALTH = "health"
    CONVERSATIONS = "conversations"
    MEETINGS = "meetings"
    PEERS = "peers"
    PEER_MESSAGES = "peer_messages"
    INTERESTS = "interests"
    REMINDERS = "reminders"
    SCHEDULED_ACTIONS = "scheduled_actions"
    WORKBOARD = "workboard"
    SMS = "sms"


SensitiveTopic = Literal["health", "relationships", "finances", "grief", "intimacy"]
ReadOperation = Literal["recent", "search", "detail", "history", "future"]
SourceStatus = Literal["ok", "empty", "disabled", "unavailable", "stale", "truncated"]
SourceFailureReason = Literal[
    "consent", "feature", "provider", "timeout", "malformed", "expired", "budget"
]
CoverageKind = Literal["occurrences", "active_facts", "dated_synthesis", "signal"]
NonEmpty = Annotated[str, Field(min_length=1, max_length=256)]
OptionalNonEmpty = Annotated[str | None, Field(min_length=1)]


class DiscussionValue(BaseModel):
    """The base of every discussion value: frozen, no extra field, stripped strings."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


GraphWeekday = Literal["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"]


class GraphRecurrencePattern(DiscussionValue):
    """A Microsoft Graph recurrence pattern, as the provider spells it."""

    type: Literal[
        "daily", "weekly", "absoluteMonthly", "relativeMonthly", "absoluteYearly", "relativeYearly"
    ]
    interval: Annotated[StrictInt, Field(ge=1, le=1000)]
    daysOfWeek: Annotated[tuple[GraphWeekday, ...], Field(max_length=7)] = ()
    dayOfMonth: Annotated[StrictInt | None, Field(ge=0, le=31)] = None
    month: Annotated[StrictInt | None, Field(ge=0, le=12)] = None
    index: Literal["first", "second", "third", "fourth", "last"] | None = None
    firstDayOfWeek: GraphWeekday | None = None


class GraphRecurrenceRange(DiscussionValue):
    """A Microsoft Graph recurrence range, as the provider spells it."""

    type: Literal["endDate", "noEnd", "numbered"]
    startDate: date
    endDate: date | None = None
    numberOfOccurrences: Annotated[StrictInt | None, Field(ge=0)] = None
    recurrenceTimeZone: Annotated[str | None, Field(max_length=256)] = None


class GraphRecurrence(DiscussionValue):
    """A Microsoft Graph patterned recurrence: its pattern and its range."""

    pattern: GraphRecurrencePattern
    range: GraphRecurrenceRange


class DiscussionEvidence(DiscussionValue):
    """One fact a source offers: identity, version, dates, authority, bounded excerpt."""

    reference: NonEmpty
    source: SourceKey
    source_account: NonEmpty = "native"
    object_id: NonEmpty
    version: NonEmpty
    observed_at: AwareDatetime
    recorded_at: AwareDatetime | None = None
    occurred_at: AwareDatetime | None = None
    interval_start: AwareDatetime | None = None
    interval_end: AwareDatetime | None = None
    expires_at: AwareDatetime | None = None
    excerpt: Annotated[str, Field(min_length=1, max_length=DISCUSSION_FULL_EXCERPT_CHARS)]
    excerpt_truncated: StrictBool = False
    category: OptionalNonEmpty = None
    usage_nuance: Annotated[str | None, Field(max_length=300)] = None
    emotional_weight: Annotated[StrictInt | None, Field(ge=-10, le=10)] = None
    assertion: Literal["planned", "reported", "observed", "inferred", "unknown"] = "unknown"
    derived: StrictBool = False
    supports: Annotated[tuple[NonEmpty, ...], Field(max_length=32)] = ()
    sensitive_topics: tuple[SensitiveTopic, ...] = ()
    required_sources: tuple[SourceKey, ...] = ()
    subject_id: OptionalNonEmpty = None
    series_id: OptionalNonEmpty = None
    original_start: AwareDatetime | None = None
    original_date: date | None = None
    planned_date: date | None = None
    occurrence_state: Literal["scheduled", "cancelled", "reported_complete", "unknown"] = "unknown"
    recurrence_rule: Annotated[str | None, Field(max_length=1000)] = None
    recurrence_spec: RecurrenceSpec | None = None
    native_recurrence: GraphRecurrence | None = None

    @model_validator(mode="after")
    def coherent_interval(self) -> Self:
        """Refuse an occurrence that is both an instant and a date, or a half or empty period."""
        if self.original_start is not None and self.original_date is not None:
            raise ValueError("original occurrence is an instant or a civil date, never both")
        if (self.interval_start is None) != (self.interval_end is None):
            raise ValueError("both evidence interval bounds are required")
        if self.interval_start is not None and self.interval_end is not None:
            if self.interval_start >= self.interval_end:
                raise ValueError("evidence interval must be nonempty and ordered")
        return self


class SourceSnapshot(DiscussionValue):
    """One page a source read: its window, status, coverage and items."""

    source: SourceKey
    owner_id: UUID
    status: SourceStatus
    read_at: AwareDatetime
    window_start: AwareDatetime
    window_end: AwareDatetime
    complete: StrictBool
    coverage_kind: CoverageKind = "occurrences"
    total: Annotated[StrictInt | None, Field(ge=0)] = None
    items: tuple[DiscussionEvidence, ...] = ()
    physical_calls: Annotated[StrictInt, Field(ge=0)] = 0
    reason: SourceFailureReason | None = None
    cursor: Annotated[str | None, Field(max_length=4096)] = None
    revision: OptionalNonEmpty = None

    @model_validator(mode="after")
    def coherent_coverage(self) -> Self:
        """Refuse an incoherent page.

        An empty window, a foreign or duplicated item, usable items on a closed page,
        or a closed or truncated page claiming complete coverage is refused.
        """
        if self.window_start >= self.window_end:
            raise ValueError("source window must be nonempty and ordered")
        if any(item.source != self.source for item in self.items):
            raise ValueError("evidence source differs from snapshot source")
        if len({item.reference for item in self.items}) != len(self.items):
            raise ValueError("duplicate evidence reference")
        if self.status in {"empty", "disabled", "unavailable", "stale"} and self.items:
            raise ValueError("source status cannot carry usable evidence")
        if self.complete and self.status in {"disabled", "unavailable", "stale", "truncated"}:
            raise ValueError("unavailable or truncated source cannot prove complete coverage")
        return self


# MODEL-FACING (context call): one bounded research wave the model asks for.
class ResearchRequest(DiscussionValue):
    source: SourceKey
    operation: ReadOperation
    query: Annotated[str | None, Field(min_length=1, max_length=400)] = None
    reference: OptionalNonEmpty = None
    start: AwareDatetime | None = None
    end: AwareDatetime | None = None
    cursor: Annotated[str | None, Field(min_length=1, max_length=4096)] = None

    @model_validator(mode="after")
    def read_shape(self) -> Self:
        """Refuse a request whose operation lacks what it needs, or whose window is empty."""
        if self.operation == "detail" and self.reference is None:
            raise ValueError("detail requires a reference")
        if self.operation == "search" and self.query is None:
            raise ValueError("search requires a query")
        if (self.start is None) != (self.end is None):
            raise ValueError("both window bounds are required")
        if self.operation in {"history", "future"} and self.start is None:
            raise ValueError("temporal research requires explicit dates")
        if self.start is not None and self.end is not None and self.start >= self.end:
            raise ValueError("research window must be nonempty and ordered")
        return self


class SourceReadRequest(DiscussionValue):
    """One bounded read: the research asked, under whose authority, with which caps."""

    owner_id: UUID
    run_id: UUID
    policy_revision: Annotated[StrictInt, Field(ge=0)]
    request: ResearchRequest
    allowed_sources: tuple[SourceKey, ...] = ()
    sensitive_topics: tuple[SensitiveTopic, ...] = ()
    cursor: Annotated[str | None, Field(max_length=4096)] = None
    now: AwareDatetime
    window_start: AwareDatetime
    window_end: AwareDatetime
    item_limit: Annotated[StrictInt, Field(ge=1, le=100)]
    item_max_chars: Annotated[StrictInt, Field(ge=1, le=DISCUSSION_FULL_EXCERPT_CHARS)] = (
        DISCUSSION_RESEARCH_ITEM_MAX_CHARS_DEFAULT
    )
    call_limit: Annotated[StrictInt, Field(ge=1, le=DISCUSSION_READ_CALL_LIMIT_MAX)]
    timeout_seconds: Annotated[float, Field(gt=0, le=DISCUSSION_READ_TIMEOUT_SECONDS_MAX)]

    @model_validator(mode="after")
    def authorized_window(self) -> Self:
        """Refuse a read window that is empty or reaches past the research window asked."""
        if self.window_start >= self.window_end:
            raise ValueError("read window must be nonempty and ordered")
        start, end = self.request.start, self.request.end
        if start is not None and end is not None:
            if self.window_start < start or self.window_end > end:
                raise ValueError("read window exceeds requested research window")
        return self


class DiscussionSource(Protocol):
    """A native source port: it reads only under fresh owner authority and its call cap."""

    async def read(self, request: SourceReadRequest) -> SourceSnapshot:
        """Read only under fresh owner authority and the supplied physical-call cap."""
        ...


def semantic_version(parts: tuple[str, ...]) -> str:
    """Hash an ordered tuple of strings into a stable 64-character version.

    Args:
        parts: The ordered parts.

    Returns:
        The hexadecimal SHA-256 of their compact JSON.
    """
    return sha256(
        json.dumps(parts, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def evidence_identity(item: DiscussionEvidence) -> str:
    """Return the identity of the object a fact is about, whatever its version.

    A calendar occurrence is identified by its series and original start (or
    date), so a moved occurrence keeps its identity.

    Args:
        item: The fact.

    Returns:
        The identity key.
    """
    parts: tuple[str, ...] = (item.source.value, item.source_account, item.object_id)
    if item.source == SourceKey.CALENDAR and (
        item.original_start is not None or item.original_date is not None
    ):
        origin = (
            item.original_start.astimezone(UTC).isoformat()
            if item.original_start
            else item.original_date.isoformat() if item.original_date else ""
        )
        parts = (item.source.value, item.source_account, item.series_id or item.object_id, origin)
    return semantic_version(parts)


def source_snapshot(
    request: SourceReadRequest,
    *,
    status: SourceStatus,
    items: tuple[DiscussionEvidence, ...] = (),
    complete: bool = False,
    total: int | None = None,
    cursor: str | None = None,
    reason: SourceFailureReason | None = None,
    coverage_kind: CoverageKind = "occurrences",
    revision: str | None = None,
    physical_calls: int = 0,
) -> SourceSnapshot:
    """Build the page a read returns, its owner and window taken from the request.

    Args:
        request: The read.
        status: How the read ended.
        items: The facts read.
        complete: Whether the whole window was read.
        total: The source's exact total, when it states one.
        cursor: Where the next page starts.
        reason: Why the read failed, when it did.
        coverage_kind: What kind of coverage the page gives.
        revision: The source's revision marker, when it has one.
        physical_calls: The physical requests the read made.

    Returns:
        The page.
    """
    return SourceSnapshot(
        source=request.request.source,
        owner_id=request.owner_id,
        read_at=request.now,
        window_start=request.window_start,
        window_end=request.window_end,
        status=status,
        items=items,
        complete=complete,
        total=total,
        cursor=cursor,
        reason=reason,
        coverage_kind=coverage_kind,
        revision=revision,
        physical_calls=physical_calls,
    )


def closed_source(
    request: SourceReadRequest, *, disabled: bool, reason: SourceFailureReason
) -> SourceSnapshot:
    """Build the empty page of a read that could not run, naming why.

    Args:
        request: The read.
        disabled: The source is switched off or not consented, rather than merely
            unavailable.
        reason: Why.

    Returns:
        The closed page.
    """
    return source_snapshot(request, status="disabled" if disabled else "unavailable", reason=reason)
