"""A mailbox draft is drawn as the person's own unsent message (ADR-344).

The card says it is a draft, in the reader's language and in words — never by
colour alone; it is headed by the people the draft is for (its sender is always
the person); it offers no « Reply » nor « Forward », which would answer the
person's own draft; and a Gmail draft opens in Gmail's compose window.
"""

from __future__ import annotations

from typing import Any

import pytest
from langchain_core.messages import AIMessage

from src.core.field_names import FIELD_MAILBOX_DRAFT_ID
from src.core.i18n_cards import card_label
from src.core.i18n_v3 import V3Messages
from src.domains.agents.display.card_actions import CARD_ACTIONS_KEY, with_card_actions
from src.domains.agents.display.components.base import RenderContext, escape_html
from src.domains.agents.display.components.email_card import EmailCard

pytestmark = [pytest.mark.unit]

LANGUAGES = ("fr", "en", "de", "es", "it", "zh-CN")


def _draft(**overrides: Any) -> dict[str, Any]:
    return {
        "id": "m1",
        FIELD_MAILBOX_DRAFT_ID: "r-1",
        "subject": "Budget 2027",
        "from": "Me <me@example.com>",
        "to": "Paul Durand <paul@example.com>, marie@example.com",
        "date": "Tue, 13 Oct 2026 09:00:00 +0000",
        "snippet": "The figures hold.",
        "body": "The figures hold.",
        "labelIds": ["DRAFT"],
        "attachments": [],
        "_provider": "google",
        **overrides,
    }


@pytest.mark.parametrize("language", LANGUAGES)
def test_a_draft_says_so_in_the_readers_language(language: str) -> None:
    html = EmailCard().render(_draft(), RenderContext(language=language))

    assert escape_html(card_label("mailbox_draft", language)) in html


def test_the_label_is_translated_in_every_language() -> None:
    assert len({card_label("mailbox_draft", lang) for lang in LANGUAGES}) == len(LANGUAGES)


def test_a_draft_is_headed_by_its_recipients() -> None:
    html = EmailCard().render(_draft(), RenderContext(language="en"))

    assert "Paul Durand" in html
    assert "mailto:me@example.com" not in html


def test_a_draft_without_a_recipient_says_so() -> None:
    html = EmailCard().render(_draft(to=""), RenderContext(language="fr"))

    assert escape_html(card_label("no_recipient", "fr")) in html


def test_a_draft_offers_no_reply_nor_forward() -> None:
    html = EmailCard().render(_draft(), RenderContext(language="en"))

    assert escape_html(V3Messages.get_reply("en")) not in html
    assert escape_html(V3Messages.get_forward("en")) not in html


def test_a_received_message_keeps_its_actions() -> None:
    received = _draft(labelIds=["INBOX"])
    del received[FIELD_MAILBOX_DRAFT_ID]

    html = EmailCard().render(received, RenderContext(language="en"))

    assert escape_html(V3Messages.get_reply("en")) in html


def test_a_gmail_draft_opens_in_the_compose_window() -> None:
    html = EmailCard().render(_draft(), RenderContext(language="en"))

    assert "https://mail.google.com/mail/u/0/#drafts?compose=m1" in html


def test_a_draft_listed_by_its_label_alone_is_a_draft_too() -> None:
    labelled = _draft()
    del labelled[FIELD_MAILBOX_DRAFT_ID]

    html = EmailCard().render(labelled, RenderContext(language="en"))

    assert escape_html(card_label("mailbox_draft", "en")) in html
    assert escape_html(V3Messages.get_reply("en")) not in html


def test_a_draft_offers_no_composition_target() -> None:
    answer = with_card_actions(
        AIMessage(content="Your drafts"),
        {
            "email_a": {
                "type": "EMAIL",
                "payload": _draft(),
                "meta": {
                    "source": "gmail",
                    "display": {"_lia_email_account": "00000000-0000-0000-0000-000000000004"},
                },
            }
        },
        run_id="run-a",
        enabled=True,
    )

    assert CARD_ACTIONS_KEY not in answer.additional_kwargs
