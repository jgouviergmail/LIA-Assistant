"""The reply a person confirms is addressed as it will leave (ADR-344, lot 5).

The confirmation card used to show the original SENDER as the recipient, and
the executor then imposed it: a reply to all lost every other recipient, and a
reply to one's own message went back to oneself. The card now shows the
recipients the client's own rule will address, read from the provider-neutral
message (Outlook and iCloud carry no Gmail header tree), and the executor sends
to exactly those — Graph would otherwise address a reply by its own rule.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.domains.agents.tools.emails_tools import ReplyEmailDraftTool, execute_email_reply_draft

pytestmark = [pytest.mark.unit]

ORIGINAL: dict[str, Any] = {
    "id": "m1",
    "threadId": "t1",
    "from": "Paul <paul@example.com>",
    "to": "me@example.com, Anna <anna@example.com>",
    "cc": "Bob <bob@example.com>",
    "subject": "Budget",
}


@pytest.fixture
def client() -> AsyncMock:
    client = AsyncMock()
    client.get_message = AsyncMock(return_value=dict(ORIGINAL))
    client.get_own_address = AsyncMock(return_value="me@example.com")
    client.reply_email = AsyncMock(return_value={"id": "s1", "threadId": "t1"})
    return client


async def _card(client: AsyncMock, *, reply_all: bool) -> dict[str, Any]:
    tool = ReplyEmailDraftTool()
    result = await tool.execute_api_call(
        client, uuid4(), message_id="m1", body="Agreed.", reply_all=reply_all
    )
    output = tool.format_registry_response(result)
    (item,) = output.registry_updates.values()
    content = item.payload["content"]
    assert isinstance(content, dict)
    return content


class TestTheCard:
    @pytest.mark.parametrize("reply_all", [False, True])
    async def test_the_reply_answers_reply_to_instead_of_the_transport_sender(
        self, client: AsyncMock, reply_all: bool
    ) -> None:
        client.get_message.return_value = {
            **ORIGINAL,
            "from": "Delivery <noreply@example.com>",
            "reply_to": "Help <help@example.com>",
        }

        card = await _card(client, reply_all=reply_all)

        expected = "Help <help@example.com>"
        if reply_all:
            expected += ", Anna <anna@example.com>"
        assert card["to"] == expected
        assert card["cc"] == ("Bob <bob@example.com>" if reply_all else "")

    async def test_a_reply_to_all_shows_everyone_it_will_reach(self, client: AsyncMock) -> None:
        card = await _card(client, reply_all=True)

        assert card["to"] == "Paul <paul@example.com>, Anna <anna@example.com>"
        assert card["cc"] == "Bob <bob@example.com>"
        assert card["subject"] == "Re: Budget"

    async def test_a_reply_to_ones_own_message_goes_to_its_recipients(
        self, client: AsyncMock
    ) -> None:
        client.get_message.return_value = {
            **ORIGINAL,
            "from": "Me <me@example.com>",
            "to": "Anna <anna@example.com>",
        }

        card = await _card(client, reply_all=False)

        assert card["to"] == "Anna <anna@example.com>"


async def _send(content: dict[str, Any], client: AsyncMock) -> None:
    with patch(
        "src.domains.connectors.provider_resolver.resolve_client_for_category",
        AsyncMock(return_value=(client, None)),
    ):
        await execute_email_reply_draft(content, uuid4(), deps=object())


class TestTheSend:
    async def test_the_reply_leaves_to_whom_the_card_showed(self, client: AsyncMock) -> None:
        card = await _card(client, reply_all=True)

        await _send(card, client)

        sent = client.reply_email.await_args.kwargs
        assert sent["to"] == "Paul <paul@example.com>, Anna <anna@example.com>"
        assert sent["reply_all"] is True

    async def test_a_recipient_the_person_changed_is_the_one_answered(
        self, client: AsyncMock
    ) -> None:
        card = await _card(client, reply_all=False)

        await _send({**card, "to": "Zoe <zoe@example.com>"}, client)

        assert client.reply_email.await_args.kwargs["to"] == "Zoe <zoe@example.com>"
