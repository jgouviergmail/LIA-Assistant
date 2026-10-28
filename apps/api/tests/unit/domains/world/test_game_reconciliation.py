"""Policy refreshes withdraw observed revocations without erasing newly admitted, unobserved peers."""

import pytest

from src.domains.world.game_context import GameLimits
from src.domains.world.game_reconciliation import reconcile_game_policy
from src.domains.world.policy import WorldPolicy
from tests.unit.domains.world.test_games import CABINET, human_table, run, setup

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("revocation", ["inactive", "blocked"])
def test_native_revocation_ends_round_without_attributing_or_awarding_a_winner(
    revocation: str,
) -> None:
    state, (host, guest, _) = human_table()
    eligible = host.eligible - ({guest.account} if revocation == "inactive" else set())
    blocked = frozenset({guest.account}) if revocation == "blocked" else frozenset()
    reconcile_game_policy(
        state,
        host.account,
        WorldPolicy("fr", blocked, eligible),
        set(host.eligible),
        101,
        GameLimits(),
    )
    table = state.games[CABINET]
    assert table.reason == "unavailable" and table.winner is None
    assert (
        guest.account not in {member.account for member in table.members}
        if revocation == "inactive"
        else table.phase == "finished"
    )
    if revocation == "blocked":
        assert table.members == []  # Hidden boards must not retain invisible reservations.


def test_old_policy_snapshot_cannot_remove_an_unobserved_new_game_participant() -> None:
    state, (host, guest, _) = human_table()
    reconcile_game_policy(
        state,
        host.account,
        WorldPolicy("fr", frozenset(), frozenset({host.account})),
        {host.account},
        101,
        GameLimits(),
    )
    assert state.games[CABINET].phase == "playing_human"
    assert any(member.account == guest.account for member in state.games[CABINET].members)


def test_blocked_request_is_withdrawn_without_abandoning_host_lobby() -> None:
    state, (host, guest, _) = setup()
    run(state, host, "wait")
    run(state, guest, "request")
    reconcile_game_policy(
        state,
        host.account,
        WorldPolicy("fr", frozenset({guest.account}), host.eligible),
        set(host.eligible),
        101,
        GameLimits(),
    )
    assert state.games[CABINET].pending is None and state.games[CABINET].phase == "waiting"
