"""Unit tests for InterestRepository.merge_interests mutations (ADR-131).

Mutation-level assertions with a mocked session, mirroring
test_repository_reactivate.py. Query behavior (notification repointing)
is covered by tests/integration/domains/interests/test_repository_subjects.py.
"""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from src.domains.interests.models import InterestStatus, UserInterest
from src.domains.interests.repository import InterestRepository


def _interest(
    topic: str,
    positive: int,
    negative: int,
    status: str = InterestStatus.ACTIVE.value,
    notified_days_ago: int | None = None,
    mentioned_days_ago: int = 10,
) -> UserInterest:
    interest = UserInterest(
        user_id=uuid.uuid4(),
        topic=topic,
        category="technology",
        positive_signals=positive,
        negative_signals=negative,
        status=status,
        last_mentioned_at=datetime.now(UTC) - timedelta(days=mentioned_days_ago),
    )
    interest.id = uuid.uuid4()
    interest.subject = "old label"
    if notified_days_ago is not None:
        interest.last_notified_at = datetime.now(UTC) - timedelta(days=notified_days_ago)
    return interest


@pytest.mark.unit
async def test_merge_sums_signals_and_resets_subject() -> None:
    db = AsyncMock()
    repo = InterestRepository(db)
    keep = _interest("Anthropic", positive=10, negative=1, mentioned_days_ago=20)
    dup = _interest("anthropic", positive=4, negative=2, notified_days_ago=1, mentioned_days_ago=5)

    merged = await repo.merge_interests(keep, dup)

    assert merged is keep
    assert keep.positive_signals == 14
    assert keep.negative_signals == 3
    assert keep.subject is None
    # Freshest activity wins on both timestamps.
    assert keep.last_mentioned_at == dup.last_mentioned_at
    assert keep.last_notified_at == dup.last_notified_at
    db.delete.assert_awaited_once_with(dup)
    db.execute.assert_awaited()  # notification repointing UPDATE
    db.flush.assert_awaited_once()


@pytest.mark.unit
async def test_merge_preserves_blocked_status_from_duplicate() -> None:
    db = AsyncMock()
    repo = InterestRepository(db)
    keep = _interest("X", positive=5, negative=0)
    dup = _interest("x", positive=1, negative=0, status=InterestStatus.BLOCKED.value)

    await repo.merge_interests(keep, dup)

    assert keep.status == InterestStatus.BLOCKED.value


@pytest.mark.unit
async def test_update_topic_resets_subject_for_reclustering() -> None:
    """Manual renames (router path) must reset the derived subject label,
    mirroring the extraction rename path (ADR-131)."""
    db = AsyncMock()
    repo = InterestRepository(db)
    interest = _interest("Old topic", positive=3, negative=0)
    assert interest.subject == "old label"

    await repo.update(interest, topic="New topic")

    assert interest.topic == "New topic"
    assert interest.subject is None


@pytest.mark.unit
async def test_update_same_topic_keeps_subject() -> None:
    """A no-op topic value must not churn the subject label."""
    db = AsyncMock()
    repo = InterestRepository(db)
    interest = _interest("Same topic", positive=3, negative=0)

    await repo.update(interest, topic="Same topic", positive_signals=5)

    assert interest.subject == "old label"
    assert interest.positive_signals == 5


@pytest.mark.unit
def test_map_source_knows_brave() -> None:
    """Brave results were logged as "custom" (141 rows/60d in prod), skewing
    every per-source statistic (ADR-135 bonus fix)."""
    from src.domains.interests.proactive_task import InterestProactiveTask
    from src.infrastructure.proactive.base import ContentSource

    assert InterestProactiveTask()._map_source("brave") == ContentSource.BRAVE
    assert InterestProactiveTask()._map_source("perplexity") == ContentSource.PERPLEXITY
    assert InterestProactiveTask()._map_source("unknown_x") == ContentSource.CUSTOM
