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

__all__ = ["TASK_CLEAR_DUE_DESCRIPTION"]
