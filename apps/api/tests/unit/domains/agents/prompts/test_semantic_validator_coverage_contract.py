"""Coverage-pass contract of the semantic validator prompt (Lot E, 2026-09).

Measured asymmetry (2026-09-02): ``SemanticIssueType.MISSING_STEP`` is exposed
to the model through the structured-output schema, yet the prompt never named
it and 0 of its 9 decision-tree bullets concerned an ABSENCE — the exact
"omission blindness" failure mode: judges verify what a plan contains, not
what it lacks. The remedy that works is structural: enumerate the demands the
request establishes FIRST, then check the plan covers each.

The pass was applied to v1 in place — prompts are not versioned in this
codebase (owner decision 2026-09-02); these tests pin the pass so it cannot
silently regress out of the prompt.
"""

from __future__ import annotations

import re

import pytest

from src.core.constants import (
    DYNAMIC_CONTEXT_MARKER,
    SEMANTIC_VALIDATOR_PROMPT_VERSION_DEFAULT,
)
from src.domains.agents.prompts.prompt_loader import load_prompt

pytestmark = [pytest.mark.unit]


def _prompt() -> str:
    return load_prompt(
        "semantic_validator_prompt", version=SEMANTIC_VALIDATOR_PROMPT_VERSION_DEFAULT
    )


class TestCoveragePassContract:
    def test_prompt_names_missing_step(self) -> None:
        """The enum value the model may emit is DESCRIBED, not just permitted."""
        assert "missing_step" in _prompt()

    def test_enumeration_runs_before_judgement(self) -> None:
        """The structural remedy: list the demands first, judge coverage second."""
        prompt = _prompt()
        coverage_pos = prompt.find("COVERAGE PASS")
        tree_pos = prompt.find("DECISION TREE")
        assert coverage_pos != -1, "coverage pass section missing"
        assert tree_pos != -1
        assert coverage_pos < tree_pos, "coverage pass must run before the verdict"

    def test_decision_tree_carries_an_absence_bullet(self) -> None:
        """At least one REJECT bullet is about what the plan LACKS."""
        prompt = _prompt()
        tree = prompt.split("## DECISION TREE", 1)[-1].split("## FIELD SEMANTICS", 1)[0]
        bullets = [b for b in tree.splitlines() if b.strip().startswith("-")]
        absence = [
            b for b in bullets if re.search(r"\bmissing_step\b|\bno covering step\b", b.lower())
        ]
        assert absence, "no decision-tree bullet concerns an absence"

    def test_analysis_demands_are_shielded_from_false_positives(self) -> None:
        """A compare/summarise demand is the Response LLM's job — never a
        missing_step. Without this shield the pass would replan every
        analytical query (bounded at planner_max_replans, but pure waste)."""
        prompt = _prompt()
        section = prompt.split("COVERAGE PASS", 1)[-1].split("## DECISION TREE", 1)[0]
        assert re.search(r"\bnever a missing_step\b", section)

    def test_unservable_demands_are_shielded_too(self) -> None:
        """A demand no capability can serve must not trigger endless replans."""
        prompt = _prompt()
        section = prompt.split("COVERAGE PASS", 1)[-1].split("## DECISION TREE", 1)[0]
        assert "not a\n  missing_step" in section or "not a missing_step" in section

    def test_prompt_keeps_the_cache_marker_and_the_role_separation(self) -> None:
        """The pass must not cost v1 its invariants: cacheable static prefix,
        role split, and the draft-confirmation HALT shield."""
        prompt = _prompt()
        assert DYNAMIC_CONTEXT_MARKER in prompt
        assert "ROLE SEPARATION" in prompt
        assert "NEVER HALT for an action that already carries its own confirmation" in prompt
