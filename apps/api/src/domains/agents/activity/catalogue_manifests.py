"""Catalogue manifests for the activity tool (ADR-318).

What LIA did and consulted for the person over a period, read from its own
registers (ADR-263): the effect register lists the actions, the consultation
register counts the reads per domain. Internal, no OAuth, read-only, unflagged —
the registers exist on every deployment. The vocabularies published here are the
registers' own, pinned to their enums by a test; the bounds are the settings the
tool enforces (ADR-184).
"""

from datetime import UTC, datetime
from typing import Literal, get_args

from src.core.config import settings
from src.core.date_contract import ISO_MOMENT_DESCRIPTION
from src.domains.agents.constants import AGENT_ACTIVITY
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

#: Whose initiative a reading keeps — the register tabs' own vocabulary
#: (``RegisterOrigin``), pinned to it by a test.
ActivityOrigin = Literal["mine", "initiative", "all"]
#: An action's outcome — the effect register's vocabulary (``EffectStatus``).
ActivityStatus = Literal["succeeded", "failed", "refused", "claimed", "abandoned"]

ACTIVITY_ORIGINS: tuple[str, ...] = get_args(ActivityOrigin)
ACTIVITY_STATUSES: tuple[str, ...] = get_args(ActivityStatus)

#: The wording of the tool's parameters, read by the manifest AND the schema.
ACTIVITY_START_DESCRIPTION = (
    f"First day (or instant) of the period, inclusive. {ISO_MOMENT_DESCRIPTION} Omitted: "
    f"{settings.effect_activity_window_days} days before the end."
)
ACTIVITY_END_DESCRIPTION = (
    "Last day of the period, inclusive (an instant is exclusive). "
    f"{ISO_MOMENT_DESCRIPTION} Omitted: now."
)
ACTIVITY_ORIGIN_DESCRIPTION = (
    "Whose initiative: mine (what the user set in motion — typed, their routines, their "
    "delegations), initiative (what LIA did on its own), all (the default)."
)
ACTIVITY_STATUS_DESCRIPTION = (
    "Only the actions with this outcome: succeeded, failed, refused (not attempted: the "
    "authority was missing), claimed (in progress), abandoned. Omitted: every outcome."
)
ACTIVITY_MAX_RESULTS_DESCRIPTION = (
    f"Most actions to list, 1 to {settings.effect_activity_max_actions} (default: the "
    "maximum). The totals are always exact."
)

# =============================================================================
# Agent Manifest: activity_agent
# =============================================================================

ACTIVITY_AGENT_MANIFEST = AgentManifest(
    name=AGENT_ACTIVITY,
    description=(
        "Agent for what LIA did and consulted for the user, read from its own "
        "transparency registers: the actions it performed and the data it read, "
        "over a period, with exact totals. Read-only."
    ),
    tools=["get_my_activity_tool"],
    max_parallel_runs=2,
    default_timeout_ms=settings.default_tool_timeout_ms,
    display=DisplayMetadata(emoji="🗂️", i18n_key="activity_agent", visible=True, category="agent"),
    version="1.0.0",
    updated_at=datetime.now(UTC),
)


# =============================================================================
# Tool Manifest: get_my_activity_tool
# =============================================================================

get_my_activity_catalogue_manifest = ToolManifest(
    name="get_my_activity_tool",
    agent=AGENT_ACTIVITY,
    description=(
        "**Tool: get_my_activity_tool** - What LIA DID and CONSULTED for the user over a "
        "period, from its own registers: the actions it performed (messages sent, events "
        "created, notifications…), newest first, with their outcome and who initiated "
        "them; and how many times it read each kind of data (e-mails, calendar, "
        "weather…). Every total is exact, even when the list is shortened. Use it for "
        "'what did you do for me this week', 'did you send it', 'what did you do on your "
        "own'. NOT the user's own agenda or tasks (event, task)."
    ),
    parameters=[
        ParameterSchema(
            name="start_date",
            type="string",
            required=False,
            description=ACTIVITY_START_DESCRIPTION,
            semantic_type="datetime",
        ),
        ParameterSchema(
            name="end_date",
            type="string",
            required=False,
            description=ACTIVITY_END_DESCRIPTION,
            semantic_type="datetime",
        ),
        ParameterSchema(
            name="origin",
            type="string",
            required=False,
            description=ACTIVITY_ORIGIN_DESCRIPTION,
            constraints=[ParameterConstraint(kind="enum", value=list(ACTIVITY_ORIGINS))],
        ),
        ParameterSchema(
            name="status",
            type="string",
            required=False,
            description=ACTIVITY_STATUS_DESCRIPTION,
            constraints=[ParameterConstraint(kind="enum", value=list(ACTIVITY_STATUSES))],
        ),
        ParameterSchema(
            name="max_results",
            type="integer",
            required=False,
            description=ACTIVITY_MAX_RESULTS_DESCRIPTION,
            constraints=[
                ParameterConstraint(kind="minimum", value=1),
                ParameterConstraint(kind="maximum", value=settings.effect_activity_max_actions),
            ],
        ),
    ],
    outputs=[
        OutputFieldSchema(path="period", type="object", description="from, to, timezone"),
        OutputFieldSchema(path="actions", type="array", description="The newest actions"),
        OutputFieldSchema(
            path="actions[].action", type="string", description="What was done, in words"
        ),
        OutputFieldSchema(path="actions[].status", type="string", description="Its outcome"),
        OutputFieldSchema(path="actions[].when", type="string", description="Local ISO time"),
        OutputFieldSchema(
            path="actions_total", type="integer", description="EXACT count of matching actions"
        ),
        OutputFieldSchema(
            path="actions_by_status", type="object", description="EXACT count per outcome"
        ),
        OutputFieldSchema(
            path="consultations", type="array", description="Reads per kind of data, exact"
        ),
        OutputFieldSchema(
            path="consultations_total", type="integer", description="EXACT count of reads"
        ),
        OutputFieldSchema(
            path="count", type="integer", description="EXACT actions + consultations"
        ),
    ],
    cost=CostProfile(est_tokens_in=40, est_tokens_out=600, est_cost_usd=0.0, est_latency_ms=150),
    permissions=PermissionProfile(
        required_scopes=[], data_classification="CONFIDENTIAL", hitl_required=False
    ),
    semantic_keywords=[
        "what did you do for me this week",
        "did you send the message I asked for",
        "what actions did you take on your own",
        "what did you read or check for me today",
        "history of what the assistant did",
    ],
    reference_examples=["actions_total", "actions[0].action"],
    display=DisplayMetadata(emoji="🗂️", i18n_key="get_my_activity", visible=True, category="tool"),
    tool_category="search",
    # LIA's own record, not an enrichment of the person's request.
    initiative_eligible=False,
    version="1.0.0",
    updated_at=datetime.now(UTC),
)


__all__ = [
    "ACTIVITY_AGENT_MANIFEST",
    "ACTIVITY_END_DESCRIPTION",
    "ACTIVITY_MAX_RESULTS_DESCRIPTION",
    "ACTIVITY_ORIGINS",
    "ACTIVITY_ORIGIN_DESCRIPTION",
    "ACTIVITY_START_DESCRIPTION",
    "ACTIVITY_STATUSES",
    "ACTIVITY_STATUS_DESCRIPTION",
    "ActivityOrigin",
    "ActivityStatus",
    "get_my_activity_catalogue_manifest",
]
