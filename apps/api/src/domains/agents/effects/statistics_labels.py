"""Turning a free-text field into a chart label nobody can widen (ADR-263).

A chart axis is a bounded vocabulary or it is a leak. Measured on the developer
instance, 2026-09-05: ``token_usage_logs.node_name`` holds 102 distinct values,
and two of its families are not ours to publish —

- ``sub-agent: Consultant expert en communication écrit`` — the title a USER
  gave their own sub-agent. On the administrator's cross-account view that
  would put one account's private naming in front of an operator;
- ``MCP Iterative: GITHUB REPOS`` — a third-party server's own name, whose
  value set belongs to nobody (the rule ``treatment_domain`` already lives by,
  and which the effect metrics enforce by refusing ``tool_name`` as a label).

So both families collapse to one word, exactly as MCP tools collapse to ``mcp``
in the consultation register. The 78 remaining values are graph node names this
repository chooses, and they are what the chart is actually about.

This is not a display nicety: it is the same cardinality contract the
Prometheus labels obey, applied to the one place a free-text field would
otherwise reach a reader.
"""

from __future__ import annotations

from typing import Final

#: Prefixes whose remainder is written by somebody else. Everything after them
#: is replaced by the family name — never truncated, never hashed: a reader
#: needs to know a sub-agent ran, not which one.
_COLLAPSED_PREFIXES: Final[tuple[tuple[str, str], ...]] = (
    ("sub-agent:", "sub-agent"),
    ("MCP Iterative:", "mcp"),
    ("mcp iterative:", "mcp"),
)

#: What an unnamed row shows. Rows written before ADR-244 carry no slot, and a
#: chart that silently dropped them would understate the period it claims to
#: describe.
UNSPECIFIED: Final[str] = "unspecified"


def collapse_node_name(value: str | None) -> str:
    """The bounded label for one execution node.

    Args:
        value: The stored node name, or None.

    Returns:
        The node's own name when this repository chose it, the family name when
        somebody else did, and :data:`UNSPECIFIED` when the row carries none.
    """
    if not value:
        return UNSPECIFIED
    for prefix, family in _COLLAPSED_PREFIXES:
        if value.startswith(prefix):
            return family
    return value


def collapse_tool_name(value: str | None) -> str:
    """The bounded label for one consulted capability.

    Native tool names are chosen by this repository and are therefore a closed
    set worth showing; an MCP tool's name is written by the server that offers
    it, and its value set belongs to nobody. The latency chart grouped by the
    raw column, so an operator's cross-account screen listed the servers one
    account had installed.

    The same rule ``treatment_domain`` lives by (ADR-255), applied one layer
    later: there it collapses to a domain, here to the family, because this
    chart's question is technical and a native tool name is its answer.

    Args:
        value: The stored tool name, or None.

    Returns:
        The tool's own name when we chose it, ``mcp`` when somebody else did,
        and :data:`UNSPECIFIED` when the row carries none.
    """
    if not value:
        return UNSPECIFIED
    from src.domains.agents.registry.catalogue import MCP_TOOL_NAME_PREFIX

    return "mcp" if value.startswith(MCP_TOOL_NAME_PREFIX) else value


def collapse_slot(value: str | None) -> str:
    """The bounded label for one configured LLM slot.

    Args:
        value: The stored ``llm_type``, or None.

    Returns:
        The slot, or :data:`UNSPECIFIED`. Rows written before ADR-244 have
        none, and they are the majority of any long history — counting them
        under an explicit name is what keeps the total honest.
    """
    return value or UNSPECIFIED


__all__ = ["UNSPECIFIED", "collapse_node_name", "collapse_slot", "collapse_tool_name"]
