"""The model-call tail bench asks Prometheus the questions it claims (lot 26)."""

from __future__ import annotations

import pytest

from scripts.agents.measure_model_call_tail import queries, readings

pytestmark = pytest.mark.unit


def test_every_question_is_asked_over_the_window() -> None:
    asked = queries("3d")

    assert all("[3d]" in expression for expression in asked.values())
    assert 'le="60.0"' in asked["llm_over_60s_by_node"]
    assert 'le="120.0"' in asked["sse_over_120s"]


def test_only_series_above_the_noise_are_kept_with_their_labels() -> None:
    payload = {
        "data": {
            "result": [
                {"metric": {"node_name": "react_call_model"}, "value": [0, "14.0"]},
                {"metric": {"node_name": "router"}, "value": [0, "0.2"]},
            ]
        }
    }

    assert readings(payload) == [{"labels": {"node_name": "react_call_model"}, "value": 14.0}]
    assert readings({}) == []


def test_the_gap_between_answer_tokens_is_asked_too() -> None:
    """The next measure of the stalled stream (MODEL_OUTPUT_HEALTH.md § 2)."""
    asked = queries("7d")

    assert "sse_token_gap_seconds_count" in asked["token_gaps"]
    assert 'le="10.0"' in asked["token_gaps_over_10s"]
    assert 'le="30.0"' in asked["token_gaps_over_30s"]
    assert "sse_token_gap_seconds_bucket" in asked["token_gap_buckets"]
