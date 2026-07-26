"""Fallback draft summary — what the confirmation card shows without the LLM.

Extracted from ``draft_critique.py`` (which sits at the 600 logical-SLOC
ceiling): the ladder is a pure function of the draft, with no dependency on the
interaction object, and it is the text a user reads before approving a side
effect. Keeping it standalone makes it testable on its own and keeps the
streaming interaction focused on streaming.

Every branch here must stay in step with ``_DRAFT_SUMMARIES`` in
``core.i18n_hitl``: a translated draft type with no branch falls through to the
generic question, and the user confirms an action without being told which one.
The completeness guard in
``tests/unit/domains/agents/services/hitl/test_draft_critique_fallback.py``
enforces that.
"""

from typing import Any

from src.core.constants import DEFAULT_USER_DISPLAY_TIMEZONE
from src.core.i18n_hitl import HitlMessages, HitlMessageType


def build_fallback_critique(
    draft_type: str,
    draft_content: dict[str, Any],
    user_language: str,
    user_timezone: str = DEFAULT_USER_DISPLAY_TIMEZONE,
) -> str:
    """
    Generate fallback critique when LLM fails.

    Creates a simple summary from draft content without LLM.
    Uses centralized i18n_hitl translations for all 6 languages.

    Args:
        draft_type: Type of draft
        draft_content: Draft content dict
        user_language: Language code (fr, en, es, de, it, zh-CN)
        user_timezone: User's IANA timezone for datetime formatting

    Returns:
        Fallback critique question
    """
    from src.core.time_utils import format_datetime_for_display

    emoji = HitlMessages.get_draft_emoji(draft_type)

    # Extract variables and build structured summary based on draft type
    extra_lines: list[str] = []

    if draft_type == "email":
        to = draft_content.get("to", "?")
        subject = draft_content.get("subject", "?")
        summary = HitlMessages.get_draft_summary(draft_type, user_language, to=to, subject=subject)
        body = draft_content.get("body")
        if body:
            extra_lines.append(f"\n{body}")

    elif draft_type == "email_reply":
        original_from = draft_content.get("original_from", "?")
        subject = draft_content.get("subject", "?")
        summary = HitlMessages.get_draft_summary(
            draft_type, user_language, original_from=original_from, subject=subject
        )
        body = draft_content.get("body")
        if body:
            extra_lines.append(f"\n{body}")

    elif draft_type == "email_forward":
        to = draft_content.get("to", "?")
        subject = draft_content.get("subject", "?")
        summary = HitlMessages.get_draft_summary(draft_type, user_language, to=to, subject=subject)
        body = draft_content.get("body")
        if body:
            extra_lines.append(f"\n{body}")

    elif draft_type == "event":
        summary_text = draft_content.get("summary", "?")
        start = draft_content.get("start_datetime", "?")
        if isinstance(start, str) and "T" in start:
            start = format_datetime_for_display(
                start, user_timezone, user_language, include_time=True
            )
        summary = HitlMessages.get_draft_summary(
            draft_type, user_language, summary=summary_text, start=start
        )
        end = draft_content.get("end_datetime")
        if end and isinstance(end, str) and "T" in end:
            end = format_datetime_for_display(end, user_timezone, user_language, include_time=True)
            extra_lines.append(f"🏁 {end}")
        location = draft_content.get("location")
        if location:
            extra_lines.append(f"📍 {location}")
        attendees = draft_content.get("attendees")
        if attendees:
            extra_lines.append(f"👥 {attendees}")

    elif draft_type == "email_delete":
        subject = draft_content.get("subject", "?")
        from_addr = draft_content.get("from", "")
        summary = HitlMessages.get_draft_summary(draft_type, user_language, subject=subject)
        if from_addr:
            extra_lines.append(f"📧 {from_addr}")
        date = draft_content.get("date")
        if date:
            date = format_datetime_for_display(
                date, user_timezone, user_language, include_time=True
            )
            extra_lines.append(f"📅 {date}")

    elif draft_type == "event_update":
        summary_text = draft_content.get("summary") or draft_content.get("current_event", {}).get(
            "summary", "?"
        )
        summary = HitlMessages.get_draft_summary(draft_type, user_language, summary=summary_text)
        start = draft_content.get("start_datetime")
        if start and isinstance(start, str) and "T" in start:
            start = format_datetime_for_display(
                start, user_timezone, user_language, include_time=True
            )
            extra_lines.append(f"🕐 {start}")

    elif draft_type == "event_delete":
        event_data = draft_content.get("current_event", {})
        summary_text = event_data.get("summary", "?")
        summary = HitlMessages.get_draft_summary(draft_type, user_language, summary=summary_text)
        start = event_data.get("start", {}).get("dateTime") or event_data.get("start_datetime")
        if start:
            start = format_datetime_for_display(
                start, user_timezone, user_language, include_time=True
            )
            extra_lines.append(f"🕐 {start}")

    elif draft_type == "contact":
        name = draft_content.get("name", "?")
        email_addr = draft_content.get("email", "")
        summary = HitlMessages.get_draft_summary(
            draft_type, user_language, name=name, email=email_addr
        )
        phone = draft_content.get("phone")
        if phone:
            extra_lines.append(f"📱 {phone}")
        organization = draft_content.get("organization")
        if organization:
            extra_lines.append(f"🏢 {organization}")

    elif draft_type == "contact_update":
        name = draft_content.get("name")
        if not name:
            current_contact = draft_content.get("current_contact", {})
            names = current_contact.get("names", [])
            name = names[0].get("displayName", "?") if names else "?"
        summary = HitlMessages.get_draft_summary(draft_type, user_language, name=name)

    elif draft_type == "contact_delete":
        contact = draft_content.get("current_contact", {})
        names = contact.get("names", [])
        name = names[0].get("displayName", "?") if names else "?"
        summary = HitlMessages.get_draft_summary(draft_type, user_language, name=name)

    elif draft_type == "task":
        title = draft_content.get("title", "?")
        summary = HitlMessages.get_draft_summary(draft_type, user_language, title=title)
        due = draft_content.get("due")
        if due and isinstance(due, str) and "T" in due:
            due = format_datetime_for_display(due, user_timezone, user_language, include_time=False)
            extra_lines.append(f"📅 {due}")
        notes = draft_content.get("notes")
        if notes:
            extra_lines.append(f"📝 {notes}")

    elif draft_type == "task_update":
        title = draft_content.get("title") or draft_content.get("current_task", {}).get(
            "title", "?"
        )
        summary = HitlMessages.get_draft_summary(draft_type, user_language, title=title)

    elif draft_type == "task_delete":
        title = draft_content.get("title", "?")
        summary = HitlMessages.get_draft_summary(draft_type, user_language, title=title)

    elif draft_type == "file_delete":
        file_data = draft_content.get("file", {})
        name = file_data.get("name", "?")
        summary = HitlMessages.get_draft_summary(draft_type, user_language, name=name)

    elif draft_type == "label_delete":
        # `_DRAFT_SUMMARIES` has carried a translated template for this type
        # in all 6 languages since it was added, but the ladder never used
        # it: the user was asked to confirm a DELETION through the generic
        # fallback, without being told which label. Sublabels are listed
        # because deleting a parent takes them with it.
        summary = HitlMessages.get_draft_summary(
            draft_type, user_language, name=draft_content.get("label_name", "?")
        )
        sublabels = draft_content.get("sublabels") or []
        sublabel_names = [
            str(sublabel.get("name"))
            for sublabel in sublabels
            if isinstance(sublabel, dict) and sublabel.get("name")
        ]
        if sublabel_names:
            extra_lines.append(f"🏷️ {', '.join(sublabel_names)}")

    else:
        summary = HitlMessages.get_fallback(HitlMessageType.DRAFT_CRITIQUE, user_language)

    # Build action lines using centralized i18n
    actions = HitlMessages.format_draft_critique_actions(user_language, include_descriptions=False)

    # Assemble: emoji + summary + extra fields + separator + actions
    extra = "\n".join(extra_lines)
    parts = [f"{emoji} {summary}"]
    if extra:
        parts.append(extra)
    parts.append(f"\n---\n{actions}")
    return "\n".join(parts)
