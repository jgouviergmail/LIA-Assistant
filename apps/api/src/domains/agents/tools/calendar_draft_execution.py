"""Calendar draft execution callbacks (HITL confirm path).

Extracted from calendar_tools (2026-08, file-size ratchet): the functions the
draft-executor registry invokes when the user confirms an event draft. They
resolve the provider client for the "calendar" category, resolve the target
calendar, and perform the actual create/update/delete.
"""

from typing import Any
from uuid import UUID

import structlog

from src.core.constants import DEFAULT_USER_DISPLAY_TIMEZONE
from src.core.i18n_api_messages import APIMessages
from src.domains.connectors.models import ConnectorType

logger = structlog.get_logger(__name__)


def _is_calendar_id(value: str) -> bool:
    """
    Check if a value is already a resolved Google Calendar ID vs a calendar name.

    Calendar IDs can be:
    - Email-like: "family08256430369052556985@group.calendar.google.com"
    - Primary alias: "primary"
    - Compact IDs: "c_xxxx" (sometimes used by Google)

    Calendar names are human-readable strings like "Famille", "Work", etc.

    Args:
        value: The string to check

    Returns:
        True if it looks like a calendar ID, False if it's a calendar name
    """
    if not value:
        return False
    # Email-like IDs (group calendars, personal calendars)
    if "@" in value:
        return True
    # Some Google calendar IDs start with c_
    if value.startswith("c_"):
        return True
    # Primary is a special alias
    if value == "primary":
        return True
    return False


async def _resolve_calendar_id(
    draft_content: dict[str, Any],
    client: Any,
    user_id: UUID,
    resolved_type: ConnectorType,
    deps: Any,
) -> str:
    """
    Resolve calendar ID from draft content or user preferences.

    Shared logic for all calendar HITL execute functions.

    Args:
        draft_content: Draft dict (may contain calendar_id).
        client: Calendar client (Google or Apple).
        user_id: User UUID.
        resolved_type: Resolved ConnectorType (GOOGLE_CALENDAR or APPLE_CALENDAR).
        deps: ToolDependencies.

    Returns:
        Resolved calendar ID string (default "primary").
    """
    from src.domains.connectors.preferences.owner_defaults import resolve_owner_calendar_id
    from src.domains.connectors.preferences.resolver import resolve_calendar_name

    draft_calendar_id = draft_content.get("calendar_id")
    calendar_id = "primary"

    if draft_calendar_id and draft_calendar_id != "primary":
        if _is_calendar_id(draft_calendar_id):
            calendar_id = draft_calendar_id
            logger.debug("using_calendar_id_from_draft", calendar_id=calendar_id)
        else:
            calendar_id = await resolve_calendar_name(client, draft_calendar_id, fallback="primary")
    else:
        connector_service = await deps.get_connector_service()
        calendar_id = await resolve_owner_calendar_id(
            db=connector_service.db,
            client=client,
            owner_id=user_id,
            connector_type=resolved_type,
        )

    return calendar_id


async def execute_event_draft(
    draft_content: dict[str, Any],
    user_id: UUID,
    deps: Any,
) -> dict[str, Any]:
    """
    Execute an event draft: actually create the calendar event.

    Called by DraftCritiqueInteraction.process_draft_action() when user confirms.

    Args:
        draft_content: Dict with event content from draft
        user_id: User UUID
        deps: ToolDependencies for getting Google Calendar client

    Returns:
        Dict with create result

    Raises:
        Exception: If event creation fails
    """
    from src.domains.connectors.provider_resolver import resolve_client_for_category

    client, resolved_type = await resolve_client_for_category("calendar", user_id, deps)
    calendar_id = await _resolve_calendar_id(draft_content, client, user_id, resolved_type, deps)

    result = await client.create_event(
        summary=draft_content["summary"],
        start_datetime=draft_content["start_datetime"],
        end_datetime=draft_content["end_datetime"],
        timezone=draft_content.get("timezone", DEFAULT_USER_DISPLAY_TIMEZONE),
        description=draft_content.get("description"),
        location=draft_content.get("location"),
        attendees=draft_content.get("attendees"),
        calendar_id=calendar_id,
        add_conference=draft_content.get("add_conference", False),
    )

    # No PII at INFO: the event title is user content (ids and flags only).
    logger.info(
        "event_draft_executed",
        user_id=str(user_id),
        event_id=result.get("id"),
        calendar_id=calendar_id,
        has_conference_link=bool(_extract_conference_link(result)),
    )

    response: dict[str, Any] = {
        "success": True,
        "event_id": result.get("id"),
        "html_link": result.get("htmlLink"),
        "summary": draft_content["summary"],
        "start": draft_content["start_datetime"],
        "end": draft_content["end_datetime"],
        "calendar_id": calendar_id,
        "message": APIMessages.event_created_successfully(draft_content["summary"]),
    }
    # Only claim a conference link the provider actually returned: Meet/Teams
    # creation is best-effort and can fail while the event itself succeeds.
    conference_link = _extract_conference_link(result)
    if conference_link:
        response["conference_link"] = conference_link
    return response


def _extract_conference_link(event: dict[str, Any]) -> str | None:
    """Extract the video join URL from a created event, if any.

    ``hangoutLink`` is Google's convenience field; the video entry point of
    ``conferenceData`` is the canonical cross-provider source (the Graph
    normalizer produces the same shape for Teams).
    """
    if event.get("hangoutLink"):
        return str(event["hangoutLink"])
    entry_points = (event.get("conferenceData") or {}).get("entryPoints", [])
    return next(
        (
            str(ep["uri"])
            for ep in entry_points
            if ep.get("entryPointType") == "video" and ep.get("uri")
        ),
        None,
    )


async def execute_event_update_draft(
    draft_content: dict[str, Any],
    user_id: UUID,
    deps: Any,
) -> dict[str, Any]:
    """
    Execute an event update draft: actually update the calendar event.

    Called by DraftCritiqueInteraction.process_draft_action() when user confirms.

    Args:
        draft_content: Dict with update content from draft
        user_id: User UUID
        deps: ToolDependencies for getting Google Calendar client

    Returns:
        Dict with update result

    Raises:
        Exception: If event update fails
    """
    from src.domains.connectors.provider_resolver import resolve_client_for_category

    client, resolved_type = await resolve_client_for_category("calendar", user_id, deps)
    calendar_id = await _resolve_calendar_id(draft_content, client, user_id, resolved_type, deps)

    result = await client.update_event(
        event_id=draft_content["event_id"],
        summary=draft_content.get("summary"),
        start_datetime=draft_content.get("start_datetime"),
        end_datetime=draft_content.get("end_datetime"),
        timezone=draft_content.get("timezone", DEFAULT_USER_DISPLAY_TIMEZONE),
        description=draft_content.get("description"),
        location=draft_content.get("location"),
        attendees=draft_content.get("attendees"),
        calendar_id=calendar_id,
    )

    # No PII at INFO: the event title is user content (ids only).
    logger.info(
        "event_update_draft_executed",
        user_id=str(user_id),
        event_id=draft_content["event_id"],
        calendar_id=calendar_id,
    )

    return {
        "success": True,
        "event_id": result.get("id"),
        "html_link": result.get("htmlLink"),
        "summary": result.get("summary"),
        "calendar_id": calendar_id,
        "message": APIMessages.event_updated_successfully(result.get("summary", "")),
    }


async def execute_event_delete_draft(
    draft_content: dict[str, Any],
    user_id: UUID,
    deps: Any,
) -> dict[str, Any]:
    """
    Execute an event delete draft: actually delete the calendar event.

    Called by DraftCritiqueInteraction.process_draft_action() when user confirms.

    Args:
        draft_content: Dict with delete content from draft
        user_id: User UUID
        deps: ToolDependencies for getting Google Calendar client

    Returns:
        Dict with delete result

    Raises:
        Exception: If event deletion fails
    """
    from src.domains.connectors.provider_resolver import resolve_client_for_category

    client, resolved_type = await resolve_client_for_category("calendar", user_id, deps)
    calendar_id = await _resolve_calendar_id(draft_content, client, user_id, resolved_type, deps)

    await client.delete_event(
        event_id=draft_content["event_id"],
        send_updates=draft_content.get("send_updates", "all"),
        calendar_id=calendar_id,
    )

    # Extract summary from event data for message
    event_data = draft_content.get("current_event", {})
    summary = event_data.get("summary", "")

    # No PII at INFO: the event title is user content (ids only).
    logger.info(
        "event_delete_draft_executed",
        user_id=str(user_id),
        event_id=draft_content["event_id"],
        calendar_id=calendar_id,
    )

    return {
        "success": True,
        "event_id": draft_content["event_id"],
        "summary": summary,
        "message": APIMessages.event_deleted_successfully(draft_content["event_id"]),
    }
