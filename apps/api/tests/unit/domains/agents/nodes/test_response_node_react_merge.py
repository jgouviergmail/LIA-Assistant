"""Regression test: the ReAct answer must survive when Initiative also wrote
agent_results (ADR-070).

On the ReAct nominal path (react_finalize -> initiative -> response) the Initiative
node writes ``{turn}:initiative`` into agent_results *before* response_node runs. The
previous ``if not agent_results`` guard would then skip injecting the ReAct answer,
silently dropping the user-facing reply. ``_merge_react_synthesis_result`` merges the
ReAct entry without overwriting the Initiative entry.
"""

from __future__ import annotations

import pytest

from src.domains.agents.nodes.response_node import _merge_react_synthesis_result


@pytest.mark.unit
class TestMergeReactSynthesisResult:
    def test_injects_react_entry_into_empty_results(self):
        merged = _merge_react_synthesis_result(None, "the answer", 4, {"item_1": object()})
        assert merged["4:react_agent"]["data"]["react_synthesis"] == "the answer"

    def test_preserves_initiative_entry_and_adds_react(self):
        existing = {"4:initiative": {"status": "success", "data": {"x": 1}}}
        merged = _merge_react_synthesis_result(existing, "the answer", 4, {})
        assert "4:initiative" in merged  # not dropped
        assert "4:react_agent" in merged  # added
        assert merged["4:react_agent"]["data"]["react_synthesis"] == "the answer"

    def test_idempotent_on_react_key(self):
        existing = {"4:react_agent": {"data": {"react_synthesis": "first"}}}
        merged = _merge_react_synthesis_result(existing, "second", 4, {})
        assert merged["4:react_agent"]["data"]["react_synthesis"] == "first"

    def test_does_not_mutate_input(self):
        existing = {"4:initiative": {"status": "success"}}
        _merge_react_synthesis_result(existing, "answer", 4, {})
        assert "4:react_agent" not in existing
