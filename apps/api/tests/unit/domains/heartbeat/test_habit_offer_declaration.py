"""The routine offer is DECLARED by the decision, never inferred from a label.

Measured 2026-09-11 (real tick on docker dev): the decision offered the
learned « email » routine (« Rituel du matin : ton point mail… ») but labelled
it ``UNREAD_EMAILS``; the bookkeeping required ``"HABITS" in sources_used`` and
charged nothing — the ≤ 1/day, 7-day cooldown and 2-ignored-offers budget of
ADR-214 depended on which enum label the model picked. Conversely the audit
row carried ``habit_offer_id`` whenever a candidate was merely PRESENT in the
context, so the offers inbox listed notifications that never offered anything.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domains.heartbeat.proactive_task import _bump_offered_habit, _offered_habit_id
from src.domains.heartbeat.schemas import HeartbeatDecision

pytestmark = pytest.mark.unit

HABIT_ID = str(uuid.uuid4())


def _target(*, habits: dict | None, habit_offered: bool, sources: list[str]) -> Any:
    decision = HeartbeatDecision(
        action="notify",
        reason="r",
        message_draft="draft",
        sources_used=sources,  # type: ignore[arg-type]
        habit_offered=habit_offered,
    )
    return SimpleNamespace(context=SimpleNamespace(habits=habits), decision=decision)


class TestSchema:
    def test_habit_offered_defaults_to_false(self) -> None:
        decision = HeartbeatDecision(action="skip", reason="nothing")
        assert decision.habit_offered is False

    def test_habit_offered_is_accepted(self) -> None:
        decision = HeartbeatDecision(
            action="notify", reason="r", message_draft="d", habit_offered=True
        )
        assert decision.habit_offered is True


class TestOfferedHabitId:
    _MISSED = {"missed_routine": {"habit_id": HABIT_ID, "signature": "email"}}

    def test_declared_offer_carries_the_id(self) -> None:
        target = _target(habits=self._MISSED, habit_offered=True, sources=["UNREAD_EMAILS"])
        assert _offered_habit_id(target) == HABIT_ID

    def test_the_label_alone_no_longer_stamps_but_is_counted(self) -> None:
        """A HABITS label with no declaration is what the rhythm context earns
        too (« you are usually active in the evening »): stamping it charged
        the 7-day cooldown for an offer never made. It is observed instead —
        the counter says how often a model labels without declaring."""
        from src.infrastructure.observability.metrics_habits import heartbeat_habit_offers_total

        before = heartbeat_habit_offers_total.labels(outcome="label_only")._value.get()
        target = _target(habits=self._MISSED, habit_offered=False, sources=["HABITS"])
        assert _offered_habit_id(target) is None
        assert heartbeat_habit_offers_total.labels(outcome="label_only")._value.get() == before + 1

    def test_every_candidate_outcome_is_counted(self) -> None:
        from src.infrastructure.observability.metrics_habits import heartbeat_habit_offers_total

        counts = {
            o: heartbeat_habit_offers_total.labels(outcome=o)._value.get()
            for o in ("declared", "label_only", "none")
        }
        _offered_habit_id(_target(habits=self._MISSED, habit_offered=True, sources=[]))
        _offered_habit_id(_target(habits=self._MISSED, habit_offered=False, sources=["HABITS"]))
        _offered_habit_id(_target(habits=self._MISSED, habit_offered=False, sources=[]))
        for outcome in ("declared", "label_only", "none"):
            assert (
                heartbeat_habit_offers_total.labels(outcome=outcome)._value.get()
                == counts[outcome] + 1
            ), outcome

    def test_a_candidate_merely_present_is_not_an_offer(self) -> None:
        target = _target(
            habits=self._MISSED, habit_offered=False, sources=["UPCOMING_CALENDAR_EVENTS"]
        )
        assert _offered_habit_id(target) is None

    def test_no_candidate_no_id_even_if_declared(self) -> None:
        target = _target(
            habits={"rhythm": {"weekday": ["08:00-10:00"]}}, habit_offered=True, sources=["HABITS"]
        )
        assert _offered_habit_id(target) is None
        assert _offered_habit_id(_target(habits=None, habit_offered=True, sources=[])) is None


class TestBumpReadsTheDeclaredOffer:
    async def test_a_declared_offer_is_stamped_whatever_the_label(self) -> None:
        habit = MagicMock()
        habit.user_id = uuid.uuid4()
        habit.payload = {"version": 1}
        habit.muted_until_reproof = False
        db = MagicMock()
        db.get = AsyncMock(return_value=habit)
        with (
            patch(
                "src.domains.heartbeat.habit_context._ledger_occurrence_days",
                AsyncMock(return_value=set()),
            ),
            patch("src.core.config.settings.habits_deviation_stop_after_ignored", 2),
        ):
            await _bump_offered_habit(
                db, habit.user_id, {"habit_offer_id": HABIT_ID, "sources_used": ["UNREAD_EMAILS"]}
            )
        assert len(habit.payload["offer_dates"]) == 1

    async def test_no_id_means_nothing_to_stamp(self) -> None:
        db = MagicMock()
        db.get = AsyncMock()
        await _bump_offered_habit(db, uuid.uuid4(), {"sources_used": ["HABITS"]})
        db.get.assert_not_awaited()
