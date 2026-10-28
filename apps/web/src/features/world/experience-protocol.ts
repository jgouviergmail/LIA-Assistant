import { z } from '@/lib/zod';

export const experiencePreferencesSchema = z
  .object({
    version: z.literal(1),
    revision: z
      .number()
      .int()
      .min(0)
      .max(2 ** 31 - 1),
    show_route: z.boolean(),
    season_mode: z.enum(['off', 'calendar', 'spring', 'summer', 'autumn', 'winter']),
    hemisphere: z.enum(['north', 'south']),
  })
  .strict();
export const experienceViewSchema = z
  .object({
    owner_id: z.uuid(),
    preferences: experiencePreferencesSchema,
    needs_reset: z.boolean(),
  })
  .strict();
export type ExperiencePreferences = z.infer<typeof experiencePreferencesSchema>;
export type ExperienceView = z.infer<typeof experienceViewSchema>;
export type ExperienceEdit = Partial<
  Pick<ExperiencePreferences, 'show_route' | 'season_mode' | 'hemisphere'>
>;
export type ExperienceWrite =
  | (ExperienceEdit & { expected_revision: number; reset?: false })
  | { expected_revision: number; reset: true };
