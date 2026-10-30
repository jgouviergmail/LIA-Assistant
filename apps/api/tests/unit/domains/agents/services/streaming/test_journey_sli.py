"""The chat JOURNEY: from the person's request to the first answer token, preparation included.

``sse_time_to_first_token_seconds`` starts when the graph starts, so the wait
before it — the MCP preparation reached p95 19 s in production (spec 2026-10-21
§0ter) — was invisible, and 2.9 % of the turns a person waited for never
produced a first token at all, so no latency signal ever saw them. These tests
pin the two journey histograms: one observation at the first answer token, one
observation by outcome for a turn that ended without one, and nothing at all
for a run nobody waits for.
"""

from __future__ import annotations

import pytest
from prometheus_client import REGISTRY

from src.domains.agents.services.streaming.journey_timing import JourneyTiming
from src.domains.agents.services.streaming.latency_sli import awaited_by_a_person

pytestmark = pytest.mark.unit


def _first_token_count() -> float:
    return REGISTRY.get_sample_value("chat_journey_first_token_seconds_count") or 0.0


def _first_token_sum() -> float:
    return REGISTRY.get_sample_value("chat_journey_first_token_seconds_sum") or 0.0


def _unanswered(outcome: str) -> float:
    return (
        REGISTRY.get_sample_value("chat_journey_unanswered_seconds_count", {"outcome": outcome})
        or 0.0
    )


def test_first_answer_token_observed_once() -> None:
    count, total = _first_token_count(), _first_token_sum()
    journey = JourneyTiming(started=100.0)

    journey.observe("token", "Bon", {}, now=103.5)
    journey.observe("token", "jour", {}, now=104.0)
    journey.close("answered", now=106.0)

    assert _first_token_count() == count + 1
    assert _first_token_sum() == pytest.approx(total + 3.5)


def test_unanswered_cancel_observed_with_outcome() -> None:
    before = _unanswered("cancelled")
    before_error = _unanswered("error")
    first = _first_token_count()
    journey = JourneyTiming(started=10.0)

    journey.close("cancelled", now=22.0)
    journey.close("error", now=30.0)  # idempotent: the first outcome stands

    assert _unanswered("cancelled") == before + 1
    assert _unanswered("error") == before_error
    assert _first_token_count() == first


def test_answered_turn_is_not_unanswered() -> None:
    before = {o: _unanswered(o) for o in ("cancelled", "error", "interrupted")}
    journey = JourneyTiming(started=0.0)

    journey.observe("token", "ok", {}, now=1.0)
    journey.close("cancelled", now=2.0)  # a cut AFTER the answer started is still answered

    assert {o: _unanswered(o) for o in before} == before


def test_nothing_observed_when_nobody_waits() -> None:
    first = _first_token_count()
    before = _unanswered("error")

    with awaited_by_a_person(False):
        journey = JourneyTiming(started=0.0)
        journey.observe("token", "routine", {}, now=95.0)
        JourneyTiming(started=0.0).close("error", now=40.0)

    assert _first_token_count() == first
    assert _unanswered("error") == before


def test_progress_chunk_is_not_a_first_token() -> None:
    first = _first_token_count()
    journey = JourneyTiming(started=0.0)

    journey.observe("execution_step", "", {"step_type": "mcp_preparation"}, now=1.0)
    journey.observe("hitl_question_token", "Which one?", {}, now=2.0)

    assert _first_token_count() == first
    assert journey.first_token_ms is None


def test_a_turn_ending_on_a_question_is_interrupted() -> None:
    before = _unanswered("interrupted")
    journey = JourneyTiming(started=0.0)

    journey.observe("hitl_question_token", "Which one?", {}, now=2.0)
    journey.close_completed(now=3.0)

    assert _unanswered("interrupted") == before + 1
