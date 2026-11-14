"""Catalogue manifests of what organises tasks (ADR-369, lot 9).

Out of ``catalogue_manifests.py``, at its size cap. Each runs at once: renaming a list and moving
a task are undone by one more call.
"""

from src.core.constants import GOOGLE_TASKS_SCOPES
from src.domains.agents.registry.catalogue import (
    REASON_UNDONE_BY_ONE_CALL,
    CostProfile,
    DisplayMetadata,
    OutputFieldSchema,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)
from src.domains.agents.tasks.parameter_descriptions import (
    TASK_LIST_NAMED_DESCRIPTION,
    TASK_LIST_OF_TASK_DESCRIPTION,
)

rename_task_list_catalogue_manifest = ToolManifest(
    name="rename_task_list_tool",
    mutation_policy="reversible",
    mutation_policy_reason=REASON_UNDONE_BY_ONE_CALL,
    agent="task_agent",
    description=(
        "**Tool: rename_task_list_tool** - Rename a task list. Runs at once, without "
        "confirmation: renaming it again undoes it."
    ),
    semantic_keywords=[
        "rename my task list",
        "change the name of a to-do list",
        "call this list something else",
    ],
    parameters=[
        ParameterSchema(
            name="task_list_id",
            type="string",
            required=True,
            description=TASK_LIST_NAMED_DESCRIPTION,
            semantic_type="task_list_id",
        ),
        ParameterSchema(name="title", type="string", required=True, description="Its new name"),
    ],
    outputs=[
        OutputFieldSchema(
            path="task_list_id", type="string", description="ID", semantic_type="task_list_id"
        ),
        OutputFieldSchema(path="title", type="string", description="Name", semantic_type="Text"),
    ],
    cost=CostProfile(est_tokens_in=100, est_tokens_out=80, est_cost_usd=0.003, est_latency_ms=400),
    permissions=PermissionProfile(
        required_scopes=GOOGLE_TASKS_SCOPES,
        hitl_required=False,
        data_classification="CONFIDENTIAL",
    ),
    max_iterations=1,
    reference_examples=["task_list_id", "title"],
    tool_category="update",
    version="1.0.0",
    maintainer="Team Agents",
    display=DisplayMetadata(emoji="✏️", i18n_key="rename_task_list", visible=True, category="tool"),
)

move_task_catalogue_manifest = ToolManifest(
    name="move_task_tool",
    mutation_policy="reversible",
    mutation_policy_reason=REASON_UNDONE_BY_ONE_CALL,
    agent="task_agent",
    description=(
        "**Tool: move_task_tool** - Move a task to another list. Runs at once, without "
        "confirmation: moving it back undoes it. Its id may change: read `task_id` from "
        "the answer before any further step on it."
    ),
    semantic_keywords=[
        "move this task to another list",
        "put a to-do in a different list",
        "transfer a task between lists",
    ],
    parameters=[
        ParameterSchema(
            name="task_id",
            type="string",
            required=True,
            description="Task ID",
            semantic_type="task_id",
        ),
        ParameterSchema(
            name="task_list_id",
            type="string",
            required=False,
            description=TASK_LIST_OF_TASK_DESCRIPTION,
            semantic_type="task_list_id",
        ),
        ParameterSchema(
            name="destination_list_id",
            type="string",
            required=True,
            description=TASK_LIST_NAMED_DESCRIPTION,
            semantic_type="task_list_id",
        ),
    ],
    outputs=[
        OutputFieldSchema(
            path="task_id", type="string", description="Its ID now", semantic_type="task_id"
        ),
        OutputFieldSchema(
            path="task_list_id", type="string", description="List", semantic_type="task_list_id"
        ),
    ],
    cost=CostProfile(est_tokens_in=120, est_tokens_out=80, est_cost_usd=0.003, est_latency_ms=800),
    permissions=PermissionProfile(
        required_scopes=GOOGLE_TASKS_SCOPES,
        hitl_required=False,
        data_classification="CONFIDENTIAL",
    ),
    max_iterations=1,
    reference_examples=["task_id", "task_list_id"],
    tool_category="update",
    version="1.0.0",
    maintainer="Team Agents",
    display=DisplayMetadata(emoji="📦", i18n_key="move_task", visible=True, category="tool"),
)


__all__ = ["move_task_catalogue_manifest", "rename_task_list_catalogue_manifest"]
