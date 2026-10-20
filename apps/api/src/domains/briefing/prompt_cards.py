"""Pure compact projections of the briefing sources authorized by their caller."""

import json
from collections.abc import Iterator

from src.core.classification_projection import classification_fields
from src.domains.briefing.constants import SECTION_NAMES, SECTIONS_NOT_SUMMARISED
from src.domains.briefing.schemas import CardsBundle, CardSection, CardStatus


def _iter_cards(cards: CardsBundle) -> Iterator[CardSection]:
    """Every card the prompts summarise, derived from the declared sections."""
    for name in SECTION_NAMES:
        if name not in SECTIONS_NOT_SUMMARISED:
            yield getattr(cards, name)


def _summarize_cards_for_llm(cards: CardsBundle, *, verbose: bool) -> str:
    """One bounded projection per readable source; preserve historical JSON order."""
    summary: dict[str, object] = {}
    for project in (
        _project_weather,
        _project_agenda,
        _project_mails,
        _project_birthdays,
        _project_for_you,
        _project_tasks,
        _project_documents,
        _project_reminders,
        _project_health,
    ):
        project(summary, cards, verbose)
    return json.dumps(summary, ensure_ascii=False, separators=(",", ":")) if summary else "{}"


def _project_weather(summary: dict[str, object], cards: CardsBundle, _verbose: bool) -> None:
    """Add the weather section without changing other sources."""

    if cards.weather.status == CardStatus.OK and cards.weather.data is not None:
        w = cards.weather.data
        alert = getattr(w, "forecast_alert", None)
        summary["weather"] = {
            "temp_c": getattr(w, "temperature_c", None),
            "condition": getattr(w, "condition_code", None),
            "city": getattr(w, "location_city", None),
            # Compact "<kind>@<HH:MM>" pivot, e.g. "rain@23:00" — readable by
            # the LLM without leaking pre-translated strings into the prompt.
            "forecast_alert": (f"{alert.kind.value}@{alert.time}" if alert is not None else None),
        }


def _project_agenda(summary: dict[str, object], cards: CardsBundle, verbose: bool) -> None:
    """Add the agenda section without changing other sources."""

    if cards.agenda.status == CardStatus.OK and cards.agenda.data is not None:
        events = getattr(cards.agenda.data, "events", []) or []
        if verbose:
            summary["agenda"] = [
                {
                    "title": e.title,
                    "start": e.start_local,
                    "loc": e.location,
                    **classification_fields(e.classification),
                }
                for e in events[:3]
            ]
        else:
            # Greeting: give the upcoming events (≤3, next ~24h) with a per-event
            # day-aware start ("15:00" = today, "demain 08:00" = tomorrow). The
            # greeting reacts to the day's SHAPE (empty/busy, today vs tomorrow) and
            # can name an imminent one. Deliberately NO aggregate count — a bare
            # count made the greeting lump tomorrow's events into today ("deux
            # rendez-vous cet après-midi"); a per-event list keeps each day explicit.
            summary["agenda"] = [
                {
                    "title": e.title,
                    "start": e.start_local,
                    **classification_fields(e.classification),
                }
                for e in events[:3]
            ]


def _project_mails(summary: dict[str, object], cards: CardsBundle, verbose: bool) -> None:
    """Add the mails section without changing other sources."""

    if cards.mails.status == CardStatus.OK and cards.mails.data is not None:
        items = getattr(cards.mails.data, "items", []) or []
        total = getattr(cards.mails.data, "total_unread_today", 0)
        summary["mails"] = (
            {
                "unread_today": total,
                "items": [
                    {
                        "from": (m.sender_name or m.sender_email or "(unknown)"),
                        "subject": m.subject,
                        **classification_fields(m.classification),
                    }
                    for m in items[:3]
                ],
            }
            if verbose or any(classification_fields(m.classification) for m in items[:3])
            else {"unread_today": total}
        )


def _project_birthdays(summary: dict[str, object], cards: CardsBundle, _verbose: bool) -> None:
    """Add the birthdays section without changing other sources."""

    if cards.birthdays.status == CardStatus.OK and cards.birthdays.data is not None:
        items = getattr(cards.birthdays.data, "items", []) or []
        summary["birthdays"] = [
            {"name": b.contact_name, "days_until": b.days_until} for b in items[:3]
        ]


def _project_for_you(summary: dict[str, object], cards: CardsBundle, _verbose: bool) -> None:
    """Add the for you section without changing other sources."""

    if cards.for_you.status == CardStatus.OK and cards.for_you.data is not None:
        fy = cards.for_you.data
        loops = getattr(fy, "open_loops", []) or []
        recents = getattr(fy, "recent_automations", []) or []
        nxt = getattr(fy, "next_automation", None)
        summary["for_you"] = {
            "open_loops": [
                {
                    "subject": ol.subject,
                    "direction": ol.direction,
                    "days_open": ol.days_open,
                }
                for ol in loops[:3]
            ],
            "automations_ran_24h": [a.title for a in recents[:3]],
            "next_automation": (
                f"{nxt.title} ({nxt.next_trigger_local})"
                if nxt is not None and nxt.next_trigger_local
                else (nxt.title if nxt is not None else None)
            ),
        }


def _project_tasks(summary: dict[str, object], cards: CardsBundle, _verbose: bool) -> None:
    """Add the tasks section without changing other sources."""

    if cards.tasks.status == CardStatus.OK and cards.tasks.data is not None:
        t_items = getattr(cards.tasks.data, "items", []) or []
        summary["tasks"] = {
            "overdue_count": getattr(cards.tasks.data, "overdue_count", 0),
            "top": [
                {
                    "title": t.title,
                    "days_until_due": t.days_until_due,
                    "overdue": t.overdue,
                }
                for t in t_items[:3]
            ],
        }


def _project_documents(summary: dict[str, object], cards: CardsBundle, _verbose: bool) -> None:
    """Add the documents section without changing other sources."""

    if cards.documents.status == CardStatus.OK and cards.documents.data is not None:
        d_items = getattr(cards.documents.data, "items", []) or []
        summary["documents"] = [{"name": d.name, "modified": d.modified_local} for d in d_items[:3]]


def _project_reminders(summary: dict[str, object], cards: CardsBundle, verbose: bool) -> None:
    """Add the reminders section without changing other sources."""

    # The SYNTHESIS is told about reminders; the greeting deliberately is not.
    # Both halves are decisions this codebase already made elsewhere:
    #
    # - a reminder fires on its own, so it is the least urgent thing a
    #   one-sentence greeting could spend its single hint on — the same
    #   ranking ``chat/suggestions`` states explicitly ("a meeting and a mail
    #   batch are more time-bound than a reminder, which will fire on its own
    #   anyway");
    # - and the only shape a greeting could take them in was a BARE COUNT,
    #   carrying no day at all. The agenda rule above records what that
    #   produces: "deux rendez-vous cet après-midi" for events spread over two
    #   days. That count was unreachable until the section became cacheable,
    #   which is precisely why it must not be reached now.
    #
    # The synthesis gets the day-aware pair its own prompt documents.
    if verbose and cards.reminders.status == CardStatus.OK and cards.reminders.data is not None:
        items = getattr(cards.reminders.data, "items", []) or []
        summary["reminders"] = [
            {"content": r.content, "trigger": r.trigger_at_local} for r in items[:3]
        ]


def _project_health(summary: dict[str, object], cards: CardsBundle, _verbose: bool) -> None:
    """Add the health section without changing other sources."""

    if cards.health.status == CardStatus.OK and cards.health.data is not None:
        items = getattr(cards.health.data, "items", []) or []
        summary["health"] = {
            item.kind: {
                "today": item.value_today,
                "avg_window": item.value_avg_window,
                "window_days": item.window_days,
                "unit": item.unit,
            }
            for item in items
        }
