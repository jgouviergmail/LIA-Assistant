"""The mail screen's folders and Gmail's labels (ADR-369, Task 4.1).

The folder pane draws the mailbox's system places — each provider's own, in the
Gmail-style vocabulary the three translate (F12) — then the person's own
folders or labels, from ``list_labels``, without the system ones a second
time: Gmail says which by the label's type, Graph by its well-known folders'
ids (their display names are in the mailbox's language), iCloud by its role
folders' names. Labels are Gmail's alone (the descriptor says so): created,
renamed, deleted — a system label never — and applied to a selection in one
act; a name Gmail already holds is said as such.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.config import settings
from src.core.exceptions import BaseAPIException, ConnectorAPIError
from src.domains.connectors.active_client import ActiveClient
from src.domains.connectors.models import ConnectorType
from src.domains.workbench import mail_folders
from src.domains.workbench.features import TOOL_PROVIDERS, WorkbenchTool
from src.domains.workbench.schemas.mail import LabelApplication, LabelChange, NewLabel

pytestmark = pytest.mark.unit

USER = uuid4()
GMAIL, OUTLOOK, ICLOUD = (
    ConnectorType.GOOGLE_GMAIL,
    ConnectorType.MICROSOFT_OUTLOOK,
    ConnectorType.APPLE_EMAIL,
)


def _door(client: Any, kind: ConnectorType) -> Any:
    @contextlib.asynccontextmanager
    async def opened(tool: Any, user_id: Any) -> AsyncIterator[ActiveClient]:
        yield ActiveClient(client=client, connector_type=kind, preferred_name=None)

    return patch.object(mail_folders, "open_tool_client", opened)


def _gmail(**overrides: Any) -> MagicMock:
    labels = [
        {"id": "INBOX", "name": "INBOX", "type": "system"},
        {"id": "SENT", "name": "SENT", "type": "system"},
        {"id": "Label_2", "name": "Travel", "type": "user"},
        {"id": "Label_1", "name": "pro/capge", "type": "user"},
    ]
    client = MagicMock(
        list_labels_full=AsyncMock(return_value=labels),
        create_label=AsyncMock(return_value={"id": "Label_9", "name": "New", "type": "user"}),
        update_label=AsyncMock(return_value={"id": "Label_1", "name": "Renamed", "type": "user"}),
        delete_label=AsyncMock(return_value=True),
        batch_modify_labels=AsyncMock(return_value=True),
    )
    client.is_system_label = lambda name: name.upper() in {"INBOX", "SENT", "TRASH", "STARRED"}
    for name, value in overrides.items():
        setattr(client, name, value)
    return client


def _taken() -> ConnectorAPIError:
    return ConnectorAPIError(connector_type="google_gmail", status_code=409, detail="exists")


class TestTheFolderPane:
    async def test_gmail_draws_its_system_places_then_the_person_s_labels(self) -> None:
        with _door(_gmail(), GMAIL):
            view = await mail_folders.read_folders(USER)

        system = [(f.id, f.role) for f in view.folders if f.kind == "system"]
        assert system == [
            ("system:inbox", "inbox"),
            ("system:starred", "starred"),
            ("system:sent", "sent"),
            ("system:drafts", "drafts"),
            ("system:spam", "spam"),
            ("system:trash", "trash"),
        ]
        user = [(folder.id, folder.name) for folder in view.folders if folder.kind == "user"]
        assert user == [("Label_1", "pro/capge"), ("Label_2", "Travel")], "sorted by name"

    async def test_gmail_s_labels_are_read_fresh(self) -> None:
        """A label made in Gmail itself shows at once — not after the assistant's hour."""
        client = _gmail()
        with _door(client, GMAIL):
            await mail_folders.read_folders(USER)

        client.list_labels_full.assert_awaited_once_with(use_cache=False)

    async def test_outlook_drops_its_well_known_folders_whatever_their_language(self) -> None:
        client = MagicMock(
            list_labels=AsyncMock(
                return_value={
                    "f1": "Boîte de réception",
                    "f2": "Éléments envoyés",
                    "f3": "Projets",
                    "f4": "Boîte d'envoi",
                }
            ),
            system_folder_ids=AsyncMock(return_value=frozenset({"f1", "f2"})),
        )
        with _door(client, OUTLOOK):
            view = await mail_folders.read_folders(USER)

        system = [folder.role for folder in view.folders if folder.kind == "system"]
        assert system == ["inbox", "starred", "sent", "drafts", "archive", "spam", "trash"]
        assert [(f.id, f.name) for f in view.folders if f.kind == "user"] == [
            ("Boîte d'envoi", "Boîte d'envoi"),
            ("Projets", "Projets"),
        ]

    async def test_icloud_drops_the_folders_its_roles_name(self) -> None:
        client = MagicMock(
            list_labels=AsyncMock(
                return_value={
                    "INBOX": "INBOX",
                    "Sent Messages": "Sent Messages",
                    "Deleted Messages": "Deleted Messages",
                    "Receipts": "Receipts",
                }
            )
        )
        with _door(client, ICLOUD):
            view = await mail_folders.read_folders(USER)

        assert [(f.id, f.name) for f in view.folders if f.kind == "user"] == [
            ("Receipts", "Receipts")
        ]

    def test_every_mail_provider_has_its_system_places(self) -> None:
        assert set(mail_folders.SYSTEM_PLACES) == TOOL_PROVIDERS[WorkbenchTool.MAIL]


class TestGmailLabels:
    async def test_create_rename_delete(self) -> None:
        client = _gmail()
        with _door(client, GMAIL):
            created = await mail_folders.create_label(USER, NewLabel(name="  New "))
            renamed = await mail_folders.rename_label(
                USER, LabelChange(label_id="Label_1", name="Renamed")
            )
            await mail_folders.delete_label(USER, "Label_1")

        assert (created.id, created.kind, created.name) == ("Label_9", "user", "New")
        assert (renamed.id, renamed.name) == ("Label_1", "Renamed")
        client.create_label.assert_awaited_once_with("New")
        client.update_label.assert_awaited_once_with("Label_1", "Renamed")
        client.delete_label.assert_awaited_once_with("Label_1")

    @pytest.mark.parametrize("act", ["rename", "delete"])
    async def test_a_system_label_is_refused_unsent(self, act: str) -> None:
        client = _gmail()
        with _door(client, GMAIL), pytest.raises(BaseAPIException) as refused:
            if act == "rename":
                await mail_folders.rename_label(USER, LabelChange(label_id="INBOX", name="x"))
            else:
                await mail_folders.delete_label(USER, "INBOX")

        assert refused.value.detail == {"code": "not_supported_by_provider"}
        client.update_label.assert_not_awaited()
        client.delete_label.assert_not_awaited()

    @pytest.mark.parametrize("act", ["create", "rename"])
    async def test_a_label_cannot_be_named_after_a_system_one(self, act: str) -> None:
        client = _gmail()
        with _door(client, GMAIL), pytest.raises(BaseAPIException) as refused:
            if act == "create":
                await mail_folders.create_label(USER, NewLabel(name="inbox"))
            else:
                await mail_folders.rename_label(
                    USER, LabelChange(label_id="Label_1", name="Starred")
                )

        assert refused.value.detail == {"code": "not_supported_by_provider"}
        client.create_label.assert_not_awaited()
        client.update_label.assert_not_awaited()

    @pytest.mark.parametrize("act", ["create", "rename"])
    async def test_a_name_gmail_already_holds_is_said_as_such(self, act: str) -> None:
        client = _gmail(
            create_label=AsyncMock(side_effect=_taken()),
            update_label=AsyncMock(side_effect=_taken()),
        )
        with _door(client, GMAIL), pytest.raises(BaseAPIException) as refused:
            if act == "create":
                await mail_folders.create_label(USER, NewLabel(name="Travel"))
            else:
                await mail_folders.rename_label(
                    USER, LabelChange(label_id="Label_1", name="Travel")
                )

        assert refused.value.detail == {"code": "name_taken"}

    async def test_labels_are_applied_to_a_selection_in_one_act(self) -> None:
        client = _gmail()
        with _door(client, GMAIL):
            await mail_folders.apply_labels(
                USER,
                LabelApplication(message_ids=["m1", "m2"], add=["Label_1"], remove=["Label_2"]),
            )

        client.batch_modify_labels.assert_awaited_once_with(
            ["m1", "m2"], add_label_ids=["Label_1"], remove_label_ids=["Label_2"]
        )

    @pytest.mark.parametrize("side", ["add", "remove"])
    async def test_a_system_label_is_never_applied(self, side: str) -> None:
        """As the assistant's tools: they resolve the person's labels only."""
        client = _gmail()
        change = {"add": ["Label_1"], "remove": []} | {side: ["TRASH"]}
        with _door(client, GMAIL), pytest.raises(BaseAPIException) as refused:
            await mail_folders.apply_labels(USER, LabelApplication(message_ids=["m1"], **change))

        assert refused.value.detail == {"code": "not_supported_by_provider"}
        client.batch_modify_labels.assert_not_awaited()

    @pytest.mark.parametrize("kind", [OUTLOOK, ICLOUD])
    async def test_labels_elsewhere_are_not_supported(self, kind: ConnectorType) -> None:
        client = MagicMock(create_label=AsyncMock())
        with _door(client, kind), pytest.raises(BaseAPIException) as refused:
            await mail_folders.create_label(USER, NewLabel(name="New"))

        assert refused.value.detail == {"code": "not_supported_by_provider"}
        client.create_label.assert_not_awaited()


class TestTheContract:
    def test_an_application_changes_something_and_stays_in_bounds(self) -> None:
        with pytest.raises(ValidationError):
            LabelApplication(message_ids=["m1"], add=[], remove=[])
        with pytest.raises(ValidationError):
            LabelApplication(
                message_ids=[f"m{index}" for index in range(settings.workbench_bulk_max_items + 1)],
                add=["Label_1"],
                remove=[],
            )

    def test_a_label_is_never_added_and_removed_at_once(self) -> None:
        with pytest.raises(ValidationError):
            LabelApplication(message_ids=["m1"], add=["Label_1"], remove=["Label_1"])

    @pytest.mark.parametrize("name", ["", "   ", "a\nb"])
    def test_a_label_name_is_read_before_it_is_sent(self, name: str) -> None:
        with pytest.raises(ValidationError):
            NewLabel(name=name)
