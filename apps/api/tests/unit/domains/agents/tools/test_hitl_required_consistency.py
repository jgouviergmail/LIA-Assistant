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

# Every draft-based mutation tool (returns requires_confirmation=True → a draft
# confirmed via draft_critique). ALL must be hitl_required=False.
DRAFT_BASED_MUTATION_TOOLS: tuple[str, ...] = (
    "send_email_tool",
    "reply_email_tool",
    "forward_email_tool",
    "delete_email_tool",
    "create_event_tool",
    "update_event_tool",
    "delete_event_tool",
    "create_contact_tool",
    "update_contact_tool",
    "delete_contact_tool",
    "create_task_tool",
    "update_task_tool",
    "delete_task_tool",
    "create_label_tool",
    "update_label_tool",
    "delete_label_tool",
    "create_reminder_tool",
    "cancel_reminder_tool",
)

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


@pytest.mark.parametrize("tool_name", DRAFT_BASED_MUTATION_TOOLS)
def test_draft_based_tool_is_not_hitl_required(registry: AgentRegistry, tool_name: str) -> None:
    """Each draft-based tool exists and is hitl_required=False (no ReAct pre-interrupt)."""
    manifest = registry.get_tool_manifest(tool_name)  # raises if renamed/removed
    assert manifest.permissions.hitl_required is False, (
        f"{tool_name} is draft-based (confirmed via draft_critique) but sets "
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
