import { z } from '@/lib/zod';
import { HOME_PALETTES } from './home-catalogue';

export const homePreferencesSchema = z
  .object({
    version: z.literal(1),
    revision: z
      .number()
      .int()
      .min(0)
      .max(2 ** 31 - 1),
    palette: z.enum(HOME_PALETTES),
  })
  .strict();
export const homeDecorationSchema = z
  .object({
    automatic_palette: z.enum(['sage', 'teal', 'clay', 'violet', 'amber', 'cream']),
    palette: z.enum(['sage', 'teal', 'clay', 'violet', 'amber', 'cream']),
  })
  .strict();
export const homeViewSchema = z
  .object({
    owner_id: z.uuid(),
    preferences: homePreferencesSchema,
    decoration: homeDecorationSchema,
    needs_reset: z.boolean(),
  })
  .strict();
export type HomeView = z.infer<typeof homeViewSchema>;
export type HomePreferences = z.infer<typeof homePreferencesSchema>;
export type HomeDecoration = z.infer<typeof homeDecorationSchema>;
export type HomeEdit = Pick<HomePreferences, 'palette'>;
export type HomeWrite =
  | (HomeEdit & { expected_revision: number })
  | { expected_revision: number; reset: true };
