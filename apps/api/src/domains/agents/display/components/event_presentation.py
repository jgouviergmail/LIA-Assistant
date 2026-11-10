"""Invitation presentation from received dates, people and explicit RSVP states."""

from collections.abc import Mapping
from datetime import date

from src.core.constants import HTML_EVENT_VISIBLE_PARTICIPANTS
from src.core.i18n_cards import CardLabel, card_label
from src.core.i18n_dates import get_month_name
from src.core.i18n_drafts import label_separator
from src.core.i18n_v3 import V3Messages
from src.core.time_utils import convert_to_user_timezone, parse_provider_datetime
from src.domains.agents.display.components.base import (
    RenderContext,
    escape_html,
    render_chip,
    render_collapsible,
    render_d_item,
)
from src.domains.agents.display.icons import Icons, icon
from src.domains.agents.display.values import list_values, nonnegative_integer, scalar_text

_RESPONSES: dict[str, tuple[str, str, CardLabel]] = {
    "accepted": ("check_circle", "accepted", "rsvp_accepted"),
    "declined": ("cancel", "declined", "rsvp_declined"),
    "tentative": ("help", "tentative", "tentative"),
    "needsAction": ("schedule", "pending", "rsvp_pending"),
}


def event_response_status(data: Mapping[str, object]) -> str:
    """Read the current person's explicit response, never infer one from their role."""
    own_response = scalar_text(data.get("myResponse"))
    if own_response in _RESPONSES:
        return own_response
    for attendee in list_values(data.get("attendees")):
        if isinstance(attendee, dict) and attendee.get("self") is True:
            return scalar_text(attendee.get("responseStatus"))
    return ""


def _participant_context(value: Mapping[str, object], ctx: RenderContext) -> str:
    """Describe explicit invitation context without changing a person's response."""
    facts: list[str] = []
    optional = value.get("optional")
    if isinstance(optional, bool):
        facts.append(
            card_label("optional_participant" if optional else "required_participant", ctx.language)
        )
    resource = value.get("resource")
    if isinstance(resource, bool):
        facts.append(
            card_label("resource_participant", ctx.language)
            + label_separator(ctx.language)
            + card_label("yes" if resource else "no", ctx.language)
        )
    guests = nonnegative_integer(value.get("additionalGuests"))
    if guests is not None:
        facts.append(
            card_label("additional_guests", ctx.language)
            + label_separator(ctx.language)
            + str(guests)
        )
    if comment := scalar_text(value.get("comment")):
        facts.append(comment)
    return "".join(
        f'<span class="lia-event__participant-state">{escape_html(fact)}</span>' for fact in facts
    )


def render_event_response(data: Mapping[str, object], ctx: RenderContext) -> str:
    """Name a known personal response independently from the event's own status."""
    response = event_response_status(data)
    presentation = _RESPONSES.get(response)
    if presentation is None:
        return ""
    symbol, _, label = presentation
    tone = "green" if response == "accepted" else "red" if response == "declined" else "amber"
    return render_chip(card_label(label, ctx.language), tone, symbol)


def _calendar_date(value: object, ctx: RenderContext) -> date | None:
    """Keep civil dates civil and convert timed dates through the existing timezone seam."""
    if not isinstance(value, dict):
        return None
    civil = scalar_text(value.get("date"))
    if civil:
        try:
            return date.fromisoformat(civil)
        except ValueError:
            return None
    instant = parse_provider_datetime(value)
    local = convert_to_user_timezone(instant, ctx.timezone) if instant else None
    return local.date() if local else None


def render_event_date(value: object, ctx: RenderContext) -> str:
    """Draw the tear-off date; the complete localized date remains in the schedule row."""
    day = _calendar_date(value, ctx)
    if day is None:
        return ""
    month = escape_html(get_month_name(day.month, ctx.language))
    return (
        '<div class="lia-event__date-sheet" aria-hidden="true">'
        f"<span>{month}</span><strong>{day.day}</strong><span>{day.year}</span></div>"
    )


def _participant(value: Mapping[str, object], ctx: RenderContext) -> str:
    """Retain name and email; missing response has no acceptance or pending claim."""
    email = scalar_text(value.get("email"))
    name = scalar_text(value.get("displayName")) or email
    identity = (
        f'<a href="mailto:{escape_html(email)}">{escape_html(name)}</a>'
        if email
        else f"<span>{escape_html(name)}</span>"
    )
    email_html = (
        f'<span class="lia-part-item__email">{escape_html(email)}</span>'
        if email and email != name
        else ""
    )
    response = _RESPONSES.get(scalar_text(value.get("responseStatus")))
    symbol, variant, label = response if response else ("person", "unknown", None)
    state = (
        f'<span class="lia-event__participant-state">{escape_html(card_label(label, ctx.language))}</span>'
        if label
        else ""
    )
    return (
        f'<li class="lia-event__participant lia-event__participant--{variant}">'
        f'<span class="lia-event__participant-icon" aria-hidden="true">{icon(symbol)}</span>'
        f'<span class="lia-event__participant-info">{identity}{email_html}{state}{_participant_context(value, ctx)}</span></li>'
    )


def render_event_attendees(value: object, ctx: RenderContext, *, partial: bool = False) -> str:
    """Show the first five named people and disclose every remaining received entry."""
    people = [
        entry
        for entry in list_values(value)
        if isinstance(entry, dict)
        and (scalar_text(entry.get("displayName")) or scalar_text(entry.get("email")))
    ]
    notice = (
        render_d_item(Icons.INFO, escape_html(card_label("participants_partial", ctx.language)))
        if partial
        else ""
    )
    if not people:
        return notice
    label = escape_html(V3Messages.get_participant(ctx.language, len(people)))
    rows = [_participant(person, ctx) for person in people]
    initial = "".join(rows[:HTML_EVENT_VISIBLE_PARTICIPANTS])
    rest = rows[HTML_EVENT_VISIBLE_PARTICIPANTS:]
    remainder = (
        render_collapsible(
            trigger_text=f"{V3Messages.get_see_more(ctx.language)} ({len(rest)})",
            content_html=f'<ul class="lia-event__participants-list">{"".join(rest)}</ul>',
            initially_open=False,
            with_separator=False,
        )
        if rest
        else ""
    )
    return (
        '<div class="lia-event__participants">'
        f'<div class="lia-event__participants-heading">{icon(Icons.GROUP)}'
        f"<span>{len(people)} {label}</span></div>"
        f'{notice}<ul class="lia-event__participants-list">{initial}</ul>{remainder}</div>'
    )


def render_event_organizer(value: object, ctx: RenderContext) -> str:
    """Preserve the existing organizer identity, human email and localized wording."""
    if not isinstance(value, dict):
        return ""
    email = scalar_text(value.get("email"))
    name = scalar_text(value.get("displayName")) or email
    if not name:
        return ""
    human_email = email and not any(
        host in email for host in ("@group.calendar.google.com", "@resource.calendar.google.com")
    )
    identity = escape_html(name)
    suffix = ""
    if human_email:
        identity = f'<a href="mailto:{escape_html(email)}">{identity}</a>'
        if email != name:
            suffix = f'<span class="lia-event__organizer-email"> {escape_html(email)}</span>'
    text = V3Messages.get_organized_by(ctx.language).format(
        name=identity, separator=label_separator(ctx.language)
    )
    return f'<div class="lia-event__organizer">{render_d_item(Icons.PERSON, text + suffix)}</div>'
