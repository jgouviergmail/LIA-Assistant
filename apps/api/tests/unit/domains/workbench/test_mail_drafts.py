"""The mailbox's drafts, by the person's own hand (ADR-369, Task 4.5; ADR-344).

A draft is saved — created once per submission, or changed against the
revision the editor holds (a draft changed elsewhere since is refused, never
overwritten) — and its answer carries the draft's id, which iCloud CHANGES on
every save. Sending one re-reads it first: changed since it was shown, it is
refused; addressed to nobody, nothing leaves. Trashing answers each draft.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.exceptions import BaseAPIException
from src.core.field_names import FIELD_MAILBOX_DRAFT_ID, FIELD_MAILBOX_DRAFT_REVISION
from src.domains.connectors.active_client import ActiveClient
from src.domains.connectors.models import ConnectorType
from src.domains.workbench import idempotency, mail_drafts
from src.domains.workbench.schemas.mail_compose import DraftSave, DraftSelection, DraftSend
from tests.unit.domains.workbench.fakes import FakeRedis

pytestmark = pytest.mark.unit

USER = uuid4()


def _door(client: Any, kind: ConnectorType = ConnectorType.GOOGLE_GMAIL) -> Any:
    @contextlib.asynccontextmanager
    async def opened(tool: Any, user_id: Any) -> AsyncIterator[ActiveClient]:
        yield ActiveClient(client=client, connector_type=kind, preferred_name=None)

    return patch.object(mail_drafts, "open_tool_client", opened)


@pytest.fixture(autouse=True)
def redis() -> Any:
    with patch.object(idempotency, "get_redis_cache", AsyncMock(return_value=FakeRedis())):
        yield


def _draft(**overrides: Any) -> dict[str, Any]:
    return {
        FIELD_MAILBOX_DRAFT_ID: "d1",
        FIELD_MAILBOX_DRAFT_REVISION: "r1",
        "to": "Ana Lima <ana@example.org>",
        "cc": "",
        "subject": "Budget",
        "snippet": "Voici",
        "body": "Voici le budget.",
        "internalDate": "1793334900000",
        "attachments": [],
        **overrides,
    }


class TestReading:
    async def test_the_drafts_newest_first_each_by_its_draft_id(self) -> None:
        client = MagicMock(
            list_drafts=AsyncMock(return_value={"messages": [_draft()], "next_page_token": "p2"})
        )
        with _door(client):
            page = await mail_drafts.list_drafts(USER, page_token=None)

        row = page.items[0]
        assert (row.id, [a.address for a in row.to], row.subject) == (
            "d1",
            ["ana@example.org"],
            "Budget",
        )
        assert page.next_page_token == "p2"

    async def test_one_draft_whole_with_the_revision_the_editor_holds(self) -> None:
        client = MagicMock(get_draft=AsyncMock(return_value=_draft()))
        with _door(client, ConnectorType.MICROSOFT_OUTLOOK):
            draft = await mail_drafts.read_draft(USER, "d1")

        client.get_draft.assert_awaited_once_with("d1")
        assert (draft.id, draft.revision, draft.body) == ("d1", "r1", "Voici le budget.")


class TestSaving:
    async def test_a_new_draft_is_created_once_per_submission(self) -> None:
        client = MagicMock(create_draft=AsyncMock(return_value=_draft()))
        save = DraftSave(to=["ana@example.org"], subject="Budget", idempotency_key=uuid4())
        with _door(client):
            saved = await mail_drafts.save_draft(USER, save)
            with pytest.raises(BaseAPIException) as replayed:
                await mail_drafts.save_draft(USER, save)

        client.create_draft.assert_awaited_once_with(
            "ana@example.org", "Budget", "", cc=None, bcc=None, is_html=False
        )
        assert saved.id == "d1"
        assert replayed.value.detail["code"] == "already_submitted"

    async def test_a_change_is_made_against_the_revision_and_answers_the_new_id(self) -> None:
        """iCloud stores a new message on every save: the answer names it."""
        client = MagicMock(
            update_draft=AsyncMock(
                return_value=_draft(
                    **{FIELD_MAILBOX_DRAFT_ID: "d2", FIELD_MAILBOX_DRAFT_REVISION: "r2"}
                )
            )
        )
        save = DraftSave(draft_id="d1", expected_revision="r1", body="Nouveau texte.", cc=[])
        with _door(client, ConnectorType.APPLE_EMAIL):
            saved = await mail_drafts.save_draft(USER, save)

        client.update_draft.assert_awaited_once_with(
            "d1",
            to=None,
            cc="",
            bcc=None,
            subject=None,
            body="Nouveau texte.",
            expected_revision="r1",
        )
        assert (saved.id, saved.revision) == ("d2", "r2")

    def test_a_change_names_the_revision_and_a_creation_its_key(self) -> None:
        with pytest.raises(ValidationError):
            DraftSave(draft_id="d1", body="x")
        with pytest.raises(ValidationError):
            DraftSave(subject="x")


class TestSending:
    async def test_a_draft_changed_since_it_was_shown_is_refused(self) -> None:
        client = MagicMock(
            get_draft=AsyncMock(return_value=_draft(**{FIELD_MAILBOX_DRAFT_REVISION: "r9"})),
            send_draft=AsyncMock(),
        )
        with _door(client), pytest.raises(BaseAPIException) as refused:
            await mail_drafts.send_draft(
                USER, DraftSend(draft_id="d1", expected_revision="r1", idempotency_key=uuid4())
            )

        assert refused.value.detail == {"code": "conflict"}
        client.send_draft.assert_not_awaited()

    async def test_a_draft_to_nobody_never_leaves(self) -> None:
        client = MagicMock(
            get_draft=AsyncMock(return_value=_draft(to="", cc="", bcc="")), send_draft=AsyncMock()
        )
        with _door(client), pytest.raises(BaseAPIException) as refused:
            await mail_drafts.send_draft(
                USER, DraftSend(draft_id="d1", expected_revision="r1", idempotency_key=uuid4())
            )

        assert refused.value.detail == {"code": "invalid_request"}
        client.send_draft.assert_not_awaited()

    async def test_the_draft_as_shown_leaves_once(self) -> None:
        client = MagicMock(
            get_draft=AsyncMock(return_value=_draft()),
            send_draft=AsyncMock(return_value={"id": "s1", "threadId": "t1"}),
        )
        send = DraftSend(draft_id="d1", expected_revision="r1", idempotency_key=uuid4())
        with _door(client):
            sent = await mail_drafts.send_draft(USER, send)

        client.send_draft.assert_awaited_once_with("d1")
        assert sent.id == "s1"


class TestTrashing:
    async def test_each_draft_is_answered(self) -> None:
        client = MagicMock(
            trash_drafts=AsyncMock(
                return_value={
                    "trashed": ["d1"],
                    "failed": [
                        {FIELD_MAILBOX_DRAFT_ID: "d2", "status": "not_found"},
                        {FIELD_MAILBOX_DRAFT_ID: "d3", "status": "refused"},
                    ],
                }
            )
        )
        with _door(client):
            outcome = await mail_drafts.trash_drafts(
                USER, DraftSelection(draft_ids=["d1", "d2", "d3"])
            )

        client.trash_drafts.assert_awaited_once_with(["d1", "d2", "d3"])
        assert outcome.done == ["d1"]
        assert [(f.id, f.status) for f in outcome.failed] == [
            ("d2", "not_found"),
            ("d3", "failed"),
        ]
