"""An unread mail on the Today briefing says whether the person already answered it (ADR-379).

The card lists UNREAD mail, and unread is not unanswered: a message answered from a
phone's notification stays unread. Until 2026-11-11 the card, the greeting, the
synthesis and the radio read each mail alone, so an answered message kept its « reply
expected » badge and could be named among the mail awaiting an answer.
"""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from src.core.config import settings
from src.core.content_classification import EmailClassification
from src.core.mail_reply_state import ReplyMessage, ReplyState, ReplyStatus
from src.core.prompt_store import read_prompt_file
from src.domains.briefing.fetchers import fetch_mails
from src.domains.briefing.prompt_cards import _summarize_cards_for_llm
from src.domains.briefing.schemas import (
    CardsBundle,
    CardSection,
    CardStatus,
    MailItem,
    MailsData,
)
from src.domains.connectors.active_client import ActiveClient
from src.domains.connectors.clients.mail_conversation import Conversation
from src.domains.connectors.models import ConnectorType
from src.domains.radio.personal import PersonalSource, briefing_drafts

pytestmark = pytest.mark.unit


def _received(message_id: str) -> dict[str, Any]:
    """An unread message of the inbox, received an hour ago."""
    return {
        "id": message_id,
        "threadId": f"t-{message_id}",
        "labelIds": ["INBOX", "UNREAD"],
        "from": "Marc Dupont <marc@example.org>",
        "subject": f"subject {message_id}",
        "snippet": "a line of it",
        "internalDate": str(int(time.time() * 1000) - 3_600_000),
    }


def _reply(message_id: str, thread: str) -> dict[str, Any]:
    """The person's own answer in ``thread``, sent a minute ago."""
    return {
        "id": message_id,
        "threadId": thread,
        "labelIds": ["SENT"],
        "from": "Me <me@example.org>",
        "to": "Marc Dupont <marc@example.org>",
        "snippet": "my words",
        "internalDate": str(int(time.time() * 1000) - 60_000),
    }


def _mailbox(found: list[dict[str, Any]], conversations: dict[str, Conversation]) -> AsyncMock:
    """A mailbox listing ``found`` (as many as it is asked) and telling ``conversations``."""
    mailbox = AsyncMock()
    mailbox.credentials = SimpleNamespace(account_binding="grant")

    async def _search(*, max_results: int, **_: object) -> dict[str, Any]:
        return {"messages": [dict(message) for message in found[:max_results]]}

    mailbox.search_emails = AsyncMock(side_effect=_search)
    mailbox.conversations_of = AsyncMock(return_value=conversations)
    return mailbox


async def _fetch(monkeypatch: pytest.MonkeyPatch, mailbox: AsyncMock, **options: bool) -> MailsData:
    """The card's own read of ``mailbox``, qualification apart (no model is asked)."""

    @asynccontextmanager
    async def _opened(*_: object) -> AsyncIterator[ActiveClient]:
        yield ActiveClient(
            client=mailbox, connector_type=ConnectorType.GOOGLE_GMAIL, preferred_name="email"
        )

    monkeypatch.setattr("src.domains.connectors.active_client.open_active_client", _opened)
    return await fetch_mails(
        user=SimpleNamespace(id=uuid4()),
        user_tz=ZoneInfo("Europe/Paris"),
        language="en",
        qualify_items=False,
        **options,
    )


class TestTheCardSaysWhereEachMailStands:
    async def test_mail_the_person_already_answered_says_so(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        asked, new = _received("asked"), _received("new")
        told = {
            "t-asked": Conversation(messages=(asked, _reply("r1", "t-asked"))),
            "t-new": Conversation(messages=(new,)),
        }

        data = await _fetch(monkeypatch, _mailbox([asked, new], told))

        standing = {item.id: item.reply_state and item.reply_state.status for item in data.items}
        assert standing == {"asked": "answered", "new": "unanswered"}
        # The card is cached as JSON and read back: the state must come back whole.
        assert MailsData.model_validate_json(data.model_dump_json()) == data

    async def test_only_what_the_card_lists_is_looked_up(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The editorial read scans far more mail than it lists: a conversation is read
        for a listed message alone."""
        cap = settings.briefing_max_mails_items
        mailbox = _mailbox([_received(f"m{index}") for index in range(cap + 3)], {})

        data = await _fetch(monkeypatch, mailbox, exclude_commercial_mails=True)

        looked_up = [message["id"] for message in mailbox.conversations_of.await_args.args[0]]
        assert looked_up == [item.id for item in data.items]
        assert len(looked_up) == cap

    async def test_a_reader_that_only_matches_the_listing_reads_no_conversation(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A routine's condition matches a sender or a subject: nothing to situate."""
        mailbox = _mailbox([_received("m")], {})

        data = await _fetch(monkeypatch, mailbox, situate_items=False)

        mailbox.conversations_of.assert_not_awaited()
        assert data.items[0].reply_state is None


def _state(status: ReplyStatus, *, observed_ago: timedelta = timedelta(0)) -> ReplyState:
    """A reading made ``observed_ago``, valid two minutes from then."""
    observed = datetime.now(UTC) - observed_ago
    settled_by = (
        ReplyMessage(
            message_id="r1",
            at=observed - timedelta(minutes=5),
            correspondents="Marc Dupont",
            excerpt="my words",
        )
        if status == "answered"
        else None
    )
    return ReplyState(
        status=status,
        message=settled_by,
        observed_at=observed,
        valid_until=observed + timedelta(minutes=2),
    )


def _asking_for_a_reply() -> EmailClassification:
    now = datetime.now(UTC)
    return EmailClassification(
        category="professional",
        priority="normal",
        reply_expected=True,
        evidence_scope="snippet",
        evaluated_at=now,
        valid_until=now + timedelta(minutes=5),
    )


def _mail(subject: str, **annotations: Any) -> MailItem:
    return MailItem(
        id=subject, subject=subject, sender_name="Marc", received_local="09:12", **annotations
    )


def _cards(*mails: MailItem) -> CardsBundle:
    now = datetime.now(UTC)
    sections = dict.fromkeys(
        CardsBundle.model_fields, CardSection(status=CardStatus.NOT_CONFIGURED, generated_at=now)
    )
    sections["mails"] = CardSection(
        status=CardStatus.OK,
        generated_at=now,
        data=MailsData(items=list(mails), total_unread_today=len(mails)),
    )
    return CardsBundle(**sections)


class TestWhatTheGreetingAndTheSynthesisAreTold:
    @pytest.mark.parametrize("verbose", [False, True], ids=["greeting", "synthesis"])
    def test_an_answered_mail_says_so_beside_what_it_asked_for(self, verbose: bool) -> None:
        answered = _mail(
            "Quote", classification=_asking_for_a_reply(), reply_state=_state("answered")
        )

        told = json.loads(_summarize_cards_for_llm(_cards(answered), verbose=verbose))

        mail = told["mails"]["items"][0]
        assert "reply_expected=true" in mail["qualification"]
        assert mail["reply_state"].startswith("answered on ")
        assert mail["reply_state"].endswith("to Marc Dupont — my words")

    def test_a_reading_of_a_moment_too_old_to_repeat_says_nothing(self) -> None:
        """The card is cached longer than « nobody answered yet » stays true."""
        stale = _mail("Quote", reply_state=_state("unanswered", observed_ago=timedelta(minutes=4)))

        told = json.loads(_summarize_cards_for_llm(_cards(stale), verbose=True))

        assert "reply_state" not in told["mails"]["items"][0]

    def test_an_answer_given_stays_given_however_old_the_card(self) -> None:
        old = _mail("Quote", reply_state=_state("answered", observed_ago=timedelta(minutes=4)))

        told = json.loads(_summarize_cards_for_llm(_cards(old), verbose=True))

        assert told["mails"]["items"][0]["reply_state"].startswith("answered on ")

    @pytest.mark.parametrize("prompt", ["briefing_greeting_prompt", "briefing_synthesis_prompt"])
    def test_a_prompt_reading_the_mail_items_explains_the_field(self, prompt: str) -> None:
        """A field nobody explains is read as the model pleases."""
        assert "`reply_state`" in read_prompt_file(prompt)


def test_the_radio_does_not_announce_mail_the_person_already_answered() -> None:
    """An answered mail is no news; the count of unread mail stays the mailbox's."""
    cards = _cards(_mail("Answered", reply_state=_state("answered")), _mail("Waiting"))

    said = [draft.text for draft in briefing_drafts(cards)[PersonalSource.MAILS]]

    assert any('"Waiting"' in line for line in said)
    assert not any('"Answered"' in line for line in said)
    assert "Unread e-mails received today: 2" in said
