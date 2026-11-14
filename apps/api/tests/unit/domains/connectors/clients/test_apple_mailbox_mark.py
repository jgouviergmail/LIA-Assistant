"""What its own mailbox says of a message — « answered » — is read WITH the message on IMAP (ADR-379).

No iCloud account can be measured, so this follows the protocol and the library. RFC 3501
§2.3.2 defines ``\\Answered`` as « Message has been answered »: a flag the client that sent
the reply stores on the original. Every FETCH returns a message's flags beside the part it
reads — ``imap_tools`` asks ``(BODY.PEEK[…] UID FLAGS RFC822.SIZE)``, headers alone or
whole — so the mark costs no command of its own. The fake server hands out real
``imap_tools`` messages parsed from FETCH data shaped as the RFC shapes them.
"""

from __future__ import annotations

from collections.abc import Iterator
from email.message import EmailMessage
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.field_names import FIELD_MAIL_ANSWERED, FIELD_MAIL_ANSWERED_AT
from src.domains.connectors.clients.apple_email_client import AppleEmailClient
from src.domains.connectors.schemas import AppleCredentials
from tests.unit.domains.connectors.clients.imap_fakes import FakeImap

pytestmark = pytest.mark.unit

APPLE = "src.domains.connectors.clients.apple_email_client"
APPLE_STATE = "src.domains.connectors.clients.apple_mail_state_mixin"


def _mail(subject: str, message_id: str) -> EmailMessage:
    message = EmailMessage()
    message["From"] = "Paul Martin <paul@example.com>"
    message["To"] = "jane@icloud.com"
    message["Subject"] = subject
    message["Message-ID"] = message_id
    message["Date"] = "Mon, 02 Nov 2026 09:00:00 +0000"
    message.set_content("Can you confirm before Friday?")
    return message


@pytest.fixture
def imap() -> FakeImap:
    """An inbox holding one message its owner answered, and one nobody touched."""
    server = FakeImap()
    server.put("INBOX", _mail("Quote", "<quote@example.com>"), ("\\Seen", "\\Answered"), uid="101")
    server.put("INBOX", _mail("Meeting", "<meeting@example.com>"), ("\\Seen",), uid="102")
    return server


@pytest.fixture
def client(imap: FakeImap) -> Iterator[AppleEmailClient]:
    instance = AppleEmailClient(
        user_id=uuid4(),
        credentials=AppleCredentials(apple_id="jane@icloud.com", app_password="abcd-efgh-ijkl"),
        connector_service=MagicMock(),
    )
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    breaker = MagicMock(check=AsyncMock(), record_success=AsyncMock(), record_failure=AsyncMock())
    with (
        patch(f"{APPLE}.MailBox", imap),
        patch(f"{APPLE_STATE}.MailBox", imap),
        patch(f"{APPLE}.get_redis_session", AsyncMock(return_value=redis)),
        patch(f"{APPLE_STATE}.get_redis_session", AsyncMock(return_value=redis)),
        patch.object(instance, "_rate_limit", AsyncMock()),
        patch.object(instance, "_get_circuit_breaker", MagicMock(return_value=breaker)),
        patch("asyncio.sleep", AsyncMock()),
    ):
        yield instance


async def _listed(client: AppleEmailClient, *, headers_only: bool) -> dict[str, dict]:
    page = await client.search_emails(
        "in:inbox", max_results=5, use_cache=False, headers_only=headers_only
    )
    return {str(row["subject"]): row for row in page["messages"]}


@pytest.mark.parametrize("headers_only", [False, True])
async def test_a_listed_message_says_what_its_mailbox_says_of_it(
    client: AppleEmailClient, headers_only: bool
) -> None:
    rows = await _listed(client, headers_only=headers_only)

    assert rows["Quote"][FIELD_MAIL_ANSWERED] is True
    assert FIELD_MAIL_ANSWERED not in rows["Meeting"]


async def test_a_message_read_alone_says_the_same(client: AppleEmailClient) -> None:
    """A proof found in a listing is read again alone: both reads must say one thing."""
    rows = await _listed(client, headers_only=False)

    answered = await client.get_message(rows["Quote"]["id"], use_cache=False, mailbox_mark=True)
    untouched = await client.get_message(rows["Meeting"]["id"], use_cache=False)

    assert answered[FIELD_MAIL_ANSWERED] is True
    assert FIELD_MAIL_ANSWERED not in untouched


async def test_the_flag_dates_nothing(client: AppleEmailClient) -> None:
    """IMAP keeps a flag, not the instant it was set: no date is claimed."""
    rows = await _listed(client, headers_only=False)

    assert FIELD_MAIL_ANSWERED_AT not in rows["Quote"]
