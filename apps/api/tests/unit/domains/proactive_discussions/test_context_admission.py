"""Context controls act before interpretation and survive paraphrases."""

from datetime import UTC, datetime, timedelta

import pytest

from src.domains.proactive_discussions.context_store.admission import (
    admissible_evidence,
    observation_key,
)
from src.domains.shared.discussion_sources import DiscussionEvidence, SourceKey

pytestmark = pytest.mark.unit
NOW = datetime(2026, 10, 20, 12, tzinfo=UTC)


def evidence(**changes: object) -> DiscussionEvidence:
    return DiscussionEvidence.model_validate(
        {
            "reference": "calendar:1",
            "source": "calendar",
            "source_account": "account-a",
            "object_id": "event-1",
            "version": "v1",
            "observed_at": NOW,
            "recorded_at": NOW - timedelta(days=2),
            "excerpt": "Fictional appointment",
            **changes,
        }
    )


def admitted(item: DiscussionEvidence, **changes: object) -> bool:
    values: dict[str, object] = {
        "allowed_sources": frozenset(SourceKey),
        "allowed_topics": frozenset(),
        "excluded_roots": frozenset(),
        "forgotten_versions": {},
        "forgotten_at": None,
        "now": NOW,
    }
    values.update(changes)
    return admissible_evidence(item, **values)


def test_identity_ignores_rephrasing_version_and_generation_but_not_source_account() -> None:
    item = evidence()
    assert observation_key(item) == observation_key(
        evidence(excerpt="Different text", version="v2")
    )
    assert observation_key(item) != observation_key(evidence(source_account="account-b"))
    assert observation_key(item) != observation_key(evidence(source="tasks"))


def test_exclusion_blocks_known_descendants_before_the_model() -> None:
    item = evidence()
    roots = frozenset({observation_key(item)})
    assert not admitted(evidence(version="v2"), excluded_roots=roots)
    assert not admitted(
        evidence(
            source="memories", object_id="m1", derived=True, supports=(observation_key(item),)
        ),
        excluded_roots=roots,
    )
    assert not admitted(
        evidence(
            source="portrait", object_id="whole", derived=True, supports=(observation_key(item),)
        ),
        excluded_roots=roots,
    )


def test_portrait_is_one_independent_source() -> None:
    portrait = evidence(source="portrait", object_id="whole", required_sources=())
    assert admitted(portrait, allowed_sources=frozenset({SourceKey.PORTRAIT}))
    assert not admitted(portrait, allowed_sources=frozenset({SourceKey.MEMORIES}))


def test_purge_blocks_unchanged_history_and_manual_rebuild_can_reconsider_it() -> None:
    item = evidence()
    marker = {observation_key(item): "v1"}
    assert not admitted(item, forgotten_versions=marker, forgotten_at=NOW)
    assert admitted(evidence(version="v2"), forgotten_versions=marker, forgotten_at=NOW)
    assert not admitted(evidence(object_id="previously-unseen"), forgotten_at=NOW)
    assert not admitted(evidence(recorded_at=None), forgotten_at=NOW)
    assert admitted(item)


def test_source_expiry_and_sensitive_consent_are_checked_before_reuse() -> None:
    assert not admitted(evidence(expires_at=NOW))
    assert not admitted(
        evidence(required_sources=(SourceKey.HEALTH,)),
        allowed_sources=frozenset({SourceKey.CALENDAR}),
    )
    assert not admitted(evidence(sensitive_topics=("health",)))
    assert admitted(evidence(sensitive_topics=("health",)), allowed_topics=frozenset({"health"}))
