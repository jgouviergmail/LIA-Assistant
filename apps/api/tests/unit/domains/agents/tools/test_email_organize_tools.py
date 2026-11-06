"""The assistant sorts e-mails and folders, on any provider (ADR-369, lot 4, owner decision D2).

What the clients gained for the « Tools » section reaches the assistant in the same
lot: one neutral tool over ``move_emails`` and ``set_starred``, one over the folders of
a mailbox that has folders. Neither deletes a message for good (A2): that stays by
hand, behind a confirmation. Each act is undone by one more call, so neither asks a
card; a move's new ids are returned for that call to name the messages.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.core.constants import EMAIL_ORGANIZE_MAX_MESSAGES
from src.core.exceptions import ConnectorAPIError
from src.domains.agents.emails.organize_manifest import (
    MAIL_FOLDER_ACTIONS,
    ORGANIZE_ACTIONS,
    ORGANIZE_IDS_DESCRIPTION,
    manage_mail_folder_catalogue_manifest,
    organize_emails_catalogue_manifest,
)
from src.domains.agents.tools.common import ToolErrorCode
from src.domains.agents.tools.email_organize_tools import (
    ManageMailFolderTool,
    OrganizeEmailsTool,
    organize_emails_tool,
)
from src.domains.connectors.clients.google_gmail_client import GoogleGmailClient
from src.domains.connectors.clients.mail_folders import (
    MailFolderNameTakenError,
    MailFolderNotEmptyError,
    MailFolderNotFoundError,
    SystemFolderError,
)
from src.domains.connectors.clients.mail_moves import MailPlace

pytestmark = pytest.mark.unit

USER = uuid4()
MOVED = {"updated": ["m1"], "failed": [], "moved": {"m1": "new-1"}}


def _client() -> Any:
    client = MagicMock()
    client.move_emails = AsyncMock(return_value=MOVED)
    client.set_starred = AsyncMock(return_value={"updated": ["m1"], "failed": []})
    client.place_named = AsyncMock(side_effect=lambda name: MailPlace(folder=name))
    return client


class TestTheManifests:
    @pytest.mark.parametrize(
        "manifest", [organize_emails_catalogue_manifest, manage_mail_folder_catalogue_manifest]
    )
    def test_they_act_without_a_card_for_a_written_reason(self, manifest: Any) -> None:
        assert manifest.mutation_policy == "reversible"
        assert manifest.mutation_policy_reason
        assert manifest.agent == "email_agent"

    def test_the_bound_is_published_to_both_readers(self) -> None:
        ids = next(
            p for p in organize_emails_catalogue_manifest.parameters if p.name == "message_ids"
        )
        assert ids.description == ORGANIZE_IDS_DESCRIPTION
        assert str(EMAIL_ORGANIZE_MAX_MESSAGES) in ORGANIZE_IDS_DESCRIPTION
        schema = organize_emails_tool.tool_call_schema.model_json_schema()
        assert schema["properties"]["message_ids"]["description"] == ORGANIZE_IDS_DESCRIPTION

    @pytest.mark.parametrize(
        ("manifest", "actions"),
        [
            (organize_emails_catalogue_manifest, ORGANIZE_ACTIONS),
            (manage_mail_folder_catalogue_manifest, MAIL_FOLDER_ACTIONS),
        ],
    )
    def test_the_actions_are_published_as_the_tool_reads_them(
        self, manifest: Any, actions: tuple[str, ...]
    ) -> None:
        action = next(p for p in manifest.parameters if p.name == "action")
        assert action.constraints[0].kind == "enum"
        assert tuple(action.constraints[0].value) == actions

    def test_nothing_here_deletes_a_message_for_good(self) -> None:
        assert not {"delete", "delete_forever", "empty_trash"} & set(ORGANIZE_ACTIONS)


class TestOrganize:
    @pytest.mark.parametrize(
        ("action", "place", "origin"),
        [
            ("archive", MailPlace(role="archive"), None),
            ("spam", MailPlace(role="spam"), None),
            ("not_spam", MailPlace(role="inbox"), MailPlace(role="spam")),
            ("restore", MailPlace(role="inbox"), MailPlace(role="trash")),
        ],
    )
    async def test_an_act_is_a_place(
        self, action: str, place: MailPlace, origin: MailPlace | None
    ) -> None:
        client = _client()

        result = await OrganizeEmailsTool().execute_api_call(
            client, USER, action=action, message_ids=["m1", "m1"]
        )

        client.move_emails.assert_awaited_once_with(["m1"], place, origin)
        assert result["moved"] == {"m1": "new-1"}
        assert result["action"] == action

    async def test_a_move_goes_to_the_folder_the_mailbox_finds(self) -> None:
        client = _client()

        await OrganizeEmailsTool().execute_api_call(
            client, USER, action="move", message_ids=["m1"], folder=" Projects "
        )

        client.place_named.assert_awaited_once_with("Projects")
        client.move_emails.assert_awaited_once_with(["m1"], MailPlace(folder="Projects"), None)

    @pytest.mark.parametrize(("action", "starred"), [("star", True), ("unstar", False)])
    async def test_a_star_needs_no_place(self, action: str, starred: bool) -> None:
        client = _client()

        result = await OrganizeEmailsTool().execute_api_call(
            client, USER, action=action, message_ids=["m1"]
        )

        client.set_starred.assert_awaited_once_with(["m1"], starred)
        client.move_emails.assert_not_awaited()
        assert result["moved"] == {}

    async def test_a_selection_past_the_bound_is_served_up_to_it_and_says_so(self) -> None:
        client = _client()
        ids = [f"m{index}" for index in range(EMAIL_ORGANIZE_MAX_MESSAGES + 2)]

        result = await OrganizeEmailsTool().execute_api_call(
            client, USER, action="archive", message_ids=ids
        )

        served = client.move_emails.await_args.args[0]
        assert served == ids[:EMAIL_ORGANIZE_MAX_MESSAGES]
        assert result["more_remaining"] is True
        assert result["not_attempted"] == ids[EMAIL_ORGANIZE_MAX_MESSAGES:]

    @pytest.mark.parametrize(
        ("kwargs", "code"),
        [
            ({"action": "archive", "message_ids": []}, ToolErrorCode.INVALID_INPUT),
            ({"action": "burn", "message_ids": ["m1"]}, ToolErrorCode.INVALID_INPUT),
            ({"action": "move", "message_ids": ["m1"]}, ToolErrorCode.INVALID_INPUT),
            (
                {"action": "move", "message_ids": ["m1"], "folder": "  "},
                ToolErrorCode.INVALID_INPUT,
            ),
        ],
    )
    async def test_what_cannot_be_acted_on_is_refused_without_a_call(
        self, kwargs: dict[str, Any], code: ToolErrorCode
    ) -> None:
        client = _client()

        result = await OrganizeEmailsTool().execute_api_call(client, USER, **kwargs)

        assert result["error_code"] == code.value
        client.move_emails.assert_not_awaited()

    async def test_a_folder_nothing_answers_to_is_said_with_those_that_do(self) -> None:
        client = _client()
        client.place_named = AsyncMock(
            side_effect=MailFolderNotFoundError("Nope", ["Projects"], complete=True)
        )

        result = await OrganizeEmailsTool().execute_api_call(
            client, USER, action="move", message_ids=["m1"], folder="Nope"
        )

        assert result["error_code"] == ToolErrorCode.NOT_FOUND.value
        assert "Projects" in str(result)

    def test_messages_all_gone_are_a_failure_that_says_to_list_again(self) -> None:
        output = OrganizeEmailsTool().format_registry_response(
            {
                "action": "archive",
                "updated": [],
                "failed": [{"id": "m1", "status": "not_found"}],
                "moved": {},
                "more_remaining": False,
                "not_attempted": [],
            }
        )

        assert output.success is False
        assert output.error_code == ToolErrorCode.NOT_FOUND.value

    def test_a_move_names_what_each_message_is_called_now(self) -> None:
        output = OrganizeEmailsTool().format_registry_response(
            {
                "action": "archive",
                "updated": ["m1"],
                "failed": [{"id": "m2", "status": "failed"}],
                "moved": {"m1": "new-1"},
                "more_remaining": False,
                "not_attempted": [],
            }
        )

        assert output.success is True
        assert "1" in output.message
        assert output.structured_data["moved"] == {"m1": "new-1"}


class TestFolders:
    def _folders(self, **answers: Any) -> Any:
        client = MagicMock()
        client.create_folder = AsyncMock(return_value="Projects/2027")
        client.rename_folder = AsyncMock(return_value="Old")
        client.delete_folder = AsyncMock()
        client.configure_mock(**answers)
        return client

    async def test_a_folder_is_created_renamed_and_deleted(self) -> None:
        client = self._folders()
        tool = ManageMailFolderTool()

        made = await tool.execute_api_call(client, USER, action="create", name="Projects/2027")
        renamed = await tool.execute_api_call(
            client, USER, action="rename", folder="Projects", name="Old"
        )
        deleted = await tool.execute_api_call(client, USER, action="delete", folder="Old")

        assert (made["folder"], renamed["folder"], deleted["folder"]) == (
            "Projects/2027",
            "Old",
            "Old",
        )
        client.delete_folder.assert_awaited_once_with("Old")

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"action": "burn", "folder": "A"},
            {"action": "create"},
            {"action": "rename", "folder": "A"},
            {"action": "rename", "name": "B"},
            {"action": "rename", "folder": "A", "name": "B/C"},
            {"action": "delete"},
        ],
    )
    async def test_what_cannot_be_acted_on_is_refused_without_a_call(
        self, kwargs: dict[str, Any]
    ) -> None:
        client = self._folders()

        result = await ManageMailFolderTool().execute_api_call(client, USER, **kwargs)

        assert result["error_code"] == ToolErrorCode.INVALID_INPUT.value
        client.create_folder.assert_not_awaited()
        client.rename_folder.assert_not_awaited()
        client.delete_folder.assert_not_awaited()

    async def test_gmail_has_labels_and_is_sent_to_its_tools(self) -> None:
        client = MagicMock(spec=GoogleGmailClient)

        result = await ManageMailFolderTool().execute_api_call(
            client, USER, action="create", name="Projects"
        )

        assert result["error_code"] == ToolErrorCode.CONSTRAINT_VIOLATION.value
        assert "create_label_tool" in result["message"]

    @pytest.mark.parametrize(
        ("failure", "code"),
        [
            (MailFolderNotEmptyError(), ToolErrorCode.CONSTRAINT_VIOLATION),
            (SystemFolderError(), ToolErrorCode.CONSTRAINT_VIOLATION),
            (MailFolderNameTakenError(), ToolErrorCode.CONFLICT),
            (
                ConnectorAPIError(connector_type="microsoft_outlook", status_code=409, detail="x"),
                ToolErrorCode.CONFLICT,
            ),
            (MailFolderNotFoundError("A", ["B"], complete=True), ToolErrorCode.NOT_FOUND),
        ],
    )
    async def test_a_refusal_is_told_by_its_type(
        self, failure: Exception, code: ToolErrorCode
    ) -> None:
        client = self._folders(delete_folder=AsyncMock(side_effect=failure))

        result = await ManageMailFolderTool().execute_api_call(
            client, USER, action="delete", folder="A"
        )

        assert result["error_code"] == code.value

    def test_the_answer_is_what_the_folder_is_called_now(self) -> None:
        output = ManageMailFolderTool().format_registry_response(
            {"action": "rename", "folder": "Old"}
        )

        assert output.success is True
        assert output.structured_data == {"action": "rename", "folder": "Old"}
