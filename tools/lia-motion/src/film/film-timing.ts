const CANONICAL_FRAMES = 480;
const FRAMES_PER_SECOND = 60;
const MAX_SNAP_FRAMES = 8;
const MIN_ANCHOR_GAP = 12;

interface TimingAnchor {
  actual: number;
  canonical: number;
}

/**
 * Map a chapter's real local clock to its authored 0..480 frame clock.
 *
 * An action proposes the nearest musical onset to its unretimed global time.
 * Measured onsets are accepted within eight frames, then rounded to renderable
 * frames and kept twelve frames apart in both clocks, including the endpoints.
 * A refused proposal only removes a timing anchor: the continuous, strictly
 * increasing interpolation still passes every authored event exactly once.
 *
 * Durations may differ from 480 because the chapter cuts follow the score.
 * The first and last anchors never move, so retiming cannot shorten a chapter.
 * Neither input array is mutated. Ties choose the earlier onset.
 */
export function frameForScene(
  frameLocal: number,
  duration: number,
  globalStart: number,
  onsetSeconds: number[],
  actionFrames: number[],
): number {
  if (!Number.isFinite(duration) || duration <= 0) return 0;
  if (Number.isNaN(frameLocal) || frameLocal <= 0) return 0;
  if (frameLocal >= duration) return CANONICAL_FRAMES;

  const anchors: TimingAnchor[] = [{ actual: 0, canonical: 0 }];
  if (Number.isFinite(globalStart)) {
    const onsets = [...new Set(onsetSeconds
      .filter(onset => Number.isFinite(onset) && onset >= 0)
      .map(onset => onset * FRAMES_PER_SECOND))]
      .filter(Number.isFinite)
      .sort((left, right) => left - right);
    const actions = [...new Set(actionFrames
      .filter(action => Number.isFinite(action) && action > 0 && action < CANONICAL_FRAMES))]
      .sort((left, right) => left - right);

    for (const canonical of actions) {
      const target = globalStart + canonical * duration / CANONICAL_FRAMES;
      let nearest: number | undefined;
      let distance = Infinity;
      for (const onset of onsets) {
        const candidateDistance = Math.abs(onset - target);
        if (candidateDistance < distance) {
          nearest = onset;
          distance = candidateDistance;
        }
      }
      if (nearest === undefined || distance > MAX_SNAP_FRAMES) continue;
      const actual = Math.round(nearest) - globalStart;
      const previous = anchors[anchors.length - 1];
      if (
        actual - previous.actual < MIN_ANCHOR_GAP ||
        canonical - previous.canonical < MIN_ANCHOR_GAP ||
        duration - actual < MIN_ANCHOR_GAP ||
        CANONICAL_FRAMES - canonical < MIN_ANCHOR_GAP
      ) continue;
      anchors.push({ actual, canonical });
    }
  }
  anchors.push({ actual: duration, canonical: CANONICAL_FRAMES });

  for (let index = 1; index < anchors.length; index++) {
    const right = anchors[index];
    if (frameLocal > right.actual) continue;
    const left = anchors[index - 1];
    const progress = (frameLocal - left.actual) / (right.actual - left.actual);
    return left.canonical + progress * (right.canonical - left.canonical);
  }
  return CANONICAL_FRAMES;
}
