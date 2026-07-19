"""Tests for the subject-aware varied interest sample (ADR-135, heartbeat context)."""

import random
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from src.domains.interests.selection import pick_varied_sample


class FakeInterest:
    def __init__(self, subject: str | None, topic: str = "t") -> None:
        self.id = uuid.uuid4()
        self.subject = subject
        self.topic = topic


NOW = datetime(2026, 7, 19, 10, 0, tzinfo=UTC)


def _pool(interests):
    return {i.id: i.subject for i in interests}


@pytest.mark.unit
class TestPickVariedSample:
    def test_one_interest_per_subject(self) -> None:
        a1, a2 = FakeInterest("ai"), FakeInterest("ai")
        b, c = FakeInterest("crypto"), FakeInterest("travel")
        sample = pick_varied_sample(
            [a1, a2, b, c], _pool([a1, a2, b, c]), [], NOW, 5, 7, random.Random(0)
        )
        subjects = [i.subject for i in sample]
        assert len(subjects) == len(set(subjects)) == 3

    def test_recently_served_subject_ranked_last(self) -> None:
        served = FakeInterest("ai")
        fresh1, fresh2 = FakeInterest("crypto"), FakeInterest("travel")
        recent = [(served.id, NOW - timedelta(hours=3))]
        for seed in range(10):
            sample = pick_varied_sample(
                [served, fresh1, fresh2],
                _pool([served, fresh1, fresh2]),
                recent,
                NOW,
                2,
                7,
                random.Random(seed),
            )
            assert served not in sample  # size 2 < 3 subjects: served one is cut

    def test_null_subject_is_singleton_group(self) -> None:
        a, b = FakeInterest(None), FakeInterest(None)
        sample = pick_varied_sample([a, b], _pool([a, b]), [], NOW, 5, 7, random.Random(0))
        assert len(sample) == 2

    def test_least_served_member_within_subject(self) -> None:
        heavy, light = FakeInterest("ai"), FakeInterest("ai")
        recent = [(heavy.id, NOW - timedelta(days=d)) for d in (1, 2, 3)]
        sample = pick_varied_sample(
            [heavy, light], _pool([heavy, light]), recent, NOW, 1, 7, random.Random(0)
        )
        assert sample == [light]

    def test_lookback_bounds_serving_counts(self) -> None:
        old_served = FakeInterest("ai")
        fresh = FakeInterest("crypto")
        recent = [(old_served.id, NOW - timedelta(days=20))]  # outside 7d
        picked = {
            pick_varied_sample(
                [old_served, fresh],
                _pool([old_served, fresh]),
                recent,
                NOW,
                1,
                7,
                random.Random(seed),
            )[0].subject
            for seed in range(20)
        }
        assert picked == {"ai", "crypto"}  # both treated as never-served (rng tiebreak)

    def test_empty_candidates(self) -> None:
        assert pick_varied_sample([], {}, [], NOW, 5, 7, random.Random(0)) == []

    def test_deleted_interest_notifications_ignored(self) -> None:
        a = FakeInterest("ai")
        sample = pick_varied_sample(
            [a], _pool([a]), [(None, NOW), (uuid.uuid4(), NOW)], NOW, 5, 7, random.Random(0)
        )
        assert sample == [a]
