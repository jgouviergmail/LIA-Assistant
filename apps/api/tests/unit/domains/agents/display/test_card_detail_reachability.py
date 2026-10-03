"""Selected provider facts remain reachable beyond a card's initial preview."""

from typing import Any

import pytest

from src.core.config import settings
from src.core.i18n_cards import card_label
from src.domains.agents.display.components.base import BaseComponent, RenderContext
from src.domains.agents.display.components.contact_card import ContactCard
from src.domains.agents.display.components.email_card import EmailCard
from src.domains.agents.display.components.event_card import EventCard
from src.domains.agents.display.components.file_item import FileItem
from src.domains.agents.display.components.task_item import TaskItem

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("language", ["fr", "en", "de", "es", "it", "zh-CN"])
@pytest.mark.parametrize(
    ("component", "data", "needles"),
    [
        (
            TaskItem(),
            {
                "title": "Task without a provider URL",
                "notes": "notes " * 90 + "FINAL_NOTE",
                "links": [
                    {"link": f"https://example.test/{i}", "description": f"LINK_{i}"}
                    for i in range(7)
                ],
                "subtasks": [{"title": f"SUBTASK_{i}", "status": "completed"} for i in range(13)]
                + [None, {"title": ""}],
            },
            ["FINAL_NOTE", "LINK_6", "SUBTASK_12", "13/13"],
        ),
        (
            ContactCard(),
            {
                "displayName": "Contact",
                "emailAddresses": [{"value": f"person{i}@example.test"} for i in range(7)],
                "phoneNumbers": [{"value": f"+3310000000{i}"} for i in range(7)],
                "addresses": [{"formattedValue": f"ADDRESS_{i}"} for i in range(5)],
                "biographies": [{"value": "bio " * 75 + "FINAL_BIO"}, {"value": "SECOND_BIO"}],
                "nicknames": [{"value": f"NICKNAME_{i}"} for i in range(7)],
                "skills": [{"value": f"SKILL_{i}"} for i in range(7)],
                "relations": [{"person": f"RELATION_{i}"} for i in range(7)],
            },
            [
                "person6@example.test",
                "tel:+33100000006",
                "ADDRESS_4",
                "FINAL_BIO",
                "SECOND_BIO",
                "NICKNAME_6",
                "SKILL_6",
                "RELATION_6",
            ],
        ),
        (
            EmailCard(),
            {
                "subject": "Email",
                "body": "body " * (settings.emails_body_max_length + 1) + "FINAL_BODY",
                "to": [{"email": f"to{i}@example.test"} for i in range(14)],
                "cc": [{"email": f"cc{i}@example.test"} for i in range(13)],
                "attachments": [{"filename": f"ATTACHMENT_{i}.pdf"} for i in range(8)],
                "labelIds": [f"LABEL_{i}" for i in range(7)],
            },
            ["FINAL_BODY", "to13@example.test", "cc12@example.test", "ATTACHMENT_7.pdf", "LABEL_6"],
        ),
        (
            EventCard(),
            {
                "summary": "Event",
                "description": "description " * 150 + "FINAL_DESCRIPTION",
                "attendees": [{"email": f"attendee{i}@example.test"} for i in range(14)],
                "attachments": [{"title": f"ATTACHMENT_{i}"} for i in range(7)],
                "reminders": {
                    "overrides": [{"minutes": i * 17, "method": "popup"} for i in range(5)]
                },
            },
            ["FINAL_DESCRIPTION", "attendee13@example.test", "ATTACHMENT_6"],
        ),
        (
            FileItem(),
            {
                "name": "File",
                "mimeType": "text/plain",
                "description": "description " * 40 + "FINAL_DESCRIPTION",
                "content": "content " * 70 + "FINAL_CONTENT",
            },
            ["FINAL_DESCRIPTION", "FINAL_CONTENT"],
        ),
    ],
    ids=["task", "contact", "email", "event", "file"],
)
def test_every_supplied_detail_is_reachable(
    language: str, component: BaseComponent, data: dict[str, Any], needles: list[str]
) -> None:
    out = component.render(data, RenderContext(language=language))
    assert "<details" in out
    for needle in needles:
        assert needle in out
    assert 'href=""' not in out


def test_invalid_subtasks_do_not_distort_progress_or_expose_raw_values() -> None:
    out = TaskItem().render(
        {
            "title": "Task",
            "subtasks": [
                None,
                {"title": ""},
                {"title": {"private": "secret"}},
                {"title": "Valid", "status": "completed"},
            ],
        },
        RenderContext(language="en"),
    )
    assert "1/1" in out
    assert "private" not in out and "secret" not in out


@pytest.mark.parametrize("language", ["fr", "en", "de", "es", "it", "zh-CN"])
def test_a_long_email_excerpt_remains_reachable_without_claiming_a_full_body(language: str) -> None:
    out = EmailCard().render(
        {"subject": "Summary", "snippet": "excerpt " * 50 + "FINAL_EXCERPT"},
        RenderContext(language=language),
    )
    assert "FINAL_EXCERPT" in out
    assert card_label("excerpt", language) in out
    assert card_label("full_message", language) not in out


def test_long_email_reading_preserves_the_configured_preview_and_safe_links(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "emails_body_max_length", 100)
    out = EmailCard().render(
        {
            "subject": "Body",
            "body": "word " * 50
            + '<script>secret()</script>FINAL_BODY <a href="javascript:alert(1)">unsafe</a>',
        },
        RenderContext(language="en"),
    )
    trigger = card_label("full_message", "en")
    before, _, after = out.partition(trigger)
    assert "FINAL_BODY" not in before
    assert "FINAL_BODY" in after
    assert "secret()" not in out and "javascript:" not in out
