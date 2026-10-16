"""Saving a draft in the person's mailbox: new, reply, forward (ADR-344).

- what the person dictated is saved as is; the subject stays on one line;
- a draft may wait for its recipient or its words — LIA writes them only when
  the person said what the draft should say;
- a reply with no text is WRITTEN from the received e-mail, billed to the turn,
  and a refused or empty writing saves nothing;
- every failure comes back as a refusal the model can act on, by its code;
- a recipient named rather than addressed is resolved from the contacts.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.core.exceptions import ConnectorAPIError
from src.core.exceptions_domains import UsageLimitExceededError
from src.core.field_names import FIELD_MAILBOX_DRAFT_ID
from src.domains.agents.context.schemas import ContextSaveMode
from src.domains.agents.tools.base import ConnectorTool
from src.domains.agents.tools.mailbox_draft_base import refusal_for
from src.domains.agents.tools.mailbox_drafts_tools import (
    CreateMailboxDraftTool,
    CreateMailboxForwardDraftTool,
    CreateMailboxReplyDraftTool,
)
from src.domains.connectors.clients.mailbox_drafts import MailboxDraftNotFoundError

pytestmark = [pytest.mark.unit]

TOOLS = "src.domains.agents.tools.mailbox_drafts_tools"


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


@pytest.fixture
def client() -> AsyncMock:
    client = AsyncMock()
    client.create_draft = AsyncMock(return_value=_saved(subject="Budget", body="Hello"))
    client.create_reply_draft = AsyncMock(
        return_value=_saved(body="Friday works.\n\nOn Mon, Paul wrote:\n> Friday?")
    )
    client.create_forward_draft = AsyncMock(return_value=_saved(subject="Fwd: Budget"))
    client.get_message = AsyncMock(return_value={"id": "m1", "body": "Friday?"})
    return client


class TestCreate:
    async def test_the_draft_is_saved_as_given_its_subject_on_one_line(
        self, client: AsyncMock
    ) -> None:
        result = await CreateMailboxDraftTool().execute_api_call(
            client, uuid4(), to="", subject="Budget\n2027", body="Hello", cc=None
        )

        client.create_draft.assert_awaited_once_with(
            to="", subject="Budget 2027", body="Hello", cc=None, bcc=None, is_html=False
        )
        assert result["emails"][0][FIELD_MAILBOX_DRAFT_ID] == "r-9"

    async def test_an_unreadable_address_is_a_refusal(self, client: AsyncMock) -> None:
        client.create_draft.side_effect = ValueError("Invalid email address format.")
        tool = CreateMailboxDraftTool()

        output = tool.format_registry_response(
            await tool.execute_api_call(client, uuid4(), to="marie@", body="Hi")
        )

        assert output.success is False
        assert output.error_code == "INVALID_PARAM_VALUE"

    async def test_the_saved_draft_becomes_the_current_item(self, client: AsyncMock) -> None:
        tool = CreateMailboxDraftTool()

        output = tool.format_registry_response(
            await tool.execute_api_call(client, uuid4(), subject="Budget")
        )

        assert output.context_save_mode is ContextSaveMode.CURRENT
        assert output.structured_data["emails"][0][FIELD_MAILBOX_DRAFT_ID] == "r-9"

    async def test_a_named_recipient_is_resolved_from_the_contacts(self) -> None:
        resolve = AsyncMock(return_value="Marie Dupont <marie@example.com>")
        base = AsyncMock(return_value="ran")
        with (
            patch(
                "src.domains.agents.tools.mailbox_draft_base.resolve_recipients_to_emails", resolve
            ),
            patch.object(ConnectorTool, "execute", base),
        ):
            await CreateMailboxDraftTool().execute(runtime=None, to="Marie", subject="Hi")

        assert base.await_args.kwargs["to"] == "Marie Dupont <marie@example.com>"


class TestReply:
    async def test_a_dictated_reply_is_saved_without_writing_anything(
        self, client: AsyncMock
    ) -> None:
        with patch(f"{TOOLS}.draft_reply_body", AsyncMock()) as written:
            result = await CreateMailboxReplyDraftTool().execute_api_call(
                client, uuid4(), message_id="m1", body="Friday works.", reply_all=True
            )

        written.assert_not_awaited()
        client.create_reply_draft.assert_awaited_once_with("m1", "Friday works.", reply_all=True)
        assert result["emails"][0]["body"] == "Friday works."
        assert result["emails"][0]["quotes_history"] is True

    async def test_a_reply_without_text_is_written_from_the_received_email(
        self, client: AsyncMock
    ) -> None:
        with patch(f"{TOOLS}.draft_reply_body", AsyncMock(return_value="Yes, Friday.")) as written:
            await CreateMailboxReplyDraftTool().execute_api_call(
                client, uuid4(), message_id="m1", content_instruction="say yes"
            )

        original = written.await_args.args[0]
        assert original == {"id": "m1", "body": "Friday?"}
        assert written.await_args.kwargs["instruction"] == "say yes"
        client.create_reply_draft.assert_awaited_once_with("m1", "Yes, Friday.", reply_all=False)

    async def test_a_blank_text_is_no_text(self, client: AsyncMock) -> None:
        with patch(f"{TOOLS}.draft_reply_body", AsyncMock(return_value="Yes.")) as written:
            await CreateMailboxReplyDraftTool().execute_api_call(
                client, uuid4(), message_id="m1", body=" \n "
            )

        written.assert_awaited_once()
        client.create_reply_draft.assert_awaited_once_with("m1", "Yes.", reply_all=False)

    @pytest.mark.parametrize(
        ("failure", "code"),
        [
            (UsageLimitExceededError(), "RATE_LIMIT_EXCEEDED"),
            (None, "EMPTY_RESULT"),
        ],
    )
    async def test_a_reply_that_could_not_be_written_saves_nothing(
        self, client: AsyncMock, failure: Exception | None, code: str
    ) -> None:
        writer = AsyncMock(side_effect=failure) if failure else AsyncMock(return_value="  ")
        with patch(f"{TOOLS}.draft_reply_body", writer):
            result = await CreateMailboxReplyDraftTool().execute_api_call(
                client, uuid4(), message_id="m1"
            )

        assert result["error_code"] == code
        client.create_reply_draft.assert_not_awaited()

    async def test_an_unknown_message_is_not_found(self, client: AsyncMock) -> None:
        client.get_message.side_effect = ConnectorAPIError(
            connector_type="google_gmail", status_code=404, detail="nf"
        )

        result = await CreateMailboxReplyDraftTool().execute_api_call(
            client, uuid4(), message_id="m404"
        )

        assert result["error_code"] == "NOT_FOUND"


class TestForward:
    async def test_a_forward_needs_its_recipient(self, client: AsyncMock) -> None:
        result = await CreateMailboxForwardDraftTool().execute_api_call(
            client, uuid4(), message_id="m1", to=""
        )

        assert result["error_code"] == "MISSING_REQUIRED_PARAM"
        client.create_forward_draft.assert_not_awaited()

    async def test_a_forward_is_saved_with_its_note(self, client: AsyncMock) -> None:
        await CreateMailboxForwardDraftTool().execute_api_call(
            client, uuid4(), message_id="m1", to="paul@example.com", body="FYI", cc="a@example.com"
        )

        client.create_forward_draft.assert_awaited_once_with(
            "m1", "paul@example.com", body="FYI", cc="a@example.com"
        )


class TestRefusals:
    def test_a_draft_that_is_gone_is_said_so(self) -> None:
        assert refusal_for(MailboxDraftNotFoundError("r-1"))["error_code"] == "NOT_FOUND"

    def test_a_provider_refusal_other_than_not_found_reaches_the_shared_handler(self) -> None:
        forbidden = ConnectorAPIError(connector_type="google_gmail", status_code=403, detail="x")

        with pytest.raises(ConnectorAPIError):
            refusal_for(forbidden)
