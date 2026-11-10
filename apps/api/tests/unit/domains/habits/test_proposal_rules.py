"""Proposal rules (ADR-375): what LIA offers from what it observed, decided by code.

Pure rules over plain observations; fixtures are generic. An observation LIA
could not make (a routine whose reads are unknown, a feedback source not
installed) HOLDS the kind it feeds — it never reads as « nothing to propose ».
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from src.domains.habits.models import ProposalKind
from src.domains.habits.needs import Need
from src.domains.habits.proposal_rules import (
    ProactiveFeedback,
    ProposalThresholds,
    RoutineRun,
    RoutineView,
    UsageObservations,
    evaluate_proposals,
)

pytestmark = pytest.mark.unit

TODAY = date(2026, 11, 6)  # a Friday
EVERY_DAY = frozenset(range(7))


def _thresholds(**over: object) -> ProposalThresholds:
    values: dict[str, object] = {
        "recurrence_window_days": 35,
        "habits_proposal_routine_gap_hours": 2.0,
        "habits_proposal_manual_min_runs": 3,
        "habits_proposal_manual_min_days": 3,
        "habits_proposal_failure_streak": 3,
        "habits_proposal_window_min_days": 5,
        "habits_proposal_window_min_cells": 8,
        "habits_proposal_window_min_share": 0.25,
        "habits_proposal_window_max_extension_hours": 3,
        "habits_proposal_silent_min_notifications": 20,
        "habits_proposal_connector_min_days": 3,
        "habits_proposal_mute_after_refusals": 3,
    }
    values.update(over)
    return ProposalThresholds.from_settings(SimpleNamespace(**values))


def _need(domain: str = "event", **over: object) -> Need:
    base = Need(
        domain=domain,
        cadence="daily",
        weekday=None,
        usual_hour=10.6,
        prefill_hour=10.25,
        part_of_day="morning",
        distinct_days=14,
        active_days=25,
        occurrences=20,
        at_automation_bar=True,
        last_day=TODAY - timedelta(days=1),
    )
    return replace(base, **over)  # type: ignore[arg-type]


def _routine(**over: object) -> RoutineView:
    base = RoutineView(
        id="r-1",
        title="Morning",
        enabled=True,
        status="active",
        trigger_kind="time",
        times=(7.75,),
        fires_on=EVERY_DAY,
        consecutive_failures=0,
        runs=(),
        read_domains=frozenset({"event", "email"}),
        fixed_times=True,
    )
    return replace(base, **over)  # type: ignore[arg-type]


def _obs(**over: object) -> UsageObservations:
    base = UsageObservations(
        today=TODAY,
        needs=(),
        need_status={},
        asked_days={},
        routines=(),
        presence={},
        heartbeat_enabled=False,
        heartbeat_window=(8, 22),
        proactive=ProactiveFeedback(sent=0, reacted=0),
        connector_categories=frozenset({"calendar", "email", "tasks", "contacts"}),
        refusals={},
        ledger_readable=True,
    )
    return replace(base, **over)  # type: ignore[arg-type]


def _kinds(result: object) -> list[tuple[str, str]]:
    return [(c.kind.value, c.key) for c in result.candidates]  # type: ignore[attr-defined]


class TestAutomateNeed:
    def test_an_unserved_need_at_the_bar_is_proposed_with_its_schedule(self) -> None:
        result = evaluate_proposals(_obs(needs=(_need(),)), _thresholds())
        assert _kinds(result) == [("automate_need", "event")]
        payload = result.candidates[0].payload
        assert payload["domain"] == "event"
        assert (payload["cadence"], payload["weekday"]) == ("daily", None)
        assert (payload["hour"], payload["minute"]) == (10, 15)
        assert (payload["distinct_days"], payload["active_days"]) == (14, 25)
        assert payload["existing_routine"] is None

    def test_a_need_whose_connector_is_not_active_is_connected_first(self) -> None:
        """A routine the person cannot run is a promise LIA would break every
        morning (ADR-184, 2026-10-14): the need waits for its connector and is
        proposed for connecting instead; the night it is connected, it is
        proposed for automating."""
        disconnected = _obs(
            needs=(_need("email"),),
            asked_days={"email": 14},
            connector_categories=frozenset({"calendar"}),
        )
        assert _kinds(evaluate_proposals(disconnected, _thresholds())) == [
            ("connect_source", "email")
        ]
        connected = replace(disconnected, connector_categories=frozenset({"calendar", "email"}))
        assert _kinds(evaluate_proposals(connected, _thresholds())) == [("automate_need", "email")]

    def test_a_need_no_connector_serves_is_automated_as_is(self) -> None:
        result = evaluate_proposals(
            _obs(needs=(_need("weather"),), connector_categories=frozenset()), _thresholds()
        )
        assert _kinds(result) == [("automate_need", "weather")]

    def test_below_the_bar_nothing_is_proposed(self) -> None:
        result = evaluate_proposals(_obs(needs=(_need(at_automation_bar=False),)), _thresholds())
        assert _kinds(result) == []

    def test_a_domain_that_needs_a_subject_is_never_proposed(self) -> None:
        result = evaluate_proposals(_obs(needs=(_need("web_search"),)), _thresholds())
        assert _kinds(result) == []

    @pytest.mark.parametrize("status", ["paused", "blocked"])
    def test_a_need_the_person_paused_or_blocked_is_left_alone(self, status: str) -> None:
        result = evaluate_proposals(
            _obs(needs=(_need(),), need_status={"event": status}), _thresholds()
        )
        assert _kinds(result) == []

    def test_a_routine_already_reading_it_near_that_time_serves_it(self) -> None:
        routine = _routine(times=(9.0,))
        result = evaluate_proposals(_obs(needs=(_need(),), routines=(routine,)), _thresholds())
        assert _kinds(result) == []

    def test_a_routine_reading_it_far_from_that_time_is_cited(self) -> None:
        result = evaluate_proposals(_obs(needs=(_need(),), routines=(_routine(),)), _thresholds())
        assert _kinds(result) == [("automate_need", "event")]
        assert result.candidates[0].payload["existing_routine"] == {
            "id": "r-1",
            "title": "Morning",
            "hour": 7,
            "minute": 45,
        }

    def test_the_cited_routine_never_depends_on_the_order_rows_arrive_in(self) -> None:
        """Rows come from an unordered query: citing the first reader would
        flip the payload from night to night and « refresh » the proposal
        forever. The nearest reader is cited, the id breaking a tie."""
        early = _routine(id="r-2", title="Early", times=(6.0,))
        nearer = _routine(id="r-3", title="Nearer", times=(7.5,))
        twin = _routine(id="r-1", title="Twin", times=(7.5,))
        cited = {
            evaluate_proposals(_obs(needs=(_need(),), routines=order), _thresholds())
            .candidates[0]
            .payload["existing_routine"]["id"]
            for order in ((early, nearer, twin), (twin, nearer, early), (nearer, early, twin))
        }
        assert cited == {"r-1"}

    def test_unknown_routine_reads_hold_automation(self) -> None:
        """Review focus 1: a routine whose reads are unknown may serve it."""
        result = evaluate_proposals(
            _obs(needs=(_need(),), routines=(_routine(read_domains=None),)), _thresholds()
        )
        assert _kinds(result) == []
        assert ProposalKind.AUTOMATE_NEED in result.held

    def test_a_disabled_routine_serves_nothing(self) -> None:
        result = evaluate_proposals(
            _obs(needs=(_need(),), routines=(_routine(enabled=False, times=(10.0,)),)),
            _thresholds(),
        )
        assert _kinds(result) == [("automate_need", "event")]

    def test_a_weekly_need_is_served_only_on_its_weekday(self) -> None:
        sunday = _need(cadence="weekly", weekday=6, prefill_hour=19.0)
        weekdays = _routine(times=(19.0,), fires_on=frozenset(range(5)))
        result = evaluate_proposals(_obs(needs=(sunday,), routines=(weekdays,)), _thresholds())
        assert _kinds(result) == [("automate_need", "event")]
        assert (
            result.candidates[0].payload["cadence"],
            result.candidates[0].payload["weekday"],
        ) == ("weekly", 6)

    def test_an_unreadable_ledger_holds_what_needs_feed(self) -> None:
        result = evaluate_proposals(_obs(ledger_readable=False), _thresholds())
        assert {ProposalKind.AUTOMATE_NEED, ProposalKind.CONNECT_SOURCE} <= result.held


class TestShiftRoutine:
    def _manual(self, *days_hours: tuple[int, float]) -> tuple[RoutineRun, ...]:
        return tuple(
            RoutineRun(
                day=TODAY - timedelta(days=d),
                hour=h,
                manual=True,
                outcome="success",
                run_id=f"m{d}",
            )
            for d, h in days_hours
        )

    def test_three_manual_runs_on_three_days_far_from_its_time_move_it(self) -> None:
        routine = _routine(times=(6.5,), runs=self._manual((1, 9.6), (3, 9.8), (6, 9.7)))
        result = evaluate_proposals(_obs(routines=(routine,)), _thresholds())
        assert _kinds(result) == [("shift_routine", "r-1")]
        payload = result.candidates[0].payload
        assert (payload["from_hour"], payload["from_minute"]) == (6, 30)
        assert (payload["hour"], payload["minute"]) == (9, 30)
        assert (payload["manual_runs"], payload["manual_days"]) == (3, 3)

    def test_manual_runs_either_side_of_midnight_are_read_across_it(self) -> None:
        routine = _routine(times=(19.0,), runs=self._manual((1, 23.5), (3, 0.5), (6, 0.75)))
        result = evaluate_proposals(_obs(routines=(routine,)), _thresholds())
        assert _kinds(result) == [("shift_routine", "r-1")]
        payload = result.candidates[0].payload
        assert (payload["hour"], payload["minute"]) == (0, 30)

    def test_manual_runs_near_its_time_are_rehearsals(self) -> None:
        routine = _routine(times=(9.0,), runs=self._manual((1, 9.6), (3, 9.8), (6, 9.7)))
        assert _kinds(evaluate_proposals(_obs(routines=(routine,)), _thresholds())) == []

    def test_three_runs_on_two_days_are_not_a_habit(self) -> None:
        routine = _routine(times=(6.5,), runs=self._manual((1, 9.6), (1, 10.8), (6, 9.7)))
        assert _kinds(evaluate_proposals(_obs(routines=(routine,)), _thresholds())) == []

    def test_a_condition_routine_has_no_time_to_move(self) -> None:
        routine = _routine(
            trigger_kind="condition", times=(), runs=self._manual((1, 9.6), (3, 9.8), (6, 9.7))
        )
        assert _kinds(evaluate_proposals(_obs(routines=(routine,)), _thresholds())) == []

    def test_a_routine_on_a_step_has_no_single_time_to_move(self) -> None:
        """Every 30 minutes from 06:00 to 08:00: moving « the » time is not an
        edit the person could recognise, so it is never proposed."""
        routine = _routine(
            times=(6.0, 6.5, 7.0, 7.5, 8.0),
            fixed_times=False,
            runs=self._manual((1, 9.6), (3, 9.8), (6, 9.7)),
        )
        assert _kinds(evaluate_proposals(_obs(routines=(routine,)), _thresholds())) == []


class TestFixRoutine:
    def test_a_routine_the_system_disabled_is_proposed(self) -> None:
        routine = _routine(enabled=False, status="error", consecutive_failures=5)
        result = evaluate_proposals(_obs(routines=(routine,)), _thresholds())
        assert _kinds(result) == [("fix_routine", "r-1")]
        assert result.candidates[0].payload == {
            "routine_id": "r-1",
            "routine_title": "Morning",
            "failures": 5,
            "disabled": True,
        }

    def test_a_failing_streak_is_proposed_before_the_system_gives_up(self) -> None:
        result = evaluate_proposals(
            _obs(routines=(_routine(consecutive_failures=3),)), _thresholds()
        )
        assert _kinds(result) == [("fix_routine", "r-1")]

    def test_two_failures_are_not_yet_a_problem(self) -> None:
        result = evaluate_proposals(
            _obs(routines=(_routine(consecutive_failures=2),)), _thresholds()
        )
        assert _kinds(result) == []


def _presence(hours: set[int], days: int = 28) -> dict[date, frozenset[int]]:
    return {TODAY - timedelta(days=k): frozenset(hours) for k in range(1, days + 1)}


class TestExtendNotificationWindow:
    def test_window_extension_wraps_midnight_contiguously(self) -> None:
        result = evaluate_proposals(
            _obs(heartbeat_enabled=True, presence=_presence({9, 14, 22, 23, 0})), _thresholds()
        )
        assert _kinds(result) == [("extend_notification_window", "heartbeat")]
        payload = result.candidates[0].payload
        assert (payload["start"], payload["end"]) == (8, 22)
        assert (payload["new_start"], payload["new_end"]) == (8, 1)

    def test_window_isolated_night_presence_no_jump(self) -> None:
        result = evaluate_proposals(
            _obs(heartbeat_enabled=True, presence=_presence({9, 14, 3, 4})), _thresholds()
        )
        assert _kinds(result) == []

    def test_an_early_morning_extends_the_start(self) -> None:
        result = evaluate_proposals(
            _obs(heartbeat_enabled=True, presence=_presence({6, 7, 9, 14})), _thresholds()
        )
        payload = result.candidates[0].payload
        assert (payload["new_start"], payload["new_end"]) == (6, 22)

    def test_the_extension_is_bounded_on_each_side(self) -> None:
        result = evaluate_proposals(
            _obs(heartbeat_enabled=True, presence=_presence({22, 23, 0, 1, 2, 3, 9})),
            _thresholds(),
        )
        assert result.candidates[0].payload["new_end"] == 1

    @pytest.mark.parametrize(
        ("window", "hours", "expected"),
        [
            # the START stops one hour short of the new end
            ((4, 23), {23, 0, 1, 2, 3, 9}, (3, 2)),
            # the END stops one hour short of the start
            ((2, 23), {23, 0, 1, 9}, (2, 1)),
        ],
    )
    def test_the_window_never_closes_on_itself(
        self, window: tuple[int, int], hours: set[int], expected: tuple[int, int]
    ) -> None:
        """start == end is an EMPTY window for the heartbeat: never produced."""
        result = evaluate_proposals(
            _obs(heartbeat_enabled=True, heartbeat_window=window, presence=_presence(hours)),
            _thresholds(),
        )
        payload = result.candidates[0].payload
        assert (payload["new_start"], payload["new_end"]) == expected

    def test_too_few_days_outside_are_not_a_pattern(self) -> None:
        presence = _presence({9, 14}) | {
            TODAY - timedelta(days=k): frozenset({9, 22, 23}) for k in range(1, 5)
        }
        result = evaluate_proposals(_obs(heartbeat_enabled=True, presence=presence), _thresholds())
        assert _kinds(result) == []

    def test_notifications_switched_off_have_no_window_to_extend(self) -> None:
        result = evaluate_proposals(
            _obs(heartbeat_enabled=False, presence=_presence({9, 22, 23, 0})), _thresholds()
        )
        assert _kinds(result) == []


class TestReviewNotifications:
    def test_twenty_silent_notifications_raise_the_question(self) -> None:
        result = evaluate_proposals(
            _obs(heartbeat_enabled=True, proactive=ProactiveFeedback(sent=20, reacted=0)),
            _thresholds(),
        )
        assert _kinds(result) == [("review_notifications", "heartbeat")]
        assert result.candidates[0].payload == {"sent": 20, "window_days": 35}

    def test_one_reaction_is_enough_to_stay_quiet(self) -> None:
        result = evaluate_proposals(
            _obs(heartbeat_enabled=True, proactive=ProactiveFeedback(sent=40, reacted=1)),
            _thresholds(),
        )
        assert _kinds(result) == []

    def test_an_unknown_feedback_source_holds_the_question(self) -> None:
        result = evaluate_proposals(_obs(heartbeat_enabled=True, proactive=None), _thresholds())
        assert _kinds(result) == []
        assert ProposalKind.REVIEW_NOTIFICATIONS in result.held


class TestConnectSource:
    def test_a_domain_asked_without_its_connector_is_proposed(self) -> None:
        result = evaluate_proposals(
            _obs(asked_days={"email": 3}, connector_categories=frozenset({"calendar"})),
            _thresholds(),
        )
        assert _kinds(result) == [("connect_source", "email")]
        assert result.candidates[0].payload == {"category": "email", "domain": "email", "days": 3}

    def test_a_connected_category_is_left_alone(self) -> None:
        result = evaluate_proposals(_obs(asked_days={"email": 9}), _thresholds())
        assert _kinds(result) == []

    def test_weather_is_never_a_connector_proposal(self) -> None:
        result = evaluate_proposals(
            _obs(asked_days={"weather": 9}, connector_categories=frozenset()), _thresholds()
        )
        assert _kinds(result) == []

    def test_a_blocked_need_silences_its_connector_proposal(self) -> None:
        result = evaluate_proposals(
            _obs(
                asked_days={"email": 9},
                connector_categories=frozenset(),
                need_status={"email": "blocked"},
            ),
            _thresholds(),
        )
        assert _kinds(result) == []


def test_kind_muted_after_three_refusals() -> None:
    """Learning from decisions: three refusals of a kind silence that kind."""
    result = evaluate_proposals(
        _obs(needs=(_need(),), refusals={ProposalKind.AUTOMATE_NEED: 3}), _thresholds()
    )
    assert _kinds(result) == []
    assert ProposalKind.AUTOMATE_NEED not in result.held


class TestEveryPayloadIsReadBackByItsKind:
    """ADR-375: the rules WRITE the facts the API publishes and the action
    reads back — one model per kind, so a field a rule stops writing fails
    here rather than in the middle of an act."""

    def test_every_kind_declares_its_facts(self) -> None:
        from src.domains.habits.proposal_facts import FACTS_BY_KIND

        assert set(FACTS_BY_KIND) == set(ProposalKind)

    def test_every_candidate_validates_as_its_kind(self) -> None:
        from src.domains.habits.proposal_facts import FACTS_BY_KIND

        manual = TestShiftRoutine()._manual((1, 9.6), (3, 9.8), (6, 9.7))
        observations = _obs(
            needs=(_need("event"), _need("email")),
            asked_days={"email": 9, "file": 4},
            routines=(
                _routine(id="r-1", times=(6.5,), runs=manual),
                _routine(id="r-2", title="Broken", status="error", enabled=False),
            ),
            connector_categories=frozenset({"calendar", "email"}),
            heartbeat_enabled=True,
            presence={TODAY - timedelta(days=k): frozenset({7, 23}) for k in range(1, 9)},
            proactive=ProactiveFeedback(sent=25, reacted=0),
        )
        candidates = evaluate_proposals(observations, _thresholds()).candidates
        assert {candidate.kind for candidate in candidates} == set(ProposalKind)
        for candidate in candidates:
            FACTS_BY_KIND[candidate.kind].model_validate(candidate.payload)
