"""Hermetic Graph → native registry → card fixtures for browser validation."""

from src.domains.agents.data_registry.card_payload import card_payload
from src.domains.agents.tools.calendar_tools import ListCalendarsTool
from src.domains.agents.tools.mixins import ToolOutputMixin
from src.domains.connectors.clients.normalizers.microsoft_calendar_normalizer import (
    normalize_graph_calendar,
    normalize_graph_event,
)
from src.domains.connectors.clients.normalizers.microsoft_tasks_normalizer import (
    normalize_graph_task,
)


class NativeReferenceOutput(ToolOutputMixin):
    tool_name = "native_reference"
    operation = "details"


def microsoft_reference_domains(language: str) -> dict[str, dict[str, object]]:
    task = normalize_graph_task(
        {
            "id": "reference-native-task",
            "title": "Préparer la visite",
            "status": "inProgress",
            "categories": ["Design", "Accessibilité"],
            "isReminderOn": False,
            "hasAttachments": True,
            "dueDateTime": {"dateTime": "2027-07-01T09:00:00", "timeZone": "Europe/Paris"},
            "createdDateTime": "2026-10-01T09:00:00Z",
            "startDateTime": {"dateTime": "2027-06-30T10:00:00", "timeZone": "Europe/Paris"},
            "body": {
                "contentType": "html",
                "content": "<p>Préparer les accès.</p><p>Dernière étape : visiter le jardin.</p>",
            },
        }
    )
    event = normalize_graph_event(
        {
            "id": "reference-native-event",
            "subject": "Visite du jardin",
            "start": {"dateTime": "2026-10-05T09:00:00", "timeZone": "Europe/Paris"},
            "end": {"dateTime": "2026-10-05T10:00:00", "timeZone": "Europe/Paris"},
            "showAs": "free",
            "recurrence": {
                "pattern": {"type": "weekly", "interval": 2, "daysOfWeek": ["monday", "friday"]},
                "range": {
                    "type": "numbered",
                    "startDate": "2026-10-05",
                    "numberOfOccurrences": 12,
                    "recurrenceTimeZone": "Europe/Paris",
                },
            },
            "createdDateTime": "2026-10-01T09:00:00Z",
            "lastModifiedDateTime": "2026-10-02T09:00:00Z",
        }
    )
    calendar = normalize_graph_calendar(
        {"id": "reference-native-calendar", "name": "Calendrier de l’équipe", "canEdit": True}
    )
    producer = NativeReferenceOutput()
    tasks = producer.build_tasks_output([task], locale=language, user_timezone="UTC")
    events = producer.build_events_output([event], locale=language, user_timezone="UTC")
    calendars = ListCalendarsTool().format_registry_response({"calendars": [calendar], "total": 1})
    return {
        domain: {domain: [card_payload(item) for item in output.registry_updates.values()]}
        for domain, output in (("tasks", tasks), ("events", events), ("calendars", calendars))
    }
