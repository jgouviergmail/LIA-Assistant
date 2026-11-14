"""An e-mail card says what stays true of its reply state (ADR-379).

A card is archived HTML, replayed weeks later: « answered » and « a reply came » stay
true and are drawn; « no reply yet » and « a draft is waiting » are readings of a
moment and are not. A message the person answered no longer shows « reply expected »,
and the conversation's size, when the mailbox told it, is the thread chip.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from src.core.i18n_cards import card_label
from src.core.i18n_classification import classification_label
from src.core.mail_reply_state import REPLY_STATE_KEY
from src.domains.agents.display.components.base import RenderContext, escape_html
from src.domains.agents.display.components.email_card import EmailCard

pytestmark = [pytest.mark.unit]

LANGUAGES = ("fr", "en", "de", "es", "it", "zh-CN")
NOW = datetime.now(UTC)
_SETTLING = {
    "message_id": "m2",
    "at": "2026-11-10T09:30:00+01:00",
    "correspondents": "Marc",
    "excerpt": "Yes, Friday works.",
}


def _state(status: str, **over: Any) -> dict[str, Any]:
    return {
        "version": "mail-reply-state-v1",
        "status": status,
        "observed_at": NOW.isoformat(),
        "valid_until": (NOW + timedelta(minutes=2)).isoformat(),
        **over,
    }


def _email(reply_state: dict[str, Any] | None = None, **over: Any) -> dict[str, Any]:
    email: dict[str, Any] = {
        "id": "m1",
        "subject": "Budget 2027",
        "from": "Marc Dupont <marc@example.org>",
        "to": "Me <me@example.org>",
        "date": "Tue, 10 Nov 2026 08:00:00 +0000",
        "snippet": "Can you confirm Friday?",
        "labelIds": ["INBOX"],
        "attachments": [],
        "_provider": "google",
        **over,
    }
    if reply_state is not None:
        email[REPLY_STATE_KEY] = reply_state
    return email


def _reply_expected() -> dict[str, Any]:
    return {
        "evidence_scope": "snippet",
        "evaluated_at": NOW.isoformat(),
        "valid_until": (NOW + timedelta(minutes=5)).isoformat(),
        "category": "professional",
        "reply_expected": True,
    }


def _card(email: dict[str, Any], language: str = "en") -> str:
    return EmailCard().render(email, RenderContext(language=language))


@pytest.mark.parametrize("language", LANGUAGES)
def test_an_answered_message_says_so_in_the_readers_language(language: str) -> None:
    html = _card(_email(_state("answered", message=_SETTLING)), language)

    assert escape_html(card_label("email_answered", language)) in html


def test_a_message_the_mailbox_marked_answered_says_so_too() -> None:
    """The mark alone, with no reply found in the conversation, is still an answer."""
    html = _card(_email(_state("answered")))

    assert card_label("email_answered", "en") in html


def test_a_sent_message_someone_answered_says_a_reply_came() -> None:
    sent = _email(_state("reply_received", message=_SETTLING), labelIds=["SENT"])

    assert card_label("email_reply_received", "en") in _card(sent)


@pytest.mark.parametrize("status", ["unanswered", "awaiting_reply", "answer_drafted"])
def test_the_reading_of_a_moment_is_never_drawn_on_a_card_that_outlives_it(status: str) -> None:
    extra = {"message": _SETTLING} if status == "answer_drafted" else {}
    html = _card(_email(_state(status, **extra)))

    assert card_label("email_answered", "en") not in html
    assert card_label("email_reply_received", "en") not in html


class TestReplyExpectedIsSettledByAnAnswer:
    def test_an_answered_message_no_longer_reads_reply_expected(self) -> None:
        email = _email(_state("answered", message=_SETTLING), classification=_reply_expected())

        html = _card(email)

        assert classification_label("reply_expected", "en") not in html
        assert classification_label("professional", "en") in html  # the rest of the row stays

    @pytest.mark.parametrize("reply_state", [None, "unanswered"])
    def test_a_message_not_answered_keeps_it(self, reply_state: str | None) -> None:
        state = _state(reply_state) if reply_state else None

        html = _card(_email(state, classification=_reply_expected()))

        assert classification_label("reply_expected", "en") in html


class TestTheThreadChipIsTheConversationsSize:
    def test_a_conversation_of_several_messages_shows_its_size(self) -> None:
        html = _card(_email(_state("answered", message=_SETTLING, conversation_size=4)))

        assert 'lia-chip--thread"><span class="material-symbols-outlined">forum</span>4<' in html

    def test_a_message_alone_in_its_conversation_shows_none(self) -> None:
        html = _card(_email(_state("unanswered", conversation_size=1)))

        assert "lia-chip--thread" not in html
