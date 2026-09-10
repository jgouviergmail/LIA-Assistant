"""The service against a real server (ADR-276).

What a stubbed repository cannot prove, and what is checked here:

- the peer-connection re-check really reads ``peer_connections`` — the
  authorisation that a CHECK constraint could not express (see
  ``test_lifecycle_db``), so it must be shown to work end to end;
- a deletion really takes its children;
- a move really renumbers the owner's column, even when a peer made it.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import BaseAPIException
from src.domains.peers.models import PeerConnection, PeerConnectionStatus, canonical_pair
from src.domains.users.models import User
from src.domains.workboard.board_queries import BoardFilters
from src.domains.workboard.constants import AssigneeKind, TicketStatus, WorkboardError
from src.domains.workboard.models import WorkboardTicket
from src.domains.workboard.schemas import TicketCreate, TicketUpdate
from src.domains.workboard.service import WorkboardService

pytestmark = pytest.mark.integration


def _user(email: str, name: str) -> User:
    return User(
        email=email,
        hashed_password="x",
        is_active=True,
        is_verified=True,
        is_superuser=False,
        full_name=name,
    )


def _code(exc: BaseAPIException) -> str:
    return exc.detail if isinstance(exc.detail, str) else str(exc.detail)


@pytest.fixture(autouse=True)
def peers_feature_on(monkeypatch: pytest.MonkeyPatch) -> None:
    """Run these tests on an instance that HAS peers.

    The test environment scrubs the developer ``.env``, so ``peers_enabled``
    falls back to its ``False`` default and every peer assignment would be
    refused before the connection is even looked at — a green flag-off refusal
    that hides whether the authorisation itself works. The flag-off behaviour
    gets its own test below, which turns it back off explicitly.
    """
    monkeypatch.setattr(settings, "peers_enabled", True, raising=False)


@pytest.fixture
async def accounts(async_session: AsyncSession) -> tuple[User, User]:
    owner = _user("wb_svc_owner@test.local", "Service Owner")
    peer = _user("wb_svc_peer@test.local", "Service Peer")
    async_session.add_all([owner, peer])
    await async_session.commit()
    return owner, peer


@pytest.fixture
async def connected(async_session: AsyncSession, accounts: tuple[User, User]) -> tuple[User, User]:
    owner, peer = accounts
    user_a, user_b = canonical_pair(owner.id, peer.id)
    async_session.add(
        PeerConnection(
            user_a_id=user_a,
            user_b_id=user_b,
            requested_by_id=owner.id,
            status=PeerConnectionStatus.ACCEPTED.value,
            requested_at=datetime.now(UTC),
            responded_at=datetime.now(UTC),
        )
    )
    await async_session.commit()
    return owner, peer


class TestPeerAuthorisation:
    """The invariant the database could not carry."""

    async def test_a_peer_assignment_needs_a_real_accepted_connection(
        self, async_session: AsyncSession, accounts: tuple[User, User]
    ) -> None:
        owner, peer = accounts
        service = WorkboardService(async_session)
        with pytest.raises(BaseAPIException) as exc:
            await service.create(
                owner, TicketCreate(title="Please handle", assignee_user_id=peer.id)
            )
        assert _code(exc.value) == WorkboardError.ASSIGNEE_NOT_CONNECTED.value

    async def test_a_connected_peer_is_accepted(
        self, async_session: AsyncSession, connected: tuple[User, User]
    ) -> None:
        owner, peer = connected
        ticket = await WorkboardService(async_session).create(
            owner, TicketCreate(title="Please handle", assignee_user_id=peer.id)
        )
        await async_session.commit()
        assert ticket.assignee_user_id == peer.id
        assert ticket.assignee_kind == AssigneeKind.HUMAN.value

    async def test_a_pending_connection_is_not_an_accepted_one(
        self, async_session: AsyncSession, accounts: tuple[User, User]
    ) -> None:
        """The status matters, not the row's existence."""
        owner, peer = accounts
        user_a, user_b = canonical_pair(owner.id, peer.id)
        async_session.add(
            PeerConnection(
                user_a_id=user_a,
                user_b_id=user_b,
                requested_by_id=owner.id,
                status=PeerConnectionStatus.PENDING.value,
                requested_at=datetime.now(UTC),
            )
        )
        await async_session.commit()

        with pytest.raises(BaseAPIException) as exc:
            await WorkboardService(async_session).create(
                owner, TicketCreate(title="Too early", assignee_user_id=peer.id)
            )
        assert _code(exc.value) == WorkboardError.ASSIGNEE_NOT_CONNECTED.value

    async def test_the_ticket_appears_on_the_peer_board(
        self, async_session: AsyncSession, connected: tuple[User, User]
    ) -> None:
        owner, peer = connected
        service = WorkboardService(async_session)
        await service.create(owner, TicketCreate(title="Yours now", assignee_user_id=peer.id))
        await service.create(owner, TicketCreate(title="Mine alone"))
        await async_session.commit()

        rows, total, counts = await service.board(peer, BoardFilters(), limit=50, offset=0)
        assert total == 1
        assert [row.title for row in rows] == ["Yours now"]
        assert counts["todo"] == 1

    async def test_an_instance_without_peers_refuses_before_looking(
        self,
        async_session: AsyncSession,
        connected: tuple[User, User],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Gate-keeper rule (ADR-061): a disabled subsystem is never offered,
        and the refusal names the FEATURE rather than the connection — the
        accounts here are genuinely connected."""
        owner, peer = connected
        monkeypatch.setattr(settings, "peers_enabled", False, raising=False)

        with pytest.raises(BaseAPIException) as exc:
            await WorkboardService(async_session).create(
                owner, TicketCreate(title="Nope", assignee_user_id=peer.id)
            )
        assert _code(exc.value) == WorkboardError.PEERS_DISABLED.value


class TestPeerRightsEndToEnd:
    async def test_a_peer_moves_it_and_the_owner_column_is_renumbered(
        self, async_session: AsyncSession, connected: tuple[User, User]
    ) -> None:
        owner, peer = connected
        service = WorkboardService(async_session)
        handed = await service.create(
            owner, TicketCreate(title="Handed over", assignee_user_id=peer.id)
        )
        await service.create(owner, TicketCreate(title="Also in progress", status="in_progress"))
        await async_session.commit()
        handed_id, owner_id = handed.id, owner.id

        await service.move(peer, handed_id, TicketStatus.IN_PROGRESS.value, 0)
        await async_session.commit()
        async_session.expire_all()

        moved = await async_session.get(WorkboardTicket, handed_id)
        assert moved is not None
        assert moved.status == TicketStatus.IN_PROGRESS.value
        assert moved.position == 0
        positions = (
            (
                await async_session.execute(
                    select(WorkboardTicket.position)
                    .where(
                        WorkboardTicket.owner_user_id == owner_id,
                        WorkboardTicket.status == TicketStatus.IN_PROGRESS.value,
                    )
                    .order_by(WorkboardTicket.position)
                )
            )
            .scalars()
            .all()
        )
        assert list(positions) == [0, 1], "the column is a contiguous order"

    async def test_a_peer_cannot_rewrite_the_owners_words(
        self, async_session: AsyncSession, connected: tuple[User, User]
    ) -> None:
        owner, peer = connected
        service = WorkboardService(async_session)
        ticket = await service.create(
            owner, TicketCreate(title="Owner wording", assignee_user_id=peer.id)
        )
        await async_session.commit()

        with pytest.raises(BaseAPIException) as exc:
            await service.update(peer, ticket.id, TicketUpdate(title="Peer wording"))
        assert _code(exc.value) == WorkboardError.PEER_CANNOT_EDIT_FIELD.value


class TestDeletion:
    async def test_deleting_a_parent_takes_its_children(
        self, async_session: AsyncSession, accounts: tuple[User, User]
    ) -> None:
        owner, _peer = accounts
        service = WorkboardService(async_session)
        parent = await service.create(owner, TicketCreate(title="Organise the party"))
        await async_session.commit()
        await service.create(owner, TicketCreate(title="Book the venue", parent_id=parent.id))
        await service.create(owner, TicketCreate(title="Call the caterer", parent_id=parent.id))
        await async_session.commit()
        owner_id = owner.id

        removed = await service.delete(owner, parent.id)
        await async_session.commit()

        assert removed == 3, "the confirmation says what it takes"
        left = (
            await async_session.execute(
                select(func.count())
                .select_from(WorkboardTicket)
                .where(WorkboardTicket.owner_user_id == owner_id)
            )
        ).scalar()
        assert left == 0


class TestDepthRule:
    async def test_a_grandchild_is_refused(
        self, async_session: AsyncSession, accounts: tuple[User, User]
    ) -> None:
        owner, _peer = accounts
        service = WorkboardService(async_session)
        parent = await service.create(owner, TicketCreate(title="Parent"))
        await async_session.commit()
        child = await service.create(owner, TicketCreate(title="Child", parent_id=parent.id))
        await async_session.commit()

        with pytest.raises(BaseAPIException) as exc:
            await service.create(owner, TicketCreate(title="Grandchild", parent_id=child.id))
        assert _code(exc.value) == WorkboardError.DEPTH_EXCEEDED.value
