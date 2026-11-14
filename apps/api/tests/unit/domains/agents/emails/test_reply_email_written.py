"""A reply the person confirms is written by LIA's writer when they dictated no words.

« Answer Paul that Friday works » is what the reply must say, not the reply: the
confirmed reply and the reply saved as a draft share ONE writer, which reads the
received e-mail and, when LIA knows it, how the person writes (ADR-344, ADR-383).
Words the person dictated are kept exactly as given.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.agents.tools.common import ToolErrorCode
from src.domains.agents.tools.emails_tools import ReplyEmailDraftTool
from src.domains.agents.tools.mailbox_draft_base import refusal

pytestmark = [pytest.mark.unit]

WRITER = "src.domains.agents.tools.reply_writing.written_reply"
ORIGINAL: dict[str, Any] = {
    "id": "m1",
    "threadId": "t1",
    "from": "Paul <paul@example.com>",
    "to": "me@example.com",
    "cc": "",
    "subject": "Thursday",
    "body": "Could we move Thursday to Friday?",
}


def _client() -> AsyncMock:
    client = AsyncMock()
    client.get_message = AsyncMock(return_value=dict(ORIGINAL))
    client.get_own_address = AsyncMock(return_value="me@example.com")
    client.conversations_of = AsyncMock(return_value={})
    return client


async def _prepare(writer: AsyncMock, **fields: Any) -> tuple[ReplyEmailDraftTool, dict[str, Any]]:
    tool = ReplyEmailDraftTool()
    tool.runtime = MagicMock()  # the turn's runtime, which execute() sets
    with (
        patch(WRITER, writer),
        patch(
            "src.domains.agents.tools.reply_writing.get_original_user_message",
            return_value="réponds-lui que vendredi me va",
        ),
    ):
        result = await tool.execute_api_call(_client(), uuid4(), message_id="m1", **fields)
    return tool, result


async def test_dictated_words_are_kept_exactly_and_no_model_writes() -> None:
    writer = AsyncMock()

    _tool, result = await _prepare(writer, body="OK pour vendredi.")

    assert result["body"] == "OK pour vendredi."
    writer.assert_not_awaited()


async def test_no_words_are_written_by_the_writer_from_what_the_reply_must_say() -> None:
    writer = AsyncMock(return_value="Salut Paul,\n\nVendredi me va.\n\n++\nSeb")

    tool, result = await _prepare(writer, body="", content_instruction="say Friday works")

    assert result["body"] == "Salut Paul,\n\nVendredi me va.\n\n++\nSeb"
    (original,) = writer.await_args.args
    assert original["subject"] == "Thursday"
    assert writer.await_args.kwargs["instruction"] == "say Friday works"
    (card,) = tool.format_registry_response(result).registry_updates.values()
    assert card.payload["content"]["body"] == result["body"]


async def test_with_no_instruction_the_persons_own_message_says_what_to_answer() -> None:
    writer = AsyncMock(return_value="Vendredi me va.")

    await _prepare(writer)

    assert writer.await_args.kwargs["instruction"] == "réponds-lui que vendredi me va"


async def test_what_the_writer_could_not_do_is_the_tools_refusal() -> None:
    said = refusal(ToolErrorCode.RATE_LIMIT_EXCEEDED, "A spending ceiling refused writing.")
    writer = AsyncMock(return_value=said)

    tool, result = await _prepare(writer, content_instruction="say yes")

    assert result == said
    output = tool.format_registry_response(result)
    assert output.success is False
    assert output.error_code == ToolErrorCode.RATE_LIMIT_EXCEEDED.value
