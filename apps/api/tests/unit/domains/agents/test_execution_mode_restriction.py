"""A tool may declare which execution modes it belongs to (ADR-249).

The pipeline plans ahead: it emits an ExecutionPlan and the orchestrator runs
it. That is the wrong home for model-authored Python, which needs the loop that
can read a traceback and repair the script — so `run_python_tool` is ReAct-only
by owner arbitration.

A restriction that lives only in the tool's own refusal is a trap: the planner
would still SEE the tool, plan a step with it, and be told "no" at execution —
an invented dead end for the user. The manifest therefore carries the contract,
and every reader of the manifest list applies it.
"""

from __future__ import annotations

import inspect

import pytest

from src.core.constants import EXECUTION_MODE_PIPELINE, EXECUTION_MODE_REACT
from src.domains.agents.registry.catalogue import manifests_for_mode

pytestmark = [pytest.mark.unit]


class _Manifest:
    def __init__(self, name: str, modes: frozenset[str]) -> None:
        self.name = name
        self.execution_modes = modes


BOTH = _Manifest("search_emails_tool", frozenset({EXECUTION_MODE_PIPELINE, EXECUTION_MODE_REACT}))
REACT_ONLY = _Manifest("run_python_tool", frozenset({EXECUTION_MODE_REACT}))


class TestTheFilter:
    def test_pipeline_never_sees_a_react_only_tool(self) -> None:
        kept = manifests_for_mode([BOTH, REACT_ONLY], EXECUTION_MODE_PIPELINE)
        assert [m.name for m in kept] == ["search_emails_tool"]

    def test_react_sees_both(self) -> None:
        kept = manifests_for_mode([BOTH, REACT_ONLY], EXECUTION_MODE_REACT)
        assert [m.name for m in kept] == ["search_emails_tool", "run_python_tool"]

    def test_a_manifest_without_the_field_is_kept(self) -> None:
        """Older or third-party manifests must not vanish (fail open)."""

        class _Legacy:
            name = "legacy_tool"

        kept = manifests_for_mode([_Legacy()], EXECUTION_MODE_PIPELINE)
        assert [m.name for m in kept] == ["legacy_tool"]


class TestEveryReaderApplotIt:
    """A filter one reader forgets is a filter that does not exist."""

    @pytest.mark.parametrize(
        "module_path",
        [
            "src.domains.agents.services.catalogue.strategies.normal_filtering",
            "src.domains.agents.services.catalogue.strategies.panic_filtering",
            "src.domains.agents.services.react_tool_selector",
        ],
    )
    def test_the_manifest_reader_filters_by_mode(self, module_path: str) -> None:
        module = __import__(module_path, fromlist=["_"])
        source = inspect.getsource(module)
        assert "get_request_tool_manifests()" in source
        assert "manifests_for_mode" in source, (
            f"{module_path} reads the manifest list without applying the mode "
            "restriction — a react-only tool would leak into the pipeline plan"
        )
