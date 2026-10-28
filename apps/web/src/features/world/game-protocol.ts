/** Strict finite participant-only game contract. No account, controller, arbitrary text or submitted board. */
import { z } from '@/lib/zod';
import { publicWorldNameSchema } from './avatar-protocol';
import { CABINET_GAMES } from './game-catalogue';

export const cabinetSchema = z.enum(['arcade-tic-tac-toe', 'arcade-four-in-row', 'arcade-reversi']);
const player = z.number().int().min(1).max(2);
const cell = z.number().int().min(0).max(2);
const revision = z
  .number()
  .int()
  .min(0)
  .max(2 ** 31 - 1);
const timestamp = z.number().finite().nonnegative();
const result = z.enum(['playing', 'draw', 'one', 'two']);
export const gameMoveSchema = z.discriminatedUnion('game', [
  z.object({ game: z.literal('tic_tac_toe'), cell: z.number().int().min(0).max(8) }).strict(),
  z.object({ game: z.literal('four_in_row'), column: z.number().int().min(0).max(6) }).strict(),
  z
    .object({ game: z.literal('reversi'), cell: z.number().int().min(0).max(63).nullable() })
    .strict(),
]);
const position = z.discriminatedUnion('game', [
  z
    .object({
      game: z.literal('tic_tac_toe'),
      board: z.array(cell).length(9),
      turn: player,
      result,
    })
    .strict(),
  z
    .object({
      game: z.literal('four_in_row'),
      board: z.array(cell).length(42),
      turn: player,
      result,
    })
    .strict(),
  z
    .object({ game: z.literal('reversi'), board: z.array(cell).length(64), turn: player, result })
    .strict(),
]);
/** Coarse hint only. A table hidden by policy reads as `full`, like any other full table,
 *  and only a `joinable` cabinet carries the round fence a join request needs. */
export const cabinetViewSchema = z
  .object({
    cabinet: cabinetSchema,
    availability: z.enum(['empty', 'joinable', 'full']),
    round_id: z.uuid().nullable(),
    revision,
  })
  .strict();
export const gameWaitingSchema = z
  .object({ cabinet: cabinetSchema, round_id: z.uuid(), revision, expires_at: timestamp })
  .strict();
export const gameViewSchema = z
  .object({
    cabinet: cabinetSchema,
    round_id: z.uuid(),
    revision,
    phase: z.enum(['empty', 'waiting', 'playing_computer', 'playing_human', 'finished']),
    computer: z.boolean(),
    position,
    players: z
      .array(z.object({ id: z.uuid(), alias: publicWorldNameSchema, number: player }).strict())
      .max(2),
    your_number: player,
    needs_rejoin: z.boolean(),
    paused: z.boolean(),
    turn_until: timestamp,
    expires_at: timestamp,
    reconnect_until: timestamp.nullable(),
    pending: z
      .object({ id: z.uuid(), alias: publicWorldNameSchema, expires_at: timestamp })
      .strict()
      .nullable(),
    legal_moves: z.array(gameMoveSchema).max(64),
    reason: z.enum(['win', 'draw', 'resigned', 'unavailable', 'abandoned']).nullable(),
    winner: player.nullable(),
    rematch_ready: z.array(player).max(2),
  })
  .strict()
  .refine(
    value =>
      CABINET_GAMES[value.cabinet] === value.position.game &&
      value.legal_moves.every(move => move.game === value.position.game),
    'world_game_binding'
  );
export const gameOutcomeSchema = z
  .object({
    action_id: z.uuid(),
    result: z.enum([
      'accepted',
      'unavailable',
      'rate_limited',
      'conflict',
      'wrong_turn',
      'illegal_move',
      'full',
      'occupied',
      'not_participant',
      'action_reused',
      'suspended',
      'out_of_reach',
    ]),
    round_id: z.uuid().nullable(),
    revision,
  })
  .strict();
export type GameView = z.infer<typeof gameViewSchema>;
export type GameMove = z.infer<typeof gameMoveSchema>;
export type CabinetView = z.infer<typeof cabinetViewSchema>;
export type GameWaiting = z.infer<typeof gameWaitingSchema>;
export type GameOutcome = z.infer<typeof gameOutcomeSchema>;
export type GameAction =
  | 'wait'
  | 'start_computer'
  | 'request'
  | 'accept'
  | 'decline'
  | 'move'
  | 'leave'
  | 'rematch'
  | 'rejoin';

export type GameIntent = {
  cabinet: z.infer<typeof cabinetSchema>;
  action_id: string;
  round_id: string | null;
  expected_revision: number;
} & ({ action: 'move'; move: GameMove } | { action: Exclude<GameAction, 'move'>; move?: never });

export interface GameDelivery {
  seq: number;
  epoch: string;
  stream: number;
}
