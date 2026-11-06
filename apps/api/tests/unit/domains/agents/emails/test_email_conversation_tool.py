"""The assistant reads a whole conversation in one call (ADR-369, lot 8.1).

Asked what was said around a message, it used to fetch one message and guess at the rest. The
bound it publishes is the one the tool enforces, a cut reaches the model beside the items, and
a request that names no message is refused rather than read as something else.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.core.constants import EMAILS_TOOL_ID_BATCH_MAX
from src.domains.agents.emails.get_emails_manifest import get_emails_catalogue_manifest
from src.domains.agents.tools.common import ToolErrorCode
from src.domains.agents.tools.emails_tools import GetEmailsTool, get_emails_tool

pytestmark = pytest.mark.unit

USER = uuid4()


def _client(*ids: str, truncated: bool = False) -> MagicMock:
    async def message(message_id: str, **_: Any) -> dict[str, Any]:
        return {"id": message_id, "subject": "Budget", "body": f"Words of {message_id}"}

    client = MagicMock()
    client.get_conversation = AsyncMock(
        return_value={"messages": [{"id": item} for item in ids], "truncated": truncated}
    )
    client.get_message = AsyncMock(side_effect=message)
    client.list_labels = AsyncMock(return_value={})
    return client


async def _read(client: MagicMock, **kwargs: Any) -> dict[str, Any]:
    result: dict[str, Any] = await GetEmailsTool().execute_api_call(client, USER, **kwargs)
    return result


class TestAWholeConversation:
    async def test_each_message_is_read_whole_oldest_first(self) -> None:
        client = _client("m1", "m2", "m3")

        result = await _read(client, message_id="m2", whole_conversation=True)

        client.get_conversation.assert_awaited_once_with("m2", EMAILS_TOOL_ID_BATCH_MAX)
        assert [email["id"] for email in result["emails"]] == ["m1", "m2", "m3"]
        assert result["emails"][0]["body"] == "Words of m1"

    async def test_the_cut_reaches_the_model_beside_the_items(self) -> None:
        tool = GetEmailsTool()
        client = _client("m2", "m3", truncated=True)

        result = await tool.execute_api_call(client, USER, message_id="m3", whole_conversation=True)

        assert tool.format_registry_response(result).structured_data["conversation_truncated"]

    async def test_nothing_is_said_of_a_cut_there_was_not(self) -> None:
        tool = GetEmailsTool()

        result = await tool.execute_api_call(
            _client("m1"), USER, message_id="m1", whole_conversation=True
        )

        assert "conversation_truncated" not in tool.format_registry_response(result).structured_data

    async def test_a_message_with_no_conversation_is_still_read(self) -> None:
        client = _client()

        result = await _read(client, message_id="d1", whole_conversation=True)

        assert [email["id"] for email in result["emails"]] == ["d1"]

    @pytest.mark.parametrize("named", [{"query": "from:ana"}, {"message_ids": ["m1", "m2"]}, {}])
    async def test_it_needs_the_one_message_it_starts_from(self, named: dict[str, Any]) -> None:
        client = _client("m1")

        result = await _read(client, whole_conversation=True, **named)

        assert result["error_code"] == ToolErrorCode.INVALID_INPUT.value
        client.get_conversation.assert_not_awaited()

    async def test_asking_for_one_message_reads_one(self) -> None:
        client = _client("m1", "m2")

        result = await _read(client, message_id="m2")

        client.get_conversation.assert_not_awaited()
        assert [email["id"] for email in result["emails"]] == ["m2"]


class TestWhatIsPublished:
    def test_the_manifest_and_the_schema_say_the_same_enforced_bound(self) -> None:
        published = next(
            item
            for item in get_emails_catalogue_manifest.parameters
            if item.name == "whole_conversation"
        )
        schema = get_emails_tool.tool_call_schema.model_json_schema()["properties"]

        assert str(EMAILS_TOOL_ID_BATCH_MAX) in published.description
        assert schema["whole_conversation"]["description"] == published.description

    async def test_a_batch_of_ids_stops_at_the_same_bound(self) -> None:
        wanted = [f"m{index}" for index in range(EMAILS_TOOL_ID_BATCH_MAX + 2)]
        client = _client()

        result = await _read(client, message_ids=wanted)

        assert len(result["emails"]) == EMAILS_TOOL_ID_BATCH_MAX
