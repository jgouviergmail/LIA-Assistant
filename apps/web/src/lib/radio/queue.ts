/**
 * The player's queue: which segment airs next, which to fetch ahead, which line
 * is being spoken — pure functions over what the API reported.
 *
 * Segments air in ascending order of their place in the session. A place the
 * server never delivered (a segment it could not produce) is simply skipped:
 * the next READY segment after the last one played is the next to air.
 */
import type { RadioSegment, RadioTranscriptLine } from './types';

/** The ready segments merged with a report's, one per place, ascending, unplayed only. */
export function mergeSegments(
  known: readonly RadioSegment[],
  reported: readonly RadioSegment[],
  lastPlayed: number
): RadioSegment[] {
  const bySeq = new Map<number, RadioSegment>();
  for (const segment of [...known, ...reported]) {
    if (segment.seq > lastPlayed) bySeq.set(segment.seq, segment);
  }
  return [...bySeq.values()].sort((a, b) => a.seq - b.seq);
}

/** The next segment to air after `lastPlayed`, if one is ready. */
export function nextSegment(
  queue: readonly RadioSegment[],
  lastPlayed: number
): RadioSegment | null {
  return queue.find(segment => segment.seq > lastPlayed) ?? null;
}

/** The index of the line being spoken at `position_s`, or -1 before the first word. */
export function lineAt(lines: readonly RadioTranscriptLine[], position_s: number): number {
  let current = -1;
  lines.forEach((line, index) => {
    if (line.offset_s <= position_s) current = index;
  });
  return current;
}
