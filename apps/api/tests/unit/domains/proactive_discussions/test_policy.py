"""Consent and cadence must reject an initiative before any personal read."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from src.domains.proactive_discussions.policy import effective_sources, may_start
from src.domains.proactive_discussions.schemas import DiscussionPolicy
from src.domains.shared.discussion_sources import SourceKey

pytestmark = pytest.mark.unit
NOW = datetime(2026, 10, 20, 10, tzinfo=UTC)


def test_null_daily_max_means_no_count_bound() -> None:
    policy = DiscussionPolicy(enabled=True, daily_max=None, timezone="UTC")
    assert policy.daily_max is None
    assert may_start(policy, now=NOW, openings_today=100)


@pytest.mark.parametrize("value", [0, -1, True, 1.5, "2"])
def test_invalid_daily_max_rejected(value: object) -> None:
    with pytest.raises(ValidationError):
        DiscussionPolicy.model_validate({"daily_max": value})


def test_equal_hours_rejected() -> None:
    with pytest.raises(ValidationError):
        DiscussionPolicy(start_hour=9, end_hour=9)


@pytest.mark.parametrize("hour,want", [(21, False), (22, True), (0, True), (5, True), (6, False)])
def test_overnight_start_inclusive_end_exclusive(hour: int, want: bool) -> None:
    policy = DiscussionPolicy(enabled=True, start_hour=22, end_hour=6, timezone="UTC")
    assert may_start(policy, now=NOW.replace(hour=hour), openings_today=0) is want


def test_account_timezone_controls_window() -> None:
    policy = DiscussionPolicy(enabled=True, timezone="America/New_York")
    assert not may_start(policy, now=NOW, openings_today=0)
    assert may_start(policy, now=NOW.replace(hour=14), openings_today=0)


def test_pause_feature_and_quota_are_independent_gates() -> None:
    policy = DiscussionPolicy(enabled=True, timezone="UTC", paused_until=NOW)
    assert may_start(policy, now=NOW, openings_today=1)
    assert not may_start(policy, now=NOW, openings_today=2)
    assert not may_start(DiscussionPolicy(timezone="UTC"), now=NOW, openings_today=0)
    assert not may_start(
        policy.model_copy(update={"paused_until": NOW.replace(day=21)}), now=NOW, openings_today=0
    )


def test_empty_allowlist_reads_nothing() -> None:
    assert effective_sources(DiscussionPolicy(enabled=True), frozenset(SourceKey)) == frozenset()


def test_added_source_defaults_off_and_revoked_authority_wins() -> None:
    policy = DiscussionPolicy(enabled=True, sources=(SourceKey.CALENDAR, SourceKey.SMS))
    assert effective_sources(policy, frozenset({SourceKey.CALENDAR})) == frozenset(
        {SourceKey.CALENDAR}
    )
    assert effective_sources(policy, frozenset(SourceKey)) == frozenset(
        {SourceKey.CALENDAR, SourceKey.SMS}
    )
    assert (
        effective_sources(policy.model_copy(update={"enabled": False}), frozenset(SourceKey))
        == frozenset()
    )


def test_portrait_is_independent_of_constituent_source_switches() -> None:
    policy = DiscussionPolicy(enabled=True, sources=(SourceKey.PORTRAIT,))
    assert effective_sources(policy, frozenset({SourceKey.PORTRAIT})) == frozenset(
        {SourceKey.PORTRAIT}
    )


def test_health_source_requires_sensitive_topic_consent_before_read() -> None:
    policy = DiscussionPolicy(enabled=True, sources=(SourceKey.HEALTH,))
    assert effective_sources(policy, frozenset(SourceKey)) == frozenset()
    allowed = policy.model_copy(update={"sensitive_topics": ("health",)})
    assert effective_sources(allowed, frozenset(SourceKey)) == frozenset({SourceKey.HEALTH})


@pytest.mark.parametrize(
    "payload",
    [
        {"sources": ["invented"]},
        {"start_hour": 24},
        {"start_hour": True},
        {"timezone": "Invalid/Place"},
        {"enabled": "yes"},
        {"extra": "ignored?"},
        {"paused_until": "2026-10-20T10:00:00"},
    ],
)
def test_malformed_policy_fails_closed(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        DiscussionPolicy.model_validate(payload)


def test_policy_json_roundtrip_preserves_all_fields() -> None:
    policy = DiscussionPolicy(
        enabled=True,
        timezone="UTC",
        daily_max=None,
        sources=(SourceKey.PORTRAIT, SourceKey.SMS),
        sensitive_topics=("health",),
        paused_until=NOW,
        revision=7,
    )
    assert DiscussionPolicy.model_validate_json(policy.model_dump_json()) == policy
