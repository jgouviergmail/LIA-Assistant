"""Only consenting participants see boards; public cabinet hints disclose no game content."""

import pytest

from src.domains.world.game_projection import project_games
from src.domains.world.policy import WorldPolicy
from tests.unit.domains.world.test_games import human_table, run

pytestmark = pytest.mark.unit


def test_nonparticipant_or_blocked_view_never_contains_board_or_player_identity() -> None:
    state, (host, guest, outsider) = human_table()
    policy = WorldPolicy("fr", frozenset(), host.eligible)
    availability, game, request = project_games(
        state, outsider.account, outsider.controller, policy, 100
    )
    assert game is None and request is None
    assert len(availability) == 3
    assert "board" not in str(availability) and host.account not in str(availability)
    blocked = WorldPolicy("fr", frozenset({guest.account}), host.eligible)
    _, game, _ = project_games(state, host.account, host.controller, blocked, 100)
    assert game is None


def test_controller_takeover_sees_explicit_rejoin_without_inheriting_move_permission() -> None:
    state, (host, _, _) = human_table()
    state.actors[host.account].controller = "replacement"
    policy = WorldPolicy("fr", frozenset(), host.eligible)
    _, game, _ = project_games(state, host.account, "replacement", policy, 100)
    assert game is not None and game.needs_rejoin and game.legal_moves == []
    encoded = game.model_dump_json()
    assert host.account not in encoded and "controller" not in encoded


def test_pending_request_is_not_a_board_participant_and_host_sees_only_public_alias() -> None:
    from tests.unit.domains.world.test_games import setup

    state, (host, guest, _) = setup()
    run(state, host, "start_computer")
    run(state, guest, "request")
    policy = WorldPolicy("fr", frozenset(), host.eligible)
    _, game, request = project_games(state, guest.account, guest.controller, policy, 100)
    assert game is None and request is not None and request.expires_at == 120
    _, game, _ = project_games(state, host.account, host.controller, policy, 100)
    assert game is not None and game.pending is not None
    assert game.pending.alias == state.actors[guest.account].alias
    assert guest.account not in game.model_dump_json()


@pytest.mark.parametrize("visibility", ["hidden", "noncontrolling", "expired", "missing"])
def test_no_game_payload_without_current_visible_admission(visibility: str) -> None:
    state, (host, _, _) = human_table()
    actor = state.actors[host.account]
    if visibility == "hidden":
        actor.visible = False
    elif visibility == "noncontrolling":
        actor.controller = "successor"
    elif visibility == "expired":
        actor.expires_at = 99
    else:
        state.actors.pop(host.account)
    assert project_games(
        state, host.account, host.controller, WorldPolicy("fr", frozenset(), host.eligible), 100
    ) == ([], None, None)


def test_blocked_pending_requester_is_never_published_to_host() -> None:
    from tests.unit.domains.world.test_games import setup

    state, (host, guest, _) = setup()
    run(state, host, "wait")
    run(state, guest, "request")
    _, game, _ = project_games(
        state,
        host.account,
        host.controller,
        WorldPolicy("fr", frozenset({guest.account}), host.eligible),
        100,
    )
    assert game is not None and game.pending is None


def test_complete_declared_snapshot_budget_stays_below_strict_browser_frame_limit() -> None:
    from uuid import uuid4

    from src.domains.world.authority import Authority, Identity, Limits
    from src.domains.world.game_models import ReversiMove
    from src.domains.world.game_rules import new_game
    from src.domains.world.game_views import GamePlayerView, GameView
    from src.domains.world.receipt_models import GameOutcome, GameReceipt
    from src.domains.world.schemas import WorldState

    state, authority = WorldState(), Authority(Limits(capacity=10))
    for index in range(10):
        authority.join(state, Identity(str(uuid4()), "🌿" * 24, "fr"), str(index), 100)
    owner = next(iter(state.actors.values()))
    owner.receipts = [
        GameReceipt(
            seq=index + 1,
            outcome=GameOutcome(
                action_id=str(uuid4()),
                result="not_participant",
                round_id=str(uuid4()),
                revision=2**31 - 1,
            ),
        )
        for index in range(16)
    ]
    view = authority.project(state, owner.account_id, set(), 100, owner.controller)
    view.game = GameView(
        cabinet="arcade-reversi",
        round_id=str(uuid4()),
        revision=2**31 - 1,
        phase="playing_human",
        computer=False,
        position=new_game("reversi"),
        players=[
            GamePlayerView(id=actor.public_id, alias=actor.alias, number=index + 1)
            for index, actor in enumerate(list(state.actors.values())[:2])
        ],
        your_number=1,
        needs_rejoin=False,
        paused=False,
        turn_until=220,
        expires_at=1300,
        legal_moves=[ReversiMove(cell=cell) for cell in range(64)],
    )
    # Exercise the complete declared legal-control ceiling, even though a real
    # board's legal subset is smaller. Wide aliases stress UTF-8, not characters.
    assert len(view.model_dump_json().encode("utf-8")) <= 16 * 1024


@pytest.mark.parametrize("withdrawn", ["blocked", "ineligible"])
def test_a_policy_hidden_cabinet_reads_exactly_like_any_full_cabinet(withdrawn: str) -> None:
    from src.domains.world.game_views import CabinetView

    state, (host, guest, outsider) = human_table()
    cabinet = state.games["arcade-tic-tac-toe"].cabinet
    unrelated = WorldPolicy("fr", frozenset(), host.eligible)
    hints, _, _ = project_games(state, outsider.account, outsider.controller, unrelated, 100)
    full = next(hint for hint in hints if hint.cabinet == cabinet)
    # A full cabinet carries no round fence: there is nothing to join.
    assert full == CabinetView(cabinet=cabinet, availability="full")
    if withdrawn == "blocked":
        hidden = WorldPolicy("fr", frozenset({host.account}), host.eligible)
    else:
        hidden = WorldPolicy("fr", frozenset(), host.eligible - {guest.account})
    hints, game, request = project_games(state, outsider.account, outsider.controller, hidden, 100)
    assert next(hint for hint in hints if hint.cabinet == cabinet) == full
    assert game is None and request is None


def test_a_solo_table_of_someone_who_blocked_the_viewer_reads_full_not_withdrawn() -> None:
    from tests.unit.domains.world.test_games import setup

    state, (host, guest, _) = setup()
    run(state, host, "start_computer")
    cabinet = "arcade-tic-tac-toe"
    open_policy = WorldPolicy("fr", frozenset(), host.eligible)
    hints, _, _ = project_games(state, guest.account, guest.controller, open_policy, 100)
    joinable = next(hint for hint in hints if hint.cabinet == cabinet)
    assert joinable.availability == "joinable" and joinable.round_id is not None
    blocked = WorldPolicy("fr", frozenset({host.account}), host.eligible)
    hints, _, _ = project_games(state, guest.account, guest.controller, blocked, 100)
    hint = next(hint for hint in hints if hint.cabinet == cabinet)
    # Indistinguishable from a table whose seat a pending request already holds.
    assert hint.availability == "full" and hint.round_id is None and hint.revision == 0
