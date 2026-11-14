"""A reply sent from iCloud leaves the mark every mail client leaves (ADR-379).

IMAP sends through SMTP: nothing tells the mailbox a message was answered unless the
client that answered says so. Gmail threads a reply into its conversation and Exchange
stamps the original itself (observed 2026-11-11); on iCloud the assistant's own reply
left no trace, so the assistant would have offered to answer mail it had just answered.
"""

from __future__ import annotations

from collections.abc import Iterator
from email.message import EmailMessage
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.connectors.clients.apple_email_client import AppleEmailClient
from src.domains.connectors.schemas import AppleCredentials
from tests.unit.domains.connectors.clients.imap_fakes import FakeImap

pytestmark = pytest.mark.unit

APPLE = "src.domains.connectors.clients.apple_email_client"
APPLE_STATE = "src.domains.connectors.clients.apple_mail_state_mixin"
ANSWERED = "\\Answered"


def _mail() -> EmailMessage:
    message = EmailMessage()
    message["From"] = "Paul <paul@example.com>"
    message["To"] = "jane@icloud.com"
    message["Subject"] = "Budget"
    message["Message-ID"] = "<asked@example.com>"
    message["Date"] = "Mon, 02 Nov 2026 09:00:00 +0000"
    message.set_content("Can you confirm?")
    return message


class TestAReplyMarksItsOriginal:
    @pytest.fixture
    def imap(self) -> FakeImap:
        imap = FakeImap()
        imap.put("INBOX", _mail(), uid="101")
        return imap

    @pytest.fixture
    def client(self, imap: FakeImap) -> Iterator[AppleEmailClient]:
        instance = AppleEmailClient(
            user_id=uuid4(),
            credentials=AppleCredentials(apple_id="jane@icloud.com", app_password="abcd-efgh-ijkl"),
            connector_service=MagicMock(),
        )
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        breaker = MagicMock(
            check=AsyncMock(), record_success=AsyncMock(), record_failure=AsyncMock()
        )
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

    async def _listed_id(self, client: AppleEmailClient) -> str:
        found = await client.search_emails("in:inbox", max_results=5)
        return str(found["messages"][0]["id"])

    async def test_the_answered_message_is_flagged_once_the_reply_has_left(
        self, client: AppleEmailClient, imap: FakeImap
    ) -> None:
        asked = await self._listed_id(client)
        sent = AsyncMock()

        with patch.object(client, "_smtp_send", sent):
            await client.reply_email(asked, "Confirmed.")

        sent.assert_awaited_once()
        assert ANSWERED in imap.store["INBOX"]["101"][1]

    async def test_a_reply_that_did_not_leave_flags_nothing(
        self, client: AppleEmailClient, imap: FakeImap
    ) -> None:
        asked = await self._listed_id(client)

        with (
            patch.object(client, "_smtp_send", AsyncMock(side_effect=OSError("smtp down"))),
            pytest.raises(OSError),
        ):
            await client.reply_email(asked, "Confirmed.")

        assert ANSWERED not in imap.store["INBOX"]["101"][1]

    async def test_a_mailbox_that_refuses_the_flag_does_not_unsend_the_reply(
        self, client: AppleEmailClient, imap: FakeImap
    ) -> None:
        """The reply HAS left: failing here must not make it read as unsent."""
        asked = await self._listed_id(client)
        imap.flag = MagicMock(side_effect=RuntimeError("STORE refused"))

        with patch.object(client, "_smtp_send", AsyncMock()):
            result = await client.reply_email(asked, "Confirmed.")

        assert result["labelIds"] == ["Sent"]
        assert ANSWERED not in imap.store["INBOX"]["101"][1]

    async def test_an_id_that_names_no_current_message_opens_no_session(
        self, client: AppleEmailClient, imap: FakeImap
    ) -> None:
        """An id nobody can locate is not worth a connection to the mailbox."""
        before = imap.sessions

        assert await client._mark_answered("42") is False
        assert imap.sessions == before
