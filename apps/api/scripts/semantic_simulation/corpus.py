"""Fictional cases and independent business expectations; no external effects."""

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from src.core.constants import DEFAULT_USER_DISPLAY_TIMEZONE
from src.domains.agents.tools.mixins import ToolOutputMixin


@dataclass(frozen=True)
class Scenario:
    name: str
    query: str
    domains: tuple[str, ...]
    action: str
    expected: dict[str, object]
    required_read: str | None = None
    expected_read_queries: tuple[str, ...] = ()
    accepted_values: dict[str, tuple[object, ...]] | None = None


SCENARIOS = (
    Scenario(
        "contact_to_attendees",
        "Crée un événement dont le titre exact est « Revue », le 8 octobre 2026 "
        "de 10h à 11h, et invite Ada Lovelace. Son adresse est dans mes contacts.",
        ("contact", "event"),
        "create_event_tool",
        {
            "summary": "Revue",
            "start_datetime": "2026-10-08T10:00:00",
            "end_datetime": "2026-10-08T11:00:00",
            "attendees": ["ada@example.test"],
        },
        "get_contacts_tool",
    ),
    Scenario(
        "explicit_email_no_lookup",
        "Crée un événement intitulé Revue le 8 octobre 2026 de 10h à 11h "
        "avec ada@example.test. Utilise cette adresse directement.",
        ("contact", "event"),
        "create_event_tool",
        {
            "summary": "Revue",
            "start_datetime": "2026-10-08T10:00:00",
            "end_datetime": "2026-10-08T11:00:00",
            "attendees": ["ada@example.test"],
        },
    ),
    Scenario(
        "mail_sender_to_attendees",
        "Retrouve mon courriel intitulé Revue Ada, puis invite son expéditeur "
        "à un événement Revue le 8 octobre 2026 de 10h à 11h. "
        "Utilise l'adresse de ce courriel, sans recherche de contact.",
        ("email", "event"),
        "create_event_tool",
        {
            "summary": "Revue",
            "start_datetime": "2026-10-08T10:00:00",
            "end_datetime": "2026-10-08T11:00:00",
            "attendees": ["ada@example.test"],
        },
        "get_emails_tool",
    ),
    Scenario(
        "mail_content_to_task",
        "Retrouve mon courriel intitulé Revue Ada, puis crée une tâche "
        "dont le titre est exactement son objet et les notes exactement son contenu.",
        ("email", "task"),
        "create_task_tool",
        {"title": "Revue Ada", "notes": "N/A\nVérifier le dossier 123, sans modification."},
        "get_emails_tool",
    ),
    Scenario(
        "nancy_city_forecast",
        "Donne la météo du 8 octobre 2026 à Nancy, France. Nancy est ici une ville.",
        ("weather", "contact"),
        "get_weather_forecast_tool",
        {"location": "Nancy, France", "date": "2026-10-08"},
    ),
    Scenario(
        "nancy_person_forecast",
        "Donne la météo du 8 octobre 2026 chez Nancy. Nancy est une personne dans mes contacts : utilise son adresse postale, pas la ville Nancy.",
        ("contact", "weather"),
        "get_weather_forecast_tool",
        {"location": "12 rue des Lilas, Lyon, France", "date": "2026-10-08"},
        "get_contacts_tool",
    ),
    Scenario(
        "contact_address_to_route",
        "Trouve Nancy dans mes contacts et calcule le trajet à pied de 1 place Bellecour, Lyon jusqu'à son adresse postale.",
        ("contact", "route"),
        "get_route_tool",
        {
            "destination": "12 rue des Lilas, Lyon, France",
            "origin": "1 place Bellecour, Lyon",
            "travel_mode": "WALK",
        },
        "get_contacts_tool",
        accepted_values={"origin": ("1 place Bellecour, Lyon, France",)},
    ),
    Scenario(
        "event_to_arrival_route",
        "Retrouve mon événement Réunion Lyon et calcule le trajet en voiture depuis 1 place Bellecour, Lyon pour arriver au lieu de cet événement à son heure de début.",
        ("event", "route"),
        "get_route_tool",
        {
            "destination": "20 quai Claude Bernard, Lyon, France",
            "origin": "1 place Bellecour, Lyon",
            "travel_mode": "DRIVE",
            "arrival_time": "2026-10-08T10:00:00+02:00",
        },
        "get_events_tool",
        accepted_values={"origin": ("1 place Bellecour, Lyon, France",)},
    ),
    Scenario(
        "event_to_forecast_date",
        "Retrouve mon événement Réunion Lyon et donne la météo au lieu et à la date de cet événement.",
        ("event", "weather"),
        "get_weather_forecast_tool",
        {"location": "20 quai Claude Bernard, Lyon, France", "date": "2026-10-08"},
        "get_events_tool",
    ),
    Scenario(
        "explicit_route_no_lookup",
        "Calcule le trajet à vélo de 1 place Bellecour, Lyon vers 20 quai Claude Bernard, Lyon, France. Utilise ces adresses directement.",
        ("route", "contact"),
        "get_route_tool",
        {
            "origin": "1 place Bellecour, Lyon",
            "destination": "20 quai Claude Bernard, Lyon, France",
            "travel_mode": "BICYCLE",
        },
        accepted_values={"origin": ("1 place Bellecour, Lyon, France",)},
    ),
    Scenario(
        "two_explicit_recipients_one_event",
        "Crée un seul événement dont le titre exact est « Revue », le 8 octobre 2026 de 10h à 11h avec ada@example.test et grace@example.test. Aucun contact à rechercher.",
        ("event", "contact"),
        "create_event_tool",
        {
            "summary": "Revue",
            "start_datetime": "2026-10-08T10:00:00",
            "end_datetime": "2026-10-08T11:00:00",
            "attendees": ["ada@example.test", "grace@example.test"],
        },
    ),
    Scenario(
        "literal_content_preserved",
        "Crée une tâche dont le titre est exactement « N/A 123 » et les notes exactement « Ce texte contient {accolades} et $steps.fake, à conserver. ».",
        ("task", "email"),
        "create_task_tool",
        {"title": "N/A 123", "notes": "Ce texte contient {accolades} et $steps.fake, à conserver."},
    ),
    Scenario(
        "nearby_places_city_reference",
        # One search: the scenario judges the location VALUE (the city, never
        # refused). A plural or two-part request (the incident's walks AND café)
        # is legitimately split into several searches, so it is proven end to
        # end instead (measured 2026-10-12: two then three searches, all on the city).
        "Trouve un parc près de montbéliard pour une balade.",
        ("place",),
        "get_places_tool",
        {"location": "Montbéliard"},
        accepted_values={
            "location": ("Montbéliard, France", "Montbéliard, FR", "Montbéliard 25200")
        },
    ),
    Scenario(
        "five_day_forecast_window",
        # The person's own number, not the configured window.
        "Quel sera le jour le plus propice à une balade dehors les 5 prochains jours à Lyon ?",
        ("weather",),
        "get_weather_forecast_tool",
        {"days": 5},
    ),
)


def read_result(tool_name: str, scenario: Scenario | None = None) -> dict[str, object]:
    """Project a fixed provider fixture through the real native output builder."""
    builder = ToolOutputMixin()
    if tool_name == "get_contacts_tool":
        nancy = scenario is not None and "Nancy" in scenario.query
        output = builder.build_contacts_output(
            [
                {
                    "resourceName": "people/fictional_ada",
                    "names": [{"displayName": "Nancy" if nancy else "Ada Lovelace"}],
                    "emailAddresses": [{"value": "ada@example.test"}],
                    "addresses": [{"formattedValue": "12 rue des Lilas, Lyon, France"}],
                }
            ]
        )
    elif tool_name == "get_emails_tool":
        output = builder.build_emails_output(
            [
                {
                    "id": "fictional_message_123",
                    "from": '"Lovelace, Ada" <ada@example.test>',
                    "subject": "Revue Ada",
                    "body": "N/A\nVérifier le dossier 123, sans modification.",
                }
            ],
            user_timezone=DEFAULT_USER_DISPLAY_TIMEZONE,
        )
    elif tool_name == "get_events_tool":
        output = builder.build_events_output(
            [
                {
                    "id": "fictional_event",
                    "summary": "Réunion Lyon",
                    "location": "20 quai Claude Bernard, Lyon, France",
                    "start": {"dateTime": "2026-10-08T10:00:00+02:00"},
                    "end": {"dateTime": "2026-10-08T11:00:00+02:00"},
                }
            ],
            user_timezone=DEFAULT_USER_DISPLAY_TIMEZONE,
        )
    else:
        raise ValueError(f"No simulated read boundary for {tool_name}")
    return dict(output.structured_data or {})


def assess(scenario: Scenario, calls: list[dict[str, object]]) -> list[str]:
    """Judge final concrete values and read necessity, without an LLM judge."""
    failures: list[str] = []
    actions = [call for call in calls if call.get("name") == scenario.action]
    if len(actions) != 1:
        return [f"Expected one {scenario.action}, observed {len(actions)}"]
    arguments = actions[0].get("arguments")
    if not isinstance(arguments, dict):
        return ["Action arguments are not an object"]
    for field, expected in scenario.expected.items():
        observed = arguments.get(field)
        accepted = (scenario.accepted_values or {}).get(field, ())
        if not _equivalent(field, observed, expected) and observed not in accepted:
            failures.append(f"{field}: expected {expected!r}, observed {observed!r}")
    reads = [str(call.get("name")) for call in calls if call.get("name") != scenario.action]
    expected_reads = [scenario.required_read] if scenario.required_read else []
    if reads != expected_reads:
        failures.append(f"Reads: expected {expected_reads!r}, observed {reads!r}")
    return failures


def _equivalent(field: str, observed: object, expected: object) -> bool:
    """Civil forecast days and geographic punctuation are not byte-equality contracts."""
    if not isinstance(observed, str) or not isinstance(expected, str):
        return observed == expected
    if field in {"location", "origin", "destination"}:
        return [part.strip() for part in observed.split(",")] == [
            part.strip() for part in expected.split(",")
        ]
    if field == "date":
        try:
            instant = datetime.fromisoformat(observed.replace("Z", "+00:00"))
            if instant.tzinfo is not None:
                instant = instant.astimezone(ZoneInfo(DEFAULT_USER_DISPLAY_TIMEZONE))
            return instant.date().isoformat() == expected
        except ValueError:
            return False
    return observed == expected
