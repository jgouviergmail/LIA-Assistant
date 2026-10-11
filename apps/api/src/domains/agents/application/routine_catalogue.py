"""Explicit desired routine state, always prepared for exact human confirmation."""

from src.domains.agents.application.routine_create_schemas import RoutineCreateRequest
from src.domains.agents.application.routine_read_schemas import RoutineRead
from src.domains.agents.application.routine_removal_schemas import RoutineDeleteRequest
from src.domains.agents.application.routine_run_schemas import RoutineRunRequest
from src.domains.agents.application.routine_schemas import RoutineStateRequest
from src.domains.agents.application.routine_update_schemas import RoutineUpdateRequest
from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    OutputFieldSchema,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)

ROUTINE_RUN_MANIFEST = ToolManifest(
    name="execute_lia_routine_tool",
    agent="setting_agent",
    description="Prepare exact human confirmation to request one immediate owned Studio routine trigger. Read its current id and configuration first. No reservation or execution before confirmation. After approval, the source worker waits for the confirming chat turn to finish and uses the exact approved configuration, current account authority and platform switch. It retains condition, future-approval, pending-question and quota checks: a condition may be unmet, an approval notification may be proposed, or a limit may refuse work. The accepted launch is not completed execution. May incur the existing LLM costs/retries; inspect the routine's week/settings for the actual outcome. An ongoing execution conflicts. Never replay uncertain launch automatically.",
    parameters=[
        ParameterSchema(
            name="selection",
            type="object",
            required=True,
            description="Owned routine id from Studio reader",
            schema=RoutineRunRequest.model_json_schema(),
        )
    ],
    outputs=[
        OutputFieldSchema(
            path="draft", type="object", description="Pending exact manual-trigger confirmation"
        )
    ],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    mutation_policy="draft",
    tool_category="update",
    binding_unit="lia_routines",
    semantic_keywords=["run my routine now", "test this automation"],
    display=DisplayMetadata(emoji="▶️", i18n_key="execute_lia_routine", category="tool"),
)

ROUTINE_UPDATE_MANIFEST = ToolManifest(
    name="update_lia_routine_tool",
    agent="setting_agent",
    description="Prepare exact human confirmation to edit one owned Studio routine. Read its id and current settings first. Supply only the requested changes; omitted settings are preserved. The source validates exactly one clock and drops the previous clock when switching modes. Preview includes the complete resulting instruction, schedule or condition, future approval mandate, execution mode, timezone and enabled state. A future clock may revive a completed routine; an explicit pause remains paused. No immediate run. Future runs follow these settings and existing LLM quotas/costs. A stale configuration requires a new proposal. Never automatically replay uncertain completion.",
    parameters=[
        ParameterSchema(
            name="change",
            type="object",
            required=True,
            description="Owned routine id and nonempty sparse Studio changes",
            schema=RoutineUpdateRequest.model_json_schema(),
        )
    ],
    outputs=[
        OutputFieldSchema(path="draft", type="object", description="Pending exact confirmation")
    ],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    mutation_policy="draft",
    tool_category="update",
    binding_unit="lia_routines",
    semantic_keywords=["edit my routine", "change automation schedule", "change watch condition"],
    display=DisplayMetadata(emoji="🔁", i18n_key="update_lia_routine", category="tool"),
)

ROUTINE_STATE_MANIFEST = ToolManifest(
    name="set_lia_routine_state_tool",
    agent="setting_agent",
    description="Prepare exact human confirmation to pause or enable one owned routine. Read its id first. Set enabled explicitly; repeated enable requests never toggle it off. No write before confirmation. Configuration changes require a fresh proposal. Pausing stops future triggers and lets an already running execution finish. Enabling resets the source clock and error state, while preserving a running execution reservation.",
    parameters=[
        ParameterSchema(
            name="change",
            type="object",
            required=True,
            description="Owned routine id and desired enabled boolean",
            schema=RoutineStateRequest.model_json_schema(),
        )
    ],
    outputs=[
        OutputFieldSchema(path="draft", type="object", description="Pending exact confirmation")
    ],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    mutation_policy="draft",
    tool_category="update",
    binding_unit="lia_routines",
    semantic_keywords=["pause my routine", "enable my automation", "resume my scheduled action"],
    display=DisplayMetadata(emoji="🔁", i18n_key="set_lia_routine_state", category="tool"),
)

ROUTINE_DELETE_MANIFEST = ToolManifest(
    name="delete_lia_routine_tool",
    agent="setting_agent",
    description="Prepare exact human confirmation to permanently delete one owned routine and its run history through the Studio source cascade. Deletion stops future triggers; an already running execution may finish and incur its existing costs. Configuration changes require a new proposal. No deletion before confirmation; never substitute another routine or retry an uncertain commit automatically.",
    parameters=[
        ParameterSchema(
            name="selection",
            type="object",
            required=True,
            description="Owned routine id from the reader",
            schema=RoutineDeleteRequest.model_json_schema(),
        )
    ],
    outputs=[
        OutputFieldSchema(path="draft", type="object", description="Pending exact confirmation")
    ],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    mutation_policy="draft",
    tool_category="delete",
    binding_unit="lia_routines",
    semantic_keywords=["delete my automation", "remove this routine"],
    display=DisplayMetadata(emoji="🗑️", i18n_key="delete_lia_routine", category="tool"),
)

ROUTINE_CREATE_MANIFEST = ToolManifest(
    name="create_lia_routine_tool",
    agent="setting_agent",
    description="Prepare exact human confirmation to create an owned Studio routine, time-based or condition-based. Use the Studio recurrence and condition contracts; exactly one clock. Configuration includes the full instruction, approval requirement for future triggers, and execution mode. The account timezone is resolved before preview and must remain current. Creation starts no run now; future executions follow the confirmed configuration and existing quotas and may incur LLM costs. No database write before confirmation. To duplicate a routine, read its configuration and prepare a distinct creation with the requested title.",
    parameters=[
        ParameterSchema(
            name="configuration",
            type="object",
            required=True,
            description="Full Studio configuration; timezone and ownership are resolved by the application",
            schema=RoutineCreateRequest.model_json_schema(),
        )
    ],
    outputs=[
        OutputFieldSchema(path="draft", type="object", description="Pending exact confirmation")
    ],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    mutation_policy="draft",
    tool_category="create",
    binding_unit="lia_routines",
    semantic_keywords=["create a routine", "watch incoming mail", "duplicate my automation"],
    display=DisplayMetadata(emoji="🔁", i18n_key="create_lia_routine", category="tool"),
)

ROUTINE_READ_MANIFEST = ToolManifest(
    name="get_lia_routines_tool",
    agent="setting_agent",
    description="Read the current account's routine Studio settings or computed current week in bounded pages. Settings include the prompt, recurrence or condition, approval requirement, execution mode, enabled/error state, clock metadata and next occurrences. Week contains the actual scheduler slots and recorded outcomes. Use an optional owned routine id to narrow the result. Continue with after_id=next_cursor, which names the last routine actually shown. Pages use stable id order, distinct from the UI's next-trigger order. Never infer an absent run or zero from incomplete results. This read never starts a routine or accesses its private condition-fact ledger.",
    parameters=[
        ParameterSchema(
            name="query",
            type="object",
            required=False,
            description="Settings or current week, optionally narrowed to one owned routine id",
            schema=RoutineRead.model_json_schema(),
        )
    ],
    outputs=[
        OutputFieldSchema(
            path="scheduled_actions[].id",
            type="string",
            description="Owned routine id",
            semantic_type="automation_id",
        ),
        OutputFieldSchema(
            path="scheduled_actions",
            type="array",
            description="The Studio's public configuration and clock metadata",
        ),
        OutputFieldSchema(
            path="actions",
            type="array",
            description="The source scheduler's current week and recorded outcomes",
        ),
        OutputFieldSchema(
            path="truncated", type="boolean", description="The source result omits owned routines"
        ),
        OutputFieldSchema(
            path="next_cursor",
            type="string",
            nullable=True,
            description="Last shown routine id; pass as after_id to continue",
        ),
    ],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    mutation_policy="read",
    tool_category="readonly",
    binding_unit="lia_routines",
    initiative_eligible=False,
    semantic_keywords=[
        "my routine settings",
        "which automation is paused",
        "when will my routine run",
        "routine execution this week",
    ],
    display=DisplayMetadata(emoji="📋", i18n_key="get_lia_routines", category="tool"),
)
