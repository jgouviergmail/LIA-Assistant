"""
Tasks normalizer: Microsoft To Do task → dict format Google Tasks API.

Converts Microsoft Graph API To Do task objects to the dict structure
expected by tasks_tools.py (same format as GoogleTasksClient).
"""

from datetime import UTC, datetime
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# Microsoft To Do status → Google Tasks status mapping
_STATUS_TO_GOOGLE: dict[str, str] = {
    "notStarted": "needsAction",
    "inProgress": "needsAction",
    "completed": "completed",
    "waitingOnOthers": "needsAction",
    "deferred": "needsAction",
}

# Google Tasks status → Microsoft To Do status mapping
_STATUS_FROM_GOOGLE: dict[str, str] = {
    "needsAction": "notStarted",
    "completed": "completed",
}


def normalize_graph_task(task: dict[str, Any]) -> dict[str, Any]:
    """
    Normalize a Microsoft To Do task to Google Tasks API dict format.

    Args:
        task: Microsoft Graph To Do task dict from /me/todo/lists/{id}/tasks.

    Returns:
        Dict in Google Tasks API task format with _provider marker.
    """
    task_id = task.get("id", "")
    title = task.get("title", "")

    # Notes from body
    body_data = task.get("body", {})
    notes = body_data.get("content", "")
    # Strip HTML if body is HTML
    if body_data.get("contentType") == "html" and notes:
        import re

        notes = re.sub(r"<[^>]+>", "", notes).strip()

    # Status mapping
    ms_status = task.get("status", "notStarted")
    google_status = _STATUS_TO_GOOGLE.get(ms_status, "needsAction")

    # Due date
    due = None
    due_data = task.get("dueDateTime")
    if due_data:
        dt_str = due_data.get("dateTime", "")
        if dt_str:
            # Normalize to RFC 3339 format (Google Tasks expects this)
            due = _normalize_due_date(dt_str)

    # Completed date
    completed = None
    completed_data = task.get("completedDateTime")
    if completed_data:
        dt_str = completed_data.get("dateTime", "")
        if dt_str:
            completed = _normalize_due_date(dt_str)

    # Updated timestamp
    updated = task.get("lastModifiedDateTime", "")

    # Importance → not in Google Tasks, but useful metadata
    importance = task.get("importance", "normal")

    return {
        "id": task_id,
        "title": title,
        "notes": notes,
        "status": google_status,
        "due": due,
        "completed": completed,
        "updated": updated,
        "selfLink": "",
        "parent": "",  # Microsoft To Do has no subtask hierarchy
        "position": "",
        # Extra metadata
        "importance": importance,
        "_provider": "microsoft",
    }


def _normalize_due_date(dt_str: str) -> str:
    """
    Normalize a datetime string to RFC 3339 format.

    Microsoft returns: "2025-01-15T00:00:00.0000000"
    Google expects:    "2025-01-15T00:00:00.000Z"
    """
    try:
        # Strip fractional seconds and parse
        clean = dt_str.split(".")[0] if "." in dt_str else dt_str
        if clean.endswith("Z"):
            clean = clean[:-1]
        dt = datetime.fromisoformat(clean)
        return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    except (ValueError, AttributeError):
        return dt_str


def normalize_graph_task_list(task_list: dict[str, Any]) -> dict[str, Any]:
    """
    Normalize a Microsoft To Do task list to Google Tasks list format.

    Args:
        task_list: Microsoft Graph To Do list dict from /me/todo/lists.

    Returns:
        Dict in Google Tasks taskList format with _provider marker.
    """
    return {
        "id": task_list.get("id", ""),
        "title": task_list.get("displayName", ""),
        "updated": task_list.get("lastModifiedDateTime", ""),
        "selfLink": "",
        "_provider": "microsoft",
    }


def build_task_body(
    title: str = "",
    notes: str | None = None,
    due: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    """
    Build a Microsoft To Do task request body from parameters.

    Args:
        title: Task title.
        notes: Task notes/description.
        due: Due date in RFC 3339 format.
        status: Google Tasks status ("needsAction" or "completed").

    Returns:
        Dict suitable for POST/PATCH /me/todo/lists/{id}/tasks.
    """
    body: dict[str, Any] = {"title": title}

    if notes is not None:
        body["body"] = {"content": notes, "contentType": "text"}

    if due is not None:
        # Microsoft expects dateTimeTimeZone object
        body["dueDateTime"] = {
            "dateTime": due,
            "timeZone": "UTC",
        }

    if status is not None:
        ms_status = _STATUS_FROM_GOOGLE.get(status, "notStarted")
        body["status"] = ms_status
        if ms_status == "completed":
            body["completedDateTime"] = {
                "dateTime": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.0000000"),
                "timeZone": "UTC",
            }

    return body
