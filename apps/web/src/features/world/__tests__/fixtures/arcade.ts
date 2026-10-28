import { gameViewSchema, type GameView } from '../../game-protocol';
import { CABINET_GAMES, type GameKind } from '../../game-catalogue';

export function arcadeFixture(kind: GameKind = 'tic_tac_toe'): GameView {
  const board = Array(kind === 'tic_tac_toe' ? 9 : kind === 'four_in_row' ? 42 : 64).fill(0);
  if (kind === 'reversi') {
    board[27] = board[36] = 2;
    board[28] = board[35] = 1;
  }
  const moves =
    kind === 'tic_tac_toe'
      ? Array.from({ length: 9 }, (_, cell) => ({ game: kind, cell }))
      : kind === 'four_in_row'
        ? Array.from({ length: 7 }, (_, column) => ({ game: kind, column }))
        : [19, 26, 37, 44].map(cell => ({ game: kind, cell }));
  return gameViewSchema.parse({
    cabinet: Object.entries(CABINET_GAMES).find(([, game]) => game === kind)?.[0],
    round_id: '11111111-1111-4111-8111-111111111111',
    revision: 0,
    phase: 'playing_human',
    computer: false,
    position: { game: kind, board, turn: 1, result: 'playing' },
    players: [
      { id: '22222222-2222-4222-8222-222222222222', alias: 'Alex', number: 1 },
      { id: '33333333-3333-4333-8333-333333333333', alias: 'Sam', number: 2 },
    ],
    your_number: 1,
    needs_rejoin: false,
    paused: false,
    turn_until: 220,
    expires_at: 1300,
    reconnect_until: null,
    pending: null,
    legal_moves: moves,
    reason: null,
    winner: null,
    rematch_ready: [],
  });
}
