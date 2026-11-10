"""Independent committed transactions prove direct peer admission and replay."""

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.core.config import settings
from src.domains.agents.effects import runtime
from src.domains.agents.effects.scope import EffectScope, effect_scope
from src.domains.peers.message_command import (
    PeerMessageReceipt,
    PeerMessageRefusal,
    enqueue_peer_message,
)
from src.domains.peers.models import PeerBlock, PeerConnection, PeerMessage, canonical_pair
from src.domains.peers.pair_fence import lock_peer_pair
from src.domains.users.models import User
from tests.helpers.runtime_context import installed_runtime_context

pytestmark = pytest.mark.integration


@dataclass(frozen=True)
class Peers:
    sender: UUID
    recipient: UUID
    other: UUID
    connection: UUID
    other_connection: UUID


@pytest_asyncio.fixture
async def peers(async_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Peers]:
    monkeypatch.setattr(settings, "peers_enabled", True)
    actor = Peers(*(uuid4() for _ in range(5)))
    ids = (actor.sender, actor.recipient, actor.other)
    async with AsyncSession(async_engine) as db:
        db.add_all(
            [
                User(id=uid, email=f"message-{uid}@example.com", full_name="Peer", is_active=True)
                for uid in ids
            ]
        )
        await db.flush()
        for recipient, connection in [
            (actor.recipient, actor.connection),
            (actor.other, actor.other_connection),
        ]:
            a, b = canonical_pair(actor.sender, recipient)
            db.add(
                PeerConnection(
                    id=connection,
                    user_a_id=a,
                    user_b_id=b,
                    requested_by_id=actor.sender,
                    status="accepted",
                )
            )
        await db.commit()
    monkeypatch.setattr(
        "src.domains.peers.message_command.is_capability_enabled", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(
        "src.domains.peers.message_command.UsageLimitService.is_user_blocked_for_llm",
        AsyncMock(return_value=False),
    )
    monkeypatch.setattr(
        "src.infrastructure.scheduler.peer_delivery_runner.is_capability_enabled",
        AsyncMock(return_value=True),
    )
    try:
        yield actor
    finally:
        async with AsyncSession(async_engine) as db:
            await db.execute(delete(User).where(User.id.in_(ids)))
            await db.commit()


async def count_messages(engine: AsyncEngine, sender: UUID) -> int:
    async with AsyncSession(engine) as db:
        return int(
            await db.scalar(
                select(func.count()).select_from(PeerMessage).where(PeerMessage.sender_id == sender)
            )
            or 0
        )


async def test_a_direct_enqueue_is_committed_and_remains_pending(
    async_engine: AsyncEngine, peers: Peers
) -> None:
    result = await enqueue_peer_message(
        peers.sender, peers.connection, peers.recipient, "A literal message"
    )
    assert isinstance(result, PeerMessageReceipt)
    async with AsyncSession(async_engine) as observer:
        row = await observer.get(PeerMessage, result.message_id)
        assert row is not None and row.status == "pending"
        assert row.content == "A literal message" and row.delivered_at is None
        assert row.expires_at is not None
        # A fresh connection can take every parent fence after enqueue returns.
        await observer.execute(
            select(User.id)
            .where(User.id.in_([peers.sender, peers.recipient]))
            .with_for_update(nowait=True)
        )


@pytest.mark.parametrize("target", ["outsider", "self", "other_pair"])
async def test_pair_membership_is_revalidated_not_trusted_from_a_draft(
    async_engine: AsyncEngine, peers: Peers, target: str
) -> None:
    sender = peers.other if target == "outsider" else peers.sender
    recipient = (
        peers.sender
        if target == "self"
        else peers.other if target == "other_pair" else peers.recipient
    )
    result = await enqueue_peer_message(sender, peers.connection, recipient, "hello")
    assert result is PeerMessageRefusal.NOT_CONNECTED
    assert await count_messages(async_engine, sender) == 0


@pytest.mark.parametrize("restriction", ["blocked", "removed", "inactive"])
async def test_current_authority_wins_over_a_previous_resolution(
    async_engine: AsyncEngine, peers: Peers, restriction: str
) -> None:
    async with AsyncSession(async_engine) as writer:
        if restriction == "blocked":
            writer.add(PeerBlock(blocker_id=peers.recipient, blocked_id=peers.sender))
        elif restriction == "inactive":
            user = await writer.get(User, peers.recipient)
            assert user is not None
            user.is_active = False
        else:
            pair = await writer.get(PeerConnection, peers.connection)
            assert pair is not None
            pair.status = "removed"
        await writer.commit()
    assert (
        await enqueue_peer_message(peers.sender, peers.connection, peers.recipient, "hello")
        is PeerMessageRefusal.NOT_CONNECTED
    )
    assert await count_messages(async_engine, peers.sender) == 0


async def test_different_recipients_share_the_senders_last_quota_slot(
    async_engine: AsyncEngine, peers: Peers, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "peers_message_max_per_day", 1)
    results = await asyncio.gather(
        enqueue_peer_message(peers.sender, peers.connection, peers.recipient, "one"),
        enqueue_peer_message(peers.sender, peers.other_connection, peers.other, "two"),
    )
    assert sum(isinstance(row, PeerMessageReceipt) for row in results) == 1
    assert PeerMessageRefusal.QUOTA_REACHED in results
    assert await count_messages(async_engine, peers.sender) == 1


async def test_a_blocking_transaction_orders_before_admission(
    async_engine: AsyncEngine, peers: Peers, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def bounded_fence(db: AsyncSession, first: UUID, second: UUID) -> None:
        await db.execute(text("SET LOCAL lock_timeout = '100ms'"))
        await lock_peer_pair(db, first, second)

    monkeypatch.setattr("src.domains.peers.message_authority.lock_peer_pair", bounded_fence)
    async with AsyncSession(async_engine) as blocker:
        await lock_peer_pair(blocker, peers.sender, peers.recipient)
        with pytest.raises(DBAPIError) as locked:
            await enqueue_peer_message(peers.sender, peers.connection, peers.recipient, "must wait")
        assert getattr(locked.value.orig, "sqlstate", None) == "55P03"
        blocker.add(PeerBlock(blocker_id=peers.recipient, blocked_id=peers.sender))
        await blocker.commit()
    assert (
        await enqueue_peer_message(peers.sender, peers.connection, peers.recipient, "after block")
        is PeerMessageRefusal.NOT_CONNECTED
    )
    assert await count_messages(async_engine, peers.sender) == 0


@pytest.mark.parametrize("mode", ["pipeline", "react"])
async def test_the_real_effect_ledger_replays_without_a_second_enqueue(
    async_engine: AsyncEngine, peers: Peers, mode: str
) -> None:
    async def act(message: str) -> dict[str, object]:
        result = await enqueue_peer_message(
            peers.sender, peers.connection, peers.recipient, message
        )
        assert isinstance(result, PeerMessageReceipt)
        return {"success": True, "message_id": str(result.message_id), "status": "pending"}

    execute = runtime.gated("send_peer_message_tool", act)
    scope = EffectScope(run_id=str(uuid4()), idempotency_key=str(uuid4()))
    with (
        installed_runtime_context(
            user_id=peers.sender, thread_id=str(uuid4()), execution_mode=mode
        ),
        patch.object(runtime, "resolve_policy", return_value="direct"),
    ):
        with effect_scope(scope):
            first = await execute(message="same words")
            second = await execute(message="same words")
        assert first == second
        assert await count_messages(async_engine, peers.sender) == 1
        with effect_scope(EffectScope(run_id=scope.run_id, idempotency_key=str(uuid4()))):
            third = await execute(message="same words")
        assert third["message_id"] != first["message_id"]
        assert await count_messages(async_engine, peers.sender) == 2


async def test_crash_after_enqueue_cannot_repeat_an_unknown_effect(
    async_engine: AsyncEngine, peers: Peers
) -> None:
    async def act() -> dict[str, object]:
        await enqueue_peer_message(
            peers.sender, peers.connection, peers.recipient, "already queued"
        )
        raise asyncio.CancelledError

    execute = runtime.gated("send_peer_message_tool", act)
    with (
        installed_runtime_context(user_id=peers.sender, thread_id=str(uuid4())),
        effect_scope(EffectScope(run_id=str(uuid4()), idempotency_key=str(uuid4()))),
        patch.object(runtime, "resolve_policy", return_value="direct"),
    ):
        with pytest.raises(asyncio.CancelledError):
            await execute()
        result = await execute()
        assert result["success"] is False
    assert await count_messages(async_engine, peers.sender) == 1


async def _claimed_delivery(engine: AsyncEngine, actors: Peers) -> PeerMessage:
    from src.domains.peers.delivery_repository import PeerDeliveryRepository

    receipt = await enqueue_peer_message(
        actors.sender, actors.connection, actors.recipient, "one delivery"
    )
    assert isinstance(receipt, PeerMessageReceipt)
    async with AsyncSession(engine, expire_on_commit=False) as db:
        (row,) = await PeerDeliveryRepository(db).claim_pending_messages()
        await db.commit()
        return row


@pytest.mark.parametrize("operation", ["renew", "finish", "fail", "cancel", "prepare", "start"])
async def test_expired_owner_cannot_modify_a_reclaimed_delivery(
    async_engine: AsyncEngine, peers: Peers, operation: str
) -> None:
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import update

    from src.domains.peers.delivery_repository import PeerDeliveryRepository, claim_of

    first = await _claimed_delivery(async_engine, peers)
    claim_a = claim_of(first)
    async with AsyncSession(async_engine, expire_on_commit=False) as db:
        await db.execute(
            update(PeerMessage)
            .where(PeerMessage.id == first.id)
            .values(lease_expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
        repo = PeerDeliveryRepository(db)
        assert await repo.recover_stale_delivering() == 1
        (second,) = await repo.claim_pending_messages()
        claim_b = claim_of(second)
        await db.commit()
    assert claim_a.owner != claim_b.owner and claim_b.generation > claim_a.generation
    async with AsyncSession(async_engine) as stale:
        repo = PeerDeliveryRepository(stale)
        match operation:
            case "renew":
                result = await repo.renew(claim_a)
            case "finish":
                result = await repo.mark_message_delivered(
                    claim_a, now=datetime.now(UTC), delivered_text="stale"
                )
            case "fail":
                result = await repo.mark_message_failed(claim_a, "stale", max_attempts=1)
            case "cancel":
                result = await repo.cancel_message(claim_a, "stale")
            case "prepare":
                result = await repo.store_prepared(claim_a, "stale")
            case "start":
                result = await repo.start_generation(claim_a)
            case _:
                raise AssertionError(operation)
        assert result is False or result is None
        await stale.commit()
    async with AsyncSession(async_engine) as fresh:
        row = await fresh.get(PeerMessage, first.id)
        assert row is not None and row.status == "delivering" and row.last_error is None
        assert row.claim_token == claim_b.owner and row.claim_generation == claim_b.generation
        assert await PeerDeliveryRepository(fresh).mark_message_delivered(
            claim_b, now=datetime.now(UTC), delivered_text="fresh"
        )
        await fresh.commit()


@pytest.mark.parametrize("prepared", [False, True])
async def test_recovery_never_regenerates_an_unknown_model_outcome(
    async_engine: AsyncEngine, peers: Peers, prepared: bool
) -> None:
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import update

    from src.core.security.utils import decrypt_data
    from src.domains.peers.delivery_repository import PeerDeliveryRepository, claim_of

    row = await _claimed_delivery(async_engine, peers)
    async with AsyncSession(async_engine) as db:
        repo = PeerDeliveryRepository(db)
        assert await repo.start_generation(claim_of(row))
        if prepared:
            assert await repo.store_prepared(claim_of(row), "Retained rendition")
        await db.execute(
            update(PeerMessage)
            .where(PeerMessage.id == row.id)
            .values(lease_expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
        await db.commit()
    async with AsyncSession(async_engine) as db:
        repo = PeerDeliveryRepository(db)
        assert await repo.recover_stale_delivering() == 1
        current = await db.get(PeerMessage, row.id)
        assert current is not None and current.claim_token is None
        if prepared:
            assert current.status == "pending"
            assert current.prepared_text_encrypted is not None
            assert decrypt_data(current.prepared_text_encrypted) == "Retained rendition"
            assert current.prepared_text_encrypted != "Retained rendition"
        else:
            assert current.status == "failed" and current.last_error == "generation_outcome_unknown"
            assert await repo.claim_pending_messages() == []


async def _archive_count(engine: AsyncEngine, target: UUID) -> int:
    from src.domains.conversations.models import ConversationMessage

    async with AsyncSession(engine) as db:
        return int(
            await db.scalar(
                select(func.count())
                .select_from(ConversationMessage)
                .where(ConversationMessage.message_metadata["target_id"].astext == str(target))
            )
            or 0
        )


async def test_archive_and_settle_are_one_transaction_and_one_delivery_key(
    async_engine: AsyncEngine, peers: Peers, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.domains.peers.delivery_repository import PeerDeliveryRepository, claim_of
    from src.infrastructure.scheduler.peer_delivery_archive import commit_delivery

    row = await _claimed_delivery(async_engine, peers)
    claim = claim_of(row)
    original = PeerDeliveryRepository.mark_message_delivered

    async def crash(*args: object, **kwargs: object) -> bool:
        raise RuntimeError("crash after archive before settlement")

    monkeypatch.setattr(PeerDeliveryRepository, "mark_message_delivered", crash)
    with pytest.raises(RuntimeError):
        await commit_delivery(row, claim, "Only one copy")
    assert await _archive_count(async_engine, row.id) == 0
    monkeypatch.setattr(PeerDeliveryRepository, "mark_message_delivered", original)
    outcomes = await asyncio.gather(
        commit_delivery(row, claim, "Only one copy"), commit_delivery(row, claim, "Only one copy")
    )
    assert sorted(outcomes) == ["delivered", "lost"]
    assert await _archive_count(async_engine, row.id) == 1
    # A crash after COMMIT but before push cannot cause another archive or spend.
    assert await commit_delivery(row, claim, "Only one copy") == "lost"
    assert await _archive_count(async_engine, row.id) == 1


async def test_a_block_after_generation_prevents_atomic_archival(
    async_engine: AsyncEngine, peers: Peers
) -> None:
    from src.domains.peers.delivery_repository import claim_of
    from src.infrastructure.scheduler.peer_delivery_archive import commit_delivery

    row = await _claimed_delivery(async_engine, peers)
    async with AsyncSession(async_engine) as db:
        db.add(PeerBlock(blocker_id=peers.recipient, blocked_id=peers.sender))
        await db.commit()
    assert await commit_delivery(row, claim_of(row), "Must not arrive") == "cancelled_not_connected"
    assert await _archive_count(async_engine, row.id) == 0


@pytest.mark.parametrize("failure", ["timeout", "cancelled", "dispatch"])
async def test_worker_closes_uncertainty_and_reuses_paid_renditions(
    async_engine: AsyncEngine, peers: Peers, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    from src.domains.peers.delivery_repository import PeerDeliveryRepository
    from src.infrastructure.scheduler import peer_delivery_runner as runner

    row = await _claimed_delivery(async_engine, peers)
    calls: list[str] = []

    async def generate(message: PeerMessage, sender: User, recipient: User, count: int) -> str:
        calls.append("generated")
        async with AsyncSession(async_engine) as observer:
            assert (
                await observer.scalar(
                    text(
                        "SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND state='idle in transaction'"
                    )
                )
                == 0
            )
        if failure == "timeout":
            raise TimeoutError("unknown paid outcome")
        if failure == "cancelled":
            raise asyncio.CancelledError
        return "A rendition bought once"

    notify = AsyncMock()
    monkeypatch.setattr(runner, "notify_result", notify)
    original = runner.commit_delivery
    if failure == "dispatch":
        monkeypatch.setattr(
            runner, "commit_delivery", AsyncMock(side_effect=RuntimeError("archive unavailable"))
        )
        assert await runner.run_delivery(row, generate) == "pending"
        monkeypatch.setattr(runner, "commit_delivery", original)
        async with AsyncSession(async_engine, expire_on_commit=False) as db:
            (retry,) = await PeerDeliveryRepository(db).claim_pending_messages()
            await db.commit()
        assert await runner.run_delivery(retry, generate) == "delivered"
        assert await _archive_count(async_engine, row.id) == 1
    elif failure == "cancelled":
        with pytest.raises(asyncio.CancelledError):
            await runner.run_delivery(row, generate)
    else:
        assert await runner.run_delivery(row, generate) == "failed"
    assert calls == ["generated"]
    async with AsyncSession(async_engine) as db:
        current = await db.get(PeerMessage, row.id)
        assert current is not None
        assert current.status == ("delivered" if failure == "dispatch" else "failed")
        assert current.claim_token is None
        assert await PeerDeliveryRepository(db).claim_pending_messages() == []


async def test_lost_heartbeat_cancels_model_and_prevents_archive(
    async_engine: AsyncEngine, peers: Peers, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.domains.peers.delivery_repository import PeerDeliveryRepository
    from src.infrastructure.scheduler import peer_delivery_runner as runner

    row = await _claimed_delivery(async_engine, peers)
    started, cancelled = asyncio.Event(), asyncio.Event()

    async def generate(message: PeerMessage, sender: User, recipient: User, count: int) -> str:
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()
        raise AssertionError("unreachable")

    async def lost(*args: object) -> bool:
        await started.wait()
        return False

    monkeypatch.setattr(PeerDeliveryRepository, "renew", lost)
    monkeypatch.setattr(settings, "peers_delivery_lease_seconds", 0.03)
    monkeypatch.setattr(runner, "notify_result", AsyncMock())
    assert await asyncio.wait_for(runner.run_delivery(row, generate), timeout=2) == "lost"
    assert cancelled.is_set()
    assert await _archive_count(async_engine, row.id) == 0


@pytest.mark.parametrize(
    "restriction",
    [
        "disabled",
        "expired",
        "empty",
        "blocked",
        "removed",
        "sender_inactive",
        "recipient_inactive",
        "quota",
    ],
)
async def test_worker_revalidates_before_any_model_or_notification(
    async_engine: AsyncEngine, peers: Peers, monkeypatch: pytest.MonkeyPatch, restriction: str
) -> None:
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import update

    from src.infrastructure.scheduler import peer_delivery_runner as runner

    row = await _claimed_delivery(async_engine, peers)
    if restriction == "disabled":
        monkeypatch.setattr(runner, "is_capability_enabled", AsyncMock(return_value=False))
    elif restriction == "quota":
        monkeypatch.setattr(
            runner.UsageLimitService, "is_user_blocked_for_llm", AsyncMock(return_value=True)
        )
    elif restriction == "expired":
        row.expires_at = datetime.now(UTC) - timedelta(days=1)
    elif restriction == "empty":
        row.content = " "
    else:
        async with AsyncSession(async_engine) as db:
            if restriction == "blocked":
                db.add(PeerBlock(blocker_id=peers.recipient, blocked_id=peers.sender))
            elif restriction == "removed":
                await db.execute(
                    update(PeerConnection)
                    .where(PeerConnection.id == peers.connection)
                    .values(status="removed")
                )
            else:
                actor = peers.sender if restriction == "sender_inactive" else peers.recipient
                await db.execute(update(User).where(User.id == actor).values(is_active=False))
            await db.commit()
    generate = AsyncMock()
    notify = AsyncMock()
    monkeypatch.setattr(runner, "notify_result", notify)
    result = await runner.run_delivery(row, generate)
    assert result.startswith("cancelled_")
    generate.assert_not_awaited()
    assert await _archive_count(async_engine, row.id) == 0
    async with AsyncSession(async_engine) as db:
        current = await db.get(PeerMessage, row.id)
        assert current is not None and current.status == "cancelled"
    notify.assert_awaited_once_with(row, result)


async def test_prepared_text_cannot_be_rewritten_or_resurrected_after_expiry(
    async_engine: AsyncEngine, peers: Peers
) -> None:
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import update

    from src.domains.peers.delivery_repository import PeerDeliveryRepository, claim_of
    from src.domains.peers.repository import PeersRepository

    row = await _claimed_delivery(async_engine, peers)
    claim = claim_of(row)
    async with AsyncSession(async_engine) as db:
        repo = PeerDeliveryRepository(db)
        assert await repo.start_generation(claim)
        assert not await repo.start_generation(claim)
        assert await repo.store_prepared(claim, "Original")
        assert not await repo.store_prepared(claim, "Replacement")
        await db.execute(
            update(PeerMessage)
            .where(PeerMessage.id == row.id)
            .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
        assert await PeersRepository(db).purge_expired_message_texts(now=datetime.now(UTC)) == 1
        assert not await repo.store_prepared(claim, "Resurrected")
        await db.commit()
    async with AsyncSession(async_engine) as db:
        current = await db.get(PeerMessage, row.id)
        assert current is not None and current.prepared_text_encrypted is None


async def test_operator_revocation_after_generation_blocks_the_archive(
    async_engine: AsyncEngine, peers: Peers, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.domains.peers.delivery_repository import claim_of
    from src.infrastructure.scheduler.peer_delivery_archive import commit_delivery

    row = await _claimed_delivery(async_engine, peers)
    monkeypatch.setattr(settings, "peers_enabled", False)
    assert await commit_delivery(row, claim_of(row), "Must not be sent") == "cancelled_disabled"
    assert await _archive_count(async_engine, row.id) == 0


async def test_delivery_claim_migration_preserves_records_and_closes_uncertain_work(
    async_engine: AsyncEngine, peers: Peers
) -> None:
    import importlib.util
    from pathlib import Path

    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import Connection, inspect

    from src.domains.peers.delivery_repository import PeerDeliveryRepository, claim_of

    row = await _claimed_delivery(async_engine, peers)
    async with AsyncSession(async_engine) as db:
        assert await PeerDeliveryRepository(db).start_generation(claim_of(row))
        await db.commit()
    path = (
        Path(__file__).resolve().parents[2]
        / "alembic/versions/2026_11_09_0500-d94b62a10e73_peer_delivery_claims.py"
    )
    spec = importlib.util.spec_from_file_location("peer_claim_migration", path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    def cycle(connection: Connection) -> None:
        with Operations.context(MigrationContext.configure(connection)):
            migration.downgrade()
            assert "claim_token" not in {
                column["name"] for column in inspect(connection).get_columns("peer_messages")
            }
            state = connection.execute(
                text("SELECT status, content FROM peer_messages WHERE id=:id"), {"id": row.id}
            ).one()
            assert state.status == "failed" and state.content == "one delivery"
            # Model an old version's uncertain active worker at upgrade time.
            connection.execute(
                text("UPDATE peer_messages SET status='delivering' WHERE id=:id"), {"id": row.id}
            )
            migration.upgrade()
        state = connection.execute(
            text(
                "SELECT status, last_error, claim_generation, generation_started FROM peer_messages WHERE id=:id"
            ),
            {"id": row.id},
        ).one()
        assert state.status == "failed" and state.last_error == "generation_outcome_unknown"
        assert state.claim_generation == 0 and state.generation_started is False

    async with async_engine.begin() as connection:
        await connection.run_sync(cycle)
