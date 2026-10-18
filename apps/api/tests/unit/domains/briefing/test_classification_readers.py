"""Selected source -> DTO/cache roundtrip -> actual synthesis input contract."""

import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from src.core.content_classification import EmailClassification, EventClassification
from src.domains.agents.services.qualification import publication
from src.domains.briefing.classification import expire_cached_annotations
from src.domains.briefing.fetchers import fetch_agenda, fetch_mails
from src.domains.briefing.llm import _summarize_cards_for_llm
from src.domains.briefing.schemas import (
    AgendaData,
    CardsBundle,
    CardSection,
    CardStatus,
    MailsData,
)
from src.domains.connectors.active_client import ActiveClient
from src.domains.connectors.calendar_access import CalendarAccess
from src.domains.connectors.models import ConnectorType

pytestmark = pytest.mark.unit


def test_accepted_normal_priority_is_known_to_the_model_without_an_extra_badge():
    from src.core.classification_projection import classification_text
    from src.domains.agents.display.components.classification_badges import classification_badges

    now = datetime.now(UTC)
    annotation = EmailClassification(
        category="unknown",
        priority="normal",
        evidence_scope="body",
        evaluated_at=now,
        valid_until=now + timedelta(minutes=5),
    ).model_dump(mode="json")
    assert "priority=normal" in classification_text(annotation)
    assert classification_badges(annotation, "fr") == ""


def stamp():
    now = datetime.now(UTC)
    return {"evaluated_at": now, "valid_until": now + timedelta(minutes=5)}


def bundle(*, mails=None, agenda=None):
    empty = CardSection(status=CardStatus.NOT_CONFIGURED, generated_at=datetime.now(UTC))
    data = dict.fromkeys(CardsBundle.model_fields, empty)
    for key, value in (("mails", mails), ("agenda", agenda)):
        if value is not None:
            data[key] = CardSection(
                status=CardStatus.OK, data=value, generated_at=datetime.now(UTC)
            )
    return CardsBundle(**data)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "provider",
    [
        ConnectorType.GOOGLE_CALENDAR,
        ConnectorType.APPLE_CALENDAR,
        ConnectorType.MICROSOFT_CALENDAR,
    ],
)
async def test_event_read_and_actual_synthesis_share_annotation(monkeypatch, provider):
    item = {
        "id": "one",
        "summary": "Team review",
        "start": {"dateTime": (datetime.now(UTC) + timedelta(hours=1)).isoformat()},
    }
    client = SimpleNamespace(
        credentials=SimpleNamespace(account_binding="grant-a"),
        list_events=AsyncMock(return_value={"items": [item]}),
    )

    @asynccontextmanager
    async def opened(_user_id):
        yield CalendarAccess(client=client, calendar_id="work", connector_type=provider)

    monkeypatch.setattr("src.domains.connectors.calendar_access.open_active_calendar", opened)
    native = AsyncMock(
        return_value={
            "0": EventClassification(category="professional", evidence_scope="event", **stamp())
        }
    )
    monkeypatch.setattr(publication, "qualify_observations", native)
    result = await fetch_agenda(
        user=SimpleNamespace(id=uuid4()), user_tz=ZoneInfo("UTC"), language="en"
    )
    restored = AgendaData.model_validate_json(result.model_dump_json())
    for verbose in (False, True):
        context = json.loads(_summarize_cards_for_llm(bundle(agenda=restored), verbose=verbose))
        assert "professional" in context["agenda"][0]["qualification"]
    assert native.call_args.kwargs["observations"][0].container_id == "work"
    native.reset_mock()
    await fetch_agenda(
        user=SimpleNamespace(id=uuid4()),
        user_tz=ZoneInfo("UTC"),
        language="en",
        qualify_items=False,
    )
    native.assert_not_called()


def test_stale_source_facts_survive_but_expired_priority_does_not():
    from src.domains.briefing.schemas import MailItem

    now = datetime.now(UTC)
    annotation = EmailClassification(
        category="professional",
        priority="urgent",
        evidence_scope="snippet",
        evaluated_at=now - timedelta(minutes=10),
        valid_until=now - timedelta(minutes=5),
    )
    section = CardSection(
        status=CardStatus.OK,
        generated_at=now,
        data=MailsData(
            items=[MailItem(subject="Kept", received_local="09:00", classification=annotation)],
            total_unread_today=1,
        ),
    )
    result = expire_cached_annotations(section)
    assert result.data.items[0].subject == "Kept"
    assert result.data.items[0].classification is None
    assert section.data.items[0].classification == annotation


@pytest.mark.asyncio
async def test_mails_select_before_qualifying_and_greeting_receives_phishing(
    monkeypatch,
):
    messages = [
        {
            "id": str(i),
            "subject": "Code requested",
            "from": "fake@example.test",
            "snippet": "Send your login code",
        }
        for i in range(15)
    ]
    client = SimpleNamespace(credentials=SimpleNamespace(account_binding="actual-grant"))

    @asynccontextmanager
    async def opened(*_args):
        yield ActiveClient(
            client=client,
            connector_type=ConnectorType.GOOGLE_GMAIL,
            preferred_name="email",
        )

    monkeypatch.setattr("src.domains.connectors.active_client.open_active_client", opened)
    monkeypatch.setattr(
        "src.domains.briefing.fetchers._unread_inbox", AsyncMock(return_value=messages)
    )
    annotation = EmailClassification(
        category="phishing_scam", priority="normal", evidence_scope="snippet", **stamp()
    )
    native = AsyncMock(return_value={"0": annotation})
    monkeypatch.setattr(publication, "qualify_observations", native)
    result = await fetch_mails(
        user=SimpleNamespace(id=uuid4()), user_tz=ZoneInfo("UTC"), language="en"
    )
    assert len(native.call_args.kwargs["observations"]) == len(result.items) < 15
    restored = MailsData.model_validate_json(result.model_dump_json())
    for verbose in (False, True):
        context = json.loads(_summarize_cards_for_llm(bundle(mails=restored), verbose=verbose))
        assert "phishing_scam" in context["mails"]["items"][0]["qualification"]
    native.reset_mock()
    await fetch_mails(
        user=SimpleNamespace(id=uuid4()),
        user_tz=ZoneInfo("UTC"),
        language="en",
        qualify_items=False,
    )
    native.assert_not_called()
