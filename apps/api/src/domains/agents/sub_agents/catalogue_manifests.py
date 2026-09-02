"""
Catalogue manifests for Sub-Agent delegation tool.

Defines agent and tool manifests for the sub-agent orchestration system.
The delegate tool is TRANSVERSAL — always included in the filtered catalogue
regardless of detected domains, so the planner can autonomously decide
when to delegate.

Phase: F6 — Persistent Specialized Sub-Agents
"""

from datetime import UTC, datetime

from src.domains.agents.registry.catalogue import (
    AgentManifest,
    CostProfile,
    DisplayMetadata,
    OutputFieldSchema,
    ParameterConstraint,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)

# =============================================================================
# Agent Manifest: sub_agent_agent
# =============================================================================

SUB_AGENT_MANIFEST = AgentManifest(
    name="sub_agent_agent",
    description=(
        "Orchestration agent for delegating complex tasks to ephemeral "
        "specialized sub-agents. Sub-agents are temporary experts created "
        "with specific directives for focused research, analysis, or synthesis."
    ),
    tools=[
        "delegate_to_sub_agent_tool",
    ],
    max_parallel_runs=5,
    default_timeout_ms=120000,  # 2 minutes per sub-agent
    prompt_version="v1",
    owner_team="Team AI",
    version="1.0.0",
    updated_at=datetime.now(UTC),
    display=DisplayMetadata(
        emoji="🤖",
        i18n_key="sub_agent_agent",
        visible=True,
        category="agent",
    ),
)

# =============================================================================
# Tool Manifest: delegate_to_sub_agent_tool
# =============================================================================

_DESCRIPTION = (
    "**Tool: delegate_to_sub_agent_tool** — "
    "Delegate a UNITARY expert task to an ephemeral specialized sub-agent "
    "(scoped ReAct loop, read-only tools).\n"
    "**Use IFF**: a specialized expert persona, with a focused prompt and "
    "read-only tools, would produce a MATERIALLY BETTER answer than the "
    "principal assistant handling the task directly (deep analysis, "
    "multi-source comparison with cross-referencing, independent parallel "
    "research tracks via fan-out to 2+ different experts).\n"
    "**DO NOT USE for**: data fetching/summarization, simple lookups, "
    "standard CRUD, single-tool tasks (do those yourself).\n"
    "**Output**: the sub-agent's analytical text in `analysis` field."
)

delegate_to_sub_agent_catalogue_manifest = ToolManifest(
    name="delegate_to_sub_agent_tool",
    # ADR-256: the sub-agent runs a READ-ONLY tool subset by contract (ADR-083),
    # so the delegation itself mutates nothing.
    tool_category="readonly",
    agent="sub_agent_agent",
    description=_DESCRIPTION,
    semantic_keywords=[
        "delegate",
        "sub-agent",
        "expert",
        "specialize",
        "decompose",
        "parallel research",
        "deep analysis",
        "compare options",
        "cross-reference",
        "domain expertise",
        "accounting analysis",
        "legal review",
        "technical audit",
    ],
    parameters=[
        ParameterSchema(
            name="expertise",
            type="string",
            required=True,
            description=(
                "Domain expertise prompt for the sub-agent specialist — defines "
                "the persona (role + seniority + domain), optionally the "
                "methodology to apply, the epistemic standards (sources, "
                "fact/inference distinction), and the expected output structure "
                "(sections, depth). For deep analysis tasks the planner "
                "typically writes 800-1500 chars; for simple summaries a short "
                "persona of 50-200 chars is enough. "
                "Examples: 'expert comptable specialise en analyse financiere', "
                "'specialiste transport ferroviaire', "
                "'analyste de donnees marketing'."
            ),
            constraints=[
                ParameterConstraint(kind="min_length", value=5),
                ParameterConstraint(kind="max_length", value=2000),
            ],
        ),
        ParameterSchema(
            name="instruction",
            type="string",
            required=True,
            description=(
                "Clear TASK STATEMENT for the sub-agent — what to analyze, "
                "what sources to use, what output format. DO NOT paste raw "
                "data; the sub-agent has its own read-only tools and fetches "
                "what it needs. May contain `$steps.step_N.analysis` for "
                "sub-agent → sub-agent chaining (short text). Never reference "
                "raw tool outputs (`$steps.step_N.<data>`) — the resolved "
                "instruction is hard-capped (configurable via "
                "SUBAGENT_INSTRUCTION_MAX_TOKENS_RESOLVED, default 3000 tokens) "
                "and oversized payloads are rejected at execution time."
            ),
            constraints=[
                ParameterConstraint(kind="min_length", value=10),
                ParameterConstraint(kind="max_length", value=5000),
            ],
        ),
    ],
    outputs=[
        OutputFieldSchema(
            path="analysis",
            type="string",
            description="Sub-agent's complete analysis result text",
        ),
    ],
    # ADR-083 — realistic estimate post-rewrite onto ReactSubAgentRunner:
    # a single scoped ReAct loop (~1-6 LLM calls bounded by recursion_limit),
    # with `instruction` hard-capped at SUBAGENT_INSTRUCTION_MAX_TOKENS_RESOLVED.
    cost=CostProfile(
        est_tokens_in=3000,
        est_tokens_out=2000,
        est_cost_usd=0.02,
        est_latency_ms=20000,
    ),
    permissions=PermissionProfile(
        required_scopes=[],
        hitl_required=True,  # User must confirm before sub-agent delegation
        data_classification="INTERNAL",
    ),
    reference_examples=["analysis"],
    version="1.0.0",
    maintainer="Team AI",
    display=DisplayMetadata(
        emoji="🤖",
        i18n_key="delegate_to_sub_agent",
        visible=True,
        category="tool",
    ),
    initiative_eligible=False,  # Infrastructure orchestration tool, not enrichment data
)

__all__ = [
    "SUB_AGENT_MANIFEST",
    "delegate_to_sub_agent_catalogue_manifest",
]
