"""The weight shown to the reader is the weight the machine applies.

An interest's effective weight is a Beta prior corrected by a temporal decay:

    (alpha0 + positives) / (alpha0 + positives + beta0 + negatives)
        * max(0.1, 1 - decay_rate * days_since_last_mention)

``decay_rate`` is a SETTING (``INTEREST_DECAY_RATE_PER_DAY``), configured at
0.005 in ``.env`` and ``.env.example`` alike. Three of the four call sites read
it. The fourth — ``get_top_weighted_interests``, which is the ONE path that
decides which interest gets notified — took the signature's hardcoded 0.01
default instead.

The consequence was a number that means two different things at once: an
interest last mentioned 90 days ago displayed 0.458 and was ranked at 0.083, a
factor of 5.5. The ``top_percent`` cut-off was therefore applied to a
distribution the reader never saw, and two long-lived interests could rank in
one order while being displayed in the other.

These tests pin the property rather than the number: whatever the setting says,
the two paths must agree.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.config import settings
from src.domains.interests.models import InterestStatus, UserInterest
from src.domains.interests.repository import InterestRepository

pytestmark = pytest.mark.unit


def _interest(*, positives: int, days_since_mention: int, now: datetime) -> UserInterest:
    interest = UserInterest(
        user_id=uuid.uuid4(),
        topic="architecture logicielle",
        category="technology",
        positive_signals=positives,
        negative_signals=0,
        status=InterestStatus.ACTIVE.value,
        last_mentioned_at=now - timedelta(days=days_since_mention),
    )
    interest.id = uuid.uuid4()
    interest.last_notified_at = None
    return interest


class TestTheDisplayedWeightIsTheAppliedWeight:
    async def test_the_ranking_uses_the_configured_decay_rate(self) -> None:
        """The selection path must not fall back to the signature default.

        Read through the setting on BOTH sides so the test states the property
        (the two agree) rather than freezing a number a config change would
        make wrong — the very trap this closes.
        """
        now = datetime(2026, 8, 3, 12, 0, tzinfo=UTC)
        interest = _interest(positives=8, days_since_mention=90, now=now)
        repo = InterestRepository(AsyncMock())

        displayed = repo.calculate_effective_weight(
            interest,
            decay_rate_per_day=settings.interest_decay_rate_per_day,
            now=now,
        )

        with patch.object(
            InterestRepository, "get_active_for_user", AsyncMock(return_value=[interest])
        ):
            ranked = await repo.get_top_weighted_interests(
                user_id=interest.user_id, top_percent=1.0, min_count=1, now=now
            )

        assert ranked, "the fixture must be eligible, otherwise nothing is proven"
        assert ranked[0][1] == pytest.approx(displayed)

    async def test_it_still_agrees_when_the_setting_is_changed(self) -> None:
        """A different configured rate must move BOTH sides together.

        The previous test would pass by coincidence if the setting happened to
        equal the hardcoded default; this one cannot.
        """
        now = datetime(2026, 8, 3, 12, 0, tzinfo=UTC)
        interest = _interest(positives=8, days_since_mention=60, now=now)
        repo = InterestRepository(AsyncMock())
        # Deliberately neither the historical default (0.01) nor the configured
        # value, so agreement cannot come from either.
        rate = 0.002

        with patch.object(settings, "interest_decay_rate_per_day", rate):
            displayed = repo.calculate_effective_weight(
                interest, decay_rate_per_day=settings.interest_decay_rate_per_day, now=now
            )
            with patch.object(
                InterestRepository, "get_active_for_user", AsyncMock(return_value=[interest])
            ):
                ranked = await repo.get_top_weighted_interests(
                    user_id=interest.user_id, top_percent=1.0, min_count=1, now=now
                )

        assert ranked[0][1] == pytest.approx(displayed)
        # And the rate really is in play — a no-op patch would prove nothing.
        assert displayed == pytest.approx((2 + 8) / (2 + 8 + 1) * (1 - 60 * rate))

    async def test_a_caller_may_still_override_the_rate_explicitly(self) -> None:
        """The parameter stays a parameter — the cleanup job passes its own."""
        now = datetime(2026, 8, 3, 12, 0, tzinfo=UTC)
        interest = _interest(positives=1, days_since_mention=10, now=now)
        repo = InterestRepository(AsyncMock())

        with patch.object(
            InterestRepository, "get_active_for_user", AsyncMock(return_value=[interest])
        ):
            ranked = await repo.get_top_weighted_interests(
                user_id=interest.user_id,
                top_percent=1.0,
                min_count=1,
                decay_rate_per_day=0.05,
                now=now,
            )

        assert ranked[0][1] == pytest.approx(
            repo.calculate_effective_weight(interest, decay_rate_per_day=0.05, now=now)
        )

    def test_omitting_the_rate_falls_back_to_the_setting_not_to_a_literal(self) -> None:
        """The root cause: a signature default that disagreed with the config.

        Every call site passes the setting today, so the literal is unreachable
        — but an unreachable trap is still a trap, and this defect was created
        exactly by a caller omitting the argument. The fallback is now the
        setting itself, so omission can no longer mean "some other rate".
        """
        now = datetime(2026, 8, 3, 12, 0, tzinfo=UTC)
        interest = _interest(positives=8, days_since_mention=90, now=now)
        repo = InterestRepository(MagicMock())

        with patch.object(settings, "interest_decay_rate_per_day", 0.002):
            implicit = repo.calculate_effective_weight(interest, now=now)
            explicit = repo.calculate_effective_weight(interest, decay_rate_per_day=0.002, now=now)

        assert implicit == pytest.approx(explicit)

    def test_the_decay_floor_is_never_crossed(self) -> None:
        """A very old interest keeps a tenth of its base, never zero.

        The floor is what stops an interest from becoming unrankable; pinned
        here because the two rates reach it at different ages (90 days at 0.01,
        180 at 0.005) and that difference was invisible until now.
        """
        now = datetime(2026, 8, 3, 12, 0, tzinfo=UTC)
        ancient = _interest(positives=3, days_since_mention=5000, now=now)
        repo = InterestRepository(AsyncMock())

        weight = repo.calculate_effective_weight(ancient, decay_rate_per_day=0.01, now=now)

        assert weight == pytest.approx(repo.calculate_weight(ancient) * 0.1)


class TestTheCoefficientsArePublishable:
    """Explaining the weight requires reading what is actually applied.

    ADR-184's doctrine: whatever a system enforces, it publishes. The reader
    cannot be told "your interest fades by X% a day" from a number the code
    only half uses.
    """

    def test_the_prior_and_the_rate_all_come_from_settings(self) -> None:
        assert settings.interest_prior_alpha > 0
        assert settings.interest_prior_beta > 0
        assert 0 < settings.interest_decay_rate_per_day <= 0.1

    def test_the_base_weight_is_the_documented_beta_mean(self) -> None:
        now = datetime(2026, 8, 3, 12, 0, tzinfo=UTC)
        interest = _interest(positives=4, days_since_mention=0, now=now)
        interest.negative_signals = 2
        repo = InterestRepository(MagicMock())

        expected = (settings.interest_prior_alpha + 4) / (
            settings.interest_prior_alpha + 4 + settings.interest_prior_beta + 2
        )

        assert repo.calculate_weight(interest) == pytest.approx(expected)
