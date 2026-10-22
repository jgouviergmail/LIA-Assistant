"""Pure admission rules, applied before IO and again before publication."""

from datetime import datetime, timedelta
from typing import get_args
from uuid import UUID
from zoneinfo import ZoneInfo

from src.domains.proactive_discussions.registry import SOURCE_REGISTRY
from src.domains.proactive_discussions.schemas import (
    DiscussionDecision,
    DiscussionPolicy,
    EngageDecision,
)
from src.domains.shared.discussion_sources import (
    RESEARCH_FUTURE_DAYS_MAX,
    RESEARCH_HISTORY_DAYS_MAX,
    DiscussionEvidence,
    ResearchRequest,
    SensitiveTopic,
    SourceKey,
    SourceSnapshot,
)
from src.infrastructure.proactive.eligibility import is_within_hour_window


def effective_sources(
    policy: DiscussionPolicy, authority: frozenset[SourceKey]
) -> frozenset[SourceKey]:
    """Return the sources a run may read now.

    A source must be consented to by the person and currently served by the
    instance and the account; health also needs the health topic's consent; and
    a source whose dependencies are not all permitted is withdrawn until the set
    is closed under its dependencies.

    Args:
        policy: The person's discussion policy.
        authority: The sources the instance and the account can currently serve.

    Returns:
        The readable sources; empty while discussions are off.
    """
    if not policy.enabled:
        return frozenset()
    permitted = frozenset(policy.sources).intersection(authority)
    if "health" not in policy.sensitive_topics:
        permitted = permitted - {SourceKey.HEALTH}
    while True:
        closed = frozenset(
            key for key in permitted if set(SOURCE_REGISTRY[key].dependencies) <= permitted
        )
        if closed == permitted:
            return closed
        permitted = closed


def may_start(policy: DiscussionPolicy, *, now: datetime, openings_today: int) -> bool:
    """Whether a run may start an opening now.

    Args:
        policy: The person's discussion policy.
        now: The current instant, timezone-aware.
        openings_today: The openings already made during the person's local day.

    Returns:
        True when discussions are on, not paused, under the daily maximum and
        inside the hour window on the person's own clock.

    Raises:
        ValueError: ``now`` is naive or the count is negative.
    """
    if now.tzinfo is None or openings_today < 0:
        raise ValueError("aware time and a nonnegative count are required")
    if not policy.enabled or (policy.paused_until is not None and now < policy.paused_until):
        return False
    if policy.daily_max is not None and openings_today >= policy.daily_max:
        return False
    return is_within_hour_window(
        now.astimezone(ZoneInfo(policy.timezone)).hour, policy.start_hour, policy.end_hour
    )


def _evidence_by_reference(
    snapshots: tuple[SourceSnapshot, ...], *, owner_id: UUID, now: datetime
) -> dict[str, DiscussionEvidence]:
    references: dict[str, DiscussionEvidence] = {}
    for snapshot in snapshots:
        if snapshot.owner_id != owner_id:
            raise ValueError("evidence owner mismatch")
        if snapshot.status not in {"ok", "truncated"}:
            continue
        for item in snapshot.items:
            if item.expires_at is not None and item.expires_at <= now:
                continue
            if item.reference in references:
                raise ValueError("ambiguous evidence reference")
            references[item.reference] = item
    return references


def validate_decision(
    decision: DiscussionDecision,
    policy: DiscussionPolicy,
    snapshots: tuple[SourceSnapshot, ...],
    *,
    owner_id: UUID,
    now: datetime,
) -> DiscussionDecision:
    """Check an engagement against the policy and the evidence actually offered.

    A skip or a deferral passes unchanged. An engagement is refused when its topic
    is one the person asked LIA to avoid, when it names a sensitive topic without
    consent, or when a reference is not live evidence of this owner from a
    readable source whose topics are consented.

    Args:
        decision: The model's decision.
        policy: The person's discussion policy.
        snapshots: The source pages this run read.
        owner_id: The account the evidence must belong to.
        now: The run's clock; expired evidence is not offered.

    Returns:
        The decision, unchanged.

    Raises:
        ValueError: The engagement breaks one of those rules, a page belongs to
            another account, or two pages offer the same reference.
    """
    if not isinstance(decision, EngageDecision):
        return decision
    if decision.topic.strip().casefold() in {
        topic.strip().casefold() for topic in policy.forbidden_topics
    }:
        raise ValueError("discussion topic is refused")
    offered = _evidence_by_reference(snapshots, owner_id=owner_id, now=now)
    permitted = effective_sources(policy, frozenset(SourceKey))
    if not set(decision.sensitive_topics).issubset(policy.sensitive_topics):
        raise ValueError("sensitive topic consent required")
    if decision.topic in get_args(SensitiveTopic) and decision.topic not in policy.sensitive_topics:
        raise ValueError("sensitive topic consent required")
    for reference in decision.references:
        item = offered.get(reference)
        if item is None:
            raise ValueError("unresolved evidence reference")
        if item.source not in permitted or not set(item.required_sources).issubset(permitted):
            raise ValueError("evidence source is refused")
        if not set(item.sensitive_topics).issubset(policy.sensitive_topics):
            raise ValueError("evidence topic is refused")
    return decision


def clamp_research_window(request: ResearchRequest, *, now: datetime) -> ResearchRequest | None:
    """Repair a research window reaching past the published bounds (ADR-184).

    The bounds are stated to the model in its payload; a window that still
    overshoots is mechanically repairable, so it is narrowed rather than turned
    into a failure after the context call was paid for.

    Args:
        request: The research the model asked for.
        now: The run's clock.

    Returns:
        The request, narrowed when it overshot, or None when nothing of its
        window lies inside the bounds.
    """
    if request.start is None or request.end is None:
        return request
    start = max(request.start, now - timedelta(days=RESEARCH_HISTORY_DAYS_MAX))
    end = min(request.end, now + timedelta(days=RESEARCH_FUTURE_DAYS_MAX))
    if start >= end:
        return None
    if (start, end) == (request.start, request.end):
        return request
    return request.model_copy(update={"start": start, "end": end})


def validate_research_request(
    request: ResearchRequest,
    policy: DiscussionPolicy,
    snapshots: tuple[SourceSnapshot, ...],
    *,
    owner_id: UUID,
    now: datetime,
) -> None:
    """Check a research request against the policy and what the run was offered.

    Args:
        request: The research the model asked for.
        policy: The person's discussion policy.
        snapshots: The source pages this run read.
        owner_id: The account the evidence must belong to.
        now: The run's clock.

    Raises:
        ValueError: The source is not readable, the operation is not one the
            source offers, the cursor or the reference was not offered by that
            source, or the window reaches past the published bounds.
    """
    if request.source not in effective_sources(policy, frozenset(SourceKey)):
        raise ValueError("research source is refused")
    if request.operation not in SOURCE_REGISTRY[request.source].operations:
        raise ValueError("research operation is unavailable for this source")
    if request.cursor is not None and not any(
        snapshot.source == request.source and snapshot.cursor == request.cursor
        for snapshot in snapshots
    ):
        raise ValueError("research cursor was not offered by its source")
    offered = _evidence_by_reference(snapshots, owner_id=owner_id, now=now)
    if request.reference is not None:
        evidence = offered.get(request.reference)
        if evidence is None or evidence.source != request.source:
            raise ValueError("research reference was not offered by this source")
    if request.start is not None and request.start < now - timedelta(
        days=RESEARCH_HISTORY_DAYS_MAX
    ):
        raise ValueError("research exceeds history bound")
    if request.end is not None and request.end > now + timedelta(days=RESEARCH_FUTURE_DAYS_MAX):
        raise ValueError("research exceeds future bound")
