"""Bounded pending-reminder management view; future data, never notification history."""

from src.domains.agents.application.reminder_create_schemas import ReminderCreateRequest
from src.domains.agents.application.reminder_read_schemas import ReminderRead
from src.domains.agents.application.reminder_removal_schemas import ReminderDeleteRequest
from src.domains.agents.application.reminder_update_schemas import ReminderUpdateRequest
from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    OutputFieldSchema,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)

REMINDER_UPDATE_MANIFEST = ToolManifest(
    name="update_lia_reminder_tool",
    agent="setting_agent",
    description="Prepare human confirmation to edit an owned pending reminder's content, single instant or complete recurrence. Omitted fields remain unchanged. Never send null or both clocks. A repeating reminder moves through its recurrence, not a one-time trigger. Preview freezes the whole source result and first UTC trigger. If the source changes or the first occurrence passes, prepare a fresh confirmation. Content-only changes preserve the stored timezone and schedule. Writes nothing before approval; future reminder notifications retain existing LLM cost and quota accounting.",
    parameters=[
        ParameterSchema(
            name="selection",
            type="object",
            required=True,
            description="Exact owned reminder id and strict sparse changes",
            schema=ReminderUpdateRequest.model_json_schema(),
        )
    ],
    outputs=[
        OutputFieldSchema(
            path="draft", type="object", description="Pending exact edit confirmation"
        )
    ],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    mutation_policy="draft",
    tool_category="update",
    binding_unit="lia_reminders",
    initiative_eligible=False,
    semantic_keywords=["change my reminder", "move my reminder", "change reminder recurrence"],
    display=DisplayMetadata(emoji="⏰", i18n_key="update_lia_reminder", category="tool"),
)


REMINDER_DELETE_MANIFEST = ToolManifest(
    name="delete_lia_reminder_tool",
    agent="setting_agent",
    description="Prepare exact human confirmation to delete one owned pending reminder, including all remaining occurrences of a recurring reminder. The approved content, recurrence, next trigger, stored timezone and creation identity must remain current. A processing reminder is busy; a fired, removed or changed reminder requires a fresh selection. Never re-resolve a natural reference during execution. Deletion writes nothing before approval and cannot recall a notification already delivered.",
    parameters=[
        ParameterSchema(
            name="selection",
            type="object",
            required=True,
            description="Exact owned reminder id",
            schema=ReminderDeleteRequest.model_json_schema(),
        )
    ],
    outputs=[
        OutputFieldSchema(
            path="draft", type="object", description="Pending exact deletion confirmation"
        )
    ],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    mutation_policy="draft",
    tool_category="delete",
    binding_unit="lia_reminders",
    initiative_eligible=False,
    semantic_keywords=["delete my reminder", "cancel all occurrences of this reminder"],
    display=DisplayMetadata(emoji="🗑️", i18n_key="delete_lia_reminder", category="tool"),
)

REMINDERS_READ_MANIFEST = ToolManifest(
    name="get_lia_reminders_tool",
    agent="setting_agent",
    description="Read the current account's pending reminders with the management screen's content, next UTC trigger, stored timezone, recurrence, localized schedule, daily frequency, future occurrences and creation time. A reminder with no future is deleted: this is never sent-notification history. Select an owned reminder id or follow next_cursor with after_id. Stable id order differs from the UI's soonest-first order. Counts and truncation are explicit; never infer complete absence from a cut page. A processing reminder is busy. This read neither creates nor cancels reminders.",
    parameters=[
        ParameterSchema(
            name="query",
            type="object",
            required=False,
            description="Owned reminder id or bounded pending page",
            schema=ReminderRead.model_json_schema(),
        )
    ],
    outputs=[
        OutputFieldSchema(
            path="reminders[].id",
            type="string",
            description="Owned reminder id",
            semantic_type="reminder_id",
        ),
        OutputFieldSchema(path="reminders", type="array", description="Source management rows"),
        OutputFieldSchema(
            path="total_available", type="integer", description="Owned pending count"
        ),
        OutputFieldSchema(
            path="truncated", type="boolean", description="More pending reminders remain"
        ),
        OutputFieldSchema(
            path="next_cursor",
            type="string",
            nullable=True,
            description="Last actually shown id; use as after_id",
        ),
    ],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    mutation_policy="read",
    tool_category="readonly",
    binding_unit="lia_reminders",
    initiative_eligible=False,
    semantic_keywords=[
        "my reminder settings",
        "when will my reminder fire",
        "repeating reminder schedule",
    ],
    display=DisplayMetadata(emoji="🔔", i18n_key="get_lia_reminders", category="tool"),
)

REMINDER_CREATE_MANIFEST = ToolManifest(
    name="create_lia_reminder_tool",
    agent="setting_agent",
    description="Prepare exact human confirmation to create an owned reminder with its full content and either one explicit ISO datetime or a complete recurrence. Never supply both. The application resolves the account timezone and first UTC trigger; a changed timezone or elapsed approved trigger requires a fresh confirmation. Recurrence follows existing reminder limits. No reminder is written before approval. Original message is the user's reminder wording; never invent private metadata. Once its last occurrence fires, the reminder is deleted rather than stored as history.",
    parameters=[
        ParameterSchema(
            name="configuration",
            type="object",
            required=True,
            description="Reminder content and one clock; ownership and timezone are resolved by LIA",
            schema=ReminderCreateRequest.model_json_schema(),
        )
    ],
    outputs=[
        OutputFieldSchema(path="draft", type="object", description="Pending exact confirmation")
    ],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    mutation_policy="draft",
    tool_category="create",
    binding_unit="lia_reminders",
    initiative_eligible=False,
    semantic_keywords=["create a reminder", "remind me every morning", "remember tomorrow"],
    display=DisplayMetadata(emoji="🔔", i18n_key="create_lia_reminder", category="tool"),
)
