"""Monotonic withdrawal on fresh native revocation; a stale read can never restore contact."""

from src.domains.world.game_context import GameLimits
from src.domains.world.game_lifecycle import finish_game
from src.domains.world.game_state import GameTable
from src.domains.world.policy import WorldPolicy
from src.domains.world.schemas import WorldState


def _withdraw_request(table: GameTable, own: bool, policy: WorldPolicy, invalid: set[str]) -> None:
    """No old invitation survives a positively observed revocation or mutual block."""
    pending = table.pending
    if pending is not None and (
        pending.account in invalid or (own and pending.account in policy.blocked)
    ):
        table.pending = None
        table.revision += 1


def reconcile_game_policy(
    state: WorldState,
    account: str,
    policy: WorldPolicy,
    observed: set[str],
    now: float,
    limits: GameLimits,
) -> None:
    """Withdraw invalid admissions globally and mutual blocks only for this policy owner.

    Args:
        state: Watched authority snapshot, mutated in place.
        account: Owner of the freshly read policy.
        policy: That owner's eligibility and block policy.
        observed: Accounts the policy was read for; those it no longer lists as
            eligible were revoked.
        now: Redis Unix time of the commit.
        limits: Effective result deadline for a round the withdrawal ends.
    """
    invalid = observed - policy.eligible
    for table in state.games.values():
        missing = any(member.account in invalid for member in table.members)
        own = any(member.account == account for member in table.members)
        blocked = own and any(member.account in policy.blocked for member in table.members)
        if (missing and table.phase not in {"finished", "empty"}) or blocked:
            table.members = [member for member in table.members if member.account not in invalid]
            finish_game(table, "unavailable", now, limits)
            if blocked:
                table.members = []
            table.revision += 1
        _withdraw_request(table, own, policy, invalid)
