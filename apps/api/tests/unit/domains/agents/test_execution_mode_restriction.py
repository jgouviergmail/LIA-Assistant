"""A tool may declare which execution modes it belongs to (ADR-249).

The pipeline plans ahead: it emits an ExecutionPlan and the orchestrator runs
it. That is the wrong home for model-authored Python, which needs the loop that
can read a traceback and repair the script — so `run_python_tool` is ReAct-only
by owner arbitration.

A restriction that lives only in the tool's own refusal is a trap: the planner
would still SEE the tool, plan a step with it, and be told "no" at execution —
an invented dead end for the user. The manifest therefore carries the contract.

Two shapes enforce it, because two kinds of reader exist (measured 2026-09-10:
seven modules read the manifest list, and only three of them filter):

- the CATALOGUE readers — the two pipeline filtering strategies and the ReAct
  selector — call `manifests_for_mode` on the list they offer;
- the initiative node builds its own adjacent-tool catalogue without that
  filter, so `is_initiative_eligible` refuses a tool the pipeline cannot run,
  ahead of every preference. The remaining readers offer nothing to a model:
  `initiative_plan` resolves an already-chosen action's agent, and the router
  and the expansion service score domains.
"""

from __future__ import annotations

import inspect

import pytest

from src.core.constants import EXECUTION_MODE_PIPELINE, EXECUTION_MODE_REACT
from src.domains.agents.registry.catalogue import is_initiative_eligible, manifests_for_mode

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


class _Candidate:
    """A manifest as the initiative predicate reads one."""

    def __init__(
        self,
        name: str,
        *,
        modes: frozenset[str] | None,
        eligible: bool | None = None,
        category: str | None = "readonly",
    ) -> None:
        self.name = name
        self.execution_modes = modes
        self.initiative_eligible = eligible
        self.tool_category = category
        self.agent = "python_sandbox_agent"


class TestInitiativeNeverOffersAToolItCannotRun:
    """The initiative node runs INSIDE the pipeline and offers a catalogue.

    `initiative_node` builds its adjacent-tool list straight from
    `get_request_tool_manifests()` and hands it to a model — one of four
    readers that do not apply `manifests_for_mode`. A ReAct-only tool reaching
    that prompt is exactly ADR-249's invented dead end: the model proposes it,
    the pipeline cannot run it.

    Nothing was broken when this was written (2026-09-10): `run_python_tool`
    declares `initiative_eligible=False`. But that is a per-manifest MEMORY,
    and the second ReAct-only tool would have to remember it too. The mode a
    tool can run in is a capability, not a preference, so the refusal belongs
    to the predicate — where it holds for every tool that will ever exist.
    """

    def test_a_react_only_tool_is_refused_whatever_its_category_says(self) -> None:
        react_only = _Candidate("run_python_tool", modes=frozenset({EXECUTION_MODE_REACT}))
        assert is_initiative_eligible(react_only) is False

    def test_an_explicit_yes_cannot_re_open_it(self) -> None:
        """A capability outranks a preference: the flag cannot grant what the
        pipeline is unable to execute."""
        insisting = _Candidate(
            "run_python_tool", modes=frozenset({EXECUTION_MODE_REACT}), eligible=True
        )
        assert is_initiative_eligible(insisting) is False

    def test_a_pipeline_tool_keeps_the_answer_it_always_had(self) -> None:
        both = _Candidate(
            "search_emails_tool",
            modes=frozenset({EXECUTION_MODE_PIPELINE, EXECUTION_MODE_REACT}),
        )
        assert is_initiative_eligible(both) is True

    def test_a_manifest_declaring_no_mode_still_fails_open(self) -> None:
        """Older and third-party manifests must not vanish from the catalogue."""
        legacy = _Candidate("some_third_party_tool", modes=None)
        assert is_initiative_eligible(legacy) is True

    def test_an_explicit_no_is_still_honoured_for_a_pipeline_tool(self) -> None:
        opted_out = _Candidate(
            "noisy_tool",
            modes=frozenset({EXECUTION_MODE_PIPELINE, EXECUTION_MODE_REACT}),
            eligible=False,
        )
        assert is_initiative_eligible(opted_out) is False
