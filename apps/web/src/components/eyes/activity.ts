/** Only execution evidence drives tool acting. Unknown versions fail closed. */
import { z } from 'zod';

export const ACTIVITY_FAMILIES = [
  'reading',
  'organizing',
  'communicating',
  'calculating',
  'creating',
  'exploring',
  'generic',
] as const;
export type ActivityFamily = (typeof ACTIVITY_FAMILIES)[number];

const activitySchema = z
  .strictObject({
    version: z.literal(1),
    run_id: z.string().min(1).max(200),
    invocation_id: z.string().min(1).max(100),
    family: z.enum(ACTIVITY_FAMILIES),
    intent: z.enum(['read', 'prepare', 'act']),
    phase: z.enum(['started', 'finished']),
    outcome: z
      .enum(['succeeded', 'prepared', 'failed', 'cancelled', 'waiting', 'unknown'])
      .nullable(),
  })
  .refine(value => (value.phase === 'started') === (value.outcome === null));

export type Activity = z.infer<typeof activitySchema>;

export function parseActivity(value: unknown): Activity | null {
  const result = activitySchema.safeParse(value);
  return result.success ? result.data : null;
}

export interface ActivityRecord {
  event: Activity;
  at: number;
}

/** A completed lookup may colour the following answer; it is never still running. */
export function recentActivity(record: ActivityRecord | null, now: number) {
  if (!record || record.event.phase !== 'finished') return null;
  const { event, at } = record;
  const age = now - at;
  if (age < 0 || age >= 6000 || !['succeeded', 'prepared'].includes(event.outcome ?? ''))
    return null;
  const t = age / 6000;
  return {
    family: event.family,
    weight: 1 - t * t * (3 - 2 * t),
    accomplished: event.intent === 'act' && event.outcome === 'succeeded',
  };
}

/** Terminal states are monotone. The bounded map also absorbs duplicate delivery. */
export function recordActivity(
  records: readonly ActivityRecord[],
  event: Activity,
  at: number
): readonly ActivityRecord[] {
  const previous = records.find(item => item.event.invocation_id === event.invocation_id);
  if (previous?.event.phase === 'finished' || previous?.event.phase === event.phase) return records;
  return [...records.filter(item => item !== previous), { event, at }].slice(-128);
}

/** Missing terminal events eventually relinquish the face; no fabricated outcome. */
export function currentActivity(records: readonly ActivityRecord[], now: number): Activity | null {
  return (
    records.findLast(
      item => item.event.phase === 'started' && now >= item.at && now - item.at < 120_000
    )?.event ?? null
  );
}
