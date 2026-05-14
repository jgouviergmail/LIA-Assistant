"""Sub-Agents domain constants.

After ADR-083 Phase 2 cleanup, this module only defines the constants still
consumed by the ephemeral planner-delegation path (`delegate_to_sub_agent_tool`
→ `ReactSubAgentRunner`). The bespoke executor pipeline, daily-budget Redis
keys, synthesis prompt name, and user templates were all removed.
"""

# ============================================================================
# BLOCKED TOOLS (write/destructive operations — read-only sub-agents)
# ============================================================================
# Consumed by `resolve_tools_for_subagent` (skill_resolver.py) when
# `delegate_to_sub_agent_tool` builds the read-only toolset for the ReAct
# sub-agent loop.

SUBAGENT_DEFAULT_BLOCKED_TOOLS: list[str] = [
    # Email write operations
    "send_email_tool",
    "reply_email_tool",
    "forward_email_tool",
    "delete_email_tool",
    # Label mutations
    "create_label_tool",
    "update_label_tool",
    "delete_label_tool",
    "apply_labels_tool",
    "remove_labels_tool",
    # Calendar write operations
    "create_event_tool",
    "update_event_tool",
    "delete_event_tool",
    # Task write operations
    "create_task_tool",
    "complete_task_tool",
    # Research tools deemed too noisy or redundant for sub-agent use:
    # - perplexity_ask_tool: returns long synthesized prose that inflates the
    #   sub-agent's pass-1 budget without improving downstream synthesis.
    # - unified_web_search_tool: aggregates brave + perplexity + wikipedia and
    #   amplifies the noise; brave_search_tool alone is sharper for facts.
    # - get_wikipedia_summary_tool: too generic, drowns specific signal.
    # Sub-agents keep brave_search_tool + fetch_web_page_tool for research.
    "perplexity_ask_tool",
    "unified_web_search_tool",
    "get_wikipedia_summary_tool",
]
