"""Sharing a generated image with a connection, on real PostgreSQL (ADR-316).

What only the database can prove:

- the copy, its gallery row and the ledger row are ONE transaction, and a
  failed write leaves no file behind;
- nothing crosses a pair that is not accepted, or that a block separates, and
  nothing but the sender's own, live, generated image can be shared;
- the daily quotas hold under concurrency: two shares racing past the last
  free slot cannot both land (the count and the insert are serialised per
  sender by a transaction-scoped advisory lock).
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
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.core.exceptions import BaseAPIException
from src.domains.attachments.models import (
    Attachment,
    AttachmentContentType,
    AttachmentOrigin,
    AttachmentStatus,
)
from src.domains.peers import image_share
from src.domains.peers.models import (
    PeerBlock,
    PeerConnection,
    PeerConnectionStatus,
    PeerImageShare,
    canonical_pair,
)
from src.domains.users.models import User

pytestmark = pytest.mark.integration

PNG = b"\x89PNG\r\n\x1a\n" + b"shared-image-bytes"


async def _user(session: AsyncSession, email: str, name: str) -> User:
    user = User(
        email=email,
        hashed_password="x",
        is_active=True,
        is_verified=True,
        is_superuser=False,
        full_name=name,
    )
    session.add(user)
    await session.flush()
    return user


async def _connection(
    session: AsyncSession, a: UUID, b: UUID, status: PeerConnectionStatus
) -> PeerConnection:
    lo, hi = canonical_pair(a, b)
    row = PeerConnection(
        user_a_id=lo,
        user_b_id=hi,
        requested_by_id=a,
        status=status.value,
        requested_at=datetime.now(UTC),
    )
    session.add(row)
    await session.flush()
    return row


async def _image(
    session: AsyncSession,
    root: Path,
    owner: UUID,
    *,
    origin: AttachmentOrigin = AttachmentOrigin.GENERATED_IMAGE,
    expires_at: datetime | None = None,
    write_file: bool = True,
) -> Attachment:
    stored = f"{uuid4()}.png"
    relative = f"{owner}/{stored}"
    if write_file:
        (root / str(owner)).mkdir(parents=True, exist_ok=True)
        (root / relative).write_bytes(PNG)
    row = Attachment(
        user_id=owner,
        original_filename=f"generated_{stored}",
        stored_filename=stored,
        mime_type="image/png",
        file_size=len(PNG),
        file_path=relative,
        content_type=AttachmentContentType.IMAGE,
        origin=origin.value,
        title="a lighthouse at dusk",
        status=AttachmentStatus.READY,
        expires_at=expires_at or datetime.now(UTC) + timedelta(hours=12),
    )
    session.add(row)
    await session.flush()
    return row


@pytest.fixture
def storage(tmp_path: Path) -> Any:
    with patch.object(image_share.settings, "attachments_storage_path", str(tmp_path)):
        yield tmp_path


@pytest_asyncio.fixture
async def pair(async_session: AsyncSession, storage: Path) -> Any:
    sender = await _user(async_session, f"s_{uuid4().hex}@test.local", "Gérard Dupont")
    recipient = await _user(async_session, f"r_{uuid4().hex}@test.local", "Claire Lefèvre")
    connection = await _connection(
        async_session, sender.id, recipient.id, PeerConnectionStatus.ACCEPTED
    )
    image = await _image(async_session, storage, sender.id)
    await async_session.commit()
    return sender, recipient, connection, image


async def _code_of(coro: Any) -> tuple[int, Any]:
    with pytest.raises(BaseAPIException) as raised:
        await coro
    return raised.value.status_code, raised.value.detail


async def _files_under(root: Path, owner: UUID) -> list[Path]:
    folder = root / str(owner)
    return sorted(folder.iterdir()) if folder.exists() else []


class TestTheCopy:
    async def test_the_recipient_gets_a_copy_in_their_gallery(
        self, async_session: AsyncSession, pair: Any, storage: Path
    ) -> None:
        sender, recipient, connection, image = pair

        shared = await image_share.share_image(
            async_session,
            sender_id=sender.id,
            connection_id=connection.id,
            attachment_id=image.id,
            comment="  Pour ton anniversaire !  ",
        )

        copy = await async_session.get(Attachment, shared.attachment_id)
        assert copy is not None
        assert copy.user_id == recipient.id
        assert copy.origin == AttachmentOrigin.GENERATED_IMAGE.value
        assert copy.status == AttachmentStatus.READY
        assert copy.title == "a lighthouse at dusk"
        assert copy.shared_by_name == "Gérard Dupont"
        # As if generated at reception: a fresh lifetime, not the sender's.
        assert copy.expires_at > image.expires_at
        assert (storage / copy.file_path).read_bytes() == PNG
        assert copy.file_path.startswith(f"{recipient.id}/")
        # The sender keeps theirs.
        assert (storage / image.file_path).read_bytes() == PNG

        ledger = (
            await async_session.execute(
                select(PeerImageShare).where(PeerImageShare.id == shared.share_id)
            )
        ).scalar_one()
        assert (ledger.sender_id, ledger.recipient_id, ledger.connection_id) == (
            sender.id,
            recipient.id,
            connection.id,
        )
        assert ledger.attachment_id == copy.id

        assert shared.recipient_id == recipient.id
        assert shared.sender_display_name == "Gérard Dupont"
        assert shared.comment == "Pour ton anniversaire !"
        assert shared.url == f"/api/v1/attachments/{copy.id}"

    async def test_the_longest_name_an_account_can_carry_travels_whole(
        self, async_session: AsyncSession, pair: Any
    ) -> None:
        """The provenance line holds whatever ``users.full_name`` can hold.

        A shorter column made the share of a long-named account fail at the
        INSERT, after the copy was on disk.
        """
        sender, _recipient, connection, image = pair
        longest = User.__table__.c.full_name.type.length
        sender.full_name = "N" * longest
        await async_session.commit()

        shared = await image_share.share_image(
            async_session,
            sender_id=sender.id,
            connection_id=connection.id,
            attachment_id=image.id,
            comment=None,
        )

        copy = await async_session.get(Attachment, shared.attachment_id)
        assert copy is not None
        assert copy.shared_by_name == "N" * longest

    async def test_a_blank_comment_is_no_comment(
        self, async_session: AsyncSession, pair: Any
    ) -> None:
        sender, _recipient, connection, image = pair

        shared = await image_share.share_image(
            async_session,
            sender_id=sender.id,
            connection_id=connection.id,
            attachment_id=image.id,
            comment="   ",
        )

        assert shared.comment is None


class TestWhoMayShareWithWhom:
    async def test_a_pending_connection_is_not_a_channel(
        self, async_session: AsyncSession, storage: Path
    ) -> None:
        sender = await _user(async_session, f"s_{uuid4().hex}@test.local", "S")
        other = await _user(async_session, f"o_{uuid4().hex}@test.local", "O")
        pending = await _connection(
            async_session, sender.id, other.id, PeerConnectionStatus.PENDING
        )
        image = await _image(async_session, storage, sender.id)
        await async_session.commit()

        status, detail = await _code_of(
            image_share.share_image(
                async_session,
                sender_id=sender.id,
                connection_id=pending.id,
                attachment_id=image.id,
                comment=None,
            )
        )

        assert (status, detail) == (400, "peers_not_connected")
        assert await _files_under(storage, other.id) == []

    async def test_a_connection_of_other_people_does_not_exist(
        self, async_session: AsyncSession, pair: Any
    ) -> None:
        _sender, _recipient, connection, image = pair
        stranger = await _user(async_session, f"x_{uuid4().hex}@test.local", "X")
        await async_session.commit()

        status, _detail = await _code_of(
            image_share.share_image(
                async_session,
                sender_id=stranger.id,
                connection_id=connection.id,
                attachment_id=image.id,
                comment=None,
            )
        )

        assert status == 404

    async def test_a_block_either_way_closes_the_pair(
        self, async_session: AsyncSession, pair: Any, storage: Path
    ) -> None:
        sender, recipient, connection, image = pair
        async_session.add(PeerBlock(blocker_id=recipient.id, blocked_id=sender.id))
        await async_session.commit()

        status, detail = await _code_of(
            image_share.share_image(
                async_session,
                sender_id=sender.id,
                connection_id=connection.id,
                attachment_id=image.id,
                comment=None,
            )
        )

        assert (status, detail) == (400, "peers_not_connected")
        assert await _files_under(storage, recipient.id) == []


class TestWhatMayBeShared:
    @pytest.mark.parametrize(
        "case", ["upload", "someone_else", "expired", "file_gone", "unknown_id"]
    )
    async def test_only_the_senders_live_generated_image(
        self, async_session: AsyncSession, pair: Any, storage: Path, case: str
    ) -> None:
        sender, recipient, connection, _image_row = pair
        if case == "upload":
            target = await _image(async_session, storage, sender.id, origin=AttachmentOrigin.UPLOAD)
        elif case == "someone_else":
            target = await _image(async_session, storage, recipient.id)
        elif case == "expired":
            target = await _image(
                async_session,
                storage,
                sender.id,
                expires_at=datetime.now(UTC) - timedelta(minutes=1),
            )
        elif case == "file_gone":
            target = await _image(async_session, storage, sender.id, write_file=False)
        await async_session.commit()
        attachment_id = uuid.uuid4() if case == "unknown_id" else target.id
        before = await _files_under(storage, recipient.id)

        status, detail = await _code_of(
            image_share.share_image(
                async_session,
                sender_id=sender.id,
                connection_id=connection.id,
                attachment_id=attachment_id,
                comment=None,
            )
        )

        assert (status, detail) == (400, "peers_image_not_shareable")
        assert await _files_under(storage, recipient.id) == before
        shares = await async_session.scalar(select(func.count(PeerImageShare.id)))
        assert shares == 0

    async def test_a_comment_past_the_bound_is_refused(
        self, async_session: AsyncSession, pair: Any
    ) -> None:
        from src.core.constants import PEERS_IMAGE_SHARE_COMMENT_MAX_CHARS

        sender, _recipient, connection, image = pair

        status, detail = await _code_of(
            image_share.share_image(
                async_session,
                sender_id=sender.id,
                connection_id=connection.id,
                attachment_id=image.id,
                comment="x" * (PEERS_IMAGE_SHARE_COMMENT_MAX_CHARS + 1),
            )
        )

        assert (status, detail) == (400, "peers_image_comment_too_long")


class TestTheQuotas:
    async def test_the_pair_quota_holds(self, async_session: AsyncSession, pair: Any) -> None:
        sender, _recipient, connection, image = pair
        with patch.object(image_share.settings, "peers_image_share_max_per_day_per_pair", 2):
            for _ in range(2):
                await image_share.share_image(
                    async_session,
                    sender_id=sender.id,
                    connection_id=connection.id,
                    attachment_id=image.id,
                    comment=None,
                )
            status, detail = await _code_of(
                image_share.share_image(
                    async_session,
                    sender_id=sender.id,
                    connection_id=connection.id,
                    attachment_id=image.id,
                    comment=None,
                )
            )

        assert (status, detail) == (429, "peers_image_quota_reached")

    async def test_the_daily_quota_counts_every_connection(
        self, async_session: AsyncSession, pair: Any, storage: Path
    ) -> None:
        sender, _recipient, connection, image = pair
        third = await _user(async_session, f"t_{uuid4().hex}@test.local", "Third")
        other_connection = await _connection(
            async_session, sender.id, third.id, PeerConnectionStatus.ACCEPTED
        )
        await async_session.commit()
        with patch.object(image_share.settings, "peers_image_share_max_per_day", 1):
            await image_share.share_image(
                async_session,
                sender_id=sender.id,
                connection_id=connection.id,
                attachment_id=image.id,
                comment=None,
            )
            status, _detail = await _code_of(
                image_share.share_image(
                    async_session,
                    sender_id=sender.id,
                    connection_id=other_connection.id,
                    attachment_id=image.id,
                    comment=None,
                )
            )

        assert status == 429
        assert await _files_under(storage, third.id) == []


class TestAFailedWriteKeepsNothing:
    async def test_the_copy_is_withdrawn_when_the_rows_cannot_be_written(
        self, async_session: AsyncSession, pair: Any, storage: Path
    ) -> None:
        sender, recipient, connection, image = pair
        # Read before the rollback expires every instance of the session.
        sender_id, recipient_id, connection_id, image_id = (
            sender.id,
            recipient.id,
            connection.id,
            image.id,
        )

        with (
            patch.object(image_share, "_record", side_effect=RuntimeError("write failed")),
            pytest.raises(RuntimeError),
        ):
            await image_share.share_image(
                async_session,
                sender_id=sender_id,
                connection_id=connection_id,
                attachment_id=image_id,
                comment=None,
            )

        assert await _files_under(storage, recipient_id) == []


@pytest_asyncio.fixture
async def committed(async_engine: Any, test_database_url: str, storage: Path) -> Any:
    """Sessions whose writes really commit — the race needs two connections."""
    engine = create_async_engine(test_database_url, echo=False)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    marker = uuid4().hex
    yield maker, marker, storage
    async with maker() as session:
        await session.execute(delete(User).where(User.email.like(f"%{marker}%")))
        await session.commit()
    await engine.dispose()


class TestTheQuotaUnderConcurrency:
    async def test_two_shares_racing_for_the_last_slot_cannot_both_land(
        self, committed: Any
    ) -> None:
        maker, marker, storage = committed
        async with maker() as session:
            sender = await _user(session, f"s_{marker}@test.local", "Racer")
            recipient = await _user(session, f"r_{marker}@test.local", "Target")
            connection = await _connection(
                session, sender.id, recipient.id, PeerConnectionStatus.ACCEPTED
            )
            image = await _image(session, storage, sender.id)
            await session.commit()

        async def _share() -> str:
            async with maker() as session:
                try:
                    await image_share.share_image(
                        session,
                        sender_id=sender.id,
                        connection_id=connection.id,
                        attachment_id=image.id,
                        comment=None,
                    )
                except BaseAPIException as exc:
                    return str(exc.detail)
                return "shared"

        with patch.object(image_share.settings, "peers_image_share_max_per_day_per_pair", 1):
            outcomes = await asyncio.gather(_share(), _share())

        assert sorted(outcomes) == ["peers_image_quota_reached", "shared"]
        async with maker() as session:
            shares = await session.scalar(
                select(func.count(PeerImageShare.id)).where(PeerImageShare.sender_id == sender.id)
            )
        assert shares == 1
        assert len(await _files_under(storage, recipient.id)) == 1
