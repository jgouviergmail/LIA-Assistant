"""Independent source projections for the heartbeat prompt."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.domains.heartbeat.sms_context import sms_prompt_sections

if TYPE_CHECKING:
    from src.domains.heartbeat.schemas import HeartbeatContext


def _missed_routine_section(missed: dict[str, object]) -> str:
    """The MISSED ROUTINE section of the decision prompt — data only.

    C13: the offer has an OBJECT. The signature is a domain key (« email »,
    « web_search »); the descriptor says what is usually asked for on it, so
    the model can name the service it offers instead of a generic « it ».
    What to DO with it (offer at most once, name the request, declare it
    with ``habit_offered``) is rule 24 of the versioned decision prompt, not
    a sentence repeated here: two wordings of one rule drift.

    Args:
        missed: The offer candidate ``habit_context.detect_missed_routine``
            produced.

    Returns:
        One prompt section.
    """
    schedule = (
        f"weekly (weekday {missed.get('weekday')})"
        if missed.get("shape") == "weekly"
        else str(missed.get("shape", "?"))
    )
    signature = missed.get("signature", "?")
    usual_intent = missed.get("usual_intent")
    request = (
        f"the user usually asks for a '{usual_intent}' on '{signature}'"
        if usual_intent
        else f"the user usually makes a request on '{signature}'"
    )
    return (
        "MISSED ROUTINE (learned recurring request whose usual slot passed "
        f"today with no ask — rule 24): {request} — {schedule} around "
        f"{missed.get('trigger_label', '?')}."
    )


def _section_user_local_time(context: HeartbeatContext, sections: list[str]) -> None:
    if context.user_local_time:
        sections.append(
            f"TIME: {context.day_of_week}, "
            f"{context.user_local_time.strftime('%d/%m/%Y %H:%M')} "
            f"({context.time_of_day})"
        )


def _section_moment(context: HeartbeatContext, sections: list[str]) -> None:
    if context.moment is not None:
        from src.domains.moments.rendering import render_moment_section

        sections.append(render_moment_section(context.moment))


def _section_wake_trigger(context: HeartbeatContext, sections: list[str]) -> None:
    if context.wake_trigger:
        from src.domains.heartbeat.wake_context import fresh_section

        fresh = fresh_section(context.wake_trigger)
        if fresh:
            sections.append(fresh)


def _section_calendar_events(context: HeartbeatContext, sections: list[str]) -> None:
    if context.calendar_events:
        events_text = "\n".join(
            f"  - {e.get('summary', 'Untitled')} "
            f"({e.get('start', '?')} → {e.get('end', '?')})"
            + (f" @ {e['location']}" if e.get("location") else "")
            for e in context.calendar_events
        )
        sections.append(
            f"UPCOMING CALENDAR EVENTS (times in user's local timezone):\n{events_text}"
        )


def _section_pending_tasks(context: HeartbeatContext, sections: list[str]) -> None:
    if context.pending_tasks:
        tasks_text = "\n".join(
            f"  - {t.get('title', 'Untitled')} (due: {t.get('due', 'no date')})"
            + (" [OVERDUE]" if t.get("overdue") else "")
            for t in context.pending_tasks
        )
        sections.append(f"PENDING TASKS:\n{tasks_text}")


def _section_unread_emails(context: HeartbeatContext, sections: list[str]) -> None:
    if context.unread_emails:
        emails_text = "\n".join(
            f"  - From: {e.get('from', '?')} — \"{e.get('subject', 'No subject')}\" "
            f"({e.get('date', '?')})" + (f" [{e['snippet'][:80]}...]" if e.get("snippet") else "")
            for e in context.unread_emails
        )
        sections.append(f"UNREAD EMAILS (received today):\n{emails_text}")


def _section_weather_current(context: HeartbeatContext, sections: list[str]) -> None:
    if context.weather_current:
        temp = context.weather_current.get("main", {}).get("temp", "?")
        desc = context.weather_current.get("weather", [{}])[0].get("description", "?")
        wind = context.weather_current.get("wind", {}).get("speed", "?")
        location_suffix = ""
        if context.weather_location_city:
            src_label = (
                "away from home" if context.weather_location_source == "last_known" else "at home"
            )
            location_suffix = f" in {context.weather_location_city} ({src_label})"
        sections.append(f"CURRENT WEATHER{location_suffix}: {desc}, {temp}°C, wind {wind} m/s")


def _section_weather_changes(context: HeartbeatContext, sections: list[str]) -> None:
    if context.weather_changes:
        changes_text = "\n".join(
            f"  - [{c.severity.upper()}] {c.description}" for c in context.weather_changes
        )
        sections.append(f"WEATHER CHANGES DETECTED:\n{changes_text}")


def _section_trending_interests(context: HeartbeatContext, sections: list[str]) -> None:
    if context.trending_interests:
        topics = ", ".join(i.get("topic", "?") for i in context.trending_interests)
        sections.append(f"USER INTERESTS (trending): {topics}")


def _section_user_memories(context: HeartbeatContext, sections: list[str]) -> None:
    if context.user_memories:
        memories_text = "\n".join(f"  - {m}" for m in context.user_memories)
        sections.append(f"USER MEMORIES:\n{memories_text}")


def _section_journal_entries(context: HeartbeatContext, sections: list[str]) -> None:
    if context.journal_entries:
        journal_text = "\n".join(
            f"  - [{e.get('date', '?')} | {e.get('theme', '')} | {e.get('mood', '')}] "
            f"{e.get('title', 'Untitled')} — {e.get('content_preview', '')}"
            for e in context.journal_entries
        )
        sections.append(f"ASSISTANT JOURNAL ENTRIES (your own reflections):\n{journal_text}")


def _section_health_signals(context: HeartbeatContext, sections: list[str]) -> None:
    if context.health_signals:
        lines: list[str] = []
        summary_today = context.health_signals.get("summary_today", {})
        for kind, payload in summary_today.items():
            lines.append(
                f"  - today {kind}: {payload.get('value')} {payload.get('unit', '')} "
                f"(updated {payload.get('last_update_minutes_ago', '?')} min ago)"
            )
        for kind, payload in context.health_signals.get("baseline_deltas_7d", {}).items():
            pct = payload.get("pct")
            mode = payload.get("mode")
            if pct is not None:
                lines.append(
                    f"  - 7d {kind} vs baseline: {pct:+.1f}% (mode={mode}, "
                    f"baseline={payload.get('baseline_value')})"
                )
        for variation in context.health_signals.get("recent_variations", []):
            lines.append(
                f"  - {variation.get('kind')} trend: {variation.get('trend')} "
                f"over {variation.get('days')} days "
                f"(avg {variation.get('delta_pct')}%)"
            )
        for event in context.health_signals.get("notable_events", []):
            lines.append(
                f"  - event: {event.get('event')} on {event.get('kind')} "
                f"({event.get('days')} days)"
            )
        if lines:
            sections.append("HEALTH SIGNALS (factual, not medical):\n" + "\n".join(lines))


def _section_upcoming_birthdays(context: HeartbeatContext, sections: list[str]) -> None:
    if context.upcoming_birthdays:
        bday_lines = []
        for b in context.upcoming_birthdays:
            days = b.get("days_until")
            when = "TODAY" if days == 0 else f"in {days} day(s)"
            age = b.get("age_at_next")
            age_txt = f", turning {age}" if age else ""
            bday_lines.append(f"  - {b.get('contact_name', '?')} — {when}{age_txt}")
        sections.append("UPCOMING BIRTHDAYS:\n" + "\n".join(bday_lines))


def _section_departure_advice(context: HeartbeatContext, sections: list[str]) -> None:
    if context.departure_advice:
        da = context.departure_advice
        sections.append(
            "DEPARTURE ADVICE (traffic-aware): leave by "
            f"{da.get('leave_by_local', '?')} for '{da.get('event_title', '?')}' "
            f"at {da.get('event_start_local', '?')} — {da.get('eta_minutes', '?')} min "
            f"to {da.get('destination', '?')}"
        )


def _section_open_loops(context: HeartbeatContext, sections: list[str]) -> None:
    if context.open_loops:
        loop_lines = []
        for ol in context.open_loops:
            due = f" (due {ol['due_local']})" if ol.get("due_local") else ""
            who = f" — {ol['counterparty']}" if ol.get("counterparty") else ""
            loop_lines.append(
                f"  - [{ol.get('direction', '?')}] {ol.get('subject', '?')}{who}{due} "
                f"(open for {ol.get('days_open', '?')} days)"
            )
        sections.append(
            "OPEN LOOPS (commitments being tracked for the user):\n" + "\n".join(loop_lines)
        )


def _section_workboard(context: HeartbeatContext, sections: list[str]) -> None:
    if context.workboard:
        ticket_lines = []
        for ticket in context.workboard:
            due = f" (due {ticket['due_local']})" if ticket.get("due_local") else ""
            said = f' — LIA wrote: "{ticket["waiting_on"]}"' if ticket.get("waiting_on") else ""
            ticket_lines.append(
                f"  - [{ticket.get('reason', '?')}] {ticket.get('title', '?')}"
                f" - {ticket.get('status', '?')},"
                f" {ticket.get('priority', '?')} priority{due}{said}"
            )
        sections.append(
            "WORKBOARD (tickets on the user's board needing attention):\n" + "\n".join(ticket_lines)
        )


def _section_habits(context: HeartbeatContext, sections: list[str]) -> None:
    if context.habits:
        rhythm = context.habits.get("rhythm") or {}
        if rhythm:
            windows = "; ".join(f"{name}: {', '.join(labels)}" for name, labels in rhythm.items())
            sections.append(
                "USER RHYTHM (learned activity windows — prefer notifying inside "
                "them; the user's configured hour bounds always prevail): " + windows
            )
        missed = context.habits.get("missed_routine")
        if missed:
            sections.append(_missed_routine_section(missed))


def _section_hours_since_last_interaction(context: HeartbeatContext, sections: list[str]) -> None:
    if context.hours_since_last_interaction is not None:
        sections.append(f"LAST INTERACTION: {context.hours_since_last_interaction:.1f} hours ago")


def render_context(context: HeartbeatContext) -> str:
    sections: list[str] = []
    _section_user_local_time(context, sections)
    _section_moment(context, sections)
    _section_wake_trigger(context, sections)
    _section_calendar_events(context, sections)
    _section_pending_tasks(context, sections)
    _section_unread_emails(context, sections)
    _section_weather_current(context, sections)
    _section_weather_changes(context, sections)
    _section_trending_interests(context, sections)
    _section_user_memories(context, sections)
    _section_journal_entries(context, sections)
    _section_health_signals(context, sections)
    _section_upcoming_birthdays(context, sections)
    _section_departure_advice(context, sections)
    _section_open_loops(context, sections)
    _section_workboard(context, sections)
    _section_habits(context, sections)
    _section_hours_since_last_interaction(context, sections)
    sections.extend(sms_prompt_sections(context.sms))
    return "\n\n".join(sections) if sections else "No context available."
