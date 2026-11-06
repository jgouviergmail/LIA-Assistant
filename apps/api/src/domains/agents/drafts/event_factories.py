"""The event draft factories — moved verbatim out of drafts/service.py (ADR-369, lot 5).

``service.py`` is frozen at its audited size: what the event drafts gained (a reminder,
free or busy, private, the call on a change, an invitation's answer) is paid for by moving
this cohesive group out, as ``task_factories`` did, never by a raised cap. Re-exported by
the package, where every caller reads them.
"""

from typing import Any

from src.core.constants import DEFAULT_USER_DISPLAY_TIMEZONE
from src.core.i18n import resolve_language
from src.domains.agents.drafts.models import (
    DraftType,
    EventAnswerDraftInput,
    EventDeleteDraftInput,
    EventDraftInput,
    EventUpdateDraftInput,
)
from src.domains.agents.drafts.service import DraftService
from src.domains.agents.tools.output import UnifiedToolOutput


def create_event_draft(
    summary: str,
    start_datetime: str,
    end_datetime: str,
    description: str | None = None,
    location: str | None = None,
    attendees: list[str] | None = None,
    timezone: str = DEFAULT_USER_DISPLAY_TIMEZONE,
    calendar_id: str | None = None,
    related_registry_ids: list[str] | None = None,
    source_tool: str = "create_event_tool",
    user_language: str | None = None,
    user_timezone: str | None = None,
    add_conference: bool = False,
    all_day: bool = False,
    reminder_minutes: int | None = None,
    busy: bool | None = None,
    private: bool | None = None,
    recurrence: dict[str, Any] | None = None,
    recurrence_text: str | None = None,
) -> UnifiedToolOutput:
    """
    Convenience function to create an event draft.

    Args:
        summary: Event title
        start_datetime: Start datetime (ISO)
        end_datetime: End datetime (ISO)
        description: Event description
        location: Event location
        attendees: Attendee emails
        timezone: Timezone
        calendar_id: Calendar ID. If None or "primary", uses user's default calendar preference.
        related_registry_ids: Related registry items
        source_tool: Source tool name
        user_language: Language for HITL
        user_timezone: User's IANA timezone for datetime display (defaults to timezone param)
        add_conference: Attach a video-conference link (Meet/Teams) at creation
        all_day: The bounds are dates, the end exclusive (ADR-369)
        reminder_minutes: Its reminder; None keeps the calendar's own (ADR-369)
        busy: False shows the time as free; None keeps it
        private: True keeps its details back; None keeps it

    Returns:
        UnifiedToolOutput with draft
    """
    service = DraftService()
    draft_input = EventDraftInput(
        summary=summary,
        start_datetime=start_datetime,
        end_datetime=end_datetime,
        description=description,
        location=location,
        attendees=attendees or [],
        timezone=timezone,
        calendar_id=calendar_id,
        add_conference=add_conference,
        all_day=all_day,
        reminder_minutes=reminder_minutes,
        busy=busy,
        private=private,
        recurrence=recurrence,
        recurrence_text=recurrence_text,
        related_registry_ids=related_registry_ids or [],
        user_language=resolve_language(user_language),
        user_timezone=user_timezone or timezone,
    )
    return service.create_event_draft(draft_input, source_tool=source_tool)


def create_update_event_draft(
    event_id: str,
    summary: str | None = None,
    start_datetime: str | None = None,
    end_datetime: str | None = None,
    description: str | None = None,
    location: str | None = None,
    attendees: list[str] | None = None,
    timezone: str = DEFAULT_USER_DISPLAY_TIMEZONE,
    calendar_id: str | None = None,
    current_event: dict[str, Any] | None = None,
    related_registry_ids: list[str] | None = None,
    source_tool: str = "update_event_tool",
    user_language: str | None = None,
    all_day: bool | None = None,
    add_conference: bool = False,
    reminder_minutes: int | None = None,
    busy: bool | None = None,
    private: bool | None = None,
    scope: str | None = None,
    moves_series: bool = False,
) -> UnifiedToolOutput:
    """
    Convenience function to create an event update draft.

    Args:
        event_id: ID of event to update
        summary: New event title (optional)
        start_datetime: New start datetime (ISO format, optional)
        end_datetime: New end datetime (ISO format, optional)
        description: New event description (optional)
        location: New event location (optional)
        attendees: New attendee emails (optional)
        timezone: Timezone
        calendar_id: Calendar ID. If None or "primary", uses user's default calendar preference.
        current_event: Current event data for comparison
        related_registry_ids: Related registry items
        source_tool: Source tool name
        user_language: Language for HITL
        all_day: True/False switches the shape; None keeps it (ADR-369)
        add_conference: Adds a video-call link (ADR-369)
        reminder_minutes: Its reminder; None keeps it
        busy: False shows the time as free; None keeps it
        private: True keeps its details back; None keeps it

    Returns:
        UnifiedToolOutput with draft
    """
    service = DraftService()
    draft_input = EventUpdateDraftInput(
        event_id=event_id,
        summary=summary,
        start_datetime=start_datetime,
        end_datetime=end_datetime,
        description=description,
        location=location,
        attendees=attendees,
        timezone=timezone,
        calendar_id=calendar_id,
        current_event=current_event or {},
        all_day=all_day,
        add_conference=add_conference,
        reminder_minutes=reminder_minutes,
        busy=busy,
        private=private,
        scope=scope,
        moves_series=moves_series,
        related_registry_ids=related_registry_ids or [],
        user_language=resolve_language(user_language),
    )
    return service.create_event_update_draft(draft_input, source_tool=source_tool)


def create_event_answer_draft(
    draft_input: EventAnswerDraftInput,
    source_tool: str = "respond_to_event_tool",
) -> UnifiedToolOutput:
    """Create the draft of an invitation's answer: it leaves only once confirmed.

    Args:
        draft_input: The answer, and what the card shows of the event.
        source_tool: Tool creating this draft.

    Returns:
        UnifiedToolOutput with the draft.
    """
    return DraftService().create_draft(
        draft_type=DraftType.EVENT_ANSWER,
        content=draft_input.model_dump(),
        related_registry_ids=draft_input.related_registry_ids,
        source_tool=source_tool,
        source_step_id=None,
        user_language=draft_input.user_language,
    )


def create_delete_event_draft(
    event_id: str,
    current_event: dict[str, Any] | None = None,
    summary: str | None = None,
    start_datetime: str | None = None,
    end_datetime: str | None = None,
    description: str | None = None,
    location: str | None = None,
    attendees: list[str] | None = None,
    timezone: str = DEFAULT_USER_DISPLAY_TIMEZONE,
    send_updates: str = "all",
    calendar_id: str | None = None,
    related_registry_ids: list[str] | None = None,
    source_tool: str = "delete_event_tool",
    user_language: str | None = None,
    scope: str | None = None,
) -> UnifiedToolOutput:
    """
    Convenience function to create an event delete draft.

    Homogenized with create_event_update_draft: carries flat fields + full event
    object to enable draft type changes (delete ↔ update) during HITL.

    Args:
        event_id: ID of event to delete.
        current_event: Full event object for display and type change.
        summary: Event title (extracted from current_event).
        start_datetime: Start datetime ISO (extracted from current_event).
        end_datetime: End datetime ISO (extracted from current_event).
        description: Event description.
        location: Event location.
        attendees: Attendee email list.
        timezone: Timezone.
        send_updates: How to notify attendees (all, externalOnly, none).
        calendar_id: Calendar ID.
        related_registry_ids: Related registry items.
        source_tool: Source tool name.
        user_language: Language for HITL.

    Returns:
        UnifiedToolOutput with draft.
    """
    service = DraftService()
    draft_input = EventDeleteDraftInput(
        scope=scope,
        event_id=event_id,
        current_event=current_event or {},
        summary=summary,
        start_datetime=start_datetime,
        end_datetime=end_datetime,
        description=description,
        location=location,
        attendees=attendees,
        timezone=timezone,
        send_updates=send_updates,
        calendar_id=calendar_id,
        related_registry_ids=related_registry_ids or [],
        user_language=resolve_language(user_language),
    )
    return service.create_event_delete_draft(draft_input, source_tool=source_tool)
