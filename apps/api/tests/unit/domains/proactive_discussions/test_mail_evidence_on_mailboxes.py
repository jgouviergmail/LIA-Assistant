"""A discussion's mail evidence, found on a page then read again alone, on each mailbox (ADR-379).

A proactive discussion finds a mail on a page of the person's mailbox, then reads it again
by its reference before any use (ADR-358): both reads must say the same thing, or the run
stops as a changed fact — and what they say must include what the mailbox itself knows of
the message, that the person already answered it.

No Outlook nor iCloud mailbox can be measured (no live proof on a consumer mailbox since
2026-11-11). So the REAL gateway, source and client run here over a mailbox scripted from
the providers' own references (``graph_mailbox``, ``imap_wire``): every request is the
client's own and claims the read's physical-call allowance through its own transport.
Only the reader's authority is stubbed — the real one reads the connector's row in the
database, never the provider.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import httpx
import pytest

from src.core.constants import (
    DISCUSSION_READ_CALL_LIMIT_DEFAULT,
    DISCUSSION_RESEARCH_ITEM_LIMIT_DEFAULT,
)
from src.domains.connectors import discussion_sources
from src.domains.connectors.active_client import ActiveClient
from src.domains.connectors.clients.apple_email_client import AppleEmailClient
from src.domains.connectors.clients.microsoft_outlook_client import MicrosoftOutlookClient
from src.domains.connectors.discussion_sources import EmailDiscussionSource
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.schemas import AppleCredentials, ConnectorCredentials
from src.domains.proactive_discussions.contextualization.loop import ContextResult
from src.domains.proactive_discussions.run_types import RunClaim
from src.domains.proactive_discussions.schemas import DiscussionPolicy
from src.domains.proactive_discussions.source_gateway import SourceGateway
from src.domains.shared.discussion_sources import (
    ResearchRequest,
    SourceKey,
    SourceReadRequest,
    SourceSnapshot,
)
from src.infrastructure.proactive.discussion_attention import InitiativeStopped
from src.infrastructure.proactive.discussion_revalidation import revalidate_evidence
from tests.unit.domains.connectors.clients.graph_mailbox import GraphMailbox
from tests.unit.domains.connectors.clients.imap_wire import WireImapServer, plug_imap_wire

pytestmark = pytest.mark.unit

OWNER = UUID(int=7)
RUN = UUID(int=8)
NOW = datetime(2026, 11, 10, 10, tzinfo=UTC)
APPLE = "src.domains.connectors.clients.apple_email_client"
SOURCE = "src.domains.connectors.discussion_sources"
#: Longer than the 255 characters a Graph listing previews: only a whole read holds its end.
QUOTE_BODY = (
    "Hello Jane, here is the quote for the roof we talked about last week. "
    "The scaffolding goes up on the 23rd, the tiles are delivered the day after, "
    "and the whole job should take four working days if the weather holds. "
    "The price includes the removal of the old gutter and the new zinc flashing. "
    "Can you confirm before Friday so I can book the team?"
)

Serve = Callable[[Any, ConnectorType], None]


async def _policy(_owner: UUID) -> DiscussionPolicy:
    return DiscussionPolicy(enabled=True, sources=(SourceKey.EMAILS,), revision=0)


def _gateway() -> SourceGateway:
    return SourceGateway(dict.fromkeys(SourceKey, EmailDiscussionSource()), _policy)


def _read(
    operation: str = "recent",
    *,
    reference: str | None = None,
    cursor: str | None = None,
    item_limit: int = 5,
    call_limit: int = 8,
) -> SourceReadRequest:
    return SourceReadRequest(
        owner_id=OWNER,
        run_id=RUN,
        policy_revision=0,
        request=ResearchRequest(source=SourceKey.EMAILS, operation=operation, reference=reference),
        cursor=cursor,
        now=NOW,
        window_start=NOW - timedelta(days=3),
        window_end=NOW + timedelta(hours=1),
        item_limit=item_limit,
        item_max_chars=4000,
        call_limit=call_limit,
        timeout_seconds=10,
    )


async def _revalidated(page: SourceSnapshot) -> tuple[SourceSnapshot, ...]:
    """What a run does before any use of a page's facts: read each one again."""
    claim = RunClaim(
        owner_id=OWNER,
        run_id=RUN,
        fence=1,
        policy_revision=0,
        context_epoch=0,
        lease_until=datetime.now(UTC) + timedelta(minutes=5),
    )
    return await revalidate_evidence(
        claim, ContextResult(True, page.items, (), (page,)), _gateway()
    )


def _by_subject(page: SourceSnapshot, subject: str) -> Any:
    return next(item for item in page.items if f'"subject":"{subject}"' in item.excerpt)


@pytest.fixture
def serve(monkeypatch: pytest.MonkeyPatch) -> Serve:
    """Hand the source ONE mailbox client, under an authority that costs no provider call."""

    def _serve(client: Any, connector_type: ConnectorType) -> None:
        @asynccontextmanager
        async def open_client(category: str, owner: UUID, **kwargs: Any) -> AsyncIterator[Any]:
            assert (category, owner, kwargs) == ("email", OWNER, {"fresh": True})
            yield ActiveClient(client=client, connector_type=connector_type, preferred_name=None)

        async def authority(*_args: Any, **_kwargs: Any) -> str:
            return "the-mailbox-account-scope"

        monkeypatch.setattr(f"{SOURCE}.open_active_client", open_client)
        monkeypatch.setattr(f"{SOURCE}.require_reader_authority", authority)

    return _serve


@pytest.fixture
async def outlook(monkeypatch: pytest.MonkeyPatch, serve: Serve) -> AsyncIterator[GraphMailbox]:
    """An Outlook inbox of two mails; the person answered the quote on the 9th at 13:40 UTC."""
    mailbox = GraphMailbox()
    mailbox.receive(
        "AAMkAGI2-quote",
        subject="Roof quote",
        sender=("Paul Martin", "paul@example.com"),
        received="2026-11-09T08:12:00Z",
        html=f"<html><body><p>{QUOTE_BODY}</p></body></html>",
    )
    mailbox.receive(
        "AAMkAGI2-trip",
        subject="School trip",
        sender=("Anna Keller", "anna@example.org"),
        received="2026-11-08T17:30:00Z",
        html="<p>The trip is on the 20th. Please send the form back.</p>",
    )
    mailbox.stamp_last_verb("AAMkAGI2-quote", 102, "2026-11-09T13:40:00Z")
    build = httpx.AsyncClient
    # The client builds its own HTTP client — hooks included — on the scripted transport.
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kwargs: build(transport=mailbox.transport(), **kwargs)
    )
    client = MicrosoftOutlookClient(
        user_id=OWNER,
        credentials=ConnectorCredentials(
            access_token="token",
            refresh_token="refresh",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            token_type="Bearer",
        ),
        connector_service=MagicMock(),
    )
    monkeypatch.setattr(client, "_rate_limit", AsyncMock())
    serve(client, ConnectorType.MICROSOFT_OUTLOOK)
    yield mailbox
    await client.close()


def _mail(subject: str, message_id: str, body: str) -> EmailMessage:
    message = EmailMessage()
    message["From"] = "Paul Martin <paul@example.com>"
    message["To"] = "jane@icloud.com"
    message["Subject"] = subject
    message["Message-ID"] = message_id
    message["Date"] = "Mon, 09 Nov 2026 08:12:00 +0000"
    message.set_content(body)
    return message


@pytest.fixture
def icloud(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch, serve: Serve
) -> WireImapServer:
    """An iCloud inbox of two mails; the person's mail client flagged the quote as answered."""
    server = WireImapServer(**getattr(request, "param", {}))
    received = NOW - timedelta(days=1)
    server.deliver(
        101,
        _mail("Roof quote", "<quote@example.com>", QUOTE_BODY),
        received=received,
        flags=("\\Seen", "\\Answered"),
    )
    server.deliver(
        102,
        _mail("School trip", "<trip@example.org>", "Please send the form back."),
        received=received,
        flags=("\\Seen",),
    )
    plug_imap_wire(monkeypatch, server)
    client = AppleEmailClient(
        user_id=OWNER,
        credentials=AppleCredentials(apple_id="jane@icloud.com", app_password="abcd-efgh-ijkl"),
        connector_service=MagicMock(),
    )
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    breaker = MagicMock(check=AsyncMock(), record_success=AsyncMock(), record_failure=AsyncMock())
    monkeypatch.setattr(f"{APPLE}.get_redis_session", AsyncMock(return_value=redis))
    monkeypatch.setattr(client, "_rate_limit", AsyncMock())
    monkeypatch.setattr(client, "_get_circuit_breaker", MagicMock(return_value=breaker))
    serve(client, ConnectorType.APPLE_EMAIL)
    return server


#: A server states FLAGS where it pleases in a FETCH answer: both places are read.
either_flag_place = pytest.mark.parametrize(
    "icloud", [{"flags_after_body": False}, {"flags_after_body": True}], indirect=True
)
#: A greeting that carries the capabilities spares the client one command: both are read.
either_greeting = pytest.mark.parametrize(
    "icloud", [{}, {"greets_with_capabilities": True}], indirect=True
)


class TestOnOutlook:
    """Graph lists a preview; the proof is read again whole. One read per hit makes them one."""

    async def test_a_mail_found_on_a_page_is_the_mail_read_again(
        self, outlook: GraphMailbox
    ) -> None:
        page = await _gateway().read(_read())

        assert page.status == "ok" and len(page.items) == 2
        again = await _revalidated(page)  # a changed fact would stop the run here

        assert [fresh.items[0].version for fresh in again] == [item.version for item in page.items]
        assert [fresh.physical_calls for fresh in again] == [1, 1]  # the mark with the message

    async def test_the_page_holds_each_mail_whole_for_one_read_apiece(
        self, outlook: GraphMailbox
    ) -> None:
        page = await _gateway().read(_read())

        assert "book the team?" in _by_subject(page, "Roof quote").excerpt  # past the preview
        assert outlook.paths() == [
            "/me/mailFolders/inbox/messages",
            "/me/messages/AAMkAGI2-quote",
            "/me/messages/AAMkAGI2-trip",
        ]
        assert page.physical_calls == 3

    async def test_a_mail_the_person_answered_says_so_and_when(self, outlook: GraphMailbox) -> None:
        page = await _gateway().read(_read())

        assert '"reply_state":"answered on 2026-11-09T13:40+00:00"' in (
            _by_subject(page, "Roof quote").excerpt
        )
        assert "reply_state" not in _by_subject(page, "School trip").excerpt

    async def test_an_answer_given_since_the_page_was_read_is_a_changed_fact(
        self, outlook: GraphMailbox
    ) -> None:
        page = await _gateway().read(_read())
        outlook.stamp_last_verb("AAMkAGI2-trip", 103, "2026-11-10T09:55:00Z")

        with pytest.raises(InitiativeStopped) as stopped:
            await _revalidated(page)

        assert stopped.value.reason == "evidence_changed"

    async def test_a_page_lists_no_more_mails_than_its_allowance_reads_whole(
        self, outlook: GraphMailbox
    ) -> None:
        """One call lists, one reads each hit: the rest waits for the next page."""
        first = await _gateway().read(_read(call_limit=2))

        assert outlook.requests[0].url.params["$top"] == "1"
        assert (first.status, len(first.items), first.physical_calls) == ("truncated", 1, 2)

        second = await _gateway().read(_read(call_limit=2, cursor=first.cursor))

        assert [item.object_id for item in (*first.items, *second.items)] == [
            "AAMkAGI2-quote",
            "AAMkAGI2-trip",
        ]

    async def test_an_allowance_that_reads_no_mail_whole_is_said(
        self, outlook: GraphMailbox
    ) -> None:
        page = await _gateway().read(_read(call_limit=1))

        assert (page.status, page.reason, page.items) == ("unavailable", "budget", ())


class TestOnICloud:
    """IMAP returns a message's flags with every FETCH: the mark costs no command.

    Every command is a call of the read's allowance, so a page comes in one FETCH.
    """

    @either_flag_place
    async def test_a_mail_the_person_answered_says_so(self, icloud: WireImapServer) -> None:
        page = await _gateway().read(_read())

        assert '"reply_state":"answered"' in _by_subject(page, "Roof quote").excerpt
        assert "reply_state" not in _by_subject(page, "School trip").excerpt

    @either_flag_place
    async def test_a_mail_found_on_a_page_is_the_mail_read_again(
        self, icloud: WireImapServer
    ) -> None:
        page = await _gateway().read(_read())

        again = await _revalidated(page)

        assert [fresh.items[0].version for fresh in again] == [item.version for item in page.items]

    async def test_the_mark_costs_no_command(self, icloud: WireImapServer) -> None:
        """The session's commands and the page's one FETCH, as for any bounded page."""
        page = await _gateway().read(_read())

        assert icloud.commands == ["CAPABILITY", "LOGIN", "SELECT", "UID SEARCH", "UID FETCH"]
        assert page.physical_calls == len(icloud.commands)

    @either_greeting
    async def test_a_full_page_comes_in_one_command_within_the_default_allowance(
        self, icloud: WireImapServer
    ) -> None:
        """A FETCH per message spent the default allowance before a full page was read."""
        full = DISCUSSION_RESEARCH_ITEM_LIMIT_DEFAULT
        for uid in range(103, 101 + full):
            icloud.deliver(
                uid,
                _mail(f"Newsletter {uid}", f"<news{uid}@example.net>", "This week's notes."),
                received=NOW - timedelta(days=1),
                flags=("\\Seen",),
            )

        page = await _gateway().read(
            _read(item_limit=full, call_limit=DISCUSSION_READ_CALL_LIMIT_DEFAULT)
        )

        assert len(page.items) == full
        assert icloud.commands.count("UID FETCH") == 1
        assert page.physical_calls == len(icloud.commands)

    async def test_a_page_read_in_one_command_lists_the_newest_first(
        self, icloud: WireImapServer
    ) -> None:
        page = await _gateway().read(_read())

        assert [json.loads(item.excerpt)["subject"] for item in page.items] == [
            "School trip",
            "Roof quote",
        ]

    async def test_a_read_nothing_bounds_fetches_one_message_per_command(
        self, icloud: WireImapServer
    ) -> None:
        """Outside a bounded read a page may be large: its messages come one at a time."""
        async with discussion_sources.open_active_client("email", OWNER, fresh=True) as opened:
            listing = await opened.client.search_emails("", max_results=5, use_cache=False)

        assert len(listing["messages"]) == 2
        assert icloud.commands.count("UID FETCH") == 2

    async def test_an_answer_given_since_the_page_was_read_is_a_changed_fact(
        self, icloud: WireImapServer
    ) -> None:
        page = await _gateway().read(_read())
        icloud.flag(102, "\\Answered")

        with pytest.raises(InitiativeStopped) as stopped:
            await _revalidated(page)

        assert stopped.value.reason == "evidence_changed"
