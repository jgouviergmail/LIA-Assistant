"""Approval pins a generated image and an accepted recipient; copying is not preparation."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.exc import OperationalError

from src.core.config import settings
from src.core.exceptions import BaseAPIException
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.peer_image import execute_peer_image, prepare_peer_image
from src.domains.agents.application.peer_image_schemas import PeerImageInput
from src.domains.attachments.models import Attachment
from src.domains.peers import image_share
from src.domains.peers.models import PeerConnectionStatus, PeerImageShare
from src.domains.users.preference_cas import PreferenceWriteReceipt
from tests.integration.domains.peers.test_image_share_db import PNG, _connection, _image, _user

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "scenario",
    [
        "saved",
        "stale_image",
        "missing_file",
        "native_off",
        "expired",
        "late_off",
        "lost_ack",
        "cancelled_commit",
        "changed_bytes",
        "quota",
        "false_copy",
        "bad_path",
        "peers_off",
    ],
)
async def test_image_approval_and_commit(
    async_session, test_user, monkeypatch, tmp_path: Path, scenario
):
    monkeypatch.setattr(settings, "peers_enabled", True)
    monkeypatch.setattr(settings, "attachments_storage_path", str(tmp_path))
    owner = test_user.id
    peer = await _user(async_session, f"image-{scenario}@example.com", "Alice")
    pair = await _connection(async_session, owner, peer.id, PeerConnectionStatus.ACCEPTED)
    image = await _image(async_session, tmp_path, owner)
    peer_id, pair_id, image_id, source_path = peer.id, pair.id, image.id, image.file_path
    await async_session.commit()
    draft = await prepare_peer_image(
        async_session,
        owner,
        PeerImageInput(
            connection_id=pair_id,
            attachment_id=image_id,
            comment="  Bonjour <script>literal</script>  ",
        ),
    )
    assert await async_session.scalar(select(func.count(PeerImageShare.id))) == 0
    assert not (tmp_path / str(peer_id)).exists()
    deliver = AsyncMock(return_value=False)
    monkeypatch.setattr("src.domains.agents.application.peer_image.deliver_shared_image", deliver)
    if scenario == "stale_image":
        await async_session.execute(
            update(Attachment).where(Attachment.id == image_id).values(title="Changed")
        )
        await async_session.commit()
    if scenario == "missing_file":
        (tmp_path / source_path).unlink()
    if scenario == "changed_bytes":
        (tmp_path / source_path).write_bytes(b"replacement image")
    if scenario == "quota":
        monkeypatch.setattr(settings, "peers_image_share_max_per_day", 0)
    if scenario == "peers_off":
        monkeypatch.setattr(settings, "peers_enabled", False)
    if scenario == "bad_path":
        await async_session.execute(
            update(Attachment).where(Attachment.id == image_id).values(file_path="../outside.png")
        )
        await async_session.commit()
    if scenario == "native_off":
        monkeypatch.setattr(settings, "application_tools_enabled", False)
    if scenario == "expired":
        draft = draft.model_copy(update={"expires_at": datetime.now(UTC) - timedelta(seconds=1)})
    if scenario in {"late_off", "false_copy"}:
        source_record = image_share._record

        async def switched_off(*args, **kwargs):
            result = await source_record(*args, **kwargs)
            if scenario == "late_off":
                monkeypatch.setattr(settings, "application_tools_enabled", False)
            else:
                await async_session.execute(
                    update(Attachment).where(Attachment.id == result[0].id).values(user_id=owner)
                )
            return result

        monkeypatch.setattr(image_share, "_record", switched_off)
    if scenario in {"lost_ack", "cancelled_commit"}:
        source_commit = async_session.commit

        async def ambiguous_commit():
            await source_commit()
            if scenario == "cancelled_commit":
                import asyncio

                raise asyncio.CancelledError
            raise OperationalError("commit", {}, RuntimeError("lost acknowledgement"))

        monkeypatch.setattr(async_session, "commit", ambiguous_commit)
    receipt = PreferenceWriteReceipt()
    if scenario == "saved":
        await execute_peer_image(async_session, owner, draft, receipt)
        assert receipt.committed
        result = receipt.values["peer_image"]
        assert result["delivered"] is False
        deliver.assert_awaited_once()
        assert await async_session.scalar(select(func.count(PeerImageShare.id))) == 1
        copy = await async_session.scalar(select(Attachment).where(Attachment.user_id == peer_id))
        assert copy is not None and (tmp_path / copy.file_path).read_bytes() == PNG
        assert deliver.call_args.args[0].comment == "Bonjour <script>literal</script>"
        return
    with pytest.raises((CommandRejected, BaseAPIException, ValueError)) as error:
        await execute_peer_image(async_session, owner, draft, receipt)
    assert not receipt.committed
    deliver.assert_not_awaited()
    await async_session.rollback()
    if scenario in {"lost_ack", "cancelled_commit"}:
        assert error.value.code == "COMPLETION_UNKNOWN"
        copy = await async_session.scalar(select(Attachment).where(Attachment.user_id == peer_id))
        assert copy is not None and (tmp_path / copy.file_path).read_bytes() == PNG
    else:
        assert await async_session.scalar(select(func.count(PeerImageShare.id))) == 0
        assert not list((tmp_path / str(peer_id)).glob("*"))
