"""Native end-to-end fixtures for host qualifications and selected map places."""

from datetime import UTC, datetime, timedelta
from importlib import import_module

from src.core.content_classification import EmailClassification, EventClassification
from src.domains.agents.data_registry.models import (
    RegistryItem,
    RegistryItemMeta,
    RegistryItemType,
)


def evolution_cards() -> dict[str, str]:
    now = datetime(2026, 10, 18, 12, tzinfo=UTC)
    until = now + timedelta(minutes=5)
    email = EmailClassification(
        category="phishing_scam",
        priority="unknown",
        evidence_scope="body",
        evaluated_at=now,
        valid_until=until,
    )
    event = EventClassification(
        category="professional",
        evidence_scope="body",
        evaluated_at=now,
        valid_until=until,
    )
    registry = {
        "email_fiction": RegistryItem(
            id="email_fiction",
            type=RegistryItemType.EMAIL,
            payload={
                "id": "fiction-email",
                "subject": "Demande suspecte",
                "from": "fiction@example.test",
                "body": "Message fictif pour vérifier le badge.",
                "classification": email.model_dump(mode="json"),
            },
            meta=RegistryItemMeta(source="gmail", domain="emails"),
        ),
        "event_fiction": RegistryItem(
            id="event_fiction",
            type=RegistryItemType.EVENT,
            payload={
                "id": "fiction-event",
                "summary": "Réunion de travail",
                "start": {"dateTime": "2026-10-18T14:00:00Z"},
                "end": {"dateTime": "2026-10-18T15:00:00Z"},
                "classification": event.model_dump(mode="json"),
            },
            meta=RegistryItemMeta(source="google_calendar", domain="events"),
        ),
    }
    for identity, name, location in [
        ("east", "Lieu Est", {"latitude": 0, "longitude": 179.9}),
        ("west", "Lieu Ouest", {"latitude": 1, "longitude": -179.9}),
        ("same", "Lieu aux mêmes coordonnées", {"latitude": 0, "longitude": 179.9}),
        ("missing", "Lieu sans coordonnées", None),
    ]:
        registry[identity] = RegistryItem(
            id=f"place_{identity}",
            type=RegistryItemType.PLACE,
            payload={
                "id": identity,
                "displayName": {"text": name},
                "location": location,
            },
            meta=RegistryItemMeta(source="google_places", domain="places"),
        )
    renderer = import_module("src.domains.agents.nodes.response_node")._render_response_html
    selected = {key: item.model_dump(mode="json") for key, item in registry.items()}
    result = {"classified_at": now.isoformat()}
    for key, mode in (("html", "cards"), ("html_mode", "html"), ("markdown", "markdown")):
        result[key] = renderer(
            final_content="Résultat sélectionné.",
            current_turn_registry=selected,
            resolved_context_for_html=None,
            user_display_mode=mode,
            user_viewport="desktop",
            user_language="fr",
            user_timezone="UTC",
            run_id="evolution-fixture",
        )
    return result
