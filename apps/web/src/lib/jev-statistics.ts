/**
 * What a JEV threshold concludes, read from the buckets the server counted (ADR-374).
 *
 * The server files a confidence at `floor(score × 100)` and a margin's judgement at its
 * distance to a certain answer, `ceil(min(p, 1 − p) × 100)` (`jev_gates.judgement_bucket`).
 * With those buckets a confidence concludes from bucket `t × 100` up and a margin up to
 * bucket `m × 100`, exactly: the screen computes the share a slider position concludes
 * without asking the server, and agrees with it at every threshold the slider offers.
 */
import type { JevGateKind } from '@/types/jev';

/** One band of buckets, split at the threshold being read. */
export interface ThresholdBand {
  /** Lowest score (a confidence) or distance (a margin) the band holds. */
  from: number;
  /** Highest one, inclusive. */
  to: number;
  concludes: number;
  handsBack: number;
}

/** A threshold as the integer hundredth the buckets count in. */
function hundredths(threshold: number): number {
  return Math.round(threshold * 100);
}

/** Whether a judgement in `bucket` concludes at `threshold` — the server's own rule. */
export function bucketConcludes(kind: JevGateKind, bucket: number, threshold: number): boolean {
  return kind === 'margin' ? bucket <= hundredths(threshold) : bucket >= hundredths(threshold);
}

/** How many judgements conclude at `threshold`, out of how many were judged. */
export function concludedShare(
  kind: JevGateKind,
  buckets: readonly number[],
  threshold: number
): { concluded: number; total: number } {
  let concluded = 0;
  let total = 0;
  buckets.forEach((count, bucket) => {
    total += count;
    if (bucketConcludes(kind, bucket, threshold)) concluded += count;
  });
  return { concluded, total };
}

/**
 * Ten bands of the buckets a gate can reach, the most conclusive first: confidences
 * from 1.00 down by tenths, distances from certainty (0.00) out by twentieths.
 */
export function thresholdBands(
  kind: JevGateKind,
  buckets: readonly number[],
  threshold: number
): ThresholdBand[] {
  const width = kind === 'margin' ? 5 : 10;
  const last = kind === 'margin' ? 50 : 100;
  return Array.from({ length: 10 }, (_, index) => {
    const band = kind === 'margin' ? index : 9 - index;
    const low = band * width;
    const high = band === 9 ? last : low + width - 1;
    let concludes = 0;
    let handsBack = 0;
    for (let bucket = low; bucket <= high; bucket += 1) {
      const count = buckets[bucket] ?? 0;
      if (bucketConcludes(kind, bucket, threshold)) concludes += count;
      else handsBack += count;
    }
    return { from: low / 100, to: high / 100, concludes, handsBack };
  });
}
