"""Real independent writers cannot remove the approved attachment or block its pair."""

from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.agents.application.peer_image import execute_peer_image, prepare_peer_image
from src.domains.agents.application.peer_image_schemas import PeerImageInput
from src.domains.attachments.models import Attachment
from src.domains.peers import image_share
from src.domains.peers.models import PeerConnectionStatus
from src.domains.peers.service import PeersService
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt
from tests.integration.domains.peers.test_image_share_db import _connection, _image, _user
from tests.integration.test_application_memory_independent_transactions import (
    assert_independent_lock_control,
)

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("writer_kind", ["image_delete", "peer_block"])
async def test_image_pair_independent_fence(async_engine, monkeypatch, tmp_path: Path, writer_kind):
    monkeypatch.setattr(settings, "peers_enabled", True)
    monkeypatch.setattr(settings, "attachments_storage_path", str(tmp_path))
    async with AsyncSession(async_engine, expire_on_commit=False) as seed:
        first = await _user(seed, f"image-fence-{uuid4()}@example.com", "Sender")
        second = await _user(seed, f"image-fence-{uuid4()}@example.com", "Recipient")
        pair = await _connection(seed, first.id, second.id, PeerConnectionStatus.ACCEPTED)
        image = await _image(seed, tmp_path, first.id)
        identities, pair_id, image_id = [first.id, second.id], pair.id, image.id
        await seed.commit()
    try:
        async with AsyncSession(async_engine, expire_on_commit=False) as db:
            for value in identities:
                await assert_independent_lock_control(db, async_engine, value)
            pid = await db.scalar(select(func.pg_backend_pid()))
            source_record = image_share._record

            async def probe(*args, **kwargs):
                async with AsyncSession(async_engine) as writer:
                    assert await writer.scalar(select(func.pg_backend_pid())) != pid
                    await writer.execute(text("SET LOCAL lock_timeout = '100ms'"))
                    with pytest.raises(DBAPIError) as waiting:
                        if writer_kind == "image_delete":
                            await writer.execute(
                                delete(Attachment).where(Attachment.id == image_id)
                            )
                        else:
                            await PeersService(writer).block_peer(*identities)
                    assert getattr(waiting.value.orig, "sqlstate", None) == "55P03"
                    await writer.rollback()
                return await source_record(*args, **kwargs)

            monkeypatch.setattr(image_share, "_record", probe)

            async def delivered(shared):
                async with AsyncSession(async_engine) as reader:
                    assert (
                        await reader.scalar(
                            select(Attachment.id).where(Attachment.id == shared.attachment_id)
                        )
                        == shared.attachment_id
                    )
                    await reader.execute(
                        select(User.id).where(User.id.in_(identities)).with_for_update(nowait=True)
                    )
                    await reader.rollback()
                return True

            monkeypatch.setattr(
                "src.domains.agents.application.peer_image.deliver_shared_image", delivered
            )
            draft = await prepare_peer_image(
                db, identities[0], PeerImageInput(connection_id=pair_id, attachment_id=image_id)
            )
            receipt = PreferenceWriteReceipt()
            await execute_peer_image(db, identities[0], draft, receipt)
            assert receipt.committed
    finally:
        async with AsyncSession(async_engine) as cleanup:
            await cleanup.execute(delete(User).where(User.id.in_(identities)))
            await cleanup.commit()
