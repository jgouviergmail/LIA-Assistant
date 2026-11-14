"""When an active skill counts as unused long enough to propose switching it off (lot 14)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from src.domains.skills.usage import is_dormant, usage_view

pytestmark = pytest.mark.unit

NOW = datetime(2026, 11, 13, 9, 0, tzinfo=UTC)
DAYS = 60


def _ago(days: int | None) -> datetime | None:
    return None if days is None else NOW - timedelta(days=days)


def _dormant(
    *,
    active: bool = True,
    always_loaded: bool = False,
    used_days_ago: int | None = None,
    counted_days_ago: int = 365,
    kept_days_ago: int | None = None,
) -> bool:
    return is_dormant(
        is_active=active,
        always_loaded=always_loaded,
        last_used_at=_ago(used_days_ago),
        counted_since=NOW - timedelta(days=counted_days_ago),
        kept_at=_ago(kept_days_ago),
        now=NOW,
        after_days=DAYS,
    )


def test_a_skill_used_recently_is_not_dormant() -> None:
    assert _dormant(used_days_ago=3) is False


def test_a_skill_unused_for_the_whole_period_is_dormant() -> None:
    assert _dormant(used_days_ago=DAYS + 1) is True
    assert _dormant(used_days_ago=DAYS) is True  # the period is over at its last day


def test_no_use_recorded_is_measured_from_when_the_counting_began() -> None:
    # Counting starts with the migration (or the person's state): a skill used
    # every day BEFORE it is not « unused for months » the day after.
    assert _dormant(counted_days_ago=DAYS - 1) is False
    assert _dormant(counted_days_ago=DAYS + 1) is True


def test_an_inactive_skill_is_never_proposed_again() -> None:
    assert _dormant(active=False, used_days_ago=DAYS * 3) is False


def test_an_always_loaded_skill_is_never_dormant() -> None:
    # Its instructions enter every turn without an activation to count: its use
    # cannot be observed, so « unused » would be a guess.
    assert _dormant(always_loaded=True, counted_days_ago=DAYS * 3) is False


def test_a_skill_the_person_chose_to_keep_waits_a_whole_period_again() -> None:
    assert _dormant(used_days_ago=DAYS * 2, kept_days_ago=DAYS - 1) is False
    assert _dormant(used_days_ago=DAYS * 2, kept_days_ago=DAYS + 1) is True


def test_the_listing_shows_the_count_since_when_the_last_use_and_the_verdict() -> None:
    listed = {
        "is_active": True,
        "use_count": 3,
        "last_used_at": NOW - timedelta(days=DAYS + 5),
        "counted_since": NOW - timedelta(days=400),
        "dormancy_kept_at": None,
    }

    assert usage_view(listed, always_loaded=False, now=NOW, after_days=DAYS) == {
        "use_count": 3,
        "last_used_at": NOW - timedelta(days=DAYS + 5),
        "counted_since": NOW - timedelta(days=400),
        "dormant": True,
    }
    assert usage_view(listed, always_loaded=True, now=NOW, after_days=DAYS)["dormant"] is False
