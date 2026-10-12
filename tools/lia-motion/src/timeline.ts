export interface TimedScene<T> {
  scene: T;
  from: number;
  durationInFrames: number;
}

export function buildTimeline<T extends { durationSeconds: number }>(
  scenes: readonly T[],
  beats: readonly number[],
  fps: number
): TimedScene<T>[] {
  if (!Number.isFinite(fps) || fps <= 0) throw new RangeError('invalid frame rate');
  if (
    beats.some(
      (beat, index) => !Number.isFinite(beat) || beat < 0 || (index > 0 && beat < beats[index - 1])
    )
  ) {
    throw new RangeError('beats must be finite, ordered and nonnegative');
  }
  let cursor = 0;
  let editorialEnd = 0;
  return scenes.map(scene => {
    if (!Number.isFinite(scene.durationSeconds) || scene.durationSeconds <= 0)
      throw new RangeError('invalid scene duration');
    editorialEnd += scene.durationSeconds;
    const nearest = beats.reduce(
      (best, beat) => (Math.abs(beat - editorialEnd) < Math.abs(best - editorialEnd) ? beat : best),
      editorialEnd + 1
    );
    const end = Math.round(
      (Math.abs(nearest - editorialEnd) <= 0.4 ? nearest : editorialEnd) * fps
    );
    const entry = { scene, from: cursor, durationInFrames: Math.max(1, end - cursor) };
    cursor += entry.durationInFrames;
    return entry;
  });
}
