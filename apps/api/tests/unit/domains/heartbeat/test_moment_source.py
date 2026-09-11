"""Serving a moment through the heartbeat, and what it is allowed to bypass.

A moment is not a source the aggregator fetches: it is a REASON the decision is
being taken now, exactly like a push wake (ADR-261). It is placed on the context
after the parallel gather, rendered as a FRESH section at the top of the prompt,
and stamped on the audit row as ``trigger = "moment"``.

The bypass is the part worth pinning, and it is narrow on purpose.

``check_eligibility`` applies the rhythm deferral (ADR-214 §11.2) and — from lot
3 — the in-meeting guard. Both DEFER: they answer « not now, later today ». For
a tick that is right, because a tick comes back. For a moment it is fatal: a
moment carries a short validity window, so deferring it by two hours expires it
unserved. A tick deferred returns; a moment deferred dies.

So a moment answers on the account's flag alone — and nothing else is bypassed.
The window, the daily quota, the global cooldown, the cross-type cooldown and
the activity cooldown all live in ``EligibilityChecker``, which the sweep runs
in full. A moment changes WHEN a decision is taken, never how many may fire.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.domains.heartbeat.proactive_task import HeartbeatProactiveTask
from src.domains.heartbeat.schemas import HeartbeatContext
from src.domains.moments.schemas import ServedMoment

pytestmark = pytest.mark.unit

_DEFER = "src.domains.heartbeat.proactive_task.should_defer_tick_for_rhythm"
_BUSY = "src.domains.heartbeat.proactive_task.should_defer_for_meeting"


def _moment(**overrides: object) -> ServedMoment:
    fields: dict[str, object] = {
        "kind": "event_followup",
        "headline": "A meeting on their calendar has just ended.",
        "lines": ('Meeting: "Point budget"', "Ended at: 15:00 (their local time)"),
    }
    fields.update(overrides)
    return ServedMoment(**fields)  # type: ignore[arg-type]


class TestWhatAMomentBypasses:
    async def test_a_moment_is_never_deferred_by_the_rhythm(self) -> None:
        """Deferring a moment expires it: it would never be served at all."""
        task = HeartbeatProactiveTask(moment=_moment())

        with (
            patch(_DEFER, new=AsyncMock(return_value=True)) as defer,
            patch(_BUSY, new=AsyncMock(return_value=True)) as busy,
        ):
            eligible = await task.check_eligibility(
                uuid4(), {"heartbeat_enabled": True}, None  # type: ignore[arg-type]
            )

        assert eligible is True
        defer.assert_not_awaited()
        # The in-meeting guard defers too, so it is bypassed for the same
        # reason: a debrief speaks exactly when a meeting has just ended.
        busy.assert_not_awaited()

    async def test_a_tick_is_still_deferred_by_the_rhythm(self) -> None:
        """The bypass is the moment's, not everyone's."""
        task = HeartbeatProactiveTask()

        with (
            patch(_DEFER, new=AsyncMock(return_value=True)),
            patch(_BUSY, new=AsyncMock(return_value=False)),
        ):
            eligible = await task.check_eligibility(
                uuid4(), {"heartbeat_enabled": True}, None  # type: ignore[arg-type]
            )

        assert eligible is False

    async def test_a_moment_still_obeys_the_account_flag(self) -> None:
        """Someone who switched proactivity off is not served a moment."""
        task = HeartbeatProactiveTask(moment=_moment())

        eligible = await task.check_eligibility(
            uuid4(), {"heartbeat_enabled": False}, None  # type: ignore[arg-type]
        )

        assert eligible is False


class TestTheAuditSaysWhatWokeIt:
    def test_a_moment_run_is_stamped_as_such(self) -> None:
        assert HeartbeatProactiveTask(moment=_moment())._trigger() == "moment"

    def test_a_plain_tick_is_still_a_tick(self) -> None:
        assert HeartbeatProactiveTask()._trigger() == "tick"


class TestThePromptSeesIt:
    def test_the_moment_makes_the_context_worth_a_decision(self) -> None:
        """Without this the aggregator's « nothing to say » short-circuit would
        drop the very reason the sweep woke up."""
        context = HeartbeatContext()
        assert context.has_meaningful_context() is False

        context.moment = _moment()
        assert context.has_meaningful_context() is True

    def test_the_fresh_section_leads_with_what_became_true(self) -> None:
        context = HeartbeatContext()
        context.moment = _moment()

        rendered = context.to_prompt_context()

        assert "FRESH" in rendered
        assert "A meeting on their calendar has just ended." in rendered
        assert "Point budget" in rendered

    def test_no_moment_renders_no_section(self) -> None:
        context = HeartbeatContext()
        context.calendar_events = [{"summary": "x", "start": "1", "end": "2"}]

        assert "FRESH" not in context.to_prompt_context()


class TestTheLabelIsDeclared:
    def test_the_decision_can_say_it_used_the_moment(self) -> None:
        """Without the label the anti-repeat window is blind to it and the
        per-source statistics under-count."""
        from src.domains.heartbeat.schemas import HeartbeatDecision

        decision = HeartbeatDecision(
            action="notify",
            reason="the meeting just ended",
            message_draft="Alors, ce point budget ?",
            priority="medium",
            sources_used=["ANTICIPATED_MOMENT"],
        )

        assert decision.sources_used == ["ANTICIPATED_MOMENT"]


class TestTheInMeetingGuard:
    """A tick stands aside while a meeting is in progress (lot 3).

    It runs BEFORE the rhythm deferral and before any model call: someone in a
    meeting is the one person the activity cooldown reads as MOST available,
    because they are precisely not typing.
    """

    async def test_a_tick_stands_aside_during_a_meeting(self) -> None:
        with (
            patch(_BUSY, new=AsyncMock(return_value=True)),
            patch(_DEFER, new=AsyncMock(return_value=False)) as rhythm,
        ):
            eligible = await HeartbeatProactiveTask().check_eligibility(
                uuid4(), {"heartbeat_enabled": True}, None  # type: ignore[arg-type]
            )

        assert eligible is False
        # Short-circuits: the rhythm is never even consulted.
        rhythm.assert_not_awaited()

    async def test_a_free_tick_goes_on_to_the_rhythm(self) -> None:
        with (
            patch(_BUSY, new=AsyncMock(return_value=False)),
            patch(_DEFER, new=AsyncMock(return_value=False)) as rhythm,
        ):
            eligible = await HeartbeatProactiveTask().check_eligibility(
                uuid4(), {"heartbeat_enabled": True}, None  # type: ignore[arg-type]
            )

        assert eligible is True
        rhythm.assert_awaited_once()
