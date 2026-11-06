"""The task draft factories — moved verbatim out of drafts/service.py (ADR-369 L6).

``service.py`` is frozen at its audited size: the ``all_day`` and ``clear_due``
parameters the drafts gained are paid for by moving this cohesive group out,
never by a raised cap. Re-exported by the package, where every caller reads them.
"""

from typing import Any

from src.core.i18n import resolve_language
from src.domains.agents.drafts.models import (
    TaskDeleteDraftInput,
    TaskDraftInput,
    TaskUpdateDraftInput,
)
from src.domains.agents.drafts.service import DraftService
from src.domains.agents.tasks.extras import TaskExtras
from src.domains.agents.tools.output import UnifiedToolOutput


def create_task_draft(
    title: str,
    notes: str | None = None,
    due: str | None = None,
    task_list_id: str = "@default",
    extras: TaskExtras | None = None,
    related_registry_ids: list[str] | None = None,
    source_tool: str = "create_task_tool",
    user_language: str | None = None,
) -> UnifiedToolOutput:
    """
    Convenience function to create a task draft.

    Args:
        title: Task title
        notes: Task notes/description
        due: Due date (RFC 3339 format)
        task_list_id: Task list ID
        extras: What To Do keeps beyond these
        related_registry_ids: Related registry items
        source_tool: Source tool name
        user_language: Language for HITL

    Returns:
        UnifiedToolOutput with draft
    """
    service = DraftService()
    kept = extras or TaskExtras()
    draft_input = TaskDraftInput(
        title=title,
        notes=notes,
        due=due,
        task_list_id=task_list_id,
        importance=kept.importance,
        reminder=kept.reminder,
        repeat=kept.repeat,
        steps=list(kept.steps),
        related_registry_ids=related_registry_ids or [],
        user_language=resolve_language(user_language),
    )
    return service.create_task_create_draft(draft_input, source_tool=source_tool)


def create_task_update_draft(
    task_id: str,
    title: str | None = None,
    notes: str | None = None,
    due: str | None = None,
    status: str | None = None,
    task_list_id: str = "@default",
    current_task: dict[str, Any] | None = None,
    related_registry_ids: list[str] | None = None,
    source_tool: str = "update_task_tool",
    user_language: str | None = None,
    clear_due: bool = False,
    extras: TaskExtras | None = None,
) -> UnifiedToolOutput:
    """
    Convenience function to create a task update draft.

    Args:
        task_id: Task ID to update
        title: New task title (optional)
        notes: New task notes (optional)
        due: New due date (RFC 3339 format, optional)
        status: New status - needsAction or completed (optional)
        task_list_id: Task list ID
        current_task: Current task data for comparison
        related_registry_ids: Related registry items
        source_tool: Source tool name
        user_language: Language for HITL
        clear_due: Remove the due date (never with ``due``)
        extras: What To Do keeps beyond these

    Returns:
        UnifiedToolOutput with draft
    """
    service = DraftService()
    kept = extras or TaskExtras()
    draft_input = TaskUpdateDraftInput(
        task_id=task_id,
        title=title,
        notes=notes,
        due=due,
        status=status,
        task_list_id=task_list_id,
        current_task=current_task or {},
        related_registry_ids=related_registry_ids or [],
        user_language=resolve_language(user_language),
        clear_due=clear_due,
        importance=kept.importance,
        reminder=kept.reminder,
        repeat=kept.repeat,
        clear_reminder=kept.clear_reminder,
        clear_repeat=kept.clear_repeat,
    )
    return service.create_task_update_draft(draft_input, source_tool=source_tool)


def create_task_delete_draft(
    task_id: str,
    title: str | None = None,
    notes: str | None = None,
    due: str | None = None,
    status: str | None = None,
    task_list_id: str = "@default",
    current_task: dict[str, Any] | None = None,
    related_registry_ids: list[str] | None = None,
    source_tool: str = "delete_task_tool",
    user_language: str | None = None,
) -> UnifiedToolOutput:
    """
    Convenience function to create a task delete draft.

    Homogenized with create_task_update_draft for draft type changes.

    Args:
        task_id: Task ID to delete.
        title: Task title.
        notes: Task notes.
        due: Due date (RFC 3339).
        status: Status (needsAction or completed).
        task_list_id: Task list ID.
        current_task: Full task object for type change.
        related_registry_ids: Related registry items.
        source_tool: Source tool name.
        user_language: Language for HITL.

    Returns:
        UnifiedToolOutput with draft.
    """
    service = DraftService()
    draft_input = TaskDeleteDraftInput(
        task_id=task_id,
        title=title,
        notes=notes,
        due=due,
        status=status,
        task_list_id=task_list_id,
        current_task=current_task or {},
        related_registry_ids=related_registry_ids or [],
        user_language=resolve_language(user_language),
    )
    return service.create_task_delete_draft(draft_input, source_tool=source_tool)
