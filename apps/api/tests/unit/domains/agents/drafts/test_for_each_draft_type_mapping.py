"""Unit tests for ``ForEachConfirmationInteraction._steps_to_draft_type``.

This helper bridges the FOR_EACH world (where the operation is described by a
tool name and a generic per-item dict) to the typed ``DraftType`` registry
(ADR-085), so both HITL paths share a single rendering helper.
"""

from __future__ import annotations

import pytest

from src.domains.agents.services.hitl.interactions.for_each_confirmation import (
    ForEachConfirmationInteraction,
)


@pytest.mark.parametrize(
    "tool_name,expected_draft_type",
    [
        # Delete variants — all map to "{domain}_delete"
        ("cancel_reminder_tool", "reminder_delete"),
        ("delete_event_tool", "event_delete"),
        ("delete_email_tool", "email_delete"),
        ("delete_contact_tool", "contact_delete"),
        ("delete_task_tool", "task_delete"),
        ("delete_file_tool", "file_delete"),
        ("delete_label_tool", "label_delete"),
        ("remove_event_tool", "event_delete"),
        ("trash_email_tool", "email_delete"),
        # Update variants — "{domain}_update"
        ("update_contact_tool", "contact_update"),
        ("update_event_tool", "event_update"),
        ("update_task_tool", "task_update"),
        ("modify_event_tool", "event_update"),
        # Email-specific verbs
        ("reply_email_tool", "email_reply"),
        ("forward_email_tool", "email_forward"),
        ("send_email_tool", "email"),  # send → base DraftType (no suffix)
        # Create / send / unknown → base DraftType
        ("create_event_tool", "event"),
        ("create_contact_tool", "contact"),
        ("create_task_tool", "task"),
        # Mixed case is normalized
        ("Cancel_Reminder_Tool", "reminder_delete"),
    ],
)
def test_steps_to_draft_type_resolves_tool_names(tool_name: str, expected_draft_type: str) -> None:
    """Tool names with a recognizable domain + verb are mapped correctly."""
    result = ForEachConfirmationInteraction._steps_to_draft_type([{"tool_name": tool_name}])
    assert result == expected_draft_type


def test_steps_to_draft_type_empty_steps_returns_none() -> None:
    """No steps → None."""
    assert ForEachConfirmationInteraction._steps_to_draft_type([]) is None


def test_steps_to_draft_type_missing_tool_name_returns_none() -> None:
    """Step without a tool_name → None."""
    assert ForEachConfirmationInteraction._steps_to_draft_type([{}]) is None
    assert ForEachConfirmationInteraction._steps_to_draft_type([{"tool_name": ""}]) is None


def test_steps_to_draft_type_unknown_domain_returns_none() -> None:
    """Tool names with no recognizable domain → None."""
    assert (
        ForEachConfirmationInteraction._steps_to_draft_type([{"tool_name": "get_weather_tool"}])
        is None
    )
    assert (
        ForEachConfirmationInteraction._steps_to_draft_type([{"tool_name": "search_places_tool"}])
        is None
    )


def test_steps_to_draft_type_only_first_step_inspected() -> None:
    """A FOR_EACH executes one tool per iteration; only the first step matters."""
    result = ForEachConfirmationInteraction._steps_to_draft_type(
        [
            {"tool_name": "cancel_reminder_tool"},
            {"tool_name": "delete_event_tool"},  # ignored
        ]
    )
    assert result == "reminder_delete"
