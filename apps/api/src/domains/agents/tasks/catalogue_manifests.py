"""
Catalogue manifests for Google Tasks tools.
Optimized for orchestration efficiency.

Architecture Simplification (2026-01):
- get_tasks_tool replaces list_tasks_tool + get_task_details_tool
- Always returns full task content (notes, timestamps)
- Supports filter mode (list) OR ID mode (direct fetch)
"""

from src.core.config import settings
from src.core.constants import (
    GOOGLE_TASKS_SCOPES,
    TASKS_TOOL_DEFAULT_LIMIT,
)
from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    OutputFieldSchema,
    ParameterConstraint,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)

# ============================================================================
# 1. GET TASKS (Unified - replaces list + details)
# ============================================================================
_get_tasks_desc = (
    "**Tool: get_tasks_tool** - Get tasks with full details.\n"
    "\n"
    "**MODES**:\n"
    "- List mode: get_tasks_tool() → list pending tasks with full details\n"
    "- ID mode: get_tasks_tool(task_id='abc123') → fetch specific task\n"
    "- Batch mode: get_tasks_tool(task_ids=['abc', 'def']) → fetch multiple tasks\n"
    "- Filter mode: get_tasks_tool(only_completed=True) → filter by status\n"
    "\n"
    "**SEARCHABLE FIELDS**: NONE - Google Tasks API has no text search.\n"
    "- All filtering (by title, notes, due date): Response LLM filters results\n"
    "- Always retrieves all tasks, LLM filters based on user criteria\n"
    "\n"
    "**COMMON USE CASES**:\n"
    "- 'my tasks' → list mode (no params)\n"
    "- 'show my todo list' → list mode\n"
    "- 'details of this task' → task_id='ID from context'\n"
    "- 'completed tasks' → only_completed=True\n"
    "- 'tasks about project X' → list mode, Response LLM filters by title/notes\n"
    "\n"
    "**Filtering**: Default=PENDING only. Use filters to see COMPLETED.\n"
    "**RETURNS**: Full task info (title, notes, due date, timestamps)."
)

get_tasks_catalogue_manifest = ToolManifest(
    name="get_tasks_tool",
    agent="task_agent",
    description=_get_tasks_desc,
    # Discriminant phrases - Task management operations
    semantic_keywords=[
        # Task listing from task manager
        "show my todo list from Google Tasks",
        "list pending tasks in my task manager",
        "what tasks do I need to complete",
        "display my to-do items from Tasks",
        # Task status and details
        "show task due date and notes",
        "get details of specific task item",
        "when is my task due in Tasks app",
        "check task completion status",
        # Task filtering
        "show completed tasks from task list",
        "unfinished items in my todo manager",
        "tasks by due date from Google Tasks",
    ],
    parameters=[
        # ID mode parameters
        ParameterSchema(
            name="task_id",
            type="string",
            required=False,
            description="Single task ID for direct fetch.",
        ),
        ParameterSchema(
            name="task_ids",
            type="array",
            required=False,
            description="Multiple task IDs for batch fetch.",
        ),
        # Filter parameters
        ParameterSchema(
            name="only_completed",
            type="boolean",
            required=False,
            description="Filter: Finished only",
        ),
        ParameterSchema(
            name="show_completed",
            type="boolean",
            required=False,
            description="Filter: All (Pending + Finished)",
        ),
        # Common options
        ParameterSchema(
            name="task_list_id",
            type="string",
            required=False,
            description="Target list ID (def: default list)",
        ),
        ParameterSchema(
            name="max_results",
            type="integer",
            required=False,
            description=f"Max (def: {TASKS_TOOL_DEFAULT_LIMIT}, max: {settings.tasks_tool_default_max_results})",
            constraints=[
                ParameterConstraint(kind="maximum", value=settings.tasks_tool_default_max_results)
            ],
        ),
    ],
    outputs=[
        # Full task outputs (merged from list + details)
        OutputFieldSchema(
            path="tasks", type="array", description="List of tasks with full details"
        ),
        OutputFieldSchema(
            path="tasks[].id", type="string", description="Task ID", semantic_type="task_id"
        ),
        OutputFieldSchema(path="tasks[].title", type="string", description="Title"),
        OutputFieldSchema(
            path="tasks[].status", type="string", description="Status", semantic_type="task_status"
        ),
        OutputFieldSchema(
            path="tasks[].due",
            type="string",
            nullable=True,
            description="Due date",
            semantic_type="datetime",
        ),
        OutputFieldSchema(path="tasks[].notes", type="string", nullable=True, description="Notes"),
        OutputFieldSchema(
            path="tasks[].updated",
            type="string",
            description="Last updated",
            semantic_type="datetime",
        ),
        OutputFieldSchema(
            path="tasks[].self_link",
            type="string",
            nullable=True,
            description="Link",
            semantic_type="URL",
        ),
        OutputFieldSchema(path="total", type="integer", description="Count"),
    ],
    cost=CostProfile(est_tokens_in=100, est_tokens_out=500, est_cost_usd=0.001, est_latency_ms=400),
    permissions=PermissionProfile(
        required_scopes=GOOGLE_TASKS_SCOPES, hitl_required=False, data_classification="CONFIDENTIAL"
    ),
    context_key="tasks",
    reference_examples=["tasks[0].id", "tasks[0].title", "tasks[0].notes", "total"],
    version="2.0.0",
    maintainer="Team Agents",
    display=DisplayMetadata(emoji="✓", i18n_key="get_tasks", visible=True, category="tool"),
)


# ============================================================================
# 2. CREATE TASK
# ============================================================================
_create_desc = (
    "**Tool: create_task_tool** - Create new task. **REQUIRES HITL**.\n"
    "**Dates**: Use ISO 8601 (YYYY-MM-DD)."
)

create_task_catalogue_manifest = ToolManifest(
    name="create_task_tool",
    agent="task_agent",
    description=_create_desc,
    # Discriminant phrases - Task creation
    semantic_keywords=[
        "create new task in my Google Tasks",
        "add item to my todo list manager",
        "put something on my task list",
        "add to-do with due date in Tasks",
        "schedule new task to complete later",
    ],
    parameters=[
        ParameterSchema(
            name="title",
            type="string",
            required=True,
            description="Title",
            constraints=[ParameterConstraint(kind="min_length", value=1)],
        ),
        ParameterSchema(name="due", type="string", required=False, description="Due date (ISO)"),
        ParameterSchema(name="notes", type="string", required=False, description="Description"),
        ParameterSchema(
            name="task_list_id", type="string", required=False, description="Target list ID"
        ),
    ],
    outputs=[
        OutputFieldSchema(
            path="task_id", type="string", description="Created ID", semantic_type="task_id"
        ),
        OutputFieldSchema(path="title", type="string", description="Title"),
        OutputFieldSchema(
            path="due",
            type="string",
            nullable=True,
            description="Due date",
            semantic_type="datetime",
        ),
        OutputFieldSchema(path="self_link", type="string", description="Link", semantic_type="URL"),
    ],
    cost=CostProfile(est_tokens_in=150, est_tokens_out=100, est_cost_usd=0.005, est_latency_ms=500),
    permissions=PermissionProfile(
        required_scopes=GOOGLE_TASKS_SCOPES,
        # hitl_required=False: HITL is handled by draft_critique (preview before creation)
        # Avoids double HITL: approval_gate (plan) + draft_critique (content)
        hitl_required=False,
        data_classification="CONFIDENTIAL",
    ),
    max_iterations=1,
    supports_dry_run=True,
    reference_examples=["task_id", "title"],
    version="1.0.0",
    maintainer="Team Agents",
    display=DisplayMetadata(emoji="➕", i18n_key="create_task", visible=True, category="tool"),
)

# ============================================================================
# 3. COMPLETE TASK
# ============================================================================
_complete_desc = "**Tool: complete_task_tool** - Mark task as completed. **REQUIRES HITL**."

complete_task_catalogue_manifest = ToolManifest(
    name="complete_task_tool",
    agent="task_agent",
    description=_complete_desc,
    # Discriminant phrases - Task completion
    semantic_keywords=[
        "mark task as completed in Google Tasks",
        "check off item from todo list",
        "finish task and mark it done",
        "complete to-do item in task manager",
    ],
    parameters=[
        ParameterSchema(name="task_id", type="string", required=True, description="Task ID"),
        ParameterSchema(
            name="task_list_id", type="string", required=False, description="List ID (if known)"
        ),
    ],
    outputs=[
        OutputFieldSchema(path="task_id", type="string", description="ID", semantic_type="task_id"),
        OutputFieldSchema(
            path="status", type="string", description="New status", semantic_type="task_status"
        ),
        OutputFieldSchema(path="title", type="string", description="Title"),
    ],
    cost=CostProfile(est_tokens_in=100, est_tokens_out=80, est_cost_usd=0.003, est_latency_ms=400),
    permissions=PermissionProfile(
        required_scopes=GOOGLE_TASKS_SCOPES,
        # hitl_required=False: HITL is handled by draft_critique (preview before modification)
        # Avoids double HITL: approval_gate (plan) + draft_critique (content)
        hitl_required=False,
        data_classification="CONFIDENTIAL",
    ),
    max_iterations=1,
    reference_examples=["task_id", "status"],
    version="1.0.0",
    maintainer="Team Agents",
    display=DisplayMetadata(emoji="✅", i18n_key="complete_task", visible=True, category="tool"),
)

# ============================================================================
# 4. UPDATE TASK
# ============================================================================
_update_desc = (
    "**Tool: update_task_tool** - Modify task details. **REQUIRES HITL**.\n"
    "Only provided fields are updated."
)

update_task_catalogue_manifest = ToolManifest(
    name="update_task_tool",
    agent="task_agent",
    description=_update_desc,
    # Discriminant phrases - Task modification
    semantic_keywords=[
        "update task details in Google Tasks",
        "change due date of todo item",
        "edit task notes or title",
        "reschedule task to different date",
        "modify to-do item in task manager",
    ],
    parameters=[
        ParameterSchema(name="task_id", type="string", required=True, description="Task ID"),
        ParameterSchema(name="title", type="string", required=False, description="New title"),
        ParameterSchema(name="notes", type="string", required=False, description="New notes"),
        ParameterSchema(name="due", type="string", required=False, description="New due date"),
        ParameterSchema(
            name="status", type="string", required=False, description="'needsAction' or 'completed'"
        ),
        ParameterSchema(name="task_list_id", type="string", required=False, description="List ID"),
    ],
    outputs=[
        OutputFieldSchema(path="task_id", type="string", description="ID", semantic_type="task_id"),
        OutputFieldSchema(path="title", type="string", description="Title"),
        OutputFieldSchema(
            path="status", type="string", description="Status", semantic_type="task_status"
        ),
        OutputFieldSchema(
            path="due", type="string", nullable=True, description="Due", semantic_type="datetime"
        ),
        OutputFieldSchema(path="notes", type="string", nullable=True, description="Notes"),
    ],
    cost=CostProfile(est_tokens_in=150, est_tokens_out=100, est_cost_usd=0.005, est_latency_ms=500),
    permissions=PermissionProfile(
        required_scopes=GOOGLE_TASKS_SCOPES,
        # hitl_required=False: HITL is handled by draft_critique (preview before modification)
        # Avoids double HITL: approval_gate (plan) + draft_critique (content)
        hitl_required=False,
        data_classification="CONFIDENTIAL",
    ),
    max_iterations=1,
    supports_dry_run=True,
    reference_examples=["task_id", "title"],
    version="1.0.0",
    maintainer="Team Agents",
    display=DisplayMetadata(emoji="✏️", i18n_key="update_task", visible=True, category="tool"),
)

# ============================================================================
# 5. DELETE TASK
# ============================================================================
_delete_desc = "**Tool: delete_task_tool** - Delete task. **REQUIRES HITL**. Irreversible."

delete_task_catalogue_manifest = ToolManifest(
    name="delete_task_tool",
    agent="task_agent",
    description=_delete_desc,
    # Discriminant phrases - Task deletion
    semantic_keywords=[
        "delete task from Google Tasks permanently",
        "remove item from todo list manager",
        "cancel task and remove from list",
    ],
    parameters=[
        ParameterSchema(name="task_id", type="string", required=True, description="ID to delete"),
        ParameterSchema(name="task_list_id", type="string", required=False, description="List ID"),
    ],
    outputs=[
        OutputFieldSchema(path="success", type="boolean", description="Success"),
        OutputFieldSchema(
            path="task_id", type="string", description="Deleted ID", semantic_type="task_id"
        ),
        OutputFieldSchema(path="message", type="string", description="Msg"),
    ],
    cost=CostProfile(est_tokens_in=100, est_tokens_out=50, est_cost_usd=0.003, est_latency_ms=400),
    permissions=PermissionProfile(
        required_scopes=GOOGLE_TASKS_SCOPES,
        # hitl_required=False: HITL is handled by draft_critique (preview before deletion)
        # Avoids double HITL: approval_gate (plan) + draft_critique (content)
        hitl_required=False,
        data_classification="CONFIDENTIAL",
    ),
    max_iterations=1,
    supports_dry_run=False,
    reference_examples=["success", "task_id"],
    version="1.0.0",
    maintainer="Team Agents",
    display=DisplayMetadata(emoji="🗑️", i18n_key="delete_task", visible=True, category="tool"),
)

# ============================================================================
# 6. LIST TASK LISTS
# ============================================================================
_lists_desc = "**Tool: list_task_lists_tool** - List available task lists to find 'task_list_id'."

list_task_lists_catalogue_manifest = ToolManifest(
    name="list_task_lists_tool",
    agent="task_agent",
    description=_lists_desc,
    # Discriminant phrases - Task list containers
    semantic_keywords=[
        "show all my task lists in Google Tasks",
        "list available todo list containers",
        "which task lists do I have",
    ],
    parameters=[
        ParameterSchema(
            name="max_results",
            type="integer",
            required=False,
            description=f"Max (def: {TASKS_TOOL_DEFAULT_LIMIT}, max: {settings.tasks_tool_default_max_results})",
            constraints=[
                ParameterConstraint(kind="maximum", value=settings.tasks_tool_default_max_results)
            ],
        ),
    ],
    outputs=[
        OutputFieldSchema(path="task_lists", type="array", description="Lists"),
        OutputFieldSchema(
            path="task_lists[].id",
            type="string",
            description="ID",
            semantic_type="task_list_id",
        ),
        OutputFieldSchema(path="task_lists[].title", type="string", description="Title"),
        OutputFieldSchema(path="total", type="integer", description="Count"),
    ],
    cost=CostProfile(est_tokens_in=50, est_tokens_out=150, est_cost_usd=0.001, est_latency_ms=300),
    permissions=PermissionProfile(
        required_scopes=GOOGLE_TASKS_SCOPES, hitl_required=False, data_classification="CONFIDENTIAL"
    ),
    context_key="tasks",
    reference_examples=["task_lists[0].id", "task_lists[0].title"],
    version="1.0.0",
    maintainer="Team Agents",
    display=DisplayMetadata(emoji="📚", i18n_key="list_task_lists", visible=True, category="tool"),
)

__all__ = [
    # Unified tool (v2.0 - replaces list + details)
    "get_tasks_catalogue_manifest",
    # Action tools
    "create_task_catalogue_manifest",
    "update_task_catalogue_manifest",
    "delete_task_catalogue_manifest",
    "complete_task_catalogue_manifest",
    # Metadata tools (list containers, not items)
    "list_task_lists_catalogue_manifest",
]
