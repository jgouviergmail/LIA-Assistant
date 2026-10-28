import { expect, it } from 'vitest';
import { cabinetViewSchema, gameViewSchema } from '../game-protocol';

const id = '11111111-1111-4111-8111-111111111111';
const view = () => ({
  cabinet: 'arcade-tic-tac-toe',
  round_id: id,
  revision: 1,
  phase: 'playing_computer',
  computer: true,
  position: { game: 'tic_tac_toe', board: Array(9).fill(0), turn: 1, result: 'playing' },
  players: [{ id, alias: 'Léa', number: 1 }],
  your_number: 1,
  needs_rejoin: false,
  paused: false,
  turn_until: 220,
  expires_at: 1300,
  reconnect_until: null,
  pending: null,
  legal_moves: [{ game: 'tic_tac_toe', cell: 0 }],
  reason: null,
  winner: null,
  rematch_ready: [],
});

it('accepts a strict participant board but rejects private fields, impossible cell shapes and cabinet mismatches', () => {
  expect(gameViewSchema.parse(view()).position.board).toHaveLength(9);
  for (const patch of [
    { controller: 'private' },
    { players: [{ id, alias: 'Léa', number: 1, account: id }] },
    { position: { ...view().position, board: Array(9).fill(true) } },
    { position: { ...view().position, board: Array(8).fill(0) } },
    { cabinet: 'arcade-reversi' },
    { legal_moves: [{ game: 'tic_tac_toe', cell: 9 }] },
    { legal_moves: [{ game: 'four_in_row', column: 0 }] },
  ])
    expect(() => gameViewSchema.parse({ ...view(), ...patch })).toThrow();
});

it('keeps public cabinet availability separate from all board, name and result data', () => {
  const hint = { cabinet: 'arcade-reversi', availability: 'empty', round_id: null, revision: 0 };
  expect(cabinetViewSchema.parse(hint)).toEqual(hint);
  for (const field of ['board', 'players', 'winner', 'account'])
    expect(() => cabinetViewSchema.parse({ ...hint, [field]: [] })).toThrow();
  // A policy-hidden table reads as full: the retired distinct state is refused.
  const full = { ...hint, availability: 'full' };
  expect(cabinetViewSchema.parse(full)).toEqual(full);
  expect(() => cabinetViewSchema.parse({ ...hint, availability: 'unavailable' })).toThrow();
});
