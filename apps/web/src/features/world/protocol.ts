/** Strict public wire contract. Unknown/private fields never reach the scene model. */
import { z } from '@/lib/zod';
import { avatarAppearanceSchema, publicWorldNameSchema } from './avatar-protocol';

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
  })
  .strict();
export const worldViewSchema = z
  .object({
    version: z.literal(1),
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
    version: z.literal(1),
    type: z.literal('ready'),
    scene: z.string().min(1).max(80),
    resume: z.string().min(16).max(128),
  })
  .strict();
const frame = z.discriminatedUnion('type', [ready, worldViewSchema]);
export type WorldView = z.infer<typeof worldViewSchema>;
export type PublicActor = z.infer<typeof publicActor>;
export type WorldFrame = z.infer<typeof frame>;

export function parseWorldFrame(text: string): WorldFrame {
  if (text.length > 16384 || new TextEncoder().encode(text).length > 16384)
    throw new Error('world_frame_limit');
  return frame.parse(JSON.parse(text));
}

export function publicAlias(value: string): string | null {
  const normalized = value.trim().normalize('NFC');
  return normalized && Array.from(normalized).length <= 24 && !/[\p{Cc}\p{Cf}]/u.test(normalized)
    ? normalized
    : null;
}
