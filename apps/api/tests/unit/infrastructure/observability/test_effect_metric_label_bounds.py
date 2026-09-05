"""No effect metric may carry an unbounded label (ADR-263).

``tool_name`` is free text — a third-party MCP server names its own tools, and
a user can install as many as they like. Carried as a Prometheus label it
multiplies every series by the size of a set nobody controls; that is how a
metric stops being observability and becomes an incident.

The guard reads the SOURCE rather than the registry, so a label added in a
future edit is refused before it ever fires once.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

MODULE = (
    Path(__file__).resolve().parents[4]
    / "src"
    / "infrastructure"
    / "observability"
    / "metrics_effects.py"
)

#: Every label an effect metric may carry, and why it is bounded.
ALLOWED_LABELS: dict[str, str] = {
    "policy": "the six declared mutation policies",
    "source": "user | scheduled | subagent (EffectSource)",
    "execution_mode": "pipeline | react",
    "status": "succeeded | failed",
    "outcome": "ok | failed (TreatmentOutcome) for a consultation — it "
    "answered or it did not; answered | failed | interrupted "
    "(DecisionOutcome) for a turn, whose third state is the one that matters",
    "reason": "gate error codes and ledger outcomes — a closed vocabulary",
    "served": "record | none",
    "operation": "claim | close | refuse | treatments_flush",
    "domain": "the taxonomy's 31 nouns (DOMAIN_REGISTRY + the declared "
    "overrides); MCP collapses to one value, so a third-party server can "
    "never widen it",
    # Three values, and a test below pins exactly which — a label whose
    # vocabulary lives in code is only bounded while something checks that the
    # code still says what this line claims.
    "table": "agent_effects | agent_treatments | ledger_chain (LEDGER_TABLES)",
    "kind": "chain.genesis | effect.claimed | effect.settled | "
    "treatment.recorded — the CHAIN_SUBJECTS stages plus the genesis, and a "
    "kind is written into every entry's hash, so the set cannot grow quietly",
}

#: Names that must never appear, whatever a future edit intends.
FORBIDDEN_LABELS = frozenset(
    {"tool_name", "user_id", "run_id", "thread_id", "draft_id", "job", "error", "message"}
)


def _declared_labels() -> dict[str, list[str]]:
    """Metric name -> label names, read from the module's AST."""
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    found: dict[str, list[str]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        if node.func.id not in {"Counter", "Gauge", "Histogram"}:
            continue
        if not node.args or not isinstance(node.args[0], ast.Constant):
            continue
        metric_name = str(node.args[0].value)
        labels: list[str] = []
        for argument in node.args[1:]:
            if isinstance(argument, ast.List):
                labels = [
                    str(element.value)
                    for element in argument.elts
                    if isinstance(element, ast.Constant)
                ]
        found[metric_name] = labels
    return found


class TestEveryLabelIsBounded:
    def test_the_module_defines_metrics(self) -> None:
        """Anti-vacuity: a parsing change must not silence this whole file."""
        assert len(_declared_labels()) >= 6

    def test_no_forbidden_label(self) -> None:
        offenders = {
            name: sorted(set(labels) & FORBIDDEN_LABELS)
            for name, labels in _declared_labels().items()
            if set(labels) & FORBIDDEN_LABELS
        }
        assert not offenders, (
            f"unbounded label(s) on effect metrics: {offenders}. "
            "A label whose values nobody controls multiplies every series."
        )

    def test_every_label_is_declared_here(self) -> None:
        """A new label must be argued for in ALLOWED_LABELS, not merely added."""
        offenders = {
            name: sorted(set(labels) - set(ALLOWED_LABELS))
            for name, labels in _declared_labels().items()
            if set(labels) - set(ALLOWED_LABELS)
        }
        assert not offenders, (
            f"undeclared label(s): {offenders}. Add them to ALLOWED_LABELS with the "
            "vocabulary that bounds them, or use an existing one."
        )

    def test_the_domain_label_cannot_carry_a_third_party_name(self) -> None:
        """The vocabulary is OURS: an MCP server's tools collapse to ``mcp``."""
        from src.core.constants import MCP_TOOL_NAME_PREFIX
        from src.domains.agents.effects.treatment_labels import treatment_domain

        assert treatment_domain(f"{MCP_TOOL_NAME_PREFIX}anything__at__all") == "mcp"

    def test_the_table_label_is_bounded_by_the_transparency_tables(self) -> None:
        """The vocabulary this declaration names, read from the code.

        A bounded label is only bounded while its source stays bounded: this
        reads ``LEDGER_TABLES`` rather than trusting the sentence above it.
        """
        from src.domains.agents.effects.volume import LEDGER_TABLES

        assert set(LEDGER_TABLES) == {"agent_effects", "agent_treatments", "ledger_chain"}

    def test_the_kind_label_is_bounded_by_the_chain_spec(self) -> None:
        """Same rule for the chain's stages: read the declaration, not the prose."""
        from src.domains.agents.effects.chain_spec import CHAIN_SUBJECTS, GENESIS_KIND

        assert {subject.kind for subject in CHAIN_SUBJECTS} | {GENESIS_KIND} == {
            "chain.genesis",
            "effect.claimed",
            "effect.settled",
            "treatment.recorded",
        }

    def test_no_metric_carries_more_than_three_labels(self) -> None:
        """The cardinality contract shared with the product metrics."""
        offenders = {name: labels for name, labels in _declared_labels().items() if len(labels) > 3}
        assert not offenders, f"more than 3 labels: {offenders}"
