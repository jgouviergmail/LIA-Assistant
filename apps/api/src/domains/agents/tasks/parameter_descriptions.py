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

__all__ = [
    "TASK_CLEAR_DUE_DESCRIPTION",
    "TASK_CLEAR_REMINDER_DESCRIPTION",
    "TASK_CLEAR_REPEAT_DESCRIPTION",
    "TASK_IMPORTANCE_DESCRIPTION",
    "TASK_REMINDER_DESCRIPTION",
    "TASK_REPEAT_DESCRIPTION",
    "TASK_STEPS_DESCRIPTION",
]
