"""Model proposals require evidence offered to this account under this policy."""

from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from src.domains.proactive_discussions.policy import validate_decision, validate_research_request
from src.domains.proactive_discussions.schemas import (
    DiscussionPolicy,
    parse_context_resolution,
    parse_decision,
)
from src.domains.shared.discussion_sources import (
    DiscussionEvidence,
    ResearchRequest,
    SourceKey,
    SourceSnapshot,
)

pytestmark = pytest.mark.unit
OWNER = UUID(int=1)
NOW = datetime(2026, 10, 20, 10, tzinfo=UTC)


def snapshot() -> SourceSnapshot:
    return SourceSnapshot(
        source=SourceKey.CALENDAR,
        owner_id=OWNER,
        status="ok",
        read_at=NOW,
        window_start=NOW.replace(day=17),
        window_end=NOW.replace(day=27),
        complete=True,
        items=(
            DiscussionEvidence(
                reference="event:1",
                source=SourceKey.CALENDAR,
                object_id="1",
                version="v2",
                observed_at=NOW,
                occurred_at=NOW,
                excerpt="Planned routine appointment; attendance unknown",
            ),
        ),
    )


@pytest.mark.parametrize(
    "payload",
    [
        {"action": "skip", "reason": "none", "message": "hello"},
        {"action": "engage", "reason": "follow-up", "topic": "health", "references": []},
        {"action": "engage", "reason": "follow-up", "references": ["event:1"]},
        {"action": "defer", "reason": "busy"},
        {"action": "defer", "reason": "busy", "retry_after_seconds": 0},
        {"action": "defer", "reason": "busy", "retry_after_seconds": 86401},
        {"action": "research", "reason": "more"},
    ],
)
def test_invalid_decision_rejected(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        parse_decision(payload)


def test_engage_requires_resolved_references() -> None:
    policy = DiscussionPolicy(
        enabled=True, sources=(SourceKey.CALENDAR,), sensitive_topics=("health",)
    )
    decision = parse_decision(
        {"action": "engage", "reason": "follow-up", "topic": "health", "references": ["event:1"]}
    )
    assert validate_decision(decision, policy, (snapshot(),), owner_id=OWNER, now=NOW) == decision
    with pytest.raises(ValueError, match="reference"):
        validate_decision(decision, policy, (), owner_id=OWNER, now=NOW)


def test_foreign_owner_or_refused_source_cannot_supply_evidence() -> None:
    policy = DiscussionPolicy(enabled=True, sources=(SourceKey.CALENDAR,))
    decision = parse_decision(
        {"action": "engage", "reason": "follow-up", "topic": "project", "references": ["event:1"]}
    )
    with pytest.raises(ValueError, match="owner"):
        validate_decision(decision, policy, (snapshot(),), owner_id=UUID(int=2), now=NOW)
    with pytest.raises(ValueError, match="source"):
        validate_decision(
            decision,
            policy.model_copy(update={"sources": ()}),
            (snapshot(),),
            owner_id=OWNER,
            now=NOW,
        )


def test_sensitive_topic_needs_its_own_permission() -> None:
    decision = parse_decision(
        {"action": "engage", "reason": "follow-up", "topic": "health", "references": ["event:1"]}
    )
    with pytest.raises(ValueError, match="topic"):
        validate_decision(
            decision,
            DiscussionPolicy(enabled=True, sources=(SourceKey.CALENDAR,)),
            (snapshot(),),
            owner_id=OWNER,
            now=NOW,
        )


@pytest.mark.parametrize(
    "payload",
    [
        {"status": "research", "requests": []},
        {"status": "research", "requests": [{"source": "calendar", "operation": "delete"}]},
        {"status": "insufficient", "reason": "unknown", "message": "hello"},
    ],
)
def test_context_resolution_is_a_distinct_strict_union(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        parse_context_resolution(payload)


def test_research_refuses_disabled_source() -> None:
    request = ResearchRequest(source=SourceKey.EMAILS, operation="search", query="project")
    with pytest.raises(ValueError, match="source"):
        validate_research_request(
            request,
            DiscussionPolicy(enabled=True, sources=(SourceKey.CALENDAR,)),
            (snapshot(),),
            owner_id=OWNER,
            now=NOW,
        )


def test_detail_cannot_read_a_reference_never_offered() -> None:
    request = ResearchRequest(
        source=SourceKey.CALENDAR, operation="detail", reference="event:foreign"
    )
    with pytest.raises(ValueError, match="reference"):
        validate_research_request(
            request,
            DiscussionPolicy(enabled=True, sources=(SourceKey.CALENDAR,)),
            (snapshot(),),
            owner_id=OWNER,
            now=NOW,
        )


@pytest.mark.parametrize(
    "payload",
    [
        {"source": "calendar", "operation": "search", "query": ""},
        {"source": "calendar", "operation": "detail"},
        {"source": "calendar", "operation": "delete", "reference": "event:1"},
        {"source": "calendar", "operation": "history", "start": "yesterday", "end": "today"},
        {
            "source": "calendar",
            "operation": "history",
            "start": "2026-10-20T00:00:00Z",
            "end": "2026-10-19T00:00:00Z",
        },
    ],
)
def test_malformed_research_rejected(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ResearchRequest.model_validate(payload)


def test_snapshot_refuses_cross_source_evidence() -> None:
    data = snapshot().model_dump()
    data["source"] = SourceKey.EMAILS
    with pytest.raises(ValidationError):
        SourceSnapshot.model_validate(data)


def test_source_json_roundtrip_preserves_all_fields() -> None:
    original = snapshot()
    assert SourceSnapshot.model_validate_json(original.model_dump_json()) == original


def test_expired_source_evidence_cannot_support_an_opening() -> None:
    current = snapshot()
    expired = current.model_copy(
        update={"items": (current.items[0].model_copy(update={"expires_at": NOW}),)}
    )
    decision = parse_decision(
        {"action": "engage", "reason": "follow-up", "topic": "project", "references": ["event:1"]}
    )
    with pytest.raises(ValueError, match="reference"):
        validate_decision(
            decision,
            DiscussionPolicy(enabled=True, sources=(SourceKey.CALENDAR,)),
            (expired,),
            owner_id=OWNER,
            now=NOW,
        )


def test_duplicate_supports_do_not_manufacture_independent_evidence() -> None:
    with pytest.raises(ValidationError):
        parse_decision(
            {
                "action": "engage",
                "reason": "follow-up",
                "topic": "project",
                "references": ["event:1", "event:1"],
            }
        )
