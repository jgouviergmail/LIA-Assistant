/**
 * The beat map of the landing video (ADR-330): `[ms, weight, bar]` triples in
 * ascending order, produced offline by `scripts/assets/encode_landing_video.py`
 * and hosted beside the video. The page reads it through
 * `/api/landing-media/beats`, which validates it here first — it is the
 * operator's file, and a list the browser walks every frame must be bounded.
 */

import { z } from '@/lib/zod';

/** Five minutes at 200 BPM is 1 000 beats; this is twenty times that. */
export const BEAT_MAP_MAX_ENTRIES = 20_000;

const beatSchema = z.tuple([
  /** Instant in the video, in milliseconds. */
  z.number().int().nonnegative(),
  /** Strength of the onset, 0..1. */
  z.number().min(0).max(1),
  /** The first beat of a bar. */
  z.boolean(),
]);

export const beatMapSchema = z.object({
  version: z.literal(1),
  beats: z
    .array(beatSchema)
    .max(BEAT_MAP_MAX_ENTRIES)
    .refine(
      beats => beats.every((beat, index) => index === 0 || beat[0] > beats[index - 1][0]),
      'beats must be in strictly ascending order'
    ),
});

export type Beat = z.infer<typeof beatSchema>;
export type BeatMap = z.infer<typeof beatMapSchema>;

/** @throws {ZodError} when the value is not a beat map. */
export function parseBeatMap(raw: unknown): BeatMap {
  return beatMapSchema.parse(raw);
}
