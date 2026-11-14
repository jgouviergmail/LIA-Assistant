"""What ``clear_due`` means on ``update_task_tool`` (ADR-369, D2).

A due date could be replaced and never removed: ``due=None`` means « keep it ».
The clients gained the removal for the workbench's task editor, and the
assistant gains it in the same lot — told in ONE wording, read by the
planner's manifest AND the tool's own schema (the ReAct loop binds the schema
and never sees the manifest, ADR-310).
"""

from typing import Final

TASK_CLEAR_DUE_DESCRIPTION: Final = (
    "true to REMOVE the task's due date (the task keeps no date). Never together with "
    "'due', which sets a new one; omit both to keep the current date."
)

TASK_IMPORTANCE_DESCRIPTION: Final = "How much it matters: low | normal | high (To Do only)"
TASK_REMINDER_DESCRIPTION: Final = "When it reminds, RFC 3339 (To Do only)"
TASK_REPEAT_DESCRIPTION: Final = (
    "How it repeats from its due date: daily | weekly | monthly | yearly (To Do only)"
)
TASK_STEPS_DESCRIPTION: Final = "The steps it starts with (To Do only)"
TASK_CLEAR_REMINDER_DESCRIPTION: Final = "true to REMOVE its reminder (To Do only)"
TASK_CLEAR_REPEAT_DESCRIPTION: Final = "true to REMOVE its repetition (To Do only)"

# Which list a tasks tool works in (owner rule, 2026-11-10): reading takes every list, a new
# task goes to the default one, an act runs in the task's own. A list is named by its id or
# by its name; one no list answers to is refused, never replaced by another.
TASK_LIST_READ_DESCRIPTION: Final = (
    "The one list to read: its id or its name (list_task_lists_tool gives both). Omit to "
    "read every list of the account."
)
TASK_LIST_GET_DESCRIPTION: Final = (
    "The one list to read: its id or its name (list_task_lists_tool gives both). Omit to "
    "read every list of the account. With `task_id` or `task_ids`: the list those tasks "
    "live in, omitted when unknown."
)
TASK_LIST_NEW_DESCRIPTION: Final = (
    "The list the new task goes in: its id or its name (list_task_lists_tool gives both). "
    "Omit for the person's default list."
)
TASK_LIST_OF_TASK_DESCRIPTION: Final = (
    "The task's own list: `tasklist_id` of the task as get_tasks_tool returned it, or that "
    "list's name. Omit when unknown: the list the conversation last read the task from is "
    "used, else every list is searched for it."
)
TASK_LIST_NAMED_DESCRIPTION: Final = (
    "A task list: its id or its name (list_task_lists_tool gives both)."
)

__all__ = [
    "TASK_CLEAR_DUE_DESCRIPTION",
    "TASK_CLEAR_REMINDER_DESCRIPTION",
    "TASK_CLEAR_REPEAT_DESCRIPTION",
    "TASK_IMPORTANCE_DESCRIPTION",
    "TASK_LIST_GET_DESCRIPTION",
    "TASK_LIST_NAMED_DESCRIPTION",
    "TASK_LIST_NEW_DESCRIPTION",
    "TASK_LIST_OF_TASK_DESCRIPTION",
    "TASK_LIST_READ_DESCRIPTION",
    "TASK_REMINDER_DESCRIPTION",
    "TASK_REPEAT_DESCRIPTION",
    "TASK_STEPS_DESCRIPTION",
]
