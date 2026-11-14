"""The chat's mail tool tells where each message stands in its conversation (ADR-379).

The assistant offered to answer mail the person had already answered: the tool listed
each message alone. It now asks the mailbox once per page (``mail_reply_states``), in
every mode and at every detail level, and what a model reads says it in words — the
person's answer, never the instants of the reading.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.core.mail_reply_state import REPLY_STATE_KEY
from src.domains.agents.display.llm_serializer import payload_to_text
from src.domains.agents.telephony.voice_projection import compact_items
from src.domains.agents.tools.emails_tools import GetEmailsTool
from src.domains.agents.tools.react_tool_wrapper import compose_tool_message, extract_data_block
from src.domains.connectors.clients.mail_conversation import Conversation

pytestmark = [pytest.mark.unit]

ME = "Me <me@example.org>"
MARC = "Marc Dupont <marc@example.org>"
START = datetime(2026, 11, 10, 8, 0, tzinfo=UTC)


def _millis(minute: int) -> str:
    return str(int((START + timedelta(minutes=minute)).timestamp() * 1000))


def _message(message_id: str, thread: str, minute: int, labels: list[str], **over: Any) -> dict:
    return {
        "id": message_id,
        "threadId": thread,
        "labelIds": labels,
        "snippet": f"words of {message_id}",
        "subject": "Budget",
        "internalDate": _millis(minute),
        "body": f"Body of {message_id}",
        "attachments": [],
        "_provider": "google",
        **over,
    }


ASKED = _message("m1", "t1", 0, ["INBOX"], **{"from": MARC, "to": ME})
REPLY = _message(
    "m2", "t1", 30, ["SENT"], **{"from": ME, "to": MARC, "snippet": "Yes, Friday works for me."}
)
WAITING = _message("n1", "t2", 5, ["INBOX"], **{"from": MARC, "to": ME})


@pytest.fixture
def tool() -> GetEmailsTool:
    return GetEmailsTool()


@pytest.fixture
def client() -> AsyncMock:
    """A mailbox whose hits are whole, holding one answered and one unanswered message."""
    client = AsyncMock()
    client.SEARCH_HITS_ARE_WHOLE = True
    client.search_emails = AsyncMock(
        return_value={"messages": [dict(ASKED), dict(WAITING)], "resultSizeEstimate": 2}
    )
    client.get_message = AsyncMock(side_effect=lambda message_id, **_: dict(_BY_ID[message_id]))
    client.list_labels = AsyncMock(return_value={})
    client.conversations_of = AsyncMock(
        return_value={
            "t1": Conversation(messages=(dict(ASKED), dict(REPLY))),
            "t2": Conversation(messages=(dict(WAITING),)),
        }
    )
    return client


_BY_ID = {"m1": ASKED, "n1": WAITING}


def _statuses(emails: list[dict[str, Any]]) -> dict[str, str | None]:
    return {email["id"]: (email.get(REPLY_STATE_KEY) or {}).get("status") for email in emails}


class TestEveryModeSituatesWhatItLists:
    async def test_a_search_says_which_messages_were_answered(
        self, tool: GetEmailsTool, client: AsyncMock
    ) -> None:
        result = await tool.execute_api_call(
            client, uuid4(), query="in:inbox", user_timezone="Europe/Paris"
        )

        assert _statuses(result["emails"]) == {"m1": "answered", "n1": "unanswered"}
        client.conversations_of.assert_awaited_once()  # one read for the page

    async def test_messages_read_by_their_ids_are_situated_too(
        self, tool: GetEmailsTool, client: AsyncMock
    ) -> None:
        result = await tool.execute_api_call(
            client, uuid4(), message_ids=["m1", "n1"], user_timezone="Europe/Paris"
        )

        assert _statuses(result["emails"]) == {"m1": "answered", "n1": "unanswered"}

    @pytest.mark.parametrize("detail", ["metadata", "full"])
    async def test_a_detail_level_never_sheds_the_state(
        self, tool: GetEmailsTool, client: AsyncMock, detail: str
    ) -> None:
        result = await tool.execute_api_call(
            client, uuid4(), query="in:inbox", detail=detail, user_timezone="Europe/Paris"
        )

        assert _statuses(result["emails"]) == {"m1": "answered", "n1": "unanswered"}

    async def test_a_mailbox_that_cannot_tell_still_lists_its_mail(
        self, tool: GetEmailsTool, client: AsyncMock
    ) -> None:
        client.conversations_of.side_effect = RuntimeError("the mailbox is away")

        result = await tool.execute_api_call(
            client, uuid4(), query="in:inbox", user_timezone="Europe/Paris"
        )
        output = tool.format_registry_response(result)

        assert output.success is True
        assert _statuses(result["emails"]) == {"m1": None, "n1": None}


class TestWhatTravelsWithTheItems:
    async def test_the_card_and_the_model_data_both_carry_the_state(
        self, tool: GetEmailsTool, client: AsyncMock
    ) -> None:
        result = await tool.execute_api_call(
            client, uuid4(), query="in:inbox", user_timezone="Europe/Paris"
        )
        output = tool.format_registry_response(result)

        carded = {
            item.payload["id"]: item.payload[REPLY_STATE_KEY]["status"]
            for item in output.registry_updates.values()
        }
        assert carded == {"m1": "answered", "n1": "unanswered"}
        assert _statuses(output.structured_data["emails"]) == carded

    async def test_a_model_reads_the_answer_in_words_and_no_instant_of_the_reading(
        self, tool: GetEmailsTool, client: AsyncMock
    ) -> None:
        result = await tool.execute_api_call(
            client, uuid4(), query="in:inbox", user_timezone="Europe/Paris"
        )
        rendered = compose_tool_message(tool.format_registry_response(result), tool_name="probe")

        # 08:30 UTC is 09:30 in Paris, the clock the model is given.
        assert "answered on 2026-11-10T09:30+01:00 to Marc Dupont — Yes, Friday works for me." in (
            rendered
        )
        assert "unanswered" in rendered
        assert "observed_at" not in rendered and "valid_until" not in rendered

    async def test_the_pipelines_answer_reads_the_same_line(
        self, tool: GetEmailsTool, client: AsyncMock
    ) -> None:
        result = await tool.execute_api_call(
            client, uuid4(), query="in:inbox", user_timezone="Europe/Paris"
        )
        items = tool.format_registry_response(result).registry_updates.values()
        answered = next(item.payload for item in items if item.payload["id"] == "m1")

        line = payload_to_text(answered)

        assert "Reply state: answered on 2026-11-10T09:30+01:00 to Marc Dupont" in line
        assert "observed_at" not in line and "valid_until" not in line

    async def test_a_voice_is_told_the_answer_too(
        self, tool: GetEmailsTool, client: AsyncMock
    ) -> None:
        """The projection runs BEFORE the voice's reduction: reduced first, the state
        is a nested structure a voice drops."""
        result = await tool.execute_api_call(
            client, uuid4(), query="in:inbox", user_timezone="Europe/Paris"
        )
        block = extract_data_block(
            tool.format_registry_response(result), 2_000, reshape=compact_items
        )

        assert block is not None
        assert "answered on 2026-11-10T09:30+01:00 to Marc Dupont" in block.text
        assert "observed_at" not in block.text
