"""Publication preserves source evidence and shares one annotation with both readers."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.core.content_classification import EmailClassification
from src.domains.agents.data_registry.models import (
    RegistryItem,
    RegistryItemMeta,
    RegistryItemType,
)
from src.domains.agents.display.llm_serializer import payload_to_text
from src.domains.agents.formatters.text_summary import generate_text_summary_for_llm
from src.domains.agents.services.qualification import publication
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.react_tool_wrapper import extract_data_for_llm

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_metadata_body_is_never_sent_and_annotation_survives_roundtrip(
    monkeypatch,
):
    now = datetime.now(UTC)
    annotation = EmailClassification(
        category="phishing_scam",
        priority="critical",
        evidence_scope="snippet",
        evaluated_at=now,
        valid_until=now + timedelta(minutes=5),
    )
    native = AsyncMock(return_value={"email_one": annotation})
    monkeypatch.setattr(publication, "qualify_observations", native)
    payload = {
        "id": "one",
        "subject": "Account",
        "snippet": "Give us your code",
        "_display_only": {"body": "HIDDEN SECRET"},
        "payload": {"body": "RAW"},
    }
    item = RegistryItem(
        id="email_one",
        type=RegistryItemType.EMAIL,
        payload=payload,
        meta=RegistryItemMeta(source="gmail", domain="emails"),
    )
    output = UnifiedToolOutput.data_success(
        message="one",
        registry_updates={item.id: item},
        structured_data={"emails": [payload]},
    )
    result = await publication.qualify_tool_output(
        output,
        client=SimpleNamespace(credentials=SimpleNamespace(account_binding="grant-a")),
        provider="gmail",
        user_id=uuid4(),
        timezone="Europe/Paris",
    )
    evidence = native.call_args.kwargs["observations"][0].evidence
    assert "HIDDEN SECRET" not in str(evidence) and "RAW" not in str(evidence)
    restored = UnifiedToolOutput.model_validate_json(result.model_dump_json())
    assert "phishing_scam" in payload_to_text(restored.registry_updates[item.id].payload)
    assert "phishing_scam" in extract_data_for_llm(restored)
    assert "critical" in extract_data_for_llm(restored)
    assert "phishing_scam" in generate_text_summary_for_llm(restored.registry_updates, "fr")
    assert restored.registry_updates[item.id].payload["subject"] == "Account"


@pytest.mark.asyncio
async def test_failure_preserves_source_and_clears_untrusted_annotation(monkeypatch):
    monkeypatch.setattr(publication, "qualify_observations", AsyncMock(side_effect=TimeoutError))
    item = RegistryItem(
        id="event_one",
        type=RegistryItemType.EVENT,
        payload={
            "id": "one",
            "summary": "Appointment",
            "classification": {"category": "personal"},
        },
        meta=RegistryItemMeta(source="google_calendar", domain="events"),
    )
    output = UnifiedToolOutput.data_success(message="one", registry_updates={item.id: item})
    result = await publication.qualify_tool_output(
        output,
        client=SimpleNamespace(credentials=SimpleNamespace(account_binding="grant-a")),
        provider="google_calendar",
        user_id=uuid4(),
        timezone="UTC",
    )
    assert "classification" not in result.registry_updates[item.id].payload
    assert result.registry_updates[item.id].payload["summary"] == "Appointment"


def test_binding_is_from_actual_client_and_never_from_a_password():
    a = SimpleNamespace(
        credentials=SimpleNamespace(apple_id="a@example.test", app_password="secret")
    )
    b = SimpleNamespace(
        credentials=SimpleNamespace(apple_id="b@example.test", app_password="secret")
    )
    assert publication.source_binding(a) != publication.source_binding(b)
    assert "secret" not in publication.source_binding(a)
    assert publication.source_binding(object()) == ""


def test_server_badges_are_closed_and_model_cannot_forge_host_container():
    from src.domains.agents.display.components.classification_badges import (
        classification_badges,
    )
    from src.domains.agents.display.sentinel_filter import strip_widget_sentinels

    now = datetime.now(UTC)
    annotation = EmailClassification(
        category="phishing_scam",
        priority="normal",
        evidence_scope="metadata",
        evaluated_at=now,
        valid_until=now + timedelta(minutes=5),
    )
    html = classification_badges(annotation.model_dump(mode="json"), "fr")
    assert "Phishing/Arnaque" in html and "normal" not in html
    assert 'role="alert"' not in html
    assert strip_widget_sentinels(html + "source text")[0] == "source text"
    assert classification_badges({"category": "phishing_scam"}, "en") == ""


@pytest.mark.parametrize("key,scope", [("gist", "summary"), ("body", "partial_body")])
def test_allowed_digest_or_partial_body_is_identified(key, scope):
    value = publication.observation(
        "one", {"id": "one", key: "visible evidence", "body_parts": 2}, kind="email"
    )
    assert value.evidence_scope == scope


@pytest.mark.asyncio
async def test_real_email_builder_keeps_display_body_out_of_both_model_inputs(
    monkeypatch,
):
    from src.domains.agents.tools.mixins import ToolOutputMixin

    now = datetime.now(UTC)
    annotation = EmailClassification(
        category="professional",
        priority="urgent",
        evidence_scope="snippet",
        evaluated_at=now,
        valid_until=now + timedelta(minutes=5),
    )
    payload = {
        "id": "one",
        "subject": "Review",
        "snippet": "Today please",
        "_display_only": {"body": "HIDDEN SECRET"},
        "payload": {"headers": [], "body": "RAW MIME"},
    }
    output = ToolOutputMixin().build_emails_output([payload], detail="metadata")
    identity = next(iter(output.registry_updates))
    native = AsyncMock(return_value={identity: annotation})
    monkeypatch.setattr(publication, "qualify_observations", native)
    await publication.qualify_tool_output(
        output,
        client=SimpleNamespace(credentials=SimpleNamespace(account_binding="actual")),
        provider="gmail",
        user_id=uuid4(),
        timezone="UTC",
    )
    pipeline = generate_text_summary_for_llm(output.registry_updates, "en")
    react = extract_data_for_llm(output)
    for source in (pipeline, react, str(native.call_args.kwargs["observations"])):
        assert "HIDDEN SECRET" not in source and "RAW MIME" not in source
        assert "Review" in source
    assert "professional" in pipeline and "urgent" in react
    assert output.registry_updates[identity].meta.display["body"] == "HIDDEN SECRET"


def test_provider_facts_reach_the_judgment_under_the_unified_names() -> None:
    """Labels, reply-to and a calendar entry's own type were dropped before 2026-10-25."""
    mail = publication.observation(
        "m",
        {
            "id": "m",
            "subject": "Offer",
            "snippet": "Up to 40 % off",
            "labelIds": ["INBOX", "CATEGORY_PROMOTIONS"],
            "reply_to": "deals@example.test",
        },
        kind="email",
    )
    assert mail is not None
    assert mail.evidence["labels"] == ["INBOX", "CATEGORY_PROMOTIONS"]
    assert mail.evidence["reply_to"] == "deals@example.test"
    event = publication.observation(
        "e",
        {
            "id": "e",
            "summary": "Focus",
            "eventType": "focusTime",
            "hangoutLink": "https://meet.example.test/x",
            "recurringEventId": "r1",
        },
        kind="event",
    )
    assert event is not None
    assert event.evidence["event_type"] == "focusTime"
    assert event.evidence["video_call"] is True and event.evidence["recurring"] is True
    assert "hangoutLink" not in event.evidence  # a join link is a fact, never the link


def test_an_untyped_entry_carries_no_invented_type_or_flags() -> None:
    event = publication.observation(
        "e", {"id": "e", "summary": "Lunch", "eventType": "default", "recurrence": []}, kind="event"
    )
    assert event is not None
    assert not {"event_type", "video_call", "recurring"} & set(event.evidence)
