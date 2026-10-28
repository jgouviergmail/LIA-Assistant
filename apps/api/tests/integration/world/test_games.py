"""Real independent SQL/Redis transactions qualify native cabinet policy and durable suspension."""

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from src.core.config import settings
from src.core.exceptions import BaseAPIException
from src.domains.peers.service import PeersService
from src.domains.system_settings.models import SystemSetting, SystemSettingKey
from src.domains.users.models import User
from src.domains.world import policy as policy_module
from src.domains.world.authority import Identity
from src.domains.world.game_catalogue import CABINETS
from src.domains.world.game_commands import GameCommand
from src.domains.world.game_models import CabinetId
from src.domains.world.game_policy import locked_game_scope
from src.domains.world.game_service import game_command
from src.domains.world.lifecycle import purge_world_account
from src.domains.world.policy import WorldPolicy
from src.domains.world.schemas import WorldState
from src.domains.world.service import WorldConnection, WorldService
from src.domains.world.store import WorldStore
from src.infrastructure.cache.session_store import SessionStore

pytestmark = pytest.mark.integration
CABINET: CabinetId = "arcade-tic-tac-toe"


@dataclass
class GameEnvironment:
    service: WorldService
    connections: list[WorldConnection]
    cookies: list[str]

    async def command(self, index: int, action: str, seq: int, **changes: object) -> GameCommand:
        state, _ = await self.service.store.read()
        table = state.games.get(CABINET)
        return GameCommand.model_validate(
            {
                "version": 2,
                "type": "game",
                "epoch": state.epoch,
                "seq": seq,
                "cabinet": CABINET,
                "action_id": str(uuid4()),
                "action": action,
                "round_id": table.round_id if table else None,
                "expected_revision": table.revision if table else 0,
                **changes,
            }
        )

    async def send(self, index: int, command: GameCommand):
        connection = self.connections[index]
        return await game_command(
            self.service.store,
            self.cookies[index],
            connection.identity.account_id,
            connection.controller,
            command,
        )


@pytest.fixture
async def games(
    async_engine: AsyncEngine,
    redis_world: Redis,
    committed_user_ids: list[UUID],
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[GameEnvironment]:
    monkeypatch.setattr(settings, "world_enabled", True)
    monkeypatch.setattr(settings, "world_arcade_enabled", True)
    monkeypatch.setattr(settings, "world_arcade_input_rate", 10)

    async def sessions() -> Redis:
        return redis_world

    monkeypatch.setattr(policy_module, "get_redis_session", sessions)
    factory = async_sessionmaker(async_engine, expire_on_commit=False)
    async with factory() as db:
        users = [
            User(
                email=f"arcade-{uuid4().hex}@example.invalid",
                full_name=f"Player {index}",
                is_active=True,
                language="fr",
            )
            for index in range(3)
        ]
        db.add_all(users)
        await db.flush()
        committed_user_ids.extend(user.id for user in users)
        await db.commit()
    store = WorldStore(redis_world, namespace=f"game-test-{uuid4().hex}", ttl=60, timeout=3)
    service = WorldService(store)
    session_store = SessionStore(redis_world)
    cookies = [(await session_store.create_session(str(user.id))).session_id for user in users]
    connections = [
        await service.enter(Identity(str(user.id), f"Player {index}", "fr"), None)
        for index, user in enumerate(users)
    ]

    def place(state: WorldState, now: float) -> None:
        for actor in state.actors.values():
            actor.position = CABINETS[CABINET].approach.copy()

    await store.update(place)
    try:
        yield GameEnvironment(service, connections, cookies)
    finally:
        await redis_world.delete(store.key, *(f"{store.key}:game-rate:{user.id}" for user in users))
        for cookie in cookies:
            await session_store.delete_session(cookie)


async def test_competing_lobby_claims_commit_exactly_one_owner(games: GameEnvironment) -> None:
    first, second = await games.command(0, "wait", 1), await games.command(1, "wait", 1)
    results = await asyncio.gather(games.send(0, first), games.send(1, second))
    assert sorted(result.result for result in results) == ["accepted", "conflict"]
    state, _ = await games.service.store.read()
    assert len(state.games[CABINET].members) == 1


async def test_real_redis_exact_duplicate_move_and_private_projection(
    games: GameEnvironment,
) -> None:
    assert (await games.send(0, await games.command(0, "start_computer", 1))).result == "accepted"
    move = await games.command(0, "move", 2, move={"game": "tic_tac_toe", "cell": 0})
    first = await games.send(0, move)
    assert first.result == "accepted" and await games.send(0, move) == first
    state, _ = await games.service.store.read()
    assert (
        state.games[CABINET].position.board.count(1)
        == state.games[CABINET].position.board.count(2)
        == 1
    )
    accounts = frozenset(state.actors)
    view = await games.service.view(games.connections[2], WorldPolicy("fr", frozenset(), accounts))
    assert view.game is None and view.game_request is None and len(view.cabinets) == 3
    assert "board" not in view.model_dump_json()


async def start_humans(games: GameEnvironment) -> None:
    assert (await games.send(0, await games.command(0, "wait", 1))).result == "accepted"
    assert (await games.send(1, await games.command(1, "request", 1))).result == "accepted"
    assert (await games.send(0, await games.command(0, "accept", 2))).result == "accepted"


async def test_disconnect_anchor_and_remaining_turn_are_durably_saved(
    games: GameEnvironment,
) -> None:
    await start_humans(games)
    await games.service.disconnect(games.connections[1])
    state, _ = await games.service.store.read()
    table = state.games[CABINET]
    assert table.paused_at is not None and table.remaining_turn is not None
    anchor = (table.paused_at, table.remaining_turn, table.members[1].offline_until, table.revision)
    policy = WorldPolicy("fr", frozenset(), frozenset(state.actors))
    for _ in range(2):
        view = await games.service.view(games.connections[0], policy)
        assert view.game is not None and view.game.paused
    state, _ = await games.service.store.read()
    table = state.games[CABINET]
    assert (
        table.paused_at,
        table.remaining_turn,
        table.members[1].offline_until,
        table.revision,
    ) == anchor


async def test_block_committed_before_move_prevents_contact_and_never_awards_win(
    games: GameEnvironment, async_engine: AsyncEngine
) -> None:
    await start_humans(games)
    move = await games.command(0, "move", 3, move={"game": "tic_tac_toe", "cell": 0})
    factory = async_sessionmaker(async_engine, expire_on_commit=False)
    async with factory() as db:
        await PeersService(db).block_peer(
            UUID(games.connections[1].identity.account_id),
            UUID(games.connections[0].identity.account_id),
        )
        await db.commit()
    assert (await games.send(0, move)).result == "unavailable"
    state, _ = await games.service.store.read()
    table = state.games[CABINET]
    assert (
        table.position.board == (0,) * 9 and table.winner is None and table.reason == "unavailable"
    )
    assert table.members == []
    other = "arcade-four-in-row"
    await games.service.store.update(
        lambda current, now: setattr(
            current.actors[games.connections[0].identity.account_id],
            "position",
            CABINETS[other].approach.copy(),
        )
    )
    next_game = await games.command(0, "wait", 4, cabinet=other, round_id=None, expected_revision=0)
    assert (await games.send(0, next_game)).result == "accepted"


async def test_disabled_arcade_withdraws_games_preserving_world_admission(
    games: GameEnvironment, monkeypatch: pytest.MonkeyPatch
) -> None:
    await start_humans(games)
    monkeypatch.setattr(settings, "world_arcade_enabled", False)
    state, _ = await games.service.store.read()
    view = await games.service.view(
        games.connections[0], WorldPolicy("fr", frozenset(), frozenset(state.actors))
    )
    state, _ = await games.service.store.read()
    assert (
        not state.games
        and len(state.actors) == 3
        and view.status == "active"
        and view.cabinets == []
    )


async def test_concurrent_second_slot_and_moves_have_exactly_one_effect(
    games: GameEnvironment,
) -> None:
    await games.send(0, await games.command(0, "wait", 1))
    requests = [await games.command(index, "request", 1) for index in (1, 2)]
    results = await asyncio.gather(
        *(games.send(index, intent) for index, intent in zip((1, 2), requests, strict=True))
    )
    assert sorted(result.result for result in results) == ["accepted", "conflict"]
    await games.send(0, await games.command(0, "accept", 2))
    moves = [
        await games.command(0, "move", 3, move={"game": "tic_tac_toe", "cell": cell})
        for cell in (0, 1)
    ]
    second = WorldService(games.service.store)
    connection = games.connections[0]
    results = await asyncio.gather(
        games.send(0, moves[0]),
        game_command(
            second.store,
            games.cookies[0],
            connection.identity.account_id,
            connection.controller,
            moves[1],
        ),
    )
    assert sorted(result.result for result in results) == ["accepted", "conflict"]
    state, _ = await games.service.store.read()
    assert state.games[CABINET].position.board.count(1) == 1


async def test_unrelated_scene_revision_does_not_conflict_with_game_revision(
    games: GameEnvironment,
) -> None:
    await start_humans(games)
    intent = await games.command(0, "move", 3, move={"game": "tic_tac_toe", "cell": 0})
    await games.service.store.update(
        lambda state, now: setattr(
            state.actors[games.connections[2].identity.account_id], "facing", 2
        )
    )
    assert (await games.send(0, intent)).result == "accepted"


async def test_game_policy_serializes_both_block_directions_on_independent_sql_connections(
    games: GameEnvironment, async_engine: AsyncEngine
) -> None:
    first, second = (UUID(connection.identity.account_id) for connection in games.connections[:2])
    controller, peers = games.connections[0].controller, frozenset({str(second)})
    factory = async_sessionmaker(async_engine, expire_on_commit=False)
    for blocker, blocked in ((first, second), (second, first)):
        # Each direction starts unblocked, so its own block is what the scope reads.
        async with locked_game_scope(str(first), controller, peers) as scope:
            assert str(second) not in scope.blocked
            async with factory() as writer:
                await writer.execute(text("SET LOCAL lock_timeout = '100ms'"))
                with pytest.raises(DBAPIError) as waiting:
                    await PeersService(writer).block_peer(blocker, blocked)
                assert getattr(waiting.value.orig, "sqlstate", None) == "55P03"
                await writer.rollback()
        async with factory() as writer:
            await PeersService(writer).block_peer(blocker, blocked)
            await writer.commit()
        async with locked_game_scope(str(first), controller, peers) as scope:
            assert str(second) in scope.blocked
        async with factory() as writer:
            assert await PeersService(writer).unblock_peer(blocker, blocked)
            await writer.commit()


async def test_the_game_fence_orders_policy_writers_never_a_reference_to_the_accounts(
    games: GameEnvironment, async_engine: AsyncEngine
) -> None:
    from sqlalchemy import delete

    from src.domains.peers.models import PeerBlock

    first, second, third = (UUID(item.identity.account_id) for item in games.connections)
    factory = async_sessionmaker(async_engine, expire_on_commit=False)
    async with locked_game_scope(
        str(first), games.connections[0].controller, frozenset({str(second)})
    ):
        async with factory() as writer:
            await writer.execute(text("SET LOCAL lock_timeout = '150ms'"))
            # A row merely referencing a fenced account (FOR KEY SHARE) never waits.
            writer.add(PeerBlock(blocker_id=third, blocked_id=first))
            await writer.flush()
            # An UPDATE of a fenced account still waits for the commit to end.
            with pytest.raises(DBAPIError) as waiting:
                await writer.execute(
                    text("UPDATE users SET full_name = full_name WHERE id = :id"), {"id": second}
                )
            assert getattr(waiting.value.orig, "sqlstate", None) == "55P03"
            await writer.rollback()
    async with factory() as cleanup:
        await cleanup.execute(delete(PeerBlock).where(PeerBlock.blocker_id == third))
        await cleanup.commit()


async def test_a_join_after_a_real_solo_rematch_commits_a_canonical_human_board(
    games: GameEnvironment,
) -> None:
    from src.domains.world.game_rules import legal_moves

    host_seq = 1
    assert (await games.send(0, await games.command(0, "start_computer", host_seq))).result == (
        "accepted"
    )
    while (await games.service.store.read())[0].games[CABINET].phase == "playing_computer":
        state, _ = await games.service.store.read()
        host_seq += 1
        move = legal_moves(state.games[CABINET].position)[0].model_dump()
        intent = await games.command(0, "move", host_seq, move=move)
        assert (await games.send(0, intent)).result == "accepted"
    host_seq += 1
    assert (await games.send(0, await games.command(0, "rematch", host_seq))).result == "accepted"
    assert (await games.service.store.read())[0].games[CABINET].members[0].number == 2
    assert (await games.send(1, await games.command(1, "request", 1))).result == "accepted"
    host_seq += 1
    assert (await games.send(0, await games.command(0, "accept", host_seq))).result == "accepted"
    raw = await games.service.store.redis.get(games.service.store.key)
    table = WorldStore.decode(raw).games[CABINET]
    host, guest = (connection.identity.account_id for connection in games.connections[:2])
    assert table.phase == "playing_human"
    assert [(member.account, member.number) for member in table.members] == [(host, 1), (guest, 2)]


async def test_startup_disabled_cleanup_prevents_later_match_revival(
    games: GameEnvironment, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.domains.world import configuration
    from src.infrastructure.startup import caches

    await start_humans(games)

    async def redis() -> Redis:
        return games.service.store.redis

    monkeypatch.setattr(caches, "get_redis_cache", redis)
    monkeypatch.setattr(configuration, "configured_store", lambda _: games.service.store)
    monkeypatch.setattr(settings, "world_arcade_enabled", False)
    await caches.withdraw_disabled_world_games()
    monkeypatch.setattr(settings, "world_arcade_enabled", True)
    state, _ = await games.service.store.read()
    assert not state.games and len(state.actors) == 3


async def test_lost_ack_after_real_exec_never_repeats_a_move(
    games: GameEnvironment, monkeypatch: pytest.MonkeyPatch
) -> None:
    await start_humans(games)
    intent = await games.command(0, "move", 3, move={"game": "tic_tac_toe", "cell": 0})
    update = games.service.store.update

    async def lost_ack(transition):
        await update(transition)
        raise asyncio.CancelledError

    monkeypatch.setattr(games.service.store, "update", lost_ack)
    with pytest.raises(asyncio.CancelledError):
        await games.send(0, intent)
    monkeypatch.setattr(games.service.store, "update", update)
    assert (await games.send(0, intent)).result == "accepted"
    state, _ = await games.service.store.read()
    assert state.games[CABINET].position.board.count(1) == 1


async def test_actual_account_erasure_removes_game_only_receipts_and_rate_keys(
    games: GameEnvironment,
) -> None:
    await start_humans(games)
    account = games.connections[1].identity.account_id

    def lose_actor(state: WorldState, now: float) -> None:
        state.actors.pop(account)
        state.presences.pop(account)

    await games.service.store.update(lose_actor)
    await games.service.store.redis.set(
        f"{games.service.store.key}:game-rate:{account}", 1, px=60000
    )
    assert await games.service.store.redis.exists(f"{games.service.store.key}:game-rate:{account}")
    await purge_world_account(games.service.store.redis, account)
    state, _ = await games.service.store.read()
    table = state.games[CABINET]
    assert (
        account not in table.model_dump_json()
        and table.reason == "unavailable"
        and table.winner is None
    )
    assert not await games.service.store.redis.exists(
        f"{games.service.store.key}:game-rate:{account}"
    )


async def test_live_world_revocation_withdraws_contact_and_cannot_restore_old_round(
    games: GameEnvironment, async_engine: AsyncEngine
) -> None:
    from sqlalchemy import delete

    await start_humans(games)
    factory = async_sessionmaker(async_engine, expire_on_commit=False)
    switch = SystemSetting(key=SystemSettingKey.CAPABILITY_WORLD_ENABLED, value="false")
    async with factory() as db:
        db.add(switch)
        await db.commit()
    try:
        with pytest.raises(BaseAPIException):
            await games.send(
                0, await games.command(0, "move", 3, move={"game": "tic_tac_toe", "cell": 0})
            )
        # The real socket's native-revocation branch invokes this same atomic boundary.
        await games.service.revoke(games.connections[0])
        state, _ = await games.service.store.read()
        assert state.games[CABINET].reason == "unavailable" and state.games[CABINET].winner is None
    finally:
        async with factory() as db:
            await db.execute(delete(SystemSetting).where(SystemSetting.id == switch.id))
            await db.commit()


async def test_a_cookie_from_another_account_cannot_mutate_the_claimed_game(
    games: GameEnvironment,
) -> None:
    intent = await games.command(0, "wait", 1)
    owner = games.connections[0]
    with pytest.raises(BaseAPIException):
        await game_command(
            games.service.store,
            games.cookies[1],
            owner.identity.account_id,
            owner.controller,
            intent,
        )
    assert not (await games.service.store.read())[0].games


async def test_distributed_game_budget_refuses_before_cpu_or_new_reservation(
    games: GameEnvironment, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.domains.world import game_service

    monkeypatch.setattr(settings, "world_arcade_input_rate", 1)
    assert (await games.send(0, await games.command(0, "start_computer", 1))).result == "accepted"
    owner = games.connections[0].identity.account_id
    await games.service.store.redis.set(f"{games.service.store.key}:game-rate:{owner}", 1, px=60000)

    async def forbidden(*args: object) -> None:
        pytest.fail("rate-limited intent must not prepare computer work")

    def unlocked(*args: object) -> None:
        pytest.fail("a refusal changes no table: it must not take the canonical SQL fence")

    monkeypatch.setattr(game_service, "prepare_bounded", forbidden)
    # Neither the native cookie revalidation nor the SQL policy fence is paid for it.
    monkeypatch.setattr(game_service, "bound_user", forbidden)
    monkeypatch.setattr(game_service, "locked_game_scope", unlocked)
    outcome = await games.send(
        0, await games.command(0, "move", 2, move={"game": "tic_tac_toe", "cell": 0})
    )
    assert outcome.result == "rate_limited"
    state, _ = await games.service.store.read()
    assert state.games[CABINET].position.board == (0,) * 9
    owner_actor = state.actors[owner]
    assert owner_actor.seq == 2 and owner_actor.receipts[-1].kind == "game"


@pytest.mark.parametrize("revocation", ["deactivated", "deleted"])
async def test_peer_revoked_after_observation_cannot_receive_a_legal_move(
    games: GameEnvironment, async_engine: AsyncEngine, revocation: str
) -> None:
    from datetime import UTC, datetime

    await start_humans(games)
    intent = await games.command(0, "move", 3, move={"game": "tic_tac_toe", "cell": 0})
    factory = async_sessionmaker(async_engine, expire_on_commit=False)
    async with factory() as db:
        peer = await db.get(User, UUID(games.connections[1].identity.account_id))
        assert peer is not None
        if revocation == "deactivated":
            peer.is_active = False
        else:
            peer.deleted_at = datetime.now(UTC)
        await db.commit()
    assert (await games.send(0, intent)).result == "unavailable"
    state, _ = await games.service.store.read()
    assert state.games[CABINET].winner is None and state.games[CABINET].reason == "unavailable"
