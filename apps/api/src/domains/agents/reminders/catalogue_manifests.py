"""
Catalogue manifests for Reminder tools.

Defines agent and tool manifests for the reminder system.
These are internal tools (no OAuth required).
"""

from datetime import UTC, datetime

from src.core.constants import DEFAULT_TOOL_TIMEOUT_MS
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
# Agent Manifest: reminder_agent
# =============================================================================

REMINDER_AGENT_MANIFEST = AgentManifest(
    name="reminder_agent",
    description=(
        "Agent specialized in reminder management. "
        "Create, list and cancel reminders. "
        "Reminders are sent via push notification (FCM) at the scheduled time. "
        "Supports natural temporal references ('in 5 minutes', 'tomorrow at noon')."
    ),
    tools=[
        "create_reminder_tool",
        "list_reminders_tool",
        "cancel_reminder_tool",
    ],
    max_parallel_runs=1,
    default_timeout_ms=DEFAULT_TOOL_TIMEOUT_MS,
    prompt_version="v1",
    owner_team="Team AI",
    version="1.0.0",
    updated_at=datetime.now(UTC),
    display=DisplayMetadata(
        emoji="🔔",
        i18n_key="reminder_agent",
        visible=True,
        category="agent",
    ),
)


# =============================================================================
# Tool Manifest: create_reminder_tool
# =============================================================================

create_reminder_catalogue_manifest = ToolManifest(
    name="create_reminder_tool",
    agent="reminder_agent",
    description=(
        "Creates a reminder for the user. "
        "The reminder will be sent as a push notification (FCM) "
        "and recorded in conversation history at the scheduled time. "
        "Use trigger_datetime for fixed times, or relative_trigger for FOR_EACH "
        "(e.g., 'day before each event at 19:00')."
    ),
    parameters=[
        ParameterSchema(
            name="content",
            type="string",
            required=True,
            description=(
                "What the user wants to be reminded about. "
                "For FOR_EACH: MUST reference item data (e.g., $item.summary, $item.name) "
                "to make each reminder identifiable. Static text = all reminders identical."
            ),
            constraints=[
                ParameterConstraint(kind="min_length", value=1),
                ParameterConstraint(kind="max_length", value=500),
            ],
        ),
        ParameterSchema(
            name="trigger_datetime",
            type="string",
            required=False,
            description=(
                "ISO date/time of the reminder in user's LOCAL time "
                "(e.g., 2025-12-29T10:00:00). Use for FIXED time reminders. "
                "Mutually exclusive with relative_trigger."
            ),
            constraints=[
                ParameterConstraint(
                    kind="pattern", value=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?$"
                ),
            ],
        ),
        ParameterSchema(
            name="relative_trigger",
            type="string",
            required=False,
            description=(
                "Relative trigger for FOR_EACH: 'ISO_DATETIME|OFFSET|@TIME'. "
                "Use when reminder is RELATIVE to an event datetime. "
                "Examples: '$item.start.dateTime|-1d|@19:00' (day before at 19h), "
                "'$item.start.dateTime|-2h' (2h before). "
                "Offsets: -1d (days), -2h (hours), -30m (minutes). "
                "Mutually exclusive with trigger_datetime."
            ),
            constraints=[
                ParameterConstraint(
                    kind="pattern",
                    value=r"^.+\|[+-]?\d+[dhm](\|@?\d{2}:\d{2})?$",  # @TIME prefix optional
                ),
            ],
        ),
        ParameterSchema(
            name="original_message",
            type="string",
            required=True,
            description="User's complete original message (for context)",
            constraints=[
                ParameterConstraint(kind="min_length", value=1),
            ],
        ),
    ],
    outputs=[
        OutputFieldSchema(
            path="success",
            type="boolean",
            description="Whether creation succeeded",
        ),
        OutputFieldSchema(
            path="reminder_id",
            type="string",
            description="UUID of the created reminder",
            semantic_type="reminder_id",
        ),
        OutputFieldSchema(
            path="message",
            type="string",
            description="Confirmation message with formatted date",
        ),
        OutputFieldSchema(
            path="trigger_at_formatted",
            type="string",
            description="Date/time formatted in user's timezone",
            semantic_type="trigger_datetime",
        ),
    ],
    cost=CostProfile(
        est_tokens_in=50,
        est_tokens_out=100,
        est_cost_usd=0.0001,
        est_latency_ms=200,
    ),
    permissions=PermissionProfile(
        required_scopes=[],  # Internal tool, no OAuth
        data_classification="CONFIDENTIAL",
        hitl_required=False,
    ),
    # Discriminant phrases - Reminder creation
    semantic_keywords=[
        # Create time-based reminder
        "remind me to do something at specific time",
        "set a reminder for tomorrow morning notification",
        "alert me with a reminder in X minutes with push notification",
        "create a reminder to not forget something",
        # Schedule notification
        "schedule a reminder for later time",
        "set a reminder at specific hour",
        "reminder me about something at future time",
        "don't let me forget to do this",
    ],
    reference_examples=[
        "reminder_id",
        "trigger_at_formatted",
    ],
    display=DisplayMetadata(
        emoji="➕",
        i18n_key="create_reminder",
        visible=True,
        category="tool",
    ),
    tool_category="create",
    version="1.0.0",
    updated_at=datetime.now(UTC),
)


# =============================================================================
# Tool Manifest: list_reminders_tool
# =============================================================================

list_reminders_catalogue_manifest = ToolManifest(
    name="list_reminders_tool",
    agent="reminder_agent",
    description=(
        "Lists user's pending reminders. "
        "Returns all reminders with 'pending' status, "
        "sorted by trigger time ascending."
    ),
    parameters=[],  # No parameters needed
    outputs=[
        OutputFieldSchema(
            path="success",
            type="boolean",
            description="Whether the request succeeded",
        ),
        OutputFieldSchema(
            path="reminders",
            type="array",
            description="List of pending reminders",
        ),
        OutputFieldSchema(
            path="reminders[].id",
            type="string",
            description="Reminder UUID",
            semantic_type="reminder_id",
        ),
        OutputFieldSchema(
            path="reminders[].content",
            type="string",
            description="Reminder content",
            semantic_type="text",
        ),
        OutputFieldSchema(
            path="reminders[].trigger_at_formatted",
            type="string",
            description="Formatted date/time",
            semantic_type="trigger_datetime",
        ),
        OutputFieldSchema(
            path="total",
            type="integer",
            description="Total number of reminders",
        ),
        OutputFieldSchema(
            path="message",
            type="string",
            description="Formatted list for display",
        ),
    ],
    cost=CostProfile(
        est_tokens_in=30,
        est_tokens_out=200,
        est_cost_usd=0.0001,
        est_latency_ms=150,
    ),
    permissions=PermissionProfile(
        required_scopes=[],  # Internal tool, no OAuth
        data_classification="CONFIDENTIAL",
        hitl_required=False,
    ),
    # Discriminant phrases - Reminder listing
    semantic_keywords=[
        "show all my pending reminders list",
        "what reminders do I have scheduled",
        "list upcoming notifications and alerts",
        "display my active reminder items",
        "check if I have any reminders set",
    ],
    reference_examples=[
        "reminders[0].id",
        "reminders[*].content",
        "total",
    ],
    display=DisplayMetadata(
        emoji="📋",
        i18n_key="list_reminders",
        visible=True,
        category="tool",
    ),
    tool_category="search",
    version="1.0.0",
    updated_at=datetime.now(UTC),
)


# =============================================================================
# Tool Manifest: cancel_reminder_tool
# =============================================================================

cancel_reminder_catalogue_manifest = ToolManifest(
    name="cancel_reminder_tool",
    agent="reminder_agent",
    description=(
        "Cancels a pending reminder. "
        "Can identify reminder by direct UUID or natural reference "
        "('next', 'the next one')."
    ),
    parameters=[
        ParameterSchema(
            name="reminder_identifier",
            type="string",
            required=True,
            description=(
                "Reminder ID (UUID) or natural reference "
                "('next' for the next scheduled reminder)"
            ),
            constraints=[
                ParameterConstraint(kind="min_length", value=1),
            ],
        ),
    ],
    outputs=[
        OutputFieldSchema(
            path="success",
            type="boolean",
            description="Whether cancellation succeeded",
        ),
        OutputFieldSchema(
            path="reminder_id",
            type="string",
            description="UUID of cancelled reminder",
            semantic_type="reminder_id",
        ),
        OutputFieldSchema(
            path="content",
            type="string",
            description="Content of cancelled reminder",
            semantic_type="text",
        ),
        OutputFieldSchema(
            path="message",
            type="string",
            description="Confirmation message",
        ),
    ],
    cost=CostProfile(
        est_tokens_in=40,
        est_tokens_out=80,
        est_cost_usd=0.0001,
        est_latency_ms=150,
    ),
    permissions=PermissionProfile(
        required_scopes=[],  # Internal tool, no OAuth
        data_classification="CONFIDENTIAL",
        hitl_required=True,
    ),
    # Discriminant phrases - Reminder cancellation
    semantic_keywords=[
        "cancel scheduled reminder notification",
        "delete pending reminder from list",
        "remove this reminder don't notify me",
        "stop upcoming reminder alert",
        "dismiss reminder I don't need it",
    ],
    reference_examples=[
        "reminder_id",
        "content",
    ],
    display=DisplayMetadata(
        emoji="❌",
        i18n_key="cancel_reminder",
        visible=True,
        category="tool",
    ),
    tool_category="delete",
    version="1.0.0",
    updated_at=datetime.now(UTC),
)


__all__ = [
    "REMINDER_AGENT_MANIFEST",
    "cancel_reminder_catalogue_manifest",
    "create_reminder_catalogue_manifest",
    "list_reminders_catalogue_manifest",
]
