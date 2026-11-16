"""Every tool that writes an e-mail to someone settles its text at ONE door (ADR-383 amendment).

A text the agent wrote itself becomes what LIA's writer must say, in the person's voice; the
words the person marked are kept exactly. Each writing tool is driven here as the agent
drives it, under a run whose message is the person's own — and a writing tool without a
driver fails the suite (``test_every_writing_tool_is_driven_here``).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.field_names import FIELD_MAILBOX_DRAFT_ID
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.emails.authorship import WRITING_TOOLS
from src.domains.agents.tools import emails_tools, mailbox_drafts_tools
from src.domains.agents.tools.emails_tools import ReplyEmailDraftTool
from src.domains.agents.tools.exceptions import ContentGenerationError
from src.domains.agents.tools.mailbox_draft_edit_tools import UpdateMailboxDraftTool
from src.domains.agents.tools.mailbox_drafts_tools import CreateMailboxReplyDraftTool
from src.domains.connectors.clients.normalizers.reply_trimming import split_quoted_history

pytestmark = pytest.mark.unit

CONTENT = "src.domains.agents.emails.content_generation"
REPLY = "src.domains.agents.tools.reply_writing"
EDIT = "src.domains.agents.tools.mailbox_draft_edit_tools"

INTENT = "Écris à paul@example.com pour lui dire que je serai en retard demain."
DICTATED = "Envoie à paul@example.com : « Salut Paul, je serai en retard demain. Jean »"
DICTATED_WORDS = "Salut Paul, je serai en retard demain. Jean"
AGENT_TEXT = "Bonjour Paul,\n\nJe voulais te prévenir que je serai en retard demain.\n\nJean"
WRITTEN = "Salut Paul ! Petit retard demain matin, désolé. ++ Jean"
HISTORY = "\n\nOn Mon, Paul wrote:\n> Are you coming tomorrow?"
#: What a tool instance answers once it ran, as the context decorator reads it.
TOOL_ANSWER = '{"success": true}'


@dataclass(frozen=True)
class Outcome:
    """What a writing tool did with the text it was given."""

    written: bool
    sent: str
    instruction: str


def _runtime(message: str) -> MagicMock:
    """The tool's runtime in a run whose person said ``message``."""
    runtime = MagicMock()
    runtime.context = LiaRuntimeContext(
        user_id=uuid4(),
        thread_id="thread",
        conversation_id="conversation",
        user_message=message,
        display_name="Jean",
    )
    return runtime


def _compose_writer() -> AsyncMock:
    return AsyncMock(return_value={"subject": "Retard", "body": WRITTEN})


def _instruction(writer: AsyncMock) -> str:
    return str(writer.await_args.kwargs["instruction"]) if writer.await_count else ""


def _saved(**fields: Any) -> dict[str, Any]:
    return {
        "id": "m9",
        "threadId": "t9",
        FIELD_MAILBOX_DRAFT_ID: "r-9",
        "labelIds": ["DRAFT"],
        "from": "me@example.com",
        "_provider": "google",
        "attachments": [],
        **fields,
    }


def _mail_client() -> AsyncMock:
    client = AsyncMock()
    client.get_message = AsyncMock(
        return_value={
            "id": "m1",
            "threadId": "t1",
            "from": "Paul <paul@example.com>",
            "to": "me@example.com",
            "cc": "",
            "subject": "Demain",
            "body": "Are you coming tomorrow?",
        }
    )
    client.get_own_address = AsyncMock(return_value="me@example.com")
    client.conversations_of = AsyncMock(return_value={})
    client.create_reply_draft = AsyncMock(return_value=_saved(body="x"))
    client.get_draft = AsyncMock(
        return_value=_saved(
            to="Paul <paul@example.com>",
            subject="Re: Demain",
            body="Old words." + HISTORY,
            mailbox_draft_revision="revision-1",
        )
    )
    client.update_draft = AsyncMock(return_value=_saved(body="x"))
    return client


async def _drive_send(message: str, body: str, **fields: Any) -> Outcome:
    writer, draft = _compose_writer(), AsyncMock(return_value=TOOL_ANSWER)
    with (
        patch(f"{CONTENT}.generate_email_content", writer),
        patch.object(emails_tools._send_email_draft_tool_instance, "execute", draft),
    ):
        await emails_tools.send_email_tool.coroutine(
            to="paul@example.com", subject="Retard", body=body, runtime=_runtime(message), **fields
        )
    return Outcome(writer.await_count > 0, draft.await_args.kwargs["body"], _instruction(writer))


async def _drive_create_draft(message: str, body: str | None, **fields: Any) -> Outcome:
    writer, save = _compose_writer(), AsyncMock(return_value=TOOL_ANSWER)
    with (
        patch(f"{CONTENT}.generate_email_content", writer),
        patch.object(mailbox_drafts_tools._create_mailbox_draft_tool_instance, "execute", save),
        patch.object(
            mailbox_drafts_tools,
            "get_user_preferences",
            AsyncMock(return_value=("UTC", None, "fr")),
        ),
    ):
        await mailbox_drafts_tools.create_mailbox_draft_tool.coroutine(
            to="paul@example.com", subject="Retard", body=body, runtime=_runtime(message), **fields
        )
    return Outcome(writer.await_count > 0, save.await_args.kwargs["body"], _instruction(writer))


async def _drive_reply(message: str, body: str) -> Outcome:
    drafter, tool = AsyncMock(return_value=WRITTEN), ReplyEmailDraftTool()
    tool.runtime = _runtime(message)
    with patch(f"{REPLY}.draft_reply_body", drafter):
        result = await tool.execute_api_call(_mail_client(), uuid4(), message_id="m1", body=body)
    return Outcome(drafter.await_count > 0, result["body"], _instruction(drafter))


async def _drive_reply_draft(message: str, body: str, client: AsyncMock | None = None) -> Outcome:
    client = client or _mail_client()
    drafter, tool = AsyncMock(return_value=WRITTEN), CreateMailboxReplyDraftTool()
    tool.runtime = _runtime(message)
    with patch(f"{REPLY}.draft_reply_body", drafter):
        await tool.execute_api_call(client, uuid4(), message_id="m1", body=body)
    return Outcome(
        drafter.await_count > 0,
        client.create_reply_draft.await_args.args[1],
        _instruction(drafter),
    )


async def _drive_update(message: str, body: str, client: AsyncMock | None = None) -> Outcome:
    client = client or _mail_client()
    writer, tool = _compose_writer(), UpdateMailboxDraftTool()
    tool.runtime = _runtime(message)
    with patch(f"{EDIT}.generate_email_content", writer):
        await tool.execute_api_call(client, uuid4(), mailbox_draft_id="r-1", body=body)
    sent = str(client.update_draft.await_args.kwargs["body"])
    return Outcome(
        writer.await_count > 0, split_quoted_history(sent)[0].strip(), _instruction(writer)
    )


#: One driver per writing tool: what the agent passes in, what the tool goes on with.
DRIVERS: dict[str, Callable[[str, str], Awaitable[Outcome]]] = {
    "send_email_tool": _drive_send,
    "create_mailbox_draft_tool": _drive_create_draft,
    "reply_email_tool": _drive_reply,
    "create_mailbox_reply_draft_tool": _drive_reply_draft,
    "update_mailbox_draft_tool": _drive_update,
}


def test_every_writing_tool_is_driven_here() -> None:
    assert set(DRIVERS) == WRITING_TOOLS


@pytest.mark.parametrize("tool", sorted(WRITING_TOOLS))
async def test_a_text_the_agent_wrote_is_written_by_lia_in_the_persons_voice(tool: str) -> None:
    outcome = await DRIVERS[tool](INTENT, AGENT_TEXT)

    assert outcome.written
    assert outcome.sent == WRITTEN
    assert outcome.instruction.endswith(AGENT_TEXT)


@pytest.mark.parametrize("tool", sorted(WRITING_TOOLS))
async def test_the_words_the_person_dictated_leave_as_they_are(tool: str) -> None:
    outcome = await DRIVERS[tool](DICTATED, DICTATED_WORDS)

    assert not outcome.written
    assert outcome.sent == DICTATED_WORDS


async def test_a_text_written_by_lia_leaves_as_plain_text() -> None:
    """The writer answers plain text: an HTML flag the agent set would flatten its lines."""
    draft = AsyncMock(return_value=TOOL_ANSWER)
    with (
        patch(f"{CONTENT}.generate_email_content", _compose_writer()),
        patch.object(emails_tools._send_email_draft_tool_instance, "execute", draft),
    ):
        await emails_tools.send_email_tool.coroutine(
            to="paul@example.com",
            body=f"<p>{AGENT_TEXT}</p>",
            is_html=True,
            runtime=_runtime(INTENT),
        )

    assert draft.await_args.kwargs["is_html"] is False


async def test_dictated_markup_keeps_its_html_flag() -> None:
    draft = AsyncMock(return_value=TOOL_ANSWER)
    with patch.object(emails_tools._send_email_draft_tool_instance, "execute", draft):
        await emails_tools.send_email_tool.coroutine(
            to="paul@example.com",
            subject="Retard",
            body=f"<p>{DICTATED_WORDS}</p>",
            is_html=True,
            runtime=_runtime(DICTATED),
        )

    assert draft.await_args.kwargs["is_html"] is True


async def test_a_new_draft_asked_empty_stays_empty() -> None:
    outcome = await _drive_create_draft(INTENT, None)

    assert not outcome.written
    assert outcome.sent is None


async def test_dictated_draft_words_ask_no_subject_of_anyone() -> None:
    writer, save = _compose_writer(), AsyncMock(return_value=TOOL_ANSWER)
    with (
        patch(f"{CONTENT}.generate_email_content", writer),
        patch.object(mailbox_drafts_tools._create_mailbox_draft_tool_instance, "execute", save),
        patch.object(
            mailbox_drafts_tools,
            "get_user_preferences",
            AsyncMock(return_value=("UTC", None, "fr")),
        ),
    ):
        await mailbox_drafts_tools.create_mailbox_draft_tool.coroutine(
            to="paul@example.com", body=DICTATED_WORDS, runtime=_runtime(DICTATED)
        )

    writer.assert_not_awaited()
    assert save.await_args.kwargs["subject"] is None


async def test_a_dictated_reply_draft_reads_no_received_mail() -> None:
    client = _mail_client()

    await _drive_reply_draft(DICTATED, DICTATED_WORDS, client)

    client.get_message.assert_not_awaited()


async def test_the_quoted_history_stays_below_the_words_lia_wrote() -> None:
    client = _mail_client()

    await _drive_update(INTENT, AGENT_TEXT, client)

    sent = str(client.update_draft.await_args.kwargs["body"])
    assert sent.startswith(WRITTEN)
    assert sent.rstrip().endswith("> Are you coming tomorrow?")


async def test_an_emptied_draft_text_is_kept_empty() -> None:
    client = _mail_client()

    outcome = await _drive_update(INTENT, "", client)

    assert not outcome.written
    assert outcome.sent.strip() == ""


async def test_the_writer_cannot_overwrite_a_concurrent_mailbox_edit() -> None:
    """The writer takes seconds: the person may edit the draft meanwhile, and keeps it."""
    client, tool = _mail_client(), UpdateMailboxDraftTool()
    tool.runtime = _runtime(INTENT)

    async def write(**_kwargs: Any) -> dict[str, str]:
        client.get_draft.return_value = _saved(
            body="The person's new words." + HISTORY, mailbox_draft_revision="revision-2"
        )
        return {"subject": "Retard", "body": WRITTEN}

    with patch(f"{EDIT}.generate_email_content", AsyncMock(side_effect=write)):
        result = await tool.execute_api_call(
            client, uuid4(), mailbox_draft_id="r-1", body=AGENT_TEXT
        )

    client.update_draft.assert_not_awaited()
    assert result["error_code"] == "CONFLICT"


async def test_a_text_the_writer_could_not_write_changes_nothing() -> None:
    client, tool = _mail_client(), UpdateMailboxDraftTool()
    tool.runtime = _runtime(INTENT)
    with patch(
        f"{EDIT}.generate_email_content", AsyncMock(side_effect=ContentGenerationError("no"))
    ):
        result = await tool.execute_api_call(
            client, uuid4(), mailbox_draft_id="r-1", body=AGENT_TEXT
        )

    assert result["error_code"] == "EXTERNAL_API_ERROR"
    client.update_draft.assert_not_awaited()
