/** Strict public wire contract. Unknown/private fields never reach the scene model. */
import { z } from '@/lib/zod';
import { avatarAppearanceSchema, publicWorldNameSchema } from './avatar-protocol';
import { EMOTES, EMOTE_OUTCOMES } from './emote-catalogue';
import {
  cabinetViewSchema,
  gameViewSchema,
  gameWaitingSchema,
  gameOutcomeSchema,
} from './game-protocol';

const sequence = z
  .number()
  .int()
  .min(1)
  .max(2 ** 31 - 1);
export const emoteSchema = z
  .object({
    emote: z.enum(EMOTES),
    serial: sequence,
    expires_at: z.number().finite().nonnegative(),
  })
  .strict();
const receipt = z.discriminatedUnion('kind', [
  z.object({ seq: sequence, kind: z.literal('game'), outcome: gameOutcomeSchema }).strict(),
  z
    .object({
      seq: sequence,
      kind: z.literal('pose'),
      result: z.enum(['accepted', 'occupied', 'out_of_reach', 'invalid']),
    })
    .strict(),
  z
    .object({
      seq: sequence,
      kind: z.literal('emote'),
      result: z.enum(EMOTE_OUTCOMES),
    })
    .strict(),
  z.object({ seq: sequence, kind: z.literal('move'), result: z.literal('accepted') }).strict(),
]);

const coordinate = z.number().finite().min(0).max(128);
const position = z.object({ x: coordinate, y: coordinate }).strict();
const publicActor = z
  .object({
    id: z.uuid(),
    alias: publicWorldNameSchema,
    appearance: avatarAppearanceSchema.optional(),
    position,
    facing: z.number().int().min(0).max(3),
    walking: z.boolean(),
    pose: z.string().min(1).max(96).nullable().optional(),
    emote: emoteSchema.nullable().optional(),
  })
  .strict();
export const worldViewSchema = z
  .object({
    cabinets: z.array(cabinetViewSchema).max(3).optional(),
    game: gameViewSchema.nullable().optional(),
    game_request: gameWaitingSchema.nullable().optional(),
    version: z.literal(2),
    server_time: z.number().finite().nonnegative(),
    receipts: z.array(receipt).max(16),
    type: z.literal('snapshot'),
    pose_result: z.enum(['accepted', 'occupied', 'out_of_reach', 'invalid']).nullable().optional(),
    epoch: z.uuid(),
    revision: z.number().int().nonnegative(),
    status: z.enum(['active', 'waiting', 'absent']),
    actors: z.array(publicActor).max(10),
    you: publicActor.nullable(),
    ack: z
      .number()
      .int()
      .min(0)
      .max(2 ** 31 - 1),
    position: z.number().int().min(1).max(128).nullable(),
    offer_until: z.number().finite().nullable(),
    idle_until: z.number().finite().nullable(),
    controlling: z.boolean(),
  })
  .strict();
const ready = z
  .object({
    version: z.literal(2),
    type: z.literal('ready'),
    scene: z.string().min(1).max(80),
    resume: z.string().min(16).max(128),
  })
  .strict();
const frame = z.discriminatedUnion('type', [ready, worldViewSchema]);
export type WorldView = z.infer<typeof worldViewSchema>;
export type PublicActor = z.infer<typeof publicActor>;
export type WorldFrame = z.infer<typeof frame>;
export class WorldProtocolMismatch extends Error {}

export function parseWorldFrame(text: string): WorldFrame {
  if (text.length > 16384 || new TextEncoder().encode(text).length > 16384)
    throw new Error('world_frame_limit');
  const value: unknown = JSON.parse(text);
  const envelope = z.object({ version: z.number().int().positive() }).safeParse(value);
  if (envelope.success && envelope.data.version !== 2)
    throw new WorldProtocolMismatch('world_reload_required');
  return frame.parse(value);
}

export function publicAlias(value: string): string | null {
  const normalized = value.trim().normalize('NFC');
  return normalized && Array.from(normalized).length <= 24 && !/[\p{Cc}\p{Cf}]/u.test(normalized)
    ? normalized
    : null;
}
