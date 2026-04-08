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
    "Delegate a task to a specialized ephemeral sub-agent.\n"
    "**Use for**: Complex tasks requiring domain expertise, "
    "parallel independent research tracks, deep analysis, "
    "or multi-faceted comparisons.\n"
    "**NOT for**: Simple lookups, standard CRUD, or HITL operations.\n"
    "**Output**: Sub-agent's complete analysis in 'analysis' field."
)

delegate_to_sub_agent_catalogue_manifest = ToolManifest(
    name="delegate_to_sub_agent_tool",
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
                "Domain expertise description for the sub-agent specialist. "
                "Be specific about the role and knowledge area. "
                "Examples: 'expert comptable specialise en analyse financiere', "
                "'specialiste transport ferroviaire', "
                "'analyste de donnees marketing'."
            ),
            constraints=[
                ParameterConstraint(kind="min_length", value=5),
                ParameterConstraint(kind="max_length", value=500),
            ],
        ),
        ParameterSchema(
            name="instruction",
            type="string",
            required=True,
            description=(
                "Detailed task instruction with all necessary context "
                "and expected output format. Include: what to analyze, "
                "what sources to use, what format the output should take. "
                "Can reference results from previous steps via $steps.step_N.field."
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
    cost=CostProfile(
        est_tokens_in=2000,
        est_tokens_out=4000,
        est_cost_usd=0.05,
        est_latency_ms=30000,
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
