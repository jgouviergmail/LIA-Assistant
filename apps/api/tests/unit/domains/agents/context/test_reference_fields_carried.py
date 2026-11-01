"""Every field a context type declares is carried by what each provider stores (ADR-367).

A description (« Marc's email », « the meeting with Marc », « Jean from Lyon »)
is matched against the STORED items — the registry payloads the builders make
from each provider's normalised data. A declared field the payload never
carries matches nothing, silently: the e-mail type declared ``from_email`` (an
address, or None) and not ``from`` (the sender's name); events declared
``start_datetime`` (the payload carries ``start.dateTime``); files ``mime_type``
(``mimeType``); the CalDAV normaliser dropped the organiser Google and Outlook
both keep. So every provider's payload is built here by the REAL normaliser and
the REAL builder, and every declared field must carry text the matcher reads —
the candidate fields too: what « which one? » shows of each option.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
import vobject
from imap_tools.utils import EmailAddress

from src.domains.agents.context.descriptor_match import strings_at
from src.domains.agents.context.registry import ContextTypeRegistry
from src.domains.agents.tools.mixins import ToolOutputMixin
from src.domains.connectors.clients.google_gmail_client import GoogleGmailClient
from src.domains.connectors.clients.normalizers.calendar_normalizer import normalize_vevent
from src.domains.connectors.clients.normalizers.contacts_normalizer import normalize_vcard
from src.domains.connectors.clients.normalizers.email_normalizer import normalize_imap_message
from src.domains.connectors.clients.normalizers.microsoft_calendar_normalizer import (
    normalize_graph_event,
)
from src.domains.connectors.clients.normalizers.microsoft_contacts_normalizer import (
    normalize_graph_contact,
)
from src.domains.connectors.clients.normalizers.microsoft_email_normalizer import (
    normalize_graph_message,
)
from src.domains.connectors.clients.normalizers.microsoft_tasks_normalizer import (
    normalize_graph_task,
)

pytestmark = pytest.mark.unit


class _Builder(ToolOutputMixin):
    operation = "search"


def _payloads(output: Any) -> list[dict[str, Any]]:
    return [
        (item.model_dump() if hasattr(item, "model_dump") else item)["payload"]
        for item in (output.registry_updates or {}).values()
    ]


# --- e-mails -----------------------------------------------------------------------------


def _gmail() -> dict[str, Any]:
    message: dict[str, Any] = {
        "id": "18f0",
        "threadId": "18f0",
        "labelIds": ["INBOX"],
        "snippet": "Voici les photos",
        "internalDate": "1789493085929",
        "payload": {
            "mimeType": "text/plain",
            "headers": [
                {"name": "From", "value": "Marc Dubois <marc@example.com>"},
                {"name": "To", "value": "Moi <me@example.net>"},
                {"name": "Subject", "value": "Photos du week-end"},
            ],
            "body": {"data": ""},
        },
    }
    GoogleGmailClient._normalize_message_fields(message, "full")
    return message


def _graph_mail() -> dict[str, Any]:
    return normalize_graph_message(
        {
            "id": "AAMk-1",
            "conversationId": "c-1",
            "subject": "Photos du week-end",
            "from": {"emailAddress": {"name": "Marc Dubois", "address": "marc@example.com"}},
            "toRecipients": [{"emailAddress": {"name": "Moi", "address": "me@example.net"}}],
            "receivedDateTime": "2026-09-15T17:24:45Z",
            "body": {"contentType": "text", "content": "Voici les photos"},
            "bodyPreview": "Voici les photos",
        }
    )


def _imap_mail() -> dict[str, Any]:
    message = SimpleNamespace(
        uid="42",
        subject="Photos du week-end",
        from_="marc@example.com",
        from_values=EmailAddress("Marc Dubois", "marc@example.com"),
        to=("me@example.net",),
        to_values=(EmailAddress("Moi", "me@example.net"),),
        cc=(),
        bcc=(),
        date=datetime(2026, 9, 15, 17, 24, 45, tzinfo=UTC),
        date_str="Tue, 15 Sep 2026 17:24:45 +0000",
        text="Voici les photos",
        html="",
        attachments=[],
        flags=(),
    )
    return normalize_imap_message(message, "INBOX")


def _emails(source: Callable[[], dict[str, Any]]) -> list[dict[str, Any]]:
    return _payloads(_Builder().build_emails_output(emails=[source()], user_timezone="UTC"))


# --- events ------------------------------------------------------------------------------

_ICS = (
    "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\nUID:ev-1\r\n"
    "DTSTART:20261103T100000Z\r\nDTEND:20261103T110000Z\r\nSUMMARY:Réunion budget\r\n"
    "LOCATION:Bureau\r\nDESCRIPTION:Préparer les chiffres\r\n"
    "ORGANIZER;CN=Marc Dubois:mailto:marc@example.com\r\n"
    "ATTENDEE;CN=Sophie Laurent;PARTSTAT=ACCEPTED:mailto:sophie@example.org\r\n"
    "END:VEVENT\r\nEND:VCALENDAR\r\n"
)


def _google_event() -> dict[str, Any]:
    return {
        "id": "g-1",
        "summary": "Réunion budget",
        "location": "Bureau",
        "description": "Préparer les chiffres",
        "start": {"dateTime": "2026-11-03T10:00:00Z"},
        "end": {"dateTime": "2026-11-03T11:00:00Z"},
        "organizer": {"email": "marc@example.com", "displayName": "Marc Dubois"},
        "attendees": [{"email": "sophie@example.org", "displayName": "Sophie Laurent"}],
    }


def _graph_event() -> dict[str, Any]:
    return normalize_graph_event(
        {
            "id": "o-1",
            "subject": "Réunion budget",
            "bodyPreview": "Préparer les chiffres",
            "body": {"contentType": "text", "content": "Préparer les chiffres"},
            "location": {"displayName": "Bureau"},
            "start": {"dateTime": "2026-11-03T10:00:00", "timeZone": "UTC"},
            "end": {"dateTime": "2026-11-03T11:00:00", "timeZone": "UTC"},
            "organizer": {"emailAddress": {"name": "Marc Dubois", "address": "marc@example.com"}},
            "attendees": [
                {
                    "emailAddress": {"name": "Sophie Laurent", "address": "sophie@example.org"},
                    "status": {"response": "accepted"},
                }
            ],
        }
    )


def _caldav_event() -> dict[str, Any]:
    calendar = vobject.readOne(_ICS)
    event = SimpleNamespace(vobject_instance=calendar, url="https://caldav.example.com/ev-1.ics")
    return normalize_vevent(event)


def _events(source: Callable[[], dict[str, Any]]) -> list[dict[str, Any]]:
    return _payloads(_Builder().build_events_output(events=[source()], user_timezone="UTC"))


# --- contacts ----------------------------------------------------------------------------

_VCARD = (
    "BEGIN:VCARD\r\nVERSION:3.0\r\nFN:Jean Martin\r\nN:Martin;Jean;;;\r\n"
    "EMAIL;TYPE=HOME:jean.martin@example.com\r\nORG:Acme\r\n"
    "ADR;TYPE=HOME:;;12 rue de la République;Lyon;;69002;France\r\n"
    "NOTE:Ami d'enfance\r\nEND:VCARD\r\n"
)


def _people_contact() -> dict[str, Any]:
    return {
        "resourceName": "people/c1",
        "names": [{"displayName": "Jean Martin", "givenName": "Jean"}],
        "emailAddresses": [{"value": "jean.martin@example.com"}],
        "organizations": [{"name": "Acme"}],
        "addresses": [{"formattedValue": "12 rue de la République, 69002 Lyon", "city": "Lyon"}],
        "biographies": [{"value": "Ami d'enfance"}],
    }


def _graph_contact() -> dict[str, Any]:
    return normalize_graph_contact(
        {
            "id": "c-1",
            "displayName": "Jean Martin",
            "givenName": "Jean",
            "surname": "Martin",
            "emailAddresses": [{"name": "Jean Martin", "address": "jean.martin@example.com"}],
            "companyName": "Acme",
            "homeAddress": {"street": "12 rue de la République", "city": "Lyon"},
            "personalNotes": "Ami d'enfance",
        }
    )


def _vcard_contact() -> dict[str, Any]:
    return normalize_vcard(_VCARD, resource_name="people/apple-1")


def _contacts(source: Callable[[], dict[str, Any]]) -> list[dict[str, Any]]:
    return _payloads(_Builder().build_contacts_output(contacts=[source()]))


# --- tasks, files, places ----------------------------------------------------------------


def _google_task() -> dict[str, Any]:
    return {
        "id": "t-1",
        "title": "Appeler le garage",
        "notes": "Pour la révision",
        "status": "needsAction",
        "due": "2026-11-05T00:00:00.000Z",
    }


def _graph_task() -> dict[str, Any]:
    return normalize_graph_task(
        {
            "id": "t-1",
            "title": "Appeler le garage",
            "body": {"content": "Pour la révision", "contentType": "text"},
            "status": "notStarted",
            "dueDateTime": {"dateTime": "2026-11-05T00:00:00.0000000", "timeZone": "UTC"},
        }
    )


def _tasks(source: Callable[[], dict[str, Any]]) -> list[dict[str, Any]]:
    return _payloads(_Builder().build_tasks_output(tasks=[source()], user_timezone="UTC"))


def _files() -> list[dict[str, Any]]:
    drive = {"id": "f-1", "name": "Devis cuisine.pdf", "mimeType": "application/pdf"}
    return _payloads(_Builder().build_files_output(files=[drive]))


def _places() -> list[dict[str, Any]]:
    from src.domains.agents.tools.places_formatting import _format_place

    place = {
        "id": "p-1",
        "displayName": {"text": "Le Petit Bistro"},
        "formattedAddress": "3 rue de Lyon, Paris",
        "types": ["restaurant", "food"],
        "location": {"latitude": 48.85, "longitude": 2.35},
    }
    return _payloads(_Builder().build_places_output(places=[_format_place(place, language="fr")]))


COVERED: dict[str, dict[str, Callable[[], list[dict[str, Any]]]]] = {
    "emails": {
        "google": lambda: _emails(_gmail),
        "microsoft": lambda: _emails(_graph_mail),
        "apple": lambda: _emails(_imap_mail),
    },
    "events": {
        "google": lambda: _events(_google_event),
        "microsoft": lambda: _events(_graph_event),
        "apple": lambda: _events(_caldav_event),
    },
    "contacts": {
        "google": lambda: _contacts(_people_contact),
        "microsoft": lambda: _contacts(_graph_contact),
        "apple": lambda: _contacts(_vcard_contact),
    },
    "tasks": {"google": lambda: _tasks(_google_task), "microsoft": lambda: _tasks(_graph_task)},
    "files": {"google": _files},
    "places": {"google": _places},
}

#: Context types nobody designates by description to ACT on it, each with why.
EXEMPT: dict[str, str] = {
    "locations": "a resolved position the planner binds, never a listed choice",
    "routes": "computed between two points the person named; nothing to designate",
    "weathers": "the provider's raw forecast; a forecast is asked again, never acted on",
    "hues": "the lamp tools resolve a name against the LIVE light list themselves",
    "tickets": "the workboard resolves a ticket title itself, refusing an ambiguous one",
    "sms_messages": "read-only relay of received messages; no action takes one",
    "health_signals": "measurements, designated by kind and period, never by words",
    "wikipedias": "web results: read, never acted on",
    "braves": "web results: read, never acted on",
    "perplexitys": "web results: read, never acted on",
    "web_searchs": "web results: read, never acted on",
    "web_fetchs": "a fetched page, read, never acted on",
    "browsers": "a browsed page, read, never acted on",
    "querys": "a local computation over other results",
}


def test_every_context_type_is_covered_or_exempt_with_a_reason() -> None:
    from src.domains.agents.registry.agent_registry import AgentRegistry
    from src.domains.agents.registry.catalogue_loader import initialize_catalogue
    from src.domains.agents.tools import tool_registry

    # The context types the product uses are the keys its tool manifests
    # declare — what the boot validates (`_validate_context_key_registrations`).
    # The global registry is not read: other tests register throwaway types.
    tool_registry.ensure_tools_loaded()
    registry = AgentRegistry()
    initialize_catalogue(registry)
    declared = {m.context_key for m in registry.list_tool_manifests() if m.context_key}
    assert declared <= set(ContextTypeRegistry.list_all())
    assert declared == set(COVERED) | set(EXEMPT), (
        "a context type was added or removed: cover it below with each provider's "
        "real payload, or exempt it with the reason nobody designates it by words"
    )


@pytest.mark.parametrize(
    ("domain", "provider"),
    [(domain, provider) for domain, sources in COVERED.items() for provider in sources],
)
def test_every_declared_field_is_carried_by_the_provider_payload(
    domain: str, provider: str
) -> None:
    definition = ContextTypeRegistry.get_definition(domain)
    (payload,) = COVERED[domain][provider]()

    declared = (
        *definition.reference_fields,
        *definition.content_reference_fields,
        *definition.candidate_fields,
    )
    empty = [
        field for field in declared if not any(text.strip() for text in strings_at(payload, field))
    ]

    assert not empty, f"{domain}/{provider}: declared fields {empty} carry no text"
