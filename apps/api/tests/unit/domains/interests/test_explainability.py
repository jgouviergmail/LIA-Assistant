"""Explaining an interest's weight, without turning it into a score.

The panel showed a percentage badge and a date. A reader deciding whether to
block a subject could see that LIA rated it 46 % and nothing about why — not
how many signals, not how old they were, not which conversation started it.
And the number itself was a claim the ranking did not honour until 2026-08-04.

What is published here are the formula's INPUTS and its COEFFICIENTS, so the
number can be reconstructed rather than trusted (ADR-184: whatever a system
enforces, it publishes). Deliberately absent: any rank, level or comparison.
A Beta mean IS an uncertainty estimate, and "two signals, so this is a guess"
serves a decision in a way no score does.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.config import settings
from src.core.constants import INTEREST_DECAY_FLOOR
from src.domains.interests.explainability_router import get_interest_explanation
from src.domains.interests.models import InterestStatus, UserInterest

pytestmark = pytest.mark.unit


def _interest(owner: uuid.UUID, *, positives: int = 4, days: int = 20) -> UserInterest:
    interest = UserInterest(
        user_id=owner,
        topic="architecture logicielle",
        category="technology",
        positive_signals=positives,
        negative_signals=1,
        status=InterestStatus.ACTIVE.value,
        last_mentioned_at=datetime.now(UTC) - timedelta(days=days),
    )
    interest.id = uuid.uuid4()
    interest.last_notified_at = None
    interest.dormant_since = None
    return interest


async def _explain(interest: UserInterest, *, caller: uuid.UUID | None = None):
    user = MagicMock()
    user.id = caller or interest.user_id
    with patch("src.domains.interests.explainability_router.InterestRepository") as repo_cls:
        # The REAL arithmetic: mocking it would prove the route returns numbers,
        # not that it returns the ones the ranking applies.
        from src.domains.interests.repository import InterestRepository

        real = InterestRepository(AsyncMock())
        repo_cls.return_value.get_by_id = AsyncMock(return_value=interest)
        repo_cls.return_value.calculate_weight = real.calculate_weight
        repo_cls.return_value.calculate_effective_weight = real.calculate_effective_weight
        return await get_interest_explanation(interest_id=interest.id, user=user, db=AsyncMock())


class TestTheWeightCanBeRecomputed:
    async def test_it_publishes_every_coefficient_of_the_formula(self) -> None:
        owner = uuid.uuid4()
        explanation = await _explain(_interest(owner))

        assert explanation.prior_alpha == settings.interest_prior_alpha
        assert explanation.prior_beta == settings.interest_prior_beta
        assert explanation.decay_rate_per_day == settings.interest_decay_rate_per_day
        assert explanation.decay_floor == INTEREST_DECAY_FLOOR

    async def test_the_reader_can_rebuild_the_number_from_what_is_published(self) -> None:
        """The point of publishing: the figure is checkable, not merely stated."""
        owner = uuid.uuid4()
        explanation = await _explain(_interest(owner, positives=4, days=20))

        expected_base = (explanation.prior_alpha + explanation.positive_signals) / (
            explanation.prior_alpha
            + explanation.positive_signals
            + explanation.prior_beta
            + explanation.negative_signals
        )
        expected_decay = max(
            explanation.decay_floor,
            1 - explanation.decay_rate_per_day * explanation.days_since_last_mention,
        )

        assert explanation.base_weight == pytest.approx(expected_base)
        assert explanation.effective_weight == pytest.approx(expected_base * expected_decay)

    async def test_the_effective_weight_is_the_one_the_ranking_applies(self) -> None:
        """Both sides now read the setting; an explanation of an unused number
        would be worse than no explanation at all."""
        owner = uuid.uuid4()
        interest = _interest(owner, positives=8, days=90)
        from src.domains.interests.repository import InterestRepository

        ranking = InterestRepository(AsyncMock()).calculate_effective_weight(interest)

        explanation = await _explain(interest)

        assert explanation.effective_weight == pytest.approx(ranking, abs=1e-6)

    async def test_it_carries_the_dates_the_reader_asked_for(self) -> None:
        owner = uuid.uuid4()
        interest = _interest(owner)
        interest.last_notified_at = datetime.now(UTC) - timedelta(days=2)

        explanation = await _explain(interest)

        assert explanation.last_mentioned_at == interest.last_mentioned_at
        assert explanation.last_notified_at == interest.last_notified_at
        assert explanation.status == InterestStatus.ACTIVE.value

    async def test_a_never_notified_interest_says_so_rather_than_inventing_a_date(self) -> None:
        explanation = await _explain(_interest(uuid.uuid4()))

        assert explanation.last_notified_at is None

    async def test_the_age_is_never_negative(self) -> None:
        """A clock skew must not produce "-1 days since the last mention"."""
        owner = uuid.uuid4()
        interest = _interest(owner)
        interest.last_mentioned_at = datetime.now(UTC) + timedelta(hours=2)

        explanation = await _explain(interest)

        assert explanation.days_since_last_mention == 0


class TestItExplainsRatherThanScores:
    async def test_nothing_published_is_a_rank_or_a_level(self) -> None:
        """Explicit product rule: no gamification, no comparison with anyone."""
        explanation = await _explain(_interest(uuid.uuid4()))
        fields = set(type(explanation).model_fields)

        forbidden = {"rank", "level", "score", "percentile", "badge", "streak", "xp"}
        assert not (fields & forbidden)

    async def test_an_interest_of_another_account_is_not_explained(self) -> None:
        """Hide-existence: a foreign id answers exactly like an unknown one."""
        from src.core.exceptions import ResourceNotFoundError

        with pytest.raises(ResourceNotFoundError):
            await _explain(_interest(uuid.uuid4()), caller=uuid.uuid4())
