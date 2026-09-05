"""Invariant: draft-based mutation tools must NOT be ``hitl_required=True``.

Why this matters (it ties the two execution modes together):

- ``hitl_required`` (a manifest permission) drives ONLY ReAct's pre-execution
  interrupt: ``react_tool_selector`` puts the tool in ``hitl_map`` and
  ``react_execute_tools_node`` interrupts BEFORE the tool runs. That interrupt
  now carries a type-tagged ``action_requests`` entry (``tool_confirmation``),
  so the streaming service renders a real confirmation and the resume is routed
  back through ``_parse_approval_decision``. The legacy bare
  ``react_tool_approval`` payload carried no ``action_requests`` and hung
  silently (issue #3); it is gone — see ``react_nodes.py`` where the interrupt
  is built.
- The pipeline does NOT gate on this flag (``approval_gate`` is a pass-through);
  it confirms mutations POST-execution via the tool's own
  ``requires_confirmation`` output (draft_critique / tool_confirmation).

Therefore a DRAFT-BASED tool (returns ``requires_confirmation`` → a draft) must
be ``hitl_required=False``: the draft *is* its confirmation, so a pre-execution
interrupt would ask the user twice. ``hitl_required=True`` is reserved for
genuinely NON-draft mutation tools that need a pre-execution confirmation
(sub-agent delegation; user MCP mutation tools whose flag comes from server
config).

Mind the asymmetry when adding a tool: because the pipeline ignores this flag,
``hitl_required=True`` alone only covers ReAct. A non-draft tool that must be
confirmed in BOTH modes needs a second mechanism — a state-changing
``tool_category`` (so ``tool_is_mutation()`` keeps it inside the
``semantic_validator_node`` safety net) or a draft-shaped return.

``claude_server_task_tool`` is the worked example (FN-1): a remote-server task
must be confirmed in both modes, and changing ``tool_category`` would have
rerouted the semantic validator, so the tool returns a ``DEVOPS_TASK`` draft
instead and keeps ``hitl_required=False`` like every other draft producer.

This test locks the invariant so a stale/new flag fails CI instead of shipping
a ReAct hang.
"""

from __future__ import annotations

import pytest

from src.domains.agents.registry.agent_registry import AgentRegistry
from src.domains.agents.registry.catalogue_loader import initialize_catalogue

# The draft-based tools are DERIVED from the catalogue since ADR-263: a tool
# whose manifest declares ``mutation_policy="draft"`` confirms through its
# draft. The hand-maintained tuple this replaced listed 18 names and had to be
# edited by whoever added the nineteenth — the declaration cannot be forgotten,
# the list could.
MIN_EXPECTED_DRAFT_TOOLS = 18  # what the hand list held on 2026-09-03 (anti-vacuity)

# The ONLY tools allowed to require a pre-execution HITL interrupt: genuinely
# non-draft mutations. Extend consciously — and make sure ReAct actually renders
# them (react_execute_tools_node, #3 fix B).
HITL_REQUIRED_ALLOWLIST: frozenset[str] = frozenset({"delegate_to_sub_agent_tool"})


@pytest.fixture(scope="module")
def registry() -> AgentRegistry:
    """A fresh registry with the full production catalogue loaded."""
    reg = AgentRegistry()
    initialize_catalogue(reg)
    return reg


def _draft_based_tools(registry: AgentRegistry) -> list[str]:
    """Tools whose manifest declares the draft policy (ADR-263)."""
    return sorted(m.name for m in registry.list_tool_manifests() if m.mutation_policy == "draft")


def test_no_draft_based_tool_is_hitl_required(registry: AgentRegistry) -> None:
    """Every draft-based tool is hitl_required=False (no ReAct pre-interrupt)."""
    names = _draft_based_tools(registry)
    assert len(names) >= MIN_EXPECTED_DRAFT_TOOLS, (
        f"only {len(names)} draft tools found ({names}) — the derivation is vacuous, "
        "so this test would pass while proving nothing."
    )
    offenders = [n for n in names if registry.get_tool_manifest(n).permissions.hitl_required]
    assert not offenders, (
        f"{offenders} are draft-based (confirmed via draft_critique) but set "
        "hitl_required=True. In ReAct this triggers the pre-execution "
        "'react_tool_approval' interrupt, which is unrendered → silent hang (#3). "
        "Set hitl_required=False."
    )


def test_hitl_required_set_is_within_allowlist(registry: AgentRegistry) -> None:
    """No tool outside the allowlist may require a pre-execution HITL interrupt."""
    hitl_tools = set(registry.get_tools_requiring_hitl())
    unexpected = hitl_tools - HITL_REQUIRED_ALLOWLIST
    assert not unexpected, (
        "These tools set hitl_required=True but are not in HITL_REQUIRED_ALLOWLIST. "
        "A draft-based tool with hitl_required=True silently hangs in ReAct (#3): "
        "set it False. If it is a genuine non-draft pre-execution HITL tool, add it "
        f"to the allowlist AND ensure ReAct renders it. Offenders: {sorted(unexpected)}"
    )
