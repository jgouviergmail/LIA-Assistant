/**
 * The film cuts can follow every percussion transient; the landing companion
 * needs time to finish a hop. Keep a roughly one-second gesture, always landing
 * on a measured attack, with at least 900 ms between two landings. Do not infer
 * musical bars from the dense transient count: every fourth gesture is simply
 * a visual accent. This map never changes the film or the soundtrack.
 */
export function landingBeats(onsets: readonly number[]): [number, number, boolean][] {
  const times = [
    ...new Set(onsets.filter(t => Number.isFinite(t) && t >= 0).map(t => Math.round(t * 1000))),
  ].sort((a, b) => a - b);
  const selected: number[] = [];
  let cursor = 0;
  while (cursor < times.length) {
    const previous = selected.at(-1);
    if (previous === undefined) {
      selected.push(times[cursor++]);
      continue;
    }
    while (cursor < times.length && times[cursor] - previous < 900) cursor++;
    if (cursor === times.length) break;
    let best = cursor;
    const target = previous + 1000;
    for (let i = cursor + 1; i < times.length && times[i] <= target + 100; i++) {
      if (Math.abs(times[i] - target) < Math.abs(times[best] - target)) best = i;
    }
    selected.push(times[best]);
    cursor = best + 1;
  }
  return selected.map((ms, i) => [ms, .7, i % 4 === 0]);
}
