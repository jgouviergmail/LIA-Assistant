"""Pure cabinet lifecycle, player consent, revision fencing and bounded receipt semantics."""

from uuid import uuid4

import pytest

from src.domains.world.authority import Authority, Identity, Limits
from src.domains.world.game_catalogue import CABINETS
from src.domains.world.game_commands import GameCommand
from src.domains.world.game_context import GameLimits, GameScope
from src.domains.world.game_lifecycle import prune_games
from src.domains.world.game_models import CabinetId, TicTacToeMove
from src.domains.world.games import apply_game_transition
from src.domains.world.receipt_models import GameOutcome
from src.domains.world.schemas import WorldState
from src.domains.world.store import WorldStore

pytestmark = pytest.mark.unit
CABINET: CabinetId = "arcade-tic-tac-toe"


def setup() -> tuple[WorldState, list[GameScope]]:
    state, authority = WorldState(), Authority(Limits())
    people = []
    for index in range(3):
        account = str(uuid4())
        authority.join(state, Identity(account, f"Player {index}", "fr"), str(index), 100)
        state.actors[account].position = CABINETS[CABINET].approach.copy()
        people.append(GameScope(account, str(index), frozenset({account})))
    eligible = frozenset(state.actors)
    return state, [GameScope(person.account, person.controller, eligible) for person in people]


def command(state: WorldState, action: str, seq: int = 1, **changes: object) -> GameCommand:
    table = state.games.get(CABINET)
    return GameCommand.model_validate(
        {
            "type": "game",
            "version": 2,
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


def run(
    state: WorldState,
    scope: GameScope,
    action: str,
    seq: int = 1,
    now: float = 100,
    limits: GameLimits | None = None,
    **changes: object,
) -> GameOutcome:
    outcome = apply_game_transition(
        state, scope, command(state, action, seq, **changes), now, limits or GameLimits()
    )
    # The real store validates complete post-transition state before EXEC.
    WorldStore.decode(state.model_dump_json())
    return outcome


def test_wait_request_explicit_consent_capacity_and_fresh_human_round() -> None:
    state, (host, guest, third) = setup()
    assert run(state, host, "wait").result == "accepted"
    first = state.games[CABINET].round_id
    assert run(state, guest, "request").result == "accepted"
    assert len(state.games[CABINET].members) == 1
    assert run(state, third, "request").result == "full"
    assert run(state, guest, "accept", 2).result == "not_participant"
    assert run(state, host, "accept", 2).result == "accepted"
    table = state.games[CABINET]
    assert table.phase == "playing_human" and len(table.members) == 2
    assert table.round_id != first and table.position.board == (0,) * 9
    assert run(state, third, "request", 2).result == "full"


def test_idempotency_round_revision_and_invalid_moves_never_double_apply() -> None:
    state, (host, guest, _) = setup()
    run(state, host, "wait")
    run(state, guest, "request")
    run(state, host, "accept", 2)
    move = command(state, "move", 3, move=TicTacToeMove(cell=0).model_dump())
    first = apply_game_transition(state, host, move, 101, GameLimits())
    assert first.result == "accepted"
    assert apply_game_transition(state, host, move, 101.1, GameLimits()) == first
    assert state.games[CABINET].position.board.count(1) == 1
    changed = move.model_copy(update={"move": TicTacToeMove(cell=1)})
    assert (
        apply_game_transition(state, host, changed, 101.2, GameLimits()).result == "action_reused"
    )
    stale = command(state, "move", 2, expected_revision=0, move=TicTacToeMove(cell=1).model_dump())
    assert apply_game_transition(state, guest, stale, 101.3, GameLimits()).result == "conflict"
    assert (
        run(state, host, "move", 4, move=TicTacToeMove(cell=1).model_dump()).result == "wrong_turn"
    )


def test_lobby_and_join_deadlines_do_not_reserve_capacity_forever() -> None:
    state, (host, guest, _) = setup()
    run(state, host, "wait")
    run(state, guest, "request")
    prune_games(state, 121, GameLimits())
    assert state.games[CABINET].pending is None
    # Keep native actor leases alive; the independently bounded lobby still expires.
    for actor in state.actors.values():
        actor.expires_at = 1000
    for presence in state.presences.values():
        presence.expires_at = 1000
    prune_games(state, 161, GameLimits())
    assert CABINET not in state.games


def human_table(limits: GameLimits | None = None) -> tuple[WorldState, list[GameScope]]:
    state, people = setup()
    run(state, people[0], "wait", limits=limits)
    run(state, people[1], "request", limits=limits)
    run(state, people[0], "accept", 2, limits=limits)
    return state, people


def test_transport_pause_restores_remaining_turn_instead_of_resetting_or_extending_grace() -> None:
    state, (host, guest, _) = human_table()
    presence = state.presences.pop(guest.account)
    prune_games(state, 105, GameLimits())
    table = state.games[CABINET]
    assert table.remaining_turn == 115
    assert table.members[1].offline_until == 135
    prune_games(state, 110, GameLimits())
    assert table.remaining_turn == 115 and table.members[1].offline_until == 135
    state.presences[guest.account] = presence
    prune_games(state, 115, GameLimits())
    assert table.paused_at is None and table.turn_until == 230
    assert (
        run(state, host, "move", 3, now=116, move=TicTacToeMove(cell=0).model_dump()).result
        == "accepted"
    )


def test_replacement_controller_requires_explicit_rejoin_within_the_original_grace() -> None:
    state, (_, guest, _) = human_table()
    Authority(Limits()).takeover(state, guest.account, "replacement", 101)
    replacement = GameScope(guest.account, "replacement", guest.eligible)
    prune_games(state, 101, GameLimits())
    assert (
        run(state, replacement, "move", 2, now=102, move=TicTacToeMove(cell=1).model_dump()).result
        == "suspended"
    )
    assert run(state, replacement, "rejoin", 3, now=103).result == "accepted"
    table = state.games[CABINET]
    assert table.members[1].controller == "replacement" and table.paused_at is None


def test_reconnect_expiry_or_admission_loss_ends_generically_without_a_winner() -> None:
    for admission_lost in [False, True]:
        state, (_, guest, _) = human_table()
        state.presences.pop(guest.account)
        if admission_lost:
            state.actors.pop(guest.account)
        prune_games(state, 101, GameLimits())
        if not admission_lost:
            prune_games(state, 131, GameLimits())
        table = state.games[CABINET]
        assert table.phase == "finished" and table.reason == "unavailable" and table.winner is None


def _keep_admissions_alive(state: WorldState) -> None:
    for actor in state.actors.values():
        actor.expires_at = 5000
    for presence in state.presences.values():
        presence.expires_at = 5000


def test_turn_and_round_deadlines_abandon_without_awarding_the_other_player() -> None:
    # Turn deadline: the round itself would last 1200 s, the turn only 120.
    state, _ = human_table()
    _keep_admissions_alive(state)
    prune_games(state, 219, GameLimits())
    assert state.games[CABINET].phase == "playing_human"
    prune_games(state, 220, GameLimits())
    table = state.games[CABINET]
    assert table.phase == "finished" and table.reason == "abandoned" and table.winner is None
    prune_games(state, 250, GameLimits())
    assert CABINET not in state.games
    # Round deadline: a turn that would last longer cannot outlive the round.
    limits = GameLimits(turn_seconds=300, round_seconds=200)
    state, _ = human_table(limits)
    _keep_admissions_alive(state)
    table = state.games[CABINET]
    assert table.expires_at == 300 and table.turn_until == 400
    prune_games(state, 299, limits)
    assert table.phase == "playing_human"
    prune_games(state, 300, limits)
    abandoned = state.games[CABINET]
    assert abandoned.phase == "finished" and abandoned.reason == "abandoned"
    assert abandoned.winner is None


def test_one_account_cannot_reserve_two_nearby_cabinets_and_refusals_acknowledge_their_kind() -> (
    None
):
    state, (host, _, _) = setup()
    run(state, host, "wait")
    state.actors[host.account].position["x"] += 1
    other = command(
        state, "wait", 2, cabinet="arcade-four-in-row", round_id=None, expected_revision=0
    )
    assert apply_game_transition(state, host, other, 101, GameLimits()).result == "occupied"
    assert len(state.games) == 1
    actor = state.actors[host.account]
    assert actor.seq == 2 and actor.pose_result is None and actor.receipts[-1].kind == "game"


def test_solo_human_handover_requires_consent_and_resets_the_partial_computer_board() -> None:
    from src.domains.world.game_preparation import prepare_game

    state, (host, guest, _) = setup()
    run(state, host, "start_computer")
    move = command(state, "move", 2, move=TicTacToeMove(cell=0).model_dump())
    prepared = prepare_game(state, host, move)
    assert prepared is not None
    assert state.games[CABINET].position.board.count(0) == 9
    assert state.actors[host.account].activity_at == 100
    state.revision += 100
    assert (
        apply_game_transition(state, host, move, 101, GameLimits(), prepared).result == "accepted"
    )
    before = state.games[CABINET].position
    assert before.board.count(0) == 7
    run(state, guest, "request", now=102)
    assert run(state, host, "decline", 3, now=103).result == "accepted"
    assert state.games[CABINET].position == before
    run(state, guest, "request", 2, now=104)
    old_round = state.games[CABINET].round_id
    assert run(state, host, "accept", 4, now=105).result == "accepted"
    table = state.games[CABINET]
    assert table.phase == "playing_human" and not table.computer
    assert table.round_id != old_round and table.position.board.count(0) == 9


def test_a_prepared_bot_answer_cannot_serve_a_different_move_or_a_new_round_revision() -> None:
    from src.domains.world.game_preparation import prepare_game, prepared_position

    state, (host, guest, _) = setup()
    run(state, host, "start_computer")
    move = command(state, "move", 2, move=TicTacToeMove(cell=0).model_dump())
    prepared = prepare_game(state, host, move)
    assert prepared is not None
    table = state.games[CABINET]
    assert prepared_position(prepared, move, table) == prepared.position
    changed = move.model_copy(update={"move": TicTacToeMove(cell=1)})
    assert (
        apply_game_transition(state, host, changed, 101, GameLimits(), prepared).result
        == "unavailable"
    )
    assert table.position.board.count(0) == 9
    # The same board at a newer revision of the round: a declined request moved it.
    run(state, guest, "request", now=102)
    run(state, host, "decline", 3, now=103)
    assert table.revision == prepared.revision + 2 and table.position == prepared.source
    assert prepared_position(prepared, move, table) is None
    # A new round on the same cabinet: same board, fresh round lifetime, revision 0.
    run(state, host, "leave", 4, now=104)
    run(state, host, "start_computer", 5, now=105, round_id=None, expected_revision=0)
    renewed = state.games[CABINET]
    assert renewed.round_id != prepared.round_id and renewed.position == prepared.source
    assert prepared_position(prepared, move, renewed) is None
    assert renewed.position.board.count(0) == 9


def test_human_rematch_requires_both_consents_and_alternates_the_starting_player() -> None:
    state, (host, guest, _) = human_table()
    for tick, cell in enumerate([0, 3, 1, 4, 2], start=101):
        scope = host if state.games[CABINET].position.turn == 1 else guest
        assert (
            run(
                state,
                scope,
                "move",
                state.actors[scope.account].seq + 1,
                now=tick,
                move=TicTacToeMove(cell=cell).model_dump(),
            ).result
            == "accepted"
        )
    table = state.games[CABINET]
    assert table.phase == "finished" and table.reason == "win" and table.winner == 1
    previous = table.round_id
    assert (
        run(state, host, "rematch", state.actors[host.account].seq + 1, now=106).result
        == "accepted"
    )
    assert table.phase == "finished"
    assert (
        run(state, guest, "rematch", state.actors[guest.account].seq + 1, now=107).result
        == "accepted"
    )
    assert table.phase == "playing_human" and table.round_id != previous
    assert table.members[0].number == 2 and table.members[1].number == 1


def test_exact_leave_retry_and_rate_refusal_are_idempotent_and_never_renew_bot_only_activity() -> (
    None
):
    state, (host, _, _) = setup()
    run(state, host, "start_computer")
    table = state.games[CABINET]
    board, revision = table.position, table.revision
    move = command(state, "move", 2, move=TicTacToeMove(cell=0).model_dump())
    refused = apply_game_transition(
        state, host, move, 100.5, GameLimits(), forced_result="rate_limited"
    )
    assert refused.result == "rate_limited"
    # A refusal consumes its sequence and changes no table, nor any activity.
    assert table.position == board and table.revision == revision
    assert state.actors[host.account].seq == 2 and state.actors[host.account].activity_at == 100
    assert (
        apply_game_transition(state, host, move, 100.6, GameLimits(), forced_result="rate_limited")
        == refused
    )
    assert state.actors[host.account].activity_at == 100
    leave = command(state, "leave", 3)
    first = apply_game_transition(state, host, leave, 101, GameLimits())
    assert first.result == "accepted" and state.games[CABINET].phase == "empty"
    assert apply_game_transition(state, host, leave, 102, GameLimits()) == first
    assert state.actors[host.account].activity_at == 101


def test_waiting_host_can_explicitly_rejoin_after_takeover_without_extending_lobby_lifetime() -> (
    None
):
    state, (host, _, _) = setup()
    run(state, host, "wait")
    Authority(Limits()).takeover(state, host.account, "new-host", 101)
    prune_games(state, 101, GameLimits())
    successor = GameScope(host.account, "new-host", host.eligible)
    assert run(state, successor, "rejoin", 1, now=102).result == "accepted"
    assert state.games[CABINET].expires_at == 160


def test_lobby_releases_a_host_who_walked_away_without_teleporting_or_retaining_a_remote_reservation() -> (
    None
):
    state, (host, _, _) = setup()
    run(state, host, "wait")
    before = state.actors[host.account].position.copy()
    state.actors[host.account].position["x"] += 3
    prune_games(state, 101, GameLimits())
    assert CABINET not in state.games
    assert state.actors[host.account].position["x"] == before["x"] + 3


def test_game_only_membership_and_receipt_ownership_are_erased_after_the_actor_disappeared() -> (
    None
):
    from src.domains.world.game_erasure import has_game_account, purge_game_account

    state, (host, guest, _) = human_table()
    state.actors.pop(guest.account)
    state.presences.pop(guest.account)
    assert has_game_account(state, guest.account)
    purge_game_account(state, guest.account, 101, GameLimits())
    assert not has_game_account(state, guest.account)
    table = state.games[CABINET]
    assert table.reason == "unavailable" and table.winner is None
    assert [member.account for member in table.members] == [host.account]


def test_a_blocked_outsider_cannot_terminate_or_replace_someone_elses_solo_round() -> None:
    state, (host, guest, _) = setup()
    run(state, host, "start_computer")
    table = state.games[CABINET]
    position, round_id = table.position, table.round_id
    blocked = GameScope(guest.account, guest.controller, guest.eligible, frozenset({host.account}))
    outcome = run(state, blocked, "request")
    assert outcome.result == "unavailable"
    assert outcome.round_id is None and outcome.revision == 0
    assert table.phase == "playing_computer" and table.reason is None
    assert table.position == position and table.round_id == round_id


def test_an_existing_participant_observing_a_block_ends_contact_without_awarding_a_win() -> None:
    state, (host, guest, _) = human_table()
    blocked = GameScope(guest.account, guest.controller, guest.eligible, frozenset({host.account}))
    assert (
        run(state, blocked, "move", 2, move=TicTacToeMove(cell=0).model_dump()).result
        == "unavailable"
    )
    table = state.games[CABINET]
    assert table.phase == "finished" and table.reason == "unavailable" and table.winner is None
    assert table.members == []
    other = "arcade-four-in-row"
    state.actors[guest.account].position = CABINETS[other].approach.copy()
    assert (
        run(state, blocked, "wait", 3, cabinet=other, round_id=None, expected_revision=0).result
        == "accepted"
    )


def test_a_replacement_host_cannot_accept_contact_before_deliberately_rejoining() -> None:
    state, (host, guest, _) = setup()
    run(state, host, "wait")
    run(state, guest, "request")
    Authority(Limits()).takeover(state, host.account, "new-host", 101)
    prune_games(state, 101, GameLimits())
    successor = GameScope(host.account, "new-host", host.eligible)
    assert run(state, successor, "accept", 1, now=102).result == "suspended"
    assert len(state.games[CABINET].members) == 1
    assert run(state, successor, "rejoin", 2, now=103).result == "accepted"
    assert run(state, successor, "accept", 3, now=104).result == "accepted"


def test_waiting_host_can_start_a_fresh_computer_round_without_releasing_admission() -> None:
    state, (host, guest, _) = setup()
    run(state, host, "wait")
    first = state.games[CABINET].round_id
    assert run(state, guest, "start_computer").result == "occupied"
    assert run(state, host, "start_computer", 2).result == "accepted"
    table = state.games[CABINET]
    assert table.phase == "playing_computer" and table.round_id != first
    assert table.members[0].account == host.account and state.actors[host.account].seq == 2


def test_completed_solo_rematches_alternate_colors_and_precompute_computer_opening() -> None:
    from src.domains.world.game_preparation import prepare_game
    from src.domains.world.game_rules import legal_moves

    state, (host, _, _) = setup()
    run(state, host, "start_computer")
    for expected_number in (2, 1):
        for _ in range(9):
            table = state.games[CABINET]
            if table.phase == "finished":
                break
            intent = command(
                state,
                "move",
                state.actors[host.account].seq + 1,
                move=legal_moves(table.position)[0].model_dump(),
            )
            prepared = prepare_game(state, host, intent, 100)
            assert (
                apply_game_transition(state, host, intent, 101, GameLimits(), prepared).result
                == "accepted"
            )
        assert state.games[CABINET].phase == "finished"
        intent = command(state, "rematch", state.actors[host.account].seq + 1)
        prepared = prepare_game(state, host, intent, 100)
        assert (
            apply_game_transition(state, host, intent, 102, GameLimits(), prepared).result
            == "accepted"
        )
        table = state.games[CABINET]
        assert table.members[0].number == expected_number and table.position.turn == expected_number
        assert table.position.board.count(1) == (1 if expected_number == 2 else 0)


def test_requester_can_withdraw_but_third_party_cannot_leave_or_rematch_other_members() -> None:
    state, (host, guest, third) = setup()
    run(state, host, "wait")
    run(state, guest, "request")
    assert run(state, third, "leave").result == "not_participant"
    assert run(state, third, "rematch", 2).result == "not_participant"
    assert run(state, host, "rematch", 2).result == "unavailable"
    assert run(state, guest, "leave", 2).result == "accepted"
    assert state.games[CABINET].pending is None and state.games[CABINET].phase == "waiting"


def test_new_world_actor_identity_cannot_inherit_a_previous_admissions_game() -> None:
    state, (_, guest, _) = human_table()
    state.actors[guest.account].public_id = str(uuid4())
    prune_games(state, 101, GameLimits())
    assert state.games[CABINET].phase == "finished" and state.games[CABINET].reason == "unavailable"


@pytest.mark.parametrize("walked_away", [False, True])
def test_leaving_after_rematch_consent_cannot_leave_orphaned_consent_in_storage(
    walked_away: bool,
) -> None:
    from src.domains.world.store import WorldStore

    state, (host, guest, _) = human_table()
    for scope, cell in ((host, 0), (guest, 3), (host, 1), (guest, 4), (host, 2)):
        assert (
            run(
                state,
                scope,
                "move",
                state.actors[scope.account].seq + 1,
                move=TicTacToeMove(cell=cell).model_dump(),
            ).result
            == "accepted"
        )
    assert run(state, host, "rematch", state.actors[host.account].seq + 1).result == "accepted"
    if walked_away:
        state.actors[host.account].position["x"] += 5
    assert run(state, host, "leave", state.actors[host.account].seq + 1).result == "accepted"
    decoded = WorldStore.decode(state.model_dump_json())
    assert decoded.games[CABINET].rematch == []
    assert [member.account for member in decoded.games[CABINET].members] == [guest.account]


def test_a_peer_move_cannot_prevent_explicit_departure_but_a_new_round_still_fences_it() -> None:
    state, (host, guest, _) = human_table()
    leave = command(state, "leave", 2)
    assert run(state, host, "move", 3, move=TicTacToeMove(cell=0).model_dump()).result == "accepted"
    assert apply_game_transition(state, guest, leave, 101, GameLimits()).result == "accepted"
    WorldStore.decode(state.model_dump_json())
    assert all(member.account != guest.account for member in state.games[CABINET].members)
    state, (host, guest, _) = human_table()
    leave = command(state, "leave", 2)
    state.games[CABINET].round_id = str(uuid4())
    assert apply_game_transition(state, guest, leave, 101, GameLimits()).result == "conflict"
    assert len(state.games[CABINET].members) == 2


def test_late_join_request_never_advertises_more_time_than_the_host_lobby_has_left() -> None:
    state, (host, guest, _) = setup()
    run(state, host, "wait")
    for actor in state.actors.values():
        actor.expires_at = 1000
    for presence in state.presences.values():
        presence.expires_at = 1000
    assert run(state, guest, "request", now=159).result == "accepted"
    table = state.games[CABINET]
    assert table.pending is not None and table.pending.expires_at == table.expires_at == 160


def _finish_solo_round(state: WorldState, host: GameScope) -> None:
    """Play the host's first legal move, with a prepared computer answer, to the end."""
    from src.domains.world.game_preparation import prepare_game
    from src.domains.world.game_rules import legal_moves

    for _ in range(9):
        table = state.games[CABINET]
        if table.phase == "finished":
            return
        intent = command(
            state,
            "move",
            state.actors[host.account].seq + 1,
            move=legal_moves(table.position)[0].model_dump(),
        )
        prepared = prepare_game(state, host, intent, 100)
        assert (
            apply_game_transition(state, host, intent, 101, GameLimits(), prepared).result
            == "accepted"
        )
        WorldStore.decode(state.model_dump_json())
    assert state.games[CABINET].phase == "finished"


def test_a_join_after_a_solo_rematch_starts_a_canonical_two_human_board() -> None:
    from src.domains.world.game_preparation import prepare_game

    state, (host, guest, _) = setup()
    run(state, host, "start_computer")
    _finish_solo_round(state, host)
    rematch = command(state, "rematch", state.actors[host.account].seq + 1)
    prepared = prepare_game(state, host, rematch, 100)
    assert (
        apply_game_transition(state, host, rematch, 102, GameLimits(), prepared).result
        == "accepted"
    )
    table = state.games[CABINET]
    # The solo rematch alternated the host onto the second color; the computer opened.
    assert table.phase == "playing_computer" and table.members[0].number == 2
    assert run(state, guest, "request", now=103).result == "accepted"
    host_seq = state.actors[host.account].seq + 1
    assert run(state, host, "accept", host_seq, now=104).result == "accepted"
    committed = WorldStore.decode(state.model_dump_json()).games[CABINET]
    assert committed.phase == "playing_human" and not committed.computer
    # A join is a new pairing, not a rematch: the canonical fresh board.
    numbers = [(member.account, member.number) for member in committed.members]
    assert numbers == [(host.account, 1), (guest.account, 2)]
    assert committed.position.board.count(0) == 9 and committed.position.turn == 1


def test_a_reconnect_on_the_result_screen_rejoins_then_rematches_the_computer() -> None:
    from src.domains.world.game_preparation import prepare_game

    state, (host, _, _) = setup()
    run(state, host, "start_computer")
    _finish_solo_round(state, host)
    # World transport resumes on a new tab: the controller rotates, its sequence restarts.
    Authority(Limits()).takeover(state, host.account, "result-screen", 102)
    successor = GameScope(host.account, "result-screen", host.eligible)
    rematch = command(state, "rematch", 1)
    assert (
        apply_game_transition(
            state, successor, rematch, 103, GameLimits(), prepare_game(state, successor, rematch)
        ).result
        == "suspended"
    )
    assert run(state, successor, "rejoin", 2, now=104).result == "accepted"
    rematch = command(state, "rematch", 3)
    prepared = prepare_game(state, successor, rematch, 100)
    assert prepared is not None
    assert (
        apply_game_transition(state, successor, rematch, 105, GameLimits(), prepared).result
        == "accepted"
    )
    table = WorldStore.decode(state.model_dump_json()).games[CABINET]
    assert table.phase == "playing_computer" and table.members[0].controller == "result-screen"


def test_a_reconnect_on_the_result_screen_rejoins_a_human_rematch_until_the_result_ends() -> None:
    state, (host, guest, _) = human_table()
    for scope, cell in ((host, 0), (guest, 3), (host, 1), (guest, 4), (host, 2)):
        seq = state.actors[scope.account].seq + 1
        outcome = run(state, scope, "move", seq, move=TicTacToeMove(cell=cell).model_dump())
        assert outcome.result == "accepted"
    assert state.games[CABINET].phase == "finished" and state.games[CABINET].expires_at == 130
    Authority(Limits()).takeover(state, guest.account, "result-screen", 101)
    successor = GameScope(guest.account, "result-screen", guest.eligible)
    assert run(state, successor, "rematch", 1, now=102).result == "suspended"
    assert run(state, successor, "rejoin", 2, now=103).result == "accepted"
    host_seq = state.actors[host.account].seq + 1
    assert run(state, host, "rematch", host_seq, now=104).result == "accepted"
    assert run(state, successor, "rematch", 3, now=105).result == "accepted"
    table = state.games[CABINET]
    assert table.phase == "playing_human" and table.members[1].controller == "result-screen"
    # Once the result has been displayed for its whole window, nothing is left to rejoin.
    state, (host, guest, _) = human_table()
    for scope, cell in ((host, 0), (guest, 3), (host, 1), (guest, 4), (host, 2)):
        seq = state.actors[scope.account].seq + 1
        run(state, scope, "move", seq, move=TicTacToeMove(cell=cell).model_dump())
    stale = command(state, "rejoin", 1)
    _keep_admissions_alive(state)
    Authority(Limits()).takeover(state, guest.account, "late", 129)
    late = GameScope(guest.account, "late", guest.eligible)
    assert apply_game_transition(state, late, stale, 130, GameLimits()).result == "conflict"
    assert CABINET not in state.games
