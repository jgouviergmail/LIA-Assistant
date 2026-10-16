"""When an answer on a confirmation card changes the KIND of action (2026-04).

« Delete it instead » said on an update card, or a change asked on a delete
card, turns the draft into its sibling type: these tables name the sibling, the
tool that builds it, and the fields that carry identity rather than content —
the ones a comparison of « what the person changed » must ignore. Extracted
from ``hitl_dispatch_node`` (file-size ratchet), which reads them.
"""

from typing import Final

#: An update (or a reply / forward) the person asked to delete instead.
TYPE_TO_DELETE: Final[dict[str, str]] = {
    "event_update": "event_delete",
    "contact_update": "contact_delete",
    "task_update": "task_delete",
    "email_reply": "email_delete",
    "email_forward": "email_delete",
}

#: A deletion the person asked to change instead.
UPDATABLE_DELETE_TYPES: Final[dict[str, str]] = {
    "event_delete": "event_update",
    "contact_delete": "contact_update",
    "task_delete": "task_update",
}

#: The tool that builds each sibling type.
DRAFT_TYPE_TO_TOOL: Final[dict[str, str]] = {
    "event_update": "update_event_tool",
    "event_delete": "delete_event_tool",
    "contact_update": "update_contact_tool",
    "contact_delete": "delete_contact_tool",
    "task_update": "update_task_tool",
    "task_delete": "delete_task_tool",
    "email_delete": "delete_email_tool",
}

#: Identity and plumbing fields, never a change the person asked for.
PRESERVED_FIELDS_FOR_DIFF: Final[frozenset[str]] = frozenset(
    {
        "event_id",
        "calendar_id",
        "timezone",
        "send_updates",
        "resource_name",
        "task_id",
        "task_list_id",
        "current_event",
        "current_contact",
        "current_task",
        "related_registry_ids",
        "user_language",
        "user_timezone",
    }
)

__all__ = [
    "DRAFT_TYPE_TO_TOOL",
    "PRESERVED_FIELDS_FOR_DIFF",
    "TYPE_TO_DELETE",
    "UPDATABLE_DELETE_TYPES",
]
