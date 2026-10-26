/** Finite public art choices; private account preferences use a separate response. */
import { z } from '@/lib/zod';

import {
  AVATAR_HAIR,
  AVATAR_COLOR_IDS,
  AVATAR_SKIN_IDS,
  AVATAR_OUTFITS,
  AVATAR_HEADWEAR,
  type AvatarAppearance,
} from './avatar-catalogue';
export * from './avatar-catalogue';

export const avatarAppearanceSchema = z
  .object({
    version: z.literal(1).default(1),
    skin: z.enum(AVATAR_SKIN_IDS).default('caramel'),
    hair: z.enum(AVATAR_HAIR).default('short'),
    hair_color: z.enum(AVATAR_COLOR_IDS).default('brown'),
    outfit: z.enum(AVATAR_OUTFITS).default('casual'),
    outfit_color: z.enum(AVATAR_COLOR_IDS).default('green'),
    headwear: z.enum(AVATAR_HEADWEAR).default('none'),
    headwear_color: z.enum(AVATAR_COLOR_IDS).default('blue'),
    glasses: z.boolean().default(false),
  })
  .strict();
export const publicWorldNameSchema = z
  .string()
  .min(1)
  .max(96)
  .refine(value => Array.from(value).length <= 24 && !/[\p{Cc}\p{Cf}]/u.test(value));

export const avatarPreferencesSchema = z
  .object({
    version: z.literal(1),
    revision: z.number().int().min(0).max(Number.MAX_SAFE_INTEGER),
    appearance: avatarAppearanceSchema,
  })
  .strict();
export const avatarViewSchema = z
  .object({
    owner_id: z.uuid(),
    public_name: publicWorldNameSchema,
    preferences: avatarPreferencesSchema,
    needs_setup: z.boolean(),
    needs_reset: z.boolean(),
  })
  .strict();
export type AvatarView = z.infer<typeof avatarViewSchema>;
export interface AvatarWrite {
  expected_revision: number;
  appearance: AvatarAppearance;
  consent: true;
  reset: boolean;
}
