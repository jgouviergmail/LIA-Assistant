"""A first useful result is answer text, never a status or an event the chat does not show."""

import pytest

from src.domains.agents.services.streaming.journey_timing import JourneyTiming

pytestmark = pytest.mark.unit


def test_a_status_or_an_unknown_event_never_counts_as_a_useful_result() -> None:
    timing = JourneyTiming(started=10.0)
    timing.observe("status", "Searching", {}, now=11)
    timing.observe("registry_update", "", {"items": [{"id": "e1"}]}, now=12)
    timing.observe("an_event_this_version_does_not_know", "text", {}, now=13)
    assert timing.first_useful_ms is None
    timing.observe("token", " ", {}, now=15)
    assert timing.first_token_ms is None
    timing.observe("token", "Answer", {}, now=16)
    timing.observe("token", "continues", {}, now=17)
    assert timing.first_useful_ms == 6000
    assert timing.first_token_ms == 6000
    assert set(timing.measurements()) == {"first_useful_ms", "first_answer_token_ms"}


def test_text_alone_counts_and_independent_turns_start_fresh() -> None:
    first = JourneyTiming(started=50)
    first.observe("token", "Done", {}, now=52)
    second = JourneyTiming(started=100)
    assert first.first_useful_ms == 2000
    assert second.first_useful_ms is None


def test_final_replacement_without_streamed_tokens_is_still_a_useful_result() -> None:
    timing = JourneyTiming(started=10)
    timing.observe("content_replacement", "Final answer", {}, now=12)
    assert timing.first_useful_ms == 2000
    assert timing.first_token_ms is None
