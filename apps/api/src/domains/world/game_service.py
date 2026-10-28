"""Session-bound game commands: distributed input cap, bounded search, locked fresh policy, pure CAS.

A command the distributed input cap or the disabled arcade refuses changes no
table: it consumes its sequence and records its receipt only, so it commits
without the native cookie revalidation, the canonical SQL policy lock or any
computer search. Everything that can change a table pays all three.
"""

import asyncio

from src.core.config import settings
from src.core.exceptions import AuthorizationError
from src.domains.world.configuration import (
    configured_arcade_enabled,
    configured_authority,
    configured_game_limits,
)
from src.domains.world.game_catalogue import CABINETS
from src.domains.world.game_commands import GameCommand
from src.domains.world.game_compute import prepare_bounded
from src.domains.world.game_context import GameScope
from src.domains.world.game_lifecycle import prune_games
from src.domains.world.game_policy import locked_game_scope
from src.domains.world.game_state import GameTable
from src.domains.world.games import apply_game_transition
from src.domains.world.policy import bound_user
from src.domains.world.receipt_models import GameOutcome, GameOutcomeKind
from src.domains.world.schemas import WorldState
from src.domains.world.store import WorldStore
from src.infrastructure.observability.metrics_world import (
    world_game_commands_total,
    world_game_compute_nodes,
)

_RATE = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then redis.call('PEXPIRE', KEYS[1], 1000) end
return count
"""


def participants(table: GameTable | None, account: str) -> frozenset[str]:
    """Derive only bounded interaction identities from the observed authoritative table.

    Args:
        table: Observed cabinet table, or None for an empty cabinet.
        account: The commanding account.

    Returns:
        The commanding account, the table's members and its pending requester.
    """
    if table is None:
        return frozenset({account})
    return frozenset(
        {
            account,
            *(member.account for member in table.members),
            *([table.pending.account] if table.pending else []),
        }
    )


def _duplicate(
    table: GameTable | None, account: str, controller: str, command: GameCommand
) -> bool:
    """Exact operation identity skips CPU work; the pure authority still verifies its full hash."""
    return table is not None and any(
        receipt.account == account
        and receipt.controller == controller
        and receipt.outcome.action_id == command.action_id
        for receipt in table.receipts
    )


async def _input_limit(store: WorldStore, account: str) -> GameOutcomeKind | None:
    """One distributed one-second account budget also fences additional sockets and workers."""
    async with asyncio.timeout(store.timeout):
        count = int(await store.redis.eval(_RATE, 1, f"{store.key}:game-rate:{account}"))
    if not configured_arcade_enabled():
        return "unavailable"
    return "rate_limited" if count > settings.world_arcade_input_rate else None


async def _commit_refusal(
    store: WorldStore, account: str, controller: str, command: GameCommand, refusal: GameOutcomeKind
) -> GameOutcome:
    """Consume the sequence and record a forced refusal without SQL, search or policy.

    The scope names only the commanding account as eligible, so the refusal never
    carries the round fence of a table someone else sits at: it cannot disclose a
    round its owner's policy would hide.
    """
    authority, scope = configured_authority(), GameScope(account, controller, frozenset({account}))

    def apply(current: WorldState, now: float) -> GameOutcome:
        """Replayed CAS callbacks never perform SQL, rate accounting or computer search."""
        if not configured_arcade_enabled():
            current.games.clear()
        authority.prune(current, now)
        return apply_game_transition(
            current, scope, command, now, configured_game_limits(), forced_result=refusal
        )

    _, outcome = await store.update(apply)
    return outcome


async def _commit_command(
    store: WorldStore, cookie: str, account: str, controller: str, command: GameCommand
) -> GameOutcome:
    """Revalidate the cookie, prepare bounded search, then commit under the canonical policy lock."""
    async with asyncio.timeout(settings.world_policy_timeout):
        user = await bound_user(cookie)
    if str(user.id) != account:
        raise AuthorizationError(detail={"error_code": "SESSION_UNAVAILABLE"})
    state, now = await store.read()
    authority = configured_authority()
    authority.prune(state, now)
    prune_games(state, now, configured_game_limits())
    table = state.games.get(command.cabinet)
    people = participants(table, account)
    prepared = (
        None
        if _duplicate(table, account, controller, command)
        else await prepare_bounded(state, GameScope(account, controller, people), command)
    )
    async with asyncio.timeout(settings.world_policy_timeout + store.timeout):
        async with locked_game_scope(account, controller, people) as scope:

            def apply(current: WorldState, now: float) -> GameOutcome:
                """Replayed CAS callbacks never perform SQL, rate accounting or computer search."""
                if not configured_arcade_enabled():
                    current.games.clear()
                authority.prune(current, now)
                return apply_game_transition(
                    current, scope, command, now, configured_game_limits(), prepared
                )

            _, outcome = await store.update(apply)
    if prepared is not None:
        world_game_compute_nodes.observe(prepared.nodes)
    return outcome


async def game_command(
    store: WorldStore, cookie: str, account: str, controller: str, command: GameCommand
) -> GameOutcome:
    """Never trust a supplied account, board, opponent identity, result or unsealed CPU answer.

    Args:
        store: Scene-scoped authority store.
        cookie: The socket's native session cookie.
        account: The socket's authenticated account.
        controller: The socket's controller generation.
        command: The validated game command.

    Returns:
        The authoritative outcome recorded under the command's sequence.

    Raises:
        AuthorizationError: The cookie no longer authenticates this account, or the
            account or World capability was revoked.
        WorldUnavailable: The authority cannot commit (contention, size).
        WorldIntegrityError: The transition produced an invalid record (a defect).
        TimeoutError: A policy or authority deadline expired.
    """
    refusal = await _input_limit(store, account)
    if refusal is not None:
        outcome = await _commit_refusal(store, account, controller, command, refusal)
    else:
        outcome = await _commit_command(store, cookie, account, controller, command)
    world_game_commands_total.labels(
        game=CABINETS[command.cabinet].game, outcome=outcome.result
    ).inc()
    return outcome
