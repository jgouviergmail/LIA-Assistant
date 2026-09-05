"""Catalogue manifests for Automation tools (P11, ADR-140).

Chat-piloted scheduled actions: create (HITL draft), list, toggle.
Internal tools (no OAuth) — the automation itself runs through the full
agent pipeline via the existing scheduled-action executor.
"""

from datetime import UTC, datetime

from src.core.config import settings
from src.domains.agents.registry.catalogue import (
    REASON_UNDONE_BY_ONE_CALL,
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
# Agent Manifest: automation_agent
# =============================================================================

AUTOMATION_AGENT_MANIFEST = AgentManifest(
    name="automation_agent",
    description=(
        "Agent specialized in recurring automations (scheduled actions). "
        "Create an automation that runs any instruction on a weekly schedule "
        "('every morning at 8, give me an AI press review'), list existing "
        "automations, enable or disable them. Creation requires user "
        "confirmation (draft)."
    ),
    tools=[
        "create_scheduled_action_tool",
        "list_scheduled_actions_tool",
        "toggle_scheduled_action_tool",
    ],
    max_parallel_runs=1,
    default_timeout_ms=settings.default_tool_timeout_ms,
    display=DisplayMetadata(
        emoji="⏰",
        i18n_key="automation_agent",
        visible=True,
        category="agent",
    ),
    version="1.0.0",
    updated_at=datetime.now(UTC),
)


# =============================================================================
# Tool Manifest: create_scheduled_action_tool
# =============================================================================

create_scheduled_action_catalogue_manifest = ToolManifest(
    name="create_scheduled_action_tool",
    mutation_policy="draft",
    agent="automation_agent",
    description=(
        "Creates a recurring automation: LIA will execute the given instruction "
        "on the chosen weekdays at the chosen time (user's timezone), and "
        "deliver the result as a notification + chat message. Returns a draft "
        "the user must confirm — nothing is scheduled before confirmation. "
        "Use when the user asks for something 'every day/morning/Monday…'."
    ),
    parameters=[
        ParameterSchema(
            name="title",
            type="string",
            required=True,
            description="Short user-facing title (e.g. 'Revue de presse IA')",
            constraints=[
                ParameterConstraint(kind="min_length", value=1),
                ParameterConstraint(kind="max_length", value=200),
            ],
        ),
        ParameterSchema(
            name="action_prompt",
            type="string",
            required=True,
            description=(
                "The instruction executed on each run, in the user's own words "
                "and language (full agent capabilities apply)."
            ),
            constraints=[
                ParameterConstraint(kind="min_length", value=1),
                ParameterConstraint(kind="max_length", value=2000),
            ],
        ),
        ParameterSchema(
            name="days_of_week",
            type="array",
            required=True,
            description=(
                "ISO weekdays to run on: 1=Monday .. 7=Sunday. "
                "[1,2,3,4,5]=weekdays, [1..7]=every day."
            ),
        ),
        ParameterSchema(
            name="trigger_hour",
            type="integer",
            required=True,
            description="Hour of execution 0-23, in the USER's timezone",
        ),
        ParameterSchema(
            name="trigger_minute",
            type="integer",
            required=False,
            description="Minute of execution 0-59 (default 0)",
        ),
    ],
    outputs=[
        OutputFieldSchema(
            path="success",
            type="boolean",
            description="Whether the draft was created",
        ),
        OutputFieldSchema(
            path="message",
            type="string",
            description="Draft confirmation message shown to the user",
        ),
    ],
    cost=CostProfile(
        est_tokens_in=80,
        est_tokens_out=60,
        est_cost_usd=0.0001,
        est_latency_ms=150,
    ),
    permissions=PermissionProfile(
        required_scopes=[],  # Internal tool, no OAuth
        data_classification="CONFIDENTIAL",
        # Draft-based: create_scheduled_action_tool returns requires_confirmation
        # (scheduled_action draft) → draft_critique. hitl_required stays False
        # (see test_hitl_required_consistency.py): the flag only drives ReAct's
        # pre-execution interrupt — redundant AND unrendered for a draft tool.
        hitl_required=False,
    ),
    semantic_keywords=[
        "automate a request every morning at a fixed time",
        "do this for me every day automatically",
        "schedule a recurring task every monday",
        "set up a daily automation with my instruction",
        "run this prompt on a weekly schedule",
        "create an automation that repeats",
    ],
    reference_examples=[],
    display=DisplayMetadata(
        emoji="➕",
        i18n_key="create_scheduled_action",
        visible=True,
        category="tool",
    ),
    tool_category="create",
    version="1.0.0",
    updated_at=datetime.now(UTC),
)


# =============================================================================
# Tool Manifest: list_scheduled_actions_tool
# =============================================================================

list_scheduled_actions_catalogue_manifest = ToolManifest(
    name="list_scheduled_actions_tool",
    mutation_policy="read",
    agent="automation_agent",
    description=(
        "Lists the user's recurring automations with their id, title, "
        "human-readable schedule, enabled state and last/next run. "
        "Use before toggling (exposes the real ids)."
    ),
    parameters=[],
    outputs=[
        OutputFieldSchema(
            path="automations",
            type="array",
            description="Automations: id, title, schedule, is_enabled, status",
        ),
        # The ONLY source of a valid action_id (a UUID nobody can dictate).
        # Declared so the catalogue closure can pull this tool in whenever
        # toggle_scheduled_action_tool survives filtering without it.
        OutputFieldSchema(
            path="automations[].id",
            type="string",
            description="Automation UUID",
            semantic_type="automation_id",
        ),
        OutputFieldSchema(
            path="count",
            type="integer",
            description="Number of automations",
        ),
    ],
    cost=CostProfile(
        est_tokens_in=30,
        est_tokens_out=120,
        est_cost_usd=0.0001,
        est_latency_ms=100,
    ),
    permissions=PermissionProfile(
        required_scopes=[],
        data_classification="CONFIDENTIAL",
        hitl_required=False,
    ),
    semantic_keywords=[
        "list my automations and scheduled tasks",
        "what recurring actions are set up",
        "show my daily automated routines",
        "which automations run every morning",
    ],
    reference_examples=[],
    display=DisplayMetadata(
        emoji="📋",
        i18n_key="list_scheduled_actions",
        visible=True,
        category="tool",
    ),
    tool_category="readonly",
    version="1.0.0",
    updated_at=datetime.now(UTC),
)


# =============================================================================
# Tool Manifest: toggle_scheduled_action_tool
# =============================================================================

toggle_scheduled_action_catalogue_manifest = ToolManifest(
    name="toggle_scheduled_action_tool",
    mutation_policy="reversible",
    mutation_policy_reason=REASON_UNDONE_BY_ONE_CALL,
    agent="automation_agent",
    description=(
        "Enables or disables an existing automation (reversible switch). "
        "Requires the automation id from list_scheduled_actions_tool. "
        "Use to pause ('désactive ma revue de presse') or resume an automation."
    ),
    parameters=[
        ParameterSchema(
            name="action_id",
            type="string",
            required=True,
            description="Automation UUID from list_scheduled_actions_tool",
            semantic_type="automation_id",
        ),
    ],
    outputs=[
        OutputFieldSchema(
            path="success",
            type="boolean",
            description="Whether the toggle succeeded",
        ),
        OutputFieldSchema(
            path="is_enabled",
            type="boolean",
            description="New enabled state",
        ),
    ],
    cost=CostProfile(
        est_tokens_in=40,
        est_tokens_out=40,
        est_cost_usd=0.0001,
        est_latency_ms=120,
    ),
    permissions=PermissionProfile(
        required_scopes=[],
        data_classification="CONFIDENTIAL",
        hitl_required=False,  # Reversible — one message toggles it back
    ),
    semantic_keywords=[
        "disable or pause one of my automations",
        "re-enable a paused scheduled automation",
        "turn off my daily automated routine",
        "stop the recurring automation temporarily",
    ],
    reference_examples=[],
    display=DisplayMetadata(
        emoji="🔁",
        i18n_key="toggle_scheduled_action",
        visible=True,
        category="tool",
    ),
    tool_category="update",
    version="1.0.0",
    updated_at=datetime.now(UTC),
)
