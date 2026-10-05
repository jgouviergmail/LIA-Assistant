"""A first useful result is neither a status nor an empty preview."""

import pytest

from src.domains.agents.services.streaming.journey_timing import JourneyTiming

pytestmark = pytest.mark.unit


def test_hidden_legacy_preview_never_counts_as_a_useful_result() -> None:
    timing = JourneyTiming(started=10.0)
    timing.observe("status", "Searching", {}, now=11)
    timing.observe("result_preview", "", {"collection": {"items": []}}, now=12)
    timing.observe(
        "result_preview", "", {"collection": {"items": [{"verdict": "non_match"}]}}, now=13
    )
    assert timing.first_useful_ms is None
    timing.observe(
        "result_preview", "", {"collection": {"items": [{"verdict": "unknown"}]}}, now=14
    )
    assert timing.first_useful_ms is None
    assert timing.first_preview_ms is None
    timing.observe("token", " ", {}, now=15)
    assert timing.first_token_ms is None
    timing.observe("token", "Answer", {}, now=16)
    timing.observe("token", "continues", {}, now=17)
    assert timing.first_useful_ms == 6000
    assert timing.first_preview_ms is None
    assert timing.first_token_ms == 6000


@pytest.mark.parametrize(
    "metadata",
    [
        {},
        {"collection": None},
        {"collection": {"items": None}},
        {"collection": {"items": [None, "bad", {"verdict": "invented"}]}},
    ],
)
def test_malformed_optional_preview_cannot_fail_a_turn(metadata: dict[str, object]) -> None:
    timing = JourneyTiming(started=0)
    timing.observe("result_preview", "", metadata, now=1)
    assert timing.first_useful_ms is None


def test_text_alone_counts_and_independent_turns_start_fresh() -> None:
    first = JourneyTiming(started=50)
    first.observe("token", "Done", {}, now=52)
    second = JourneyTiming(started=100)
    assert first.first_useful_ms == 2000
    assert first.first_preview_ms is None
    assert second.first_useful_ms is None


def test_final_replacement_without_streamed_tokens_is_still_a_useful_result() -> None:
    timing = JourneyTiming(started=10)
    timing.observe("content_replacement", "Final answer", {}, now=12)
    assert timing.first_useful_ms == 2000
    assert timing.first_token_ms is None
