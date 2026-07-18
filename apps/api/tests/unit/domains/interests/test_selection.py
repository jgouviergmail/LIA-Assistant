"""Tests for the pure subject-rarity selection algorithm (ADR-131, bench V5)."""

import random
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from src.domains.interests.selection import (
    SelectionConfig,
    select_interest_subject_rarity,
)


class FakeInterest:
    """Duck-typed stand-in: selection only reads .id and .subject."""

    def __init__(self, subject: str | None) -> None:
        self.id = uuid.uuid4()
        self.subject = subject


CONFIG = SelectionConfig(
    subject_cooldown_hours=36,
    subject_rarity_gamma=1.0,
    subject_weight_beta=0.0,
    intra_subject_rarity_gamma=1.0,
    lookback_days=30,
)
NOW = datetime(2026, 7, 18, 12, 0, tzinfo=UTC)


def _pool(interests: list[FakeInterest]) -> dict[uuid.UUID, str | None]:
    return {i.id: i.subject for i in interests}


@pytest.mark.unit
class TestSubjectCooldown:
    def test_recently_notified_subject_is_excluded(self) -> None:
        ia = FakeInterest("ai")
        travel = FakeInterest("travel")
        candidates = [(ia, 0.9), (travel, 0.9)]
        recent = [(ia.id, NOW - timedelta(hours=2))]  # "ai" notified 2h ago
        for seed in range(20):
            result = select_interest_subject_rarity(
                candidates, _pool([ia, travel]), recent, NOW, CONFIG, random.Random(seed)
            )
            assert result is not None
            picked, debug = result
            assert picked is travel
            assert debug.fail_open is False

    def test_cooldown_counts_interests_outside_candidates(self) -> None:
        """A same-subject sibling in per-topic cooldown still freezes the subject."""
        sibling = FakeInterest("ai")  # notified 2h ago -> NOT in candidates
        other_ai = FakeInterest("ai")
        travel = FakeInterest("travel")
        candidates = [(other_ai, 0.9), (travel, 0.9)]
        pool = _pool([sibling, other_ai, travel])
        recent = [(sibling.id, NOW - timedelta(hours=2))]
        for seed in range(20):
            result = select_interest_subject_rarity(
                candidates, pool, recent, NOW, CONFIG, random.Random(seed)
            )
            assert result is not None
            assert result[0] is travel

    def test_fail_open_when_all_subjects_cooling(self) -> None:
        ia = FakeInterest("ai")
        candidates = [(ia, 0.9)]
        recent = [(ia.id, NOW - timedelta(hours=1))]
        result = select_interest_subject_rarity(
            candidates, _pool([ia]), recent, NOW, CONFIG, random.Random(0)
        )
        assert result is not None
        picked, debug = result
        assert picked is ia
        assert debug.fail_open is True


@pytest.mark.unit
class TestRarityDraw:
    def test_null_subject_is_singleton(self) -> None:
        """Unclustered interests each form their own subject (fail-open semantics)."""
        a = FakeInterest(None)
        b = FakeInterest(None)
        result = select_interest_subject_rarity(
            [(a, 0.9), (b, 0.9)], _pool([a, b]), [], NOW, CONFIG, random.Random(0)
        )
        assert result is not None
        assert result[1].total_subjects == 2

    def test_rarity_prefers_less_notified_subject(self) -> None:
        """Statistical: subject with 5 recent notifs loses to a fresh subject ~6:1."""
        served = FakeInterest("ai")
        fresh = FakeInterest("travel")
        pool = _pool([served, fresh])
        recent = [
            (served.id, NOW - timedelta(days=d)) for d in (3, 6, 9, 12, 15)
        ]  # outside 36h cooldown, inside 30d lookback
        wins = 0
        for seed in range(400):
            result = select_interest_subject_rarity(
                [(served, 0.9), (fresh, 0.9)], pool, recent, NOW, CONFIG, random.Random(seed)
            )
            assert result is not None
            if result[0] is fresh:
                wins += 1
        # Expected p(fresh) = 1 / (1 + 1/6) ~= 0.857; allow generous CI margin.
        assert 0.78 <= wins / 400 <= 0.93

    def test_intra_subject_rarity_spreads_members(self) -> None:
        heavy = FakeInterest("ai")  # 4 recent notifs
        light = FakeInterest("ai")  # 0 recent notifs
        pool = _pool([heavy, light])
        recent = [(heavy.id, NOW - timedelta(days=d)) for d in (2, 5, 8, 11)]
        # Subject 'ai' is beyond cooldown (last notif 2 days ago vs 36h) -> eligible.
        wins = 0
        for seed in range(400):
            result = select_interest_subject_rarity(
                [(heavy, 0.9), (light, 0.9)], pool, recent, NOW, CONFIG, random.Random(seed)
            )
            assert result is not None
            if result[0] is light:
                wins += 1
        # p(light) = 5/6 ~= 0.833 within the subject.
        assert 0.75 <= wins / 400 <= 0.91


@pytest.mark.unit
class TestEdgeCases:
    def test_empty_candidates_returns_none(self) -> None:
        assert select_interest_subject_rarity([], {}, [], NOW, CONFIG, random.Random(0)) is None

    def test_unknown_notified_interest_is_ignored(self) -> None:
        """Notifications of deleted/dormant interests must not crash nor count."""
        a = FakeInterest("ai")
        ghost_id = uuid.uuid4()
        result = select_interest_subject_rarity(
            [(a, 0.9)], _pool([a]), [(ghost_id, NOW), (None, NOW)], NOW, CONFIG, random.Random(0)
        )
        assert result is not None and result[0] is a

    def test_lookback_bounds_rarity_window(self) -> None:
        """Notifications older than lookback_days do not count for rarity."""
        a = FakeInterest("ai")
        b = FakeInterest("travel")
        pool = _pool([a, b])
        old = [(a.id, NOW - timedelta(days=40))]  # outside 30d window
        counts = {True: 0, False: 0}
        for seed in range(200):
            result = select_interest_subject_rarity(
                [(a, 0.9), (b, 0.9)], pool, old, NOW, CONFIG, random.Random(seed)
            )
            assert result is not None
            counts[result[0] is a] += 1
        # Old notif ignored -> both subjects equally likely (~50/50).
        assert 0.40 <= counts[True] / 200 <= 0.60
