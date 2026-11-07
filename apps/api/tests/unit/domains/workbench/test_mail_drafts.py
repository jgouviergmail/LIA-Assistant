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

from src.core.constants import WORKBENCH_MAIL_ATTACHMENTS_MAX
from src.core.exceptions import BaseAPIException
from src.core.field_names import FIELD_MAILBOX_DRAFT_ID, FIELD_MAILBOX_DRAFT_REVISION
from src.domains.connectors.active_client import ActiveClient
from src.domains.connectors.models import ConnectorType
from src.domains.workbench import idempotency, mail_drafts
from src.domains.workbench.schemas.mail_compose import (
    DraftOrigin,
    DraftSave,
    DraftSelection,
    DraftSend,
)
from src.infrastructure.email.outgoing import OutgoingAttachment
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
            "ana@example.org", "Budget", "", cc=None, bcc=None, is_html=False, attachments=()
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
            add_files=(),
            remove_files=[],
            is_html=False,
        )
        assert (saved.id, saved.revision) == ("d2", "r2")

    def test_a_change_names_the_revision_and_a_creation_its_key(self) -> None:
        with pytest.raises(ValidationError):
            DraftSave(draft_id="d1", body="x")
        with pytest.raises(ValidationError):
            DraftSave(subject="x")


class TestAnAnswerKept:
    """A reply or a forward kept for later stays one: its thread, its quote, its files."""

    KEPT = OutgoingAttachment("note.txt", "text/plain", b"hello")

    async def test_a_reply_lets_the_provider_say_whom_it_reaches(self) -> None:
        client = MagicMock(create_reply_draft=AsyncMock(return_value=_draft()))
        request = DraftSave(
            body="Validé.",
            origin=DraftOrigin(message_id="m1", kind="reply"),
            idempotency_key=uuid4(),
        )
        with _door(client):
            saved = await mail_drafts.save_draft(USER, request)

        client.create_reply_draft.assert_awaited_once_with(
            "m1", "Validé.", reply_all=False, is_html=False, to=None, cc=None, attachments=()
        )
        assert saved.id == "d1"

    async def test_a_reply_to_all_goes_to_those_the_person_kept(self) -> None:
        client = MagicMock(create_reply_draft=AsyncMock(return_value=_draft()))
        request = DraftSave(
            to=["ana@example.org"],
            cc=[],
            body="Validé.",
            origin=DraftOrigin(message_id="m1", kind="reply_all"),
            idempotency_key=uuid4(),
        )
        with _door(client):
            await mail_drafts.save_draft(USER, request)

        client.create_reply_draft.assert_awaited_once_with(
            "m1",
            "Validé.",
            reply_all=True,
            is_html=False,
            to="ana@example.org",
            cc="",
            attachments=(),
        )

    async def test_a_forward_carries_the_files_the_person_chose(self) -> None:
        client = MagicMock(
            create_forward_draft=AsyncMock(return_value=_draft()), OUTGOING_FILE_MAX_BYTES=1000
        )
        request = DraftSave(
            to=["ana@example.org"],
            body="Pour info.",
            attachment_ids=[uuid4()],
            origin=DraftOrigin(message_id="m1", kind="forward"),
            idempotency_key=uuid4(),
        )
        with (
            _door(client),
            patch.object(mail_drafts, "carried_files", AsyncMock(return_value=(self.KEPT,))),
        ):
            await mail_drafts.save_draft(USER, request)

        client.create_forward_draft.assert_awaited_once_with(
            "m1",
            "ana@example.org",
            body="Pour info.",
            cc=None,
            is_html=False,
            attachments=(self.KEPT,),
        )

    async def test_it_is_created_once_per_submission(self) -> None:
        client = MagicMock(create_reply_draft=AsyncMock(return_value=_draft()))
        request = DraftSave(
            body="Validé.",
            origin=DraftOrigin(message_id="m1", kind="reply"),
            idempotency_key=uuid4(),
        )
        with _door(client):
            await mail_drafts.save_draft(USER, request)
            with pytest.raises(BaseAPIException) as replayed:
                await mail_drafts.save_draft(USER, request)

        client.create_reply_draft.assert_awaited_once()
        assert replayed.value.detail["code"] == "already_submitted"

    def test_a_forward_is_addressed_from_its_first_save(self) -> None:
        with pytest.raises(ValidationError):
            DraftSave(origin=DraftOrigin(message_id="m1", kind="forward"), idempotency_key=uuid4())

    @pytest.mark.parametrize("kept", [{"bcc": ["ana@example.org"]}, {"subject": "Mine"}])
    def test_an_answer_carries_neither_its_own_subject_nor_a_blind_copy(
        self, kept: dict[str, object]
    ) -> None:
        with pytest.raises(ValidationError):
            DraftSave(
                origin=DraftOrigin(message_id="m1", kind="reply"),
                idempotency_key=uuid4(),
                **kept,
            )

    def test_only_a_first_save_names_what_it_answers(self) -> None:
        with pytest.raises(ValidationError):
            DraftSave(
                draft_id="d1",
                expected_revision="r1",
                origin=DraftOrigin(message_id="m1", kind="reply"),
            )


class TestFormattedWords:
    MARKED = "<b>Hi</b><script>alert(1)</script>"

    async def test_a_new_draft_keeps_them_rebuilt_here(self) -> None:
        client = MagicMock(create_draft=AsyncMock(return_value=_draft()))
        request = DraftSave(subject="s", html=self.MARKED, idempotency_key=uuid4())
        with _door(client):
            await mail_drafts.save_draft(USER, request)

        call = client.create_draft.await_args
        assert call.args[2] == "<b>Hi</b>"
        assert call.kwargs["is_html"] is True

    async def test_a_change_keeps_them_too(self) -> None:
        client = MagicMock(update_draft=AsyncMock(return_value=_draft()))
        request = DraftSave(draft_id="d1", expected_revision="r1", html=self.MARKED)
        with _door(client):
            await mail_drafts.save_draft(USER, request)

        call = client.update_draft.await_args.kwargs
        assert call["body"] == "<b>Hi</b>"
        assert call["is_html"] is True

    async def test_a_change_of_words_alone_stays_text(self) -> None:
        client = MagicMock(update_draft=AsyncMock(return_value=_draft()))
        request = DraftSave(draft_id="d1", expected_revision="r1", body="Hi")
        with _door(client):
            await mail_drafts.save_draft(USER, request)

        call = client.update_draft.await_args.kwargs
        assert (call["body"], call["is_html"]) == ("Hi", False)


class TestAnAddressChosen:
    async def test_a_new_draft_leaves_from_it_later(self) -> None:
        client = MagicMock(create_draft=AsyncMock(return_value=_draft()))
        chosen = AsyncMock()
        request = DraftSave(subject="s", send_as="w@example.com", idempotency_key=uuid4())
        with _door(client), patch.object(mail_drafts, "apply_send_as", chosen):
            await mail_drafts.save_draft(USER, request)

        chosen.assert_awaited_once()

    async def test_a_change_may_name_one(self) -> None:
        client = MagicMock(update_draft=AsyncMock(return_value=_draft()))
        chosen = AsyncMock()
        request = DraftSave(draft_id="d1", expected_revision="r1", send_as="w@example.com")
        with _door(client), patch.object(mail_drafts, "apply_send_as", chosen):
            await mail_drafts.save_draft(USER, request)

        chosen.assert_awaited_once()

    async def test_a_draft_says_where_it_leaves_from(self) -> None:
        client = MagicMock(get_draft=AsyncMock(return_value=_draft(**{"from": "w@example.com"})))
        with _door(client):
            read = await mail_drafts.read_draft(USER, "d1")

        assert read.sender is not None and read.sender.address == "w@example.com"


class TestItsFiles:
    KEPT = OutgoingAttachment("note.txt", "text/plain", b"hello")

    def _read(self) -> Any:
        return patch.object(mail_drafts, "carried_files", AsyncMock(return_value=(self.KEPT,)))

    async def test_a_new_draft_carries_those_it_was_given(self) -> None:
        client = MagicMock(
            create_draft=AsyncMock(return_value=_draft()), OUTGOING_FILE_MAX_BYTES=1000
        )
        own = [uuid4()]
        request = DraftSave(
            subject="s", attachment_ids=own, drive_file_ids=["f1"], idempotency_key=uuid4()
        )
        with _door(client), self._read() as read:
            await mail_drafts.save_draft(USER, request)

        read.assert_awaited_once_with(USER, own, ["f1"], max_bytes=1000)
        assert client.create_draft.await_args.kwargs["attachments"] == (self.KEPT,)

    async def test_a_change_adds_those_and_drops_the_ones_named(self) -> None:
        client = MagicMock(
            update_draft=AsyncMock(return_value=_draft()), OUTGOING_FILE_MAX_BYTES=1000
        )
        request = DraftSave(
            draft_id="d1",
            expected_revision="r1",
            attachment_ids=[uuid4()],
            removed_files=["old.pdf"],
        )
        with _door(client), self._read():
            await mail_drafts.save_draft(USER, request)

        call = client.update_draft.await_args.kwargs
        assert call["add_files"] == (self.KEPT,)
        assert call["remove_files"] == ["old.pdf"]

    async def test_a_save_with_none_reads_none(self) -> None:
        client = MagicMock(update_draft=AsyncMock(return_value=_draft()))
        request = DraftSave(draft_id="d1", expected_revision="r1", body="b")
        with _door(client), self._read() as read:
            await mail_drafts.save_draft(USER, request)

        read.assert_not_awaited()

    async def test_a_file_that_cannot_be_read_saves_nothing(self) -> None:
        client = MagicMock(update_draft=AsyncMock(), OUTGOING_FILE_MAX_BYTES=1000)
        request = DraftSave(draft_id="d1", expected_revision="r1", attachment_ids=[uuid4()])
        gone = AsyncMock(side_effect=BaseAPIException(status_code=404, detail="gone"))
        with (
            _door(client),
            patch.object(mail_drafts, "carried_files", gone),
            pytest.raises(BaseAPIException),
        ):
            await mail_drafts.save_draft(USER, request)

        client.update_draft.assert_not_awaited()

    def test_a_save_names_a_bounded_number_of_files_to_drop(self) -> None:
        with pytest.raises(ValidationError):
            DraftSave(
                draft_id="d1",
                expected_revision="r1",
                removed_files=["a"] * (WORKBENCH_MAIL_ATTACHMENTS_MAX + 1),
            )


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
