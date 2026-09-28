"""Keeping a generated file past its deadline, on real PostgreSQL (ADR-319).

What only the database can prove:

- a kept file has no deadline, and the cleanup — ONE conditional ``DELETE`` —
  never reaches it, even when the keep lands while the sweep is running;
- a file whose deadline passed but that the sweep has not removed yet can
  still be rescued;
- the account's ceilings hold, and hold under concurrency: two keeps racing
  for the last free slot cannot both land (advisory lock per account);
- only what LIA produced can be kept; an upload always keeps a deadline (CHECK).
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.core.config import get_settings
from src.domains.attachments import keep as keep_module
from src.domains.attachments import service as service_module
from src.domains.attachments.card_lifetimes import current_lifetimes
from src.domains.attachments.keep import (
    GeneratedAssetKeepLimitError,
    keep_generated,
    keep_usage,
    release_generated,
)
from src.domains.attachments.models import (
    Attachment,
    AttachmentContentType,
    AttachmentOrigin,
    AttachmentStatus,
)
from src.domains.attachments.service import AttachmentService
from src.domains.users.models import User

pytestmark = pytest.mark.integration

BYTES = b"\x89PNG\r\n\x1a\n" + b"kept-bytes"


async def _user(session: AsyncSession, email: str) -> User:
    user = User(
        email=email,
        hashed_password="x",
        is_active=True,
        is_verified=True,
        is_superuser=False,
        full_name="Keeper",
    )
    session.add(user)
    await session.flush()
    return user


async def _file(
    session: AsyncSession,
    root: Path,
    owner: UUID,
    *,
    origin: AttachmentOrigin = AttachmentOrigin.GENERATED_IMAGE,
    expires_at: datetime | None = None,
    size: int = len(BYTES),
) -> Attachment:
    stored = f"{uuid4()}.png"
    relative = f"{owner}/{stored}"
    (root / str(owner)).mkdir(parents=True, exist_ok=True)
    (root / relative).write_bytes(BYTES)
    row = Attachment(
        user_id=owner,
        original_filename=f"generated_{stored}",
        stored_filename=stored,
        mime_type="image/png",
        file_size=size,
        file_path=relative,
        content_type=AttachmentContentType.IMAGE,
        origin=origin.value,
        status=AttachmentStatus.READY,
        expires_at=expires_at or datetime.now(UTC) + timedelta(hours=12),
    )
    session.add(row)
    await session.flush()
    return row


@pytest.fixture
def storage(tmp_path: Path) -> Any:
    patched = get_settings()
    patched.attachments_storage_path = str(tmp_path)
    with patch.object(service_module, "get_settings", return_value=patched):
        yield tmp_path


async def _deadline(session: AsyncSession, file_id: UUID) -> datetime | None:
    return await session.scalar(select(Attachment.expires_at).where(Attachment.id == file_id))


class TestKeeping:
    async def test_a_kept_file_loses_its_deadline_and_the_sweep_leaves_it(
        self, async_session: AsyncSession, storage: Path
    ) -> None:
        owner = await _user(async_session, f"k_{uuid4().hex}@test.local")
        # Past its deadline, not swept yet: still listed, still served — rescuable.
        file = await _file(
            async_session, storage, owner.id, expires_at=datetime.now(UTC) - timedelta(minutes=5)
        )
        await async_session.commit()

        kept, skipped = await keep_generated(async_session, owner.id, [file.id], language="fr")
        stats = await AttachmentService(async_session).cleanup_expired()

        assert (kept, skipped) == ([file.id], [])
        assert await _deadline(async_session, file.id) is None
        assert stats["deleted"] == 0
        assert (storage / file.file_path).is_file()

    async def test_keeping_twice_is_one_keep(
        self, async_session: AsyncSession, storage: Path
    ) -> None:
        owner = await _user(async_session, f"k_{uuid4().hex}@test.local")
        file = await _file(async_session, storage, owner.id)
        await async_session.commit()

        await keep_generated(async_session, owner.id, [file.id, file.id], language="fr")
        kept, skipped = await keep_generated(async_session, owner.id, [file.id], language="fr")

        assert (kept, skipped) == ([file.id], [])
        usage = await keep_usage(async_session, owner.id)
        assert (usage.kept_files, usage.kept_bytes) == (1, len(BYTES))

    async def test_an_upload_a_stranger_s_file_and_a_missing_id_are_skipped(
        self, async_session: AsyncSession, storage: Path
    ) -> None:
        owner = await _user(async_session, f"k_{uuid4().hex}@test.local")
        stranger = await _user(async_session, f"s_{uuid4().hex}@test.local")
        upload = await _file(async_session, storage, owner.id, origin=AttachmentOrigin.UPLOAD)
        theirs = await _file(async_session, storage, stranger.id)
        missing = uuid4()
        await async_session.commit()

        kept, skipped = await keep_generated(
            async_session, owner.id, [upload.id, theirs.id, missing], language="fr"
        )

        assert (kept, skipped) == ([], [upload.id, theirs.id, missing])
        assert await _deadline(async_session, upload.id) is not None
        assert await _deadline(async_session, theirs.id) is not None

    async def test_the_file_ceiling_refuses_the_whole_selection(
        self, async_session: AsyncSession, storage: Path
    ) -> None:
        owner = await _user(async_session, f"k_{uuid4().hex}@test.local")
        first = await _file(async_session, storage, owner.id)
        second = await _file(async_session, storage, owner.id)
        third = await _file(async_session, storage, owner.id)
        await async_session.commit()
        # The refusal rolls the transaction back (releasing the account's lock at
        # once), which expires every loaded row: read the ids before.
        first_id, second_id, third_id = first.id, second.id, third.id

        with patch.object(keep_module.settings, "generated_assets_keep_max_files", 2):
            await keep_generated(async_session, owner.id, [first_id], language="fr")
            with pytest.raises(GeneratedAssetKeepLimitError) as refused:
                await keep_generated(async_session, owner.id, [second_id, third_id], language="fr")

        assert refused.value.status_code == 409
        assert "2" in str(refused.value.detail)
        # Nothing of the refused selection was kept — not even the one that fit.
        assert await _deadline(async_session, second_id) is not None
        assert await _deadline(async_session, third_id) is not None

    async def test_the_byte_ceiling_counts_what_is_already_kept(
        self, async_session: AsyncSession, storage: Path
    ) -> None:
        owner = await _user(async_session, f"k_{uuid4().hex}@test.local")
        big = await _file(async_session, storage, owner.id, size=700 * 1024)
        other = await _file(async_session, storage, owner.id, size=700 * 1024)
        await async_session.commit()
        big_id, other_id = big.id, other.id

        with patch.object(keep_module.settings, "generated_assets_keep_max_mb", 1):
            await keep_generated(async_session, owner.id, [big_id], language="fr")
            with pytest.raises(GeneratedAssetKeepLimitError):
                await keep_generated(async_session, owner.id, [other_id], language="fr")

        assert await _deadline(async_session, other_id) is not None

    async def test_a_zero_ceiling_turns_keeping_off(
        self, async_session: AsyncSession, storage: Path
    ) -> None:
        owner = await _user(async_session, f"k_{uuid4().hex}@test.local")
        file = await _file(async_session, storage, owner.id)
        await async_session.commit()

        with patch.object(keep_module.settings, "generated_assets_keep_max_files", 0):
            with pytest.raises(GeneratedAssetKeepLimitError):
                await keep_generated(async_session, owner.id, [file.id], language="en")

    async def test_releasing_gives_a_fresh_deadline_never_an_immediate_deletion(
        self, async_session: AsyncSession, storage: Path
    ) -> None:
        owner = await _user(async_session, f"k_{uuid4().hex}@test.local")
        file = await _file(
            async_session, storage, owner.id, expires_at=datetime.now(UTC) - timedelta(hours=3)
        )
        never_kept = await _file(async_session, storage, owner.id)
        await async_session.commit()
        await keep_generated(async_session, owner.id, [file.id], language="fr")

        before = datetime.now(UTC)
        released, skipped = await release_generated(
            async_session, owner.id, [file.id, never_kept.id]
        )

        assert (released, skipped) == ([file.id], [never_kept.id])
        deadline = await _deadline(async_session, file.id)
        assert deadline is not None
        ttl = timedelta(hours=keep_module.settings.attachments_ttl_hours)
        assert before + ttl - timedelta(seconds=5) <= deadline <= datetime.now(UTC) + ttl

    async def test_the_sweep_removes_rows_then_their_files_and_nothing_else(
        self, async_session: AsyncSession, storage: Path
    ) -> None:
        owner = await _user(async_session, f"k_{uuid4().hex}@test.local")
        expired = await _file(
            async_session, storage, owner.id, expires_at=datetime.now(UTC) - timedelta(minutes=1)
        )
        alive = await _file(async_session, storage, owner.id)
        kept = await _file(async_session, storage, owner.id)
        await async_session.commit()
        await keep_generated(async_session, owner.id, [kept.id], language="fr")

        stats = await AttachmentService(async_session).cleanup_expired()

        assert stats == {"deleted": 1, "errors": 0}
        gone = await async_session.scalar(select(Attachment.id).where(Attachment.id == expired.id))
        assert gone is None
        assert not (storage / expired.file_path).exists()
        for survivor in (alive, kept):
            assert (storage / survivor.file_path).is_file()

    async def test_the_usage_counts_every_family_of_the_account(
        self, async_session: AsyncSession, storage: Path
    ) -> None:
        owner = await _user(async_session, f"k_{uuid4().hex}@test.local")
        image = await _file(async_session, storage, owner.id, size=100)
        document = await _file(
            async_session,
            storage,
            owner.id,
            origin=AttachmentOrigin.GENERATED_DOCUMENT,
            size=250,
        )
        await async_session.commit()
        await keep_generated(async_session, owner.id, [image.id, document.id], language="fr")

        usage = await keep_usage(async_session, owner.id)

        assert (usage.kept_files, usage.kept_bytes) == (2, 350)

    async def test_the_card_lifetimes_read_only_the_readers_files(
        self, async_session: AsyncSession, storage: Path
    ) -> None:
        owner = await _user(async_session, f"k_{uuid4().hex}@test.local")
        stranger = await _user(async_session, f"s_{uuid4().hex}@test.local")
        mine = await _file(async_session, storage, owner.id)
        kept = await _file(async_session, storage, owner.id)
        theirs = await _file(async_session, storage, stranger.id)
        await async_session.commit()
        await keep_generated(async_session, owner.id, [kept.id], language="fr")

        lifetimes = await current_lifetimes(async_session, owner.id, {mine.id, kept.id, theirs.id})

        assert set(lifetimes) == {mine.id, kept.id}
        assert lifetimes[kept.id] is None
        assert lifetimes[mine.id] is not None

    async def test_an_upload_can_never_lose_its_deadline(
        self, async_session: AsyncSession, storage: Path
    ) -> None:
        owner = await _user(async_session, f"k_{uuid4().hex}@test.local")
        upload = await _file(async_session, storage, owner.id, origin=AttachmentOrigin.UPLOAD)
        await async_session.commit()

        with pytest.raises(IntegrityError):
            await async_session.execute(
                update(Attachment).where(Attachment.id == upload.id).values(expires_at=None)
            )
        await async_session.rollback()


@pytest_asyncio.fixture
async def committed(async_engine: Any, test_database_url: str, storage: Path) -> Any:
    """Sessions whose writes really commit — a race needs two connections."""
    engine = create_async_engine(test_database_url, echo=False)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    marker = uuid4().hex
    yield maker, marker, storage
    async with maker() as session:
        await session.execute(delete(User).where(User.email.like(f"%{marker}%")))
        await session.commit()
    await engine.dispose()


class TestUnderConcurrency:
    async def test_two_keeps_racing_for_the_last_slot_cannot_both_land(
        self, committed: Any
    ) -> None:
        maker, marker, storage = committed
        async with maker() as session:
            owner = await _user(session, f"k_{marker}@test.local")
            first = await _file(session, storage, owner.id)
            second = await _file(session, storage, owner.id)
            await session.commit()

        async def _keep(file_id: uuid.UUID) -> str:
            async with maker() as session:
                try:
                    await keep_generated(session, owner.id, [file_id], language="fr")
                except GeneratedAssetKeepLimitError:
                    return "refused"
                return "kept"

        with patch.object(keep_module.settings, "generated_assets_keep_max_files", 1):
            outcomes = await asyncio.gather(_keep(first.id), _keep(second.id))

        assert sorted(outcomes) == ["kept", "refused"]
        async with maker() as session:
            usage = await keep_usage(session, owner.id)
        assert usage.kept_files == 1

    async def test_a_keep_holding_the_row_wins_over_a_sweep_already_running(
        self, committed: Any
    ) -> None:
        # The sweep's DELETE meets the row locked by the keep's UPDATE, waits,
        # then re-evaluates its condition on the committed row: NULL never
        # matches ``expires_at <= now()``, so the kept file survives.
        maker, marker, storage = committed
        async with maker() as session:
            owner = await _user(session, f"k_{marker}@test.local")
            file = await _file(
                session, storage, owner.id, expires_at=datetime.now(UTC) - timedelta(minutes=1)
            )
            await session.commit()

        async with maker() as keeper, maker() as sweeper:
            await keeper.execute(
                update(Attachment).where(Attachment.id == file.id).values(expires_at=None)
            )  # row locked, not committed
            sweep = asyncio.create_task(AttachmentService(sweeper).cleanup_expired())
            await asyncio.sleep(0.5)
            assert not sweep.done()  # the DELETE waits on the keep's row lock
            await keeper.commit()
            stats = await sweep

        assert stats["deleted"] == 0
        async with maker() as session:
            assert await _deadline(session, file.id) is None
        assert (storage / file.file_path).is_file()
