"""
EventCard Component - Modern Calendar Event Display v3.0.

Renders calendar events with:
- Wrapper for assistant comment + suggested actions
- Time block with duration
- Location with map/meet links
- Attendees and status badges
- Collapsible details section
- Action buttons (Open, Join Meet, Edit)
"""

from __future__ import annotations

import re
from datetime import datetime
from html import unescape
from typing import Any
from urllib.parse import urlparse

import structlog

from src.core.i18n import resolve_language
from src.core.i18n_cards import card_label
from src.core.i18n_drafts import label_separator
from src.core.i18n_v3 import V3Messages
from src.core.text_clip import one_line
from src.core.time_utils import parse_provider_datetime
from src.domains.agents.constants import CONTEXT_DOMAIN_EVENTS
from src.domains.agents.display.components.base import (
    BaseComponent,
    RenderContext,
    build_directions_url,
    escape_html,
    format_duration,
    format_full_date,
    format_time,
    render_att_row,
    render_card_top,
    render_chip,
    render_chip_row,
    render_collapsible,
    render_d_item,
    render_d_row,
    render_desc_block,
    render_part_list,
    render_section_header,
    safe_url,
    wrap_with_response,
)
from src.domains.agents.display.components.calendar_details import render_reminder_settings
from src.domains.agents.display.components.card_content import render_linked_title
from src.domains.agents.display.components.conference_details import render_conference_details
from src.domains.agents.display.components.source_details import event_native_details
from src.domains.agents.display.components.source_recurrence import render_source_recurrence
from src.domains.agents.display.icons import Icons, icon
from src.domains.agents.display.values import list_values

logger = structlog.get_logger(__name__)

#: Where a block no reader wrote opens: a style, a script, the document's head
#: and its title (the ``display/components/base.py`` stripper's own set), or a
#: comment.
_INVISIBLE_OPENING_RE = re.compile(r"<(style|script|head|title)\b[^<>]*>|<(!--)", re.IGNORECASE)

#: Where each closes. CSS and code hold « < » and « > » (« div > p »,
#: « a<b »), so a block ends at its closing tag and nowhere before; a closing
#: tag may carry what HTML ignores (``</style foo>`` closes the block), and a
#: comment ends at ``-->`` whatever it holds (« <!-- a > b --> ») — or at
#: ``--!>``, which the HTML parser also reads as its end (an « incorrectly
#: closed comment » parse error, recovered): read as an open comment, that
#: form dropped everything a reader wrote after it (CodeQL py/bad-tag-filter,
#: ADR-326 amendment).
_INVISIBLE_CLOSINGS = {
    **{
        name: re.compile(rf"</{name}\b[^<>]*>", re.IGNORECASE)
        for name in ("style", "script", "head", "title")
    },
    "!--": re.compile("--!?>"),
}

#: A tag, never a « < » inside it: a run of unclosed « < » is read once. With
#: ``[^>]`` every « < » restarted the scan — 3.6 s for 100 000 of them in a
#: description, on the event loop (review 12).
_TAG_RE = re.compile(r"<[^<>]+>")

#: Two spaces or more of any kind: the layout of an HTML description (a dozen
#: no-break spaces, a space a removed tag left beside one), folded to one space
#: — the typographic one touching the text, when there is one (:func:`_one_space`).
_SPACE_RUN_RE = re.compile(r"\s{2,}")

#: The spaces a layout run is made of; any other space is typography (a
#: no-break, narrow, figure or ideographic space), as ``text_clip.one_line``
#: reads it.
_ORDINARY_SPACES = frozenset(" \t\n\r\f\v\x1c\x1d\x1e\x1f\x85\u2028\u2029")


def _without_invisible_blocks(html: str) -> str:
    """A description with the blocks no reader wrote dropped, content included.

    Each closing tag is searched from where its block opened — searched from
    before it, a stray « </script> » earlier in the text closed a block that
    had not opened yet and showed a passage twice (review 14) — so every
    character is read a bounded number of times, and a block left open drops
    everything after it: its content is not text to show.

    Args:
        html: The description, as its author's client wrote it.

    Returns:
        The description, one space where each block was.
    """
    kept: list[str] = []
    position = 0
    while (opening := _INVISIBLE_OPENING_RE.search(html, position)) is not None:
        kept.append(html[position : opening.start()])
        kept.append(" ")
        kind = (opening.group(1) or opening.group(2)).lower()
        closing = _INVISIBLE_CLOSINGS[kind].search(html, opening.end())
        if closing is None:
            return "".join(kept)
        position = closing.end()
    kept.append(html[position:])
    return "".join(kept)


def _one_space(match: re.Match[str]) -> str:
    """One space for a layout run: the typographic space that touches the text.

    A tag removed beside a no-break space (« Ordre du jour » + « : ») leaves a
    run ending on it: that space is the typography of what the run separates,
    and it stays. A space inside a run is layout — an empty paragraph
    (« <p>&nbsp;</p> ») joined « Intro » and « Suite » with a no-break space
    (review 14) —, and so is an ordinary one.

    Args:
        match: The run.

    Returns:
        The run's last character, or its first, when it is typography; else
        an ordinary space.
    """
    run = match.group(0)
    return next((char for char in (run[-1], run[0]) if char not in _ORDINARY_SPACES), " ")


def _is_meet_url(text: str) -> bool:
    """Check if text is or contains a Google Meet URL by parsing the domain.

    Args:
        text: Location string that may contain a Meet URL.

    Returns:
        True if text contains a valid meet.google.com domain.
    """
    try:
        # Handle bare URLs and URLs embedded in location text
        parsed = urlparse(text)
        domain = (parsed.netloc or parsed.path.split("/")[0]).lower()
        return domain == "meet.google.com"
    except ValueError, AttributeError, IndexError:
        return False


class EventCard(BaseComponent):
    """
    Modern calendar event card v3.1.

    Design:
    - Response wrapper with assistant comment zone + actions zone
    - Left border color based on user's response status:
      - Green (#34a853): accepted
      - Orange (#fbbc04): needsAction or tentative
      - Red (#ea4335): declined
      - Gray (transparent): no attendees / organizer only
    - Time block (prominent) with duration
    - Title as link
    - Location with map/meet link
    - Attendees count badge
    - Collapsible details (description, organizer, reminders, etc.)
    - Action buttons
    """

    # Response status to CSS class mapping
    RESPONSE_STATUS_CLASS = {
        "accepted": "lia-event--accepted",
        "needsAction": "lia-event--pending",
        "tentative": "lia-event--pending",
        "declined": "lia-event--declined",
    }

    def render(
        self,
        data: dict[str, Any],
        ctx: RenderContext,
        assistant_comment: str | None = None,
        suggested_actions: list[dict[str, str]] | None = None,
        with_wrapper: bool = True,
        is_first_item: bool = True,
        is_last_item: bool = True,
    ) -> str:
        """
        Render event as modern card with wrapper.

        Args:
            data: Event data from Google Calendar API
            ctx: Render context (viewport, language, timezone)
            assistant_comment: Optional comment from assistant above card
            suggested_actions: Optional action buttons below card
            with_wrapper: Whether to wrap with response zones
            is_first_item: If True, add top separator (for list rendering)
            is_last_item: If True, add bottom separator (for list rendering)

        Returns:
            HTML string for the event card
        """
        # Extract data
        title = data.get("summary") or data.get("title") or V3Messages.get_no_title(ctx.language)
        url = data.get("htmlLink") or data.get("url", "")
        start = data.get("start", {})
        end = data.get("end", {})
        location = data.get("location", "")
        attendees = data.get("attendees", [])
        status = data.get("status", "")
        color = data.get("colorId") or data.get("color", "")
        is_all_day = self._is_all_day(start)

        # Parse times
        start_str = self._format_event_time(start, is_all_day, ctx.language, ctx.timezone)
        end_str = (
            self._format_event_time(end, is_all_day, ctx.language, ctx.timezone)
            if not is_all_day
            else ""
        )
        duration = self._get_duration(start, end, ctx.language) if not is_all_day else ""

        # Format date
        date_str = self._format_event_date(start, ctx.language, ctx.timezone, is_all_day)

        # Build default actions if not provided
        # Note: Actions can exist even without URL (Meet link, directions to location)
        if suggested_actions is None:
            suggested_actions = self._build_default_actions(data, ctx)

        # Unified render - CSS handles responsive adaptation
        card_html = self._render_card(
            title,
            url,
            date_str,
            start_str,
            end_str,
            duration,
            location,
            attendees,
            is_all_day,
            color,
            status,
            ctx,
            data,
        )

        # Wrap with response zones if requested
        if with_wrapper:
            return wrap_with_response(
                card_html=card_html,
                assistant_comment=assistant_comment,
                suggested_actions=suggested_actions,
                domain=CONTEXT_DOMAIN_EVENTS,
                with_top_separator=is_first_item,
                with_bottom_separator=is_last_item,
            )
        return card_html

    def _build_default_actions(
        self, data: dict[str, Any], ctx: RenderContext
    ) -> list[dict[str, str]]:
        """Build default action buttons for event."""
        actions = []
        url = data.get("htmlLink") or data.get("url", "")
        location = data.get("location", "")
        conference = data.get("conferenceData", {})

        # View details in Calendar
        if url:
            actions.append(
                {
                    "icon": Icons.CALENDAR,
                    "label": V3Messages.get_view_details(ctx.language),
                    "url": url,
                }
            )

        # Join Meet if available
        if isinstance(conference, dict):
            entry_points = list_values(conference.get("entryPoints"))
            for ep in entry_points:
                if isinstance(ep, dict) and ep.get("entryPointType") == "video":
                    meet_url = ep.get("uri", "")
                    if meet_url:
                        actions.append(
                            {
                                "icon": Icons.VIDEO_CALL,
                                "label": V3Messages.get_join_meet(ctx.language),
                                "url": meet_url,
                            }
                        )
                        break

        # Directions if location (and not a Meet link)
        # Uses centralized build_directions_url for consistent behavior
        if location and not _is_meet_url(location):
            actions.append(
                {
                    "icon": Icons.DIRECTIONS,
                    "label": V3Messages.get_directions(ctx.language),
                    "url": build_directions_url(location),
                }
            )

        return actions

    def _render_card(
        self,
        title: str,
        url: str,
        date_str: str,
        start_str: str,
        end_str: str,
        duration: str,
        location: str,
        attendees: list,
        is_all_day: bool,
        color: str,
        status: str,
        ctx: RenderContext,
        data: dict[str, Any],
    ) -> str:
        """Unified event card using Design System v4 components."""
        nested_class = self._nested_class(ctx)
        response_class = self._get_response_status_class(data)

        # --- Card top: illustration + title + participant count ---
        illus_icon, illus_color = self._get_illus_for_status(data)
        title_html = render_linked_title(title, url)

        # Only status badge in card-top (participant count shown with avatars below)
        badges_parts = []
        status_badge = self._render_status_badge(status, ctx)
        if status_badge:
            badges_parts.append(status_badge)

        card_top_html = render_card_top(
            icon_name=illus_icon,
            illus_color=illus_color,
            title_html=title_html,
            badges_html=" ".join(badges_parts) if badges_parts else "",
        )

        # --- Chips row: date + time + duration ---
        chips = []
        if date_str:
            chips.append(render_chip(date_str, "indigo", Icons.CALENDAR))
        if is_all_day:
            chips.append(
                render_chip(
                    V3Messages.get_all_day(ctx.language, long_form=True), "allday", "wb_sunny"
                )
            )
        else:
            if start_str and end_str:
                chips.append(render_chip(f"{start_str} - {end_str}", "time", Icons.SCHEDULE))
            if duration:
                chips.append(render_chip(duration, "", "timer"))
        chip_row_html = render_chip_row(" ".join(chips))

        # --- Location (extra top margin after chip separator) ---
        location_raw = self._render_location_v4(location, ctx)
        location_html = (
            f'<div style="margin-top:var(--lia-space-sm)">{location_raw}</div>'
            if location_raw
            else ""
        )

        # --- Attendee avatars with "N participants" label ---
        if attendees:
            participant_label = V3Messages.get_participant(ctx.language, len(attendees))
            attendees_html = render_att_row(attendees, label_text=participant_label)
        else:
            attendees_html = ""

        # --- Collapsible details ---
        collapsible_html = self._render_collapsible_details(data, attendees, ctx)

        return f"""<div class="lia-card lia-event {response_class} {nested_class}">
{card_top_html}
{chip_row_html}
{location_html}
{attendees_html}
{collapsible_html}
</div>"""

    def _get_illus_for_status(self, data: dict[str, Any]) -> tuple[str, str]:
        """Get illustration icon and color based on user's response status."""
        status = self._get_user_response_status(data)
        if status == "accepted":
            return "event_available", "green"
        elif status == "declined":
            return "event_busy", "red"
        return "pending", "amber"

    def _render_location_v4(self, location: str, ctx: RenderContext) -> str:
        """Render location using v4 d-row component."""
        if not location:
            return ""
        if _is_meet_url(location):
            link = f'<a href="{safe_url(location)}" target="_blank">Google Meet</a>'
            return render_d_row(Icons.VIDEO_CALL, link)
        link = f'<a href="{build_directions_url(location)}" target="_blank">{escape_html(location)}</a>'
        return render_d_row(
            Icons.LOCATION,
            link,
            icon_style="font-variation-settings:'FILL' 1,'wght' 400,'GRAD' 0,'opsz' 20;color:#ef4444",
        )

    def _render_status_badge(self, status: str, ctx: RenderContext) -> str:
        """Render status badge for non-confirmed events."""
        if status and status != "confirmed":
            status_map = {
                "tentative": ("lia-badge--warning", V3Messages.get_tentative(ctx.language)),
                "cancelled": ("lia-badge--danger", V3Messages.get_cancelled(ctx.language)),
            }
            badge_class, badge_text = status_map.get(status, ("", ""))
            if badge_class:
                return f'<span class="lia-badge {badge_class}">{badge_text}</span>'
        return ""

    def _render_collapsible_details(
        self,
        data: dict[str, Any],
        attendees: list,
        ctx: RenderContext,
    ) -> str:
        """Render collapsible section with extended details using v4 components."""
        detail_sections: list[str] = []
        detail_sections.extend(event_native_details(data, ctx))

        # Description block: a third party's HTML, read as text — its style and
        # script blocks dropped and its tags removed, entities decoded AFTER
        # them (so « &lt;b&gt; » stays text), and layout runs folded. The native
        # details retain the complete supplied description.
        description = data.get("description", "")
        if description:
            text = unescape(_TAG_RE.sub(" ", _without_invisible_blocks(description)))
            desc_clean = one_line(_SPACE_RUN_RE.sub(_one_space, text))
            if desc_clean:
                detail_sections.append(render_desc_block(escape_html(desc_clean)))

        # Organizer with email
        organizer = data.get("organizer", {})
        if organizer and isinstance(organizer, dict):
            org_name = organizer.get("displayName") or organizer.get("email", "")
            org_email = organizer.get("email", "")
            # Skip non-human emails (calendar groups, resources)
            is_human_email = bool(
                org_email
                and "@group.calendar.google.com" not in org_email
                and "@resource.calendar.google.com" not in org_email
            )
            if org_name:
                organized_by = V3Messages.get_organized_by(ctx.language)
                if is_human_email:
                    name_html = (
                        f'<a href="mailto:{escape_html(org_email)}">' f"{escape_html(org_name)}</a>"
                    )
                    # The space rides INSIDE the span: the card's compaction
                    # removes the whitespace between two tags, and the name
                    # ran into the address.
                    email_suffix = (
                        '<span style="color:var(--lia-text-muted);'
                        'font-size:var(--lia-text-xs)">'
                        f" {escape_html(org_email)}</span>"
                        if org_email != org_name
                        else ""
                    )
                else:
                    name_html = escape_html(org_name)
                    email_suffix = ""
                detail_sections.append(
                    render_d_item(
                        Icons.PERSON,
                        organized_by.format(name=name_html, separator=label_separator(ctx.language))
                        + email_suffix,
                    )
                )

        detail_sections.append(render_conference_details(data.get("conferenceData"), ctx))

        # Recurrence info
        detail_sections.append(
            render_source_recurrence(
                data.get("source_recurrence")
                or data.get("recurrence_pattern")
                or data.get("recurrence"),
                data.get("start"),
                ctx,
            )
        )

        detail_sections.append(render_reminder_settings(data.get("reminders"), ctx))

        # Participants section with status + name + email
        if attendees:
            participants_label = V3Messages.get_participants(ctx.language)
            detail_sections.append(render_section_header(participants_label, Icons.GROUP, "indigo"))
            detail_sections.append(render_part_list(attendees, max_shown=len(attendees)))

        # Attachments
        attachments = data.get("attachments", [])
        if attachments:
            att_items = []
            attachment_fallback = V3Messages.get_attachment(ctx.language)
            for att in attachments:
                if isinstance(att, dict):
                    att_title = att.get("title", "") or att.get("name", attachment_fallback)
                    file_url = att.get("fileUrl", "") or att.get("url", "")
                    if file_url:
                        att_items.append(
                            f'<a href="{safe_url(file_url)}" target="_blank">'
                            f"{escape_html(att_title)}</a>"
                        )
                    else:
                        att_items.append(escape_html(att_title))
            if att_items:
                attachments_label = V3Messages.get_attachments(ctx.language)
                detail_sections.append(
                    render_d_item(
                        Icons.ATTACHMENT,
                        f"{attachments_label}{label_separator(ctx.language)}{', '.join(att_items)}",
                    )
                )

        # Wrap in collapsible (no separator — chip-row above already has one)
        if detail_sections:
            content_html = "\n".join(detail_sections)
            return render_collapsible(
                trigger_text=V3Messages.get_see_more(ctx.language),
                content_html=content_html,
                initially_open=False,
                with_separator=False,
            )

        return ""

    def _is_all_day(self, start: dict) -> bool:
        """Check if event is all-day."""
        # The registry can add a synthetic clock for cross-domain binding;
        # the provider's civil date still defines the presentation.
        return isinstance(start.get("date"), str) and bool(start["date"])

    def _format_event_time(
        self, start: dict, is_all_day: bool, language: str, timezone: str
    ) -> str:
        """Format event time with locale-aware conventions."""
        if is_all_day:
            date_str = start.get("date", "")
            try:
                dt = datetime.fromisoformat(date_str)
                # Locale-aware date format
                if language == "en":
                    return dt.strftime("%m/%d")  # MM/DD for English
                else:
                    return dt.strftime("%d/%m")  # DD/MM for others
            except ValueError, TypeError:
                return date_str  # type: ignore[no-any-return]
        else:
            dt_str = start.get("dateTime", "")
            if not dt_str:
                return ""
            parsed = parse_provider_datetime(start)
            return (
                format_time(parsed, language, timezone)
                if parsed
                else card_label("unavailable", language)
            )

    def _get_duration(self, start: dict, end: dict, language: str) -> str:
        """Calculate event duration with localized labels."""
        if "dateTime" in start or "dateTime" in end:
            start_dt, end_dt = parse_provider_datetime(start), parse_provider_datetime(end)
            return (
                format_duration(start_dt.isoformat(), end_dt.isoformat(), language)
                if start_dt and end_dt
                else ""
            )
        start_str = start.get("date", "")
        end_str = end.get("date", "")
        return format_duration(start_str, end_str, language)

    def _format_event_date(
        self,
        start: dict,
        language: str,
        timezone: str,
        is_all_day: bool,
    ) -> str:
        """Format event date for display with full localized date."""
        if is_all_day:
            date_str = start.get("date", "")
        else:
            date_str = start.get("dateTime", "")

        if not date_str:
            return ""

        parsed = date_str if is_all_day else parse_provider_datetime(start)
        if parsed is None:
            return card_label("unavailable", language)
        full = format_full_date(parsed, language, "UTC" if is_all_day else timezone)
        # Strip year from event date (e.g., "samedi 29 mars 2026" -> "samedi 29 mars")
        import re

        return re.sub(r"\s*\d{4}\s*$", "", full).rstrip(" ,")

    def _format_reminder_time(
        self, minutes: int, method: str = "popup", language: str | None = None
    ) -> str:
        """Format reminder time in human-readable form."""
        method_icon = (
            icon(Icons.EMAIL, size="xs") if method == "email" else icon(Icons.REMINDER, size="xs")
        )
        time_text = V3Messages.get_reminder_time(resolve_language(language), minutes)
        return f"{method_icon} {time_text}"

    def _get_user_response_status(self, data: dict[str, Any]) -> str:
        """
        Get the current user's response status for this event.

        Looks for the attendee with 'self: true' flag (current user)
        and returns their responseStatus.

        Returns:
            Response status: 'accepted', 'declined', 'tentative', 'needsAction'
            or empty string if user is not an attendee (organizer only event).
        """
        event_title = data.get("summary", "Unknown")
        attendees = data.get("attendees", [])
        organizer = data.get("organizer", {})

        logger.debug(
            "event_response_status_detection",
            event_title=event_title,
            attendees_count=len(attendees),
        )

        if not attendees:
            return "accepted"

        for attendee in attendees:
            if isinstance(attendee, dict) and attendee.get("self"):
                return attendee.get("responseStatus", "needsAction")  # type: ignore[no-any-return]

        if isinstance(organizer, dict) and organizer.get("self"):
            return "accepted"

        return "needsAction"

    def _get_response_status_class(self, data: dict[str, Any]) -> str:
        """Get CSS class for user's response status."""
        status = self._get_user_response_status(data)
        return self.RESPONSE_STATUS_CLASS.get(status, "lia-event--pending")
