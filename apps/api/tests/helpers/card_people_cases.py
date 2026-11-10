"""Fictional, network-free density fixtures through the actual registry boundary."""

from datetime import UTC, datetime, timedelta

from src.core.content_classification import EmailClassification
from src.domains.agents.data_registry.card_payload import card_payload
from src.domains.agents.data_registry.models import RegistryItem
from tests.helpers.card_microsoft_reference import NativeReferenceOutput


def ten_email_messages() -> list[dict[str, object]]:
    """Return ten distinct fictional messages, each with a complete received body."""
    subjects = (
        "Les plans du jardin sont prêts",
        "Votre visite de samedi",
        "Le devis de la verrière",
        "Les graines sont arrivées",
        "Une question sur les accès",
        "Le compte rendu de notre atelier",
        "La prochaine permanence",
        "Votre réservation est confirmée",
        "Les photos du chantier",
        "Le programme de décembre",
    )
    senders = ("Camille Vernet", "Noémie Roussel", "Idriss Moreau", "Louise Mercier")
    messages: list[dict[str, object]] = []
    for index, subject in enumerate(subjects, 1):
        messages.append(
            {
                "id": f"envelope-message-{index}",
                "subject": subject,
                "from": f"{senders[(index - 1) % len(senders)]} <sender{index}@example.test>",
                "to": '"Martin, Alex" <alex@example.test>, équipe@example.test',
                "cc": "Louise Mercier <louise@example.test>",
                "date": f"2026-11-{index:02d}T09:30:00Z",
                "snippet": f"Bonjour Alex, voici les nouvelles du jardin — message {index}.",
                "body": (
                    f"Bonjour Alex,\n\nVoici les nouvelles du jardin — message {index}. "
                    "Les allées seront accessibles dès samedi. Le rendez-vous se tient "
                    "à l'entrée principale, sous la verrière. Merci de prévoir des chaussures "
                    "adaptées et de confirmer votre présence.\n\n"
                    f"Dernière précision reçue : EMAIL_COMPLETE_BODY_{index}."
                ),
                "labelIds": ["INBOX", "UNREAD"] if index < 3 else ["INBOX"],
                "threadCount": 3 if index == 1 else 1,
                "attachments": (
                    [
                        {
                            "filename": "Plan du jardin.pdf",
                            "mimeType": "application/pdf",
                            "size": 8420,
                        }
                    ]
                    if index == 1
                    else []
                ),
            }
        )
    evaluated_at = datetime(2026, 11, 7, 12, tzinfo=UTC)
    messages[0]["classification"] = EmailClassification(
        category="personal",
        priority="normal",
        evidence_scope="body",
        evaluated_at=evaluated_at,
        valid_until=evaluated_at + timedelta(minutes=5),
    ).model_dump(mode="json")
    messages[0]["labelIds"] = ["INBOX", "UNREAD", "STARRED"]
    messages[1]["labelIds"] = ["SENT"]
    messages[2]["labelIds"] = ["TRASH"]
    messages[3]["labelIds"] = ["SPAM"]
    return messages


def seven_guest_event() -> dict[str, object]:
    """Return an invitation with seven fictional people and varied explicit responses."""
    names = (
        "Camille Vernet",
        "Idriss Moreau",
        "Louise Mercier",
        "Noémie Roussel",
        "Alex Martin",
        "Émile Laurent",
        "Sacha Perrin",
    )
    responses = ("accepted", "tentative", "declined", "needsAction", "needsAction", "", "accepted")
    attendees: list[dict[str, object]] = []
    for index, (name, response) in enumerate(zip(names, responses, strict=True), 1):
        person: dict[str, object] = {
            "displayName": name,
            "email": f"guest{index}@example.test",
        }
        if response:
            person["responseStatus"] = response
        if index == 5:
            person["self"] = True
        if index == 1:
            person.update(optional=False, additionalGuests=0, comment="J’apporte le plan.")
        if index == 2:
            person.update(optional=True, additionalGuests=2)
        attendees.append(person)
    return {
        "id": "invitation-seven-guests",
        "summary": "Un jardin pour le quartier",
        "start": {"dateTime": "2026-11-21T09:30:00Z", "timeZone": "Europe/Paris"},
        "end": {"dateTime": "2026-11-21T11:00:00Z", "timeZone": "Europe/Paris"},
        "created": "2026-11-01T10:00:00Z",
        "updated": "2026-11-07T11:15:00Z",
        "location": "La Verrière, 18 rue des Tilleuls",
        "status": "confirmed",
        "htmlLink": "https://calendar.example.test/invitation-seven-guests",
        "organizer": {"displayName": "Atelier des Tilleuls", "email": "atelier@example.test"},
        "description": (
            "Nous préparons ensemble les plantations de printemps.\n\n"
            "Au programme : accueil, visite des parcelles et répartition des prochaines étapes. "
            "Apporter un carnet. EVENT_COMPLETE_DESCRIPTION."
        ),
        "attendees": attendees,
        "conferenceData": {
            "entryPoints": [{"entryPointType": "video", "uri": "https://video.example.test/garden"}]
        },
        "reminders": {"useDefault": False, "overrides": [{"method": "popup", "minutes": 30}]},
    }


def people_density_domains(language: str) -> dict[str, dict[str, object]]:
    """Project the fictional payloads through producers and a JSON registry round-trip."""
    producer = NativeReferenceOutput()
    emails = producer.build_emails_output(
        ten_email_messages(), locale=language, user_timezone="UTC"
    )
    events = producer.build_events_output(
        [seven_guest_event()], locale=language, user_timezone="UTC"
    )
    return {
        domain: {
            domain: [
                card_payload(RegistryItem.model_validate_json(item.model_dump_json()))
                for item in output.registry_updates.values()
            ]
        }
        for domain, output in (("emails", emails), ("events", events))
    }
