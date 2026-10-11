"""Native email sends exact approved bytes once, only after certain preflight commit."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from src.core.config import settings
from src.core.exceptions import BaseAPIException
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.email_share_send import execute_email_share, prepare_email_share
from src.domains.agents.application.email_share_send_schemas import EmailShareSendInput
from src.domains.email_share.schemas import EmailShareResult
from src.domains.email_share.service import ShareRoute
from src.domains.users.preference_cas import PreferenceWriteReceipt
from tests.integration.domains.bookmarks.test_bookmarks_db import _bookmark

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "scenario",
    [
        "valid",
        "source_changed",
        "route_changed",
        "disabled",
        "ack_lost",
        "cancelled",
        "remote_unknown",
        "revoked",
        "late_ack_lost",
    ],
)
async def test_confirmed_email_copy_never_sends_changed_content_or_replays_unknown(
    async_session, test_user, monkeypatch, scenario
):
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "email_share_enabled", True)
    owner = test_user.id
    saved = await _bookmark(async_session, test_user, None, content="The complete approved answer")
    await async_session.commit()
    route = ShareRoute.relay(test_user.email, max_file_bytes=100_000)
    resolver = AsyncMock(return_value=route)
    monkeypatch.setattr("src.domains.agents.application.email_share_send.resolve_route", resolver)
    monkeypatch.setattr(
        "src.domains.agents.application.email_share_send.rate_limit_email_share", AsyncMock()
    )
    draft = await prepare_email_share(
        async_session,
        owner,
        EmailShareSendInput(
            subject="Approved literal subject",
            message="Actual user words",
            attachment={"kind": "saved_answer", "bookmark_id": saved.id},
        ),
    )
    await async_session.commit()
    if scenario == "source_changed":
        saved.content = "Different copied answer"
        await async_session.commit()
    elif scenario == "route_changed":
        resolver.return_value = ShareRoute.relay("changed@example.test", max_file_bytes=100_000)
    elif scenario == "disabled":
        monkeypatch.setattr(settings, "application_tools_enabled", False)
    elif scenario == "revoked":
        test_user.is_active = False
        await async_session.commit()
    original = async_session.commit
    ack = False
    commits = 0

    async def commit():
        nonlocal ack, commits
        commits += 1
        await original()
        if scenario == "ack_lost":
            raise OSError("Controlled lost preflight acknowledgement")
        if scenario == "late_ack_lost" and commits == 3:
            raise OSError("Controlled lost final preflight acknowledgement")
        if scenario == "cancelled":
            raise asyncio.CancelledError()
        ack = True

    sends = []

    async def deliver(actor, prepared):
        assert ack and not async_session.in_transaction()
        assert prepared.single_attempt
        assert actor == owner
        actual = await prepared.source.read()
        assert b"The complete approved answer" in actual.data
        assert (
            prepared.subject == "Approved literal subject"
            and prepared.message == "Actual user words"
        )
        sends.append(prepared)
        if scenario == "remote_unknown":
            raise OSError("Controlled unknown remote acknowledgement")
        return EmailShareResult(route="relay", recipients=1)

    monkeypatch.setattr(async_session, "commit", commit)
    monkeypatch.setattr("src.domains.agents.application.email_share_send.deliver_share", deliver)
    receipt = PreferenceWriteReceipt()
    if scenario == "valid":
        await execute_email_share(async_session, owner, draft, receipt)
        assert receipt.committed and receipt.values["email_to_send"]["provider_acknowledged"]
    else:
        with pytest.raises((CommandRejected, BaseAPIException)):
            await execute_email_share(async_session, owner, draft, receipt)
        assert not receipt.committed
    assert len(sends) == int(scenario in {"valid", "remote_unknown"})


@pytest.mark.parametrize(
    "scenario", ["valid", "file_changed", "metadata_changed", "after_preflight_replaced"]
)
async def test_generated_email_attachment_uses_frozen_exact_approved_descriptor(
    async_session, test_user, monkeypatch, tmp_path, scenario
):
    from tests.integration.domains.attachments.test_keep_db import _file

    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "email_share_enabled", True)
    monkeypatch.setattr(settings, "attachments_storage_path", str(tmp_path))
    owner = test_user.id
    row = await _file(async_session, tmp_path, owner)
    path = tmp_path / row.file_path
    original_bytes = path.read_bytes()
    await async_session.commit()
    monkeypatch.setattr(
        "src.domains.agents.application.email_share_send.resolve_route",
        AsyncMock(return_value=ShareRoute.relay(test_user.email, max_file_bytes=100_000)),
    )
    monkeypatch.setattr(
        "src.domains.agents.application.email_share_send.rate_limit_email_share", AsyncMock()
    )
    draft = await prepare_email_share(
        async_session,
        owner,
        EmailShareSendInput(
            subject="Actual subject", attachment={"kind": "file", "attachment_id": row.id}
        ),
    )
    await async_session.commit()
    if scenario == "file_changed":
        path.write_bytes(b"different file")
    elif scenario == "metadata_changed":
        row.original_filename = "renamed-file.txt"
        await async_session.commit()
    sends = []

    async def deliver(actor, prepared):
        assert not async_session.in_transaction()
        if scenario == "after_preflight_replaced":
            path.write_bytes(b"replacement after approval")
        attachment = await prepared.source.read()
        sends.append(attachment.data)
        return EmailShareResult(route="relay", recipients=1)

    monkeypatch.setattr("src.domains.agents.application.email_share_send.deliver_share", deliver)
    receipt = PreferenceWriteReceipt()
    if scenario in {"valid", "after_preflight_replaced"}:
        await execute_email_share(async_session, owner, draft, receipt)
        assert receipt.committed and sends == [original_bytes]
    else:
        with pytest.raises((CommandRejected, BaseAPIException)):
            await execute_email_share(async_session, owner, draft, receipt)
        assert not sends and not receipt.committed
    assert path.exists()


@pytest.mark.parametrize("hidden", [False, True])
async def test_email_archived_answer_reuses_actual_visible_full_request_copy(
    async_session, test_user, monkeypatch, hidden
):
    from tests.integration.domains.bookmarks.test_bookmarks_db import _conversation, _message

    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "email_share_enabled", True)
    owner = test_user.id
    conversation = await _conversation(async_session, test_user)
    await _message(
        async_session, conversation, role="user", content="Complete original request", minutes=0
    )
    answer = await _message(
        async_session,
        conversation,
        role="assistant",
        content="Complete archived answer",
        hidden=hidden,
        minutes=1,
    )
    await async_session.commit()
    monkeypatch.setattr(
        "src.domains.agents.application.email_share_send.resolve_route",
        AsyncMock(return_value=ShareRoute.relay(test_user.email, max_file_bytes=100_000)),
    )
    monkeypatch.setattr(
        "src.domains.agents.application.email_share_send.rate_limit_email_share", AsyncMock()
    )
    request = EmailShareSendInput(
        subject="Actual subject", attachment={"kind": "answer", "message_id": answer.id}
    )
    sends = []

    async def deliver(actor, prepared):
        assert not async_session.in_transaction()
        data = (await prepared.source.read()).data
        assert b"Complete original request" in data and b"Complete archived answer" in data
        sends.append(data)
        return EmailShareResult(route="relay", recipients=1)

    monkeypatch.setattr("src.domains.agents.application.email_share_send.deliver_share", deliver)
    if hidden:
        with pytest.raises(BaseAPIException):
            await prepare_email_share(async_session, owner, request)
        assert not sends
    else:
        draft = await prepare_email_share(async_session, owner, request)
        receipt = PreferenceWriteReceipt()
        await execute_email_share(async_session, owner, draft, receipt)
        assert receipt.committed and len(sends) == 1
