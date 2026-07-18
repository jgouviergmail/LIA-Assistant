"""Distribution regression for subject-rarity selection (bench 2026-07-18).

Replays 30 days of selection over a pool shaped like the prod snapshot
(one subject holding 9 of 19 interests). Guards the headline ADR-131 result:
the dominant subject's share drops from ~47% (uniform) to well under 40%
and no interest starves systematically.
"""

import random
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from src.domains.interests.selection import (
    SelectionConfig,
    select_interest_subject_rarity,
)


class FakeInterest:
    def __init__(self, subject: str) -> None:
        self.id = uuid.uuid4()
        self.subject = subject


@pytest.mark.unit
def test_dominant_subject_share_drops() -> None:
    config = SelectionConfig(
        subject_cooldown_hours=36,
        subject_rarity_gamma=1.0,
        subject_weight_beta=0.0,
        intra_subject_rarity_gamma=1.0,
        lookback_days=30,
    )
    subjects = (
        ["ai"] * 9
        + ["crypto"] * 2
        + ["mobile"] * 2
        + ["films"] * 2
        + ["indonesia", "usa", "china", "moderation"]
    )
    interests = [FakeInterest(s) for s in subjects]
    pool = {i.id: i.subject for i in interests}
    rng = random.Random(42)
    start = datetime(2026, 7, 1, tzinfo=UTC)

    notif_log: list[tuple[uuid.UUID, datetime]] = []
    picks: dict[str, int] = {}
    per_interest: dict[uuid.UUID, int] = {}
    for day in range(30):
        for slot in range(3):
            now = start + timedelta(days=day, hours=9 + slot * 4)
            topic_floor = now - timedelta(hours=12)
            candidates = [
                (i, 0.9)
                for i in interests
                if not any(iid == i.id and ts >= topic_floor for iid, ts in notif_log)
            ]
            result = select_interest_subject_rarity(
                candidates, pool, list(notif_log), now, config, rng
            )
            assert result is not None
            picked, _ = result
            notif_log.append((picked.id, now))
            picks[picked.subject] = picks.get(picked.subject, 0) + 1
            per_interest[picked.id] = per_interest.get(picked.id, 0) + 1

    total = sum(picks.values())
    ai_share = picks.get("ai", 0) / total
    # Uniform baseline would give ai 9/19 ~= 47%; V5 target ~1/8 subjects.
    assert ai_share < 0.40, f"ai share {ai_share:.1%} not reduced"
    starved = sum(1 for i in interests if per_interest.get(i.id, 0) == 0)
    assert starved <= 2, f"{starved} interests never notified in 30 days"
