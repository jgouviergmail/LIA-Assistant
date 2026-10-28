"""Selective game erasure includes member, request and receipt-only ownership."""

from src.domains.world.game_context import GameLimits
from src.domains.world.game_lifecycle import finish_game
from src.domains.world.game_state import GameTable
from src.domains.world.schemas import WorldState


def _table_has_account(table: GameTable, account: str) -> bool:
    """Inspect every bounded private identity carrier, even after its actor has disappeared."""
    return (
        any(member.account == account for member in table.members)
        or (table.pending is not None and table.pending.account == account)
        or any(receipt.account == account for receipt in table.receipts)
        or account in table.rematch
    )


def has_game_account(state: WorldState, account: str) -> bool:
    """Return whether the current scene still carries this account in any game record.

    Args:
        state: Authority to inspect.
        account: Account being erased.

    Returns:
        Whether a membership, request, consent or receipt still names it.
    """
    return any(_table_has_account(table, account) for table in state.games.values())


def purge_game_account(state: WorldState, account: str, now: float, limits: GameLimits) -> None:
    """Erase only the owner and withdraw contact generically; peer receipts/epoch/boards remain bounded.

    Args:
        state: Watched authority snapshot, mutated in place.
        account: Account being erased.
        now: Redis Unix time of the commit.
        limits: Effective result deadline for a round the erasure ends.
    """
    for table in state.games.values():
        if not _table_has_account(table, account):
            continue
        member = any(member.account == account for member in table.members)
        table.members = [member for member in table.members if member.account != account]
        table.receipts = [receipt for receipt in table.receipts if receipt.account != account]
        table.rematch = [owner for owner in table.rematch if owner != account]
        if table.pending is not None and table.pending.account == account:
            table.pending = None
        if member:
            finish_game(table, "unavailable", now, limits)
            if not table.members:
                table.phase = "empty"
        table.revision += 1
