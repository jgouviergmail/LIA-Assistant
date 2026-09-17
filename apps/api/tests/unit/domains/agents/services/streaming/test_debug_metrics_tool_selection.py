"""The debug panel's tool-selection section reads the PLANNER's scores only.

Since ADR-293 ``tool_selection_result`` can carry the global relevance order
alone — an actionable turn whose detected domains own no tool, or one the
router placed in no domain. The builder indexed ``top_score`` and
``all_scores`` unconditionally, the ``KeyError`` was caught one level up, and
the WHOLE debug panel of the turn vanished (no ``debug_metrics`` chunk), not
merely its tool section.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.domains.agents.nodes.router_tool_scoring import GLOBAL_RANKING_KEY
from src.domains.agents.services.streaming.debug_metrics_builder import DebugMetricsBuilder

pytestmark = pytest.mark.unit


def _builder(cached_tool_scores: dict[str, Any] | None) -> DebugMetricsBuilder:
    return DebugMetricsBuilder(
        tracker=None,
        cached_filtered_catalogue=None,
        cached_tool_scores=cached_tool_scores,
        skill_name_resolver=lambda _state: None,
    )


def test_a_ranking_only_result_builds_no_section_and_raises_nothing() -> None:
    debug_metrics: dict[str, Any] = {}
    _builder({GLOBAL_RANKING_KEY: ["get_emails_tool", "get_events_tool"]})._build_tool_selection(
        debug_metrics, "run-1"
    )
    assert "tool_selection" not in debug_metrics


def test_the_planner_scores_build_the_section_as_before() -> None:
    debug_metrics: dict[str, Any] = {}
    _builder(
        {
            GLOBAL_RANKING_KEY: ["get_emails_tool"],
            "all_scores": {"get_emails_tool": 0.71},
            "selected_tools": [
                {"tool_name": "get_emails_tool", "score": 0.71, "confidence": "high"}
            ],
            "top_score": 0.71,
            "has_uncertainty": False,
        }
    )._build_tool_selection(debug_metrics, "run-1")
    section = debug_metrics["tool_selection"]
    assert section["top_score"] == 0.71
    assert section["all_scores"] == {"get_emails_tool": 0.71}
    assert section["selected_tools"][0]["tool_name"] == "get_emails_tool"
