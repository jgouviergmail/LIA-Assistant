"""Known extra source requirements cannot disappear behind a memory projection."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from src.domains.proactive_discussions.policy import validate_decision
from src.domains.proactive_discussions.schemas import DiscussionPolicy, EngageDecision
from src.domains.shared.discussion_sources import DiscussionEvidence, SourceKey, SourceSnapshot

pytestmark = pytest.mark.unit


def test_declared_sensitive_classification_cannot_hide_behind_a_free_text_topic() -> None:
    now = datetime(2026, 10, 20, 10, tzinfo=UTC)
    item = DiscussionEvidence(
        reference="calendar:1",
        source=SourceKey.CALENDAR,
        object_id="1",
        version="v1",
        observed_at=now,
        excerpt="Fictional appointment",
    )
    source = SourceSnapshot(
        source=SourceKey.CALENDAR,
        owner_id=UUID(int=1),
        status="ok",
        read_at=now,
        window_start=now - timedelta(days=3),
        window_end=now + timedelta(days=7),
        complete=False,
        items=(item,),
    )
    decision = EngageDecision(
        action="engage",
        reason="follow-up",
        topic="appointment_follow_up",
        references=(item.reference,),
        sensitive_topics=("health",),
    )
    with pytest.raises(ValueError, match="topic"):
        validate_decision(
            decision,
            DiscussionPolicy(enabled=True, sources=(SourceKey.CALENDAR,), sensitive_topics=()),
            (source,),
            owner_id=UUID(int=1),
            now=now,
        )


def test_sensitive_topic_consent_does_not_replace_required_source_consent() -> None:
    now = datetime(2026, 10, 20, 10, tzinfo=UTC)
    item = DiscussionEvidence.model_validate(
        {
            "reference": "memories:1",
            "source": "memories",
            "object_id": "1",
            "version": "v1",
            "observed_at": now,
            "excerpt": "Fictional health-related fact",
            "sensitive_topics": ["health"],
            "required_sources": ["health"],
        }
    )
    snapshot = SourceSnapshot(
        source=SourceKey.MEMORIES,
        owner_id=UUID(int=1),
        status="ok",
        read_at=now,
        window_start=now - timedelta(days=3),
        window_end=now + timedelta(days=7),
        complete=True,
        items=(item,),
    )
    decision = EngageDecision(
        action="engage", reason="follow-up", topic="health", references=("memories:1",)
    )
    policy = DiscussionPolicy(
        enabled=True, sources=(SourceKey.MEMORIES,), sensitive_topics=("health",)
    )
    with pytest.raises(ValueError, match="source"):
        validate_decision(decision, policy, (snapshot,), owner_id=UUID(int=1), now=now)
