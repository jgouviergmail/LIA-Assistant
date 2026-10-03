/**
 * Beat-synced titles for the landing video (ADR-330).
 *
 * Two halves. `createBeatTrack` is pure: a beat map (offline analysis of the
 * soundtrack, `[ms, weight, bar]`) and a playback time give ONE intensity in
 * [0, 1] — a 40 ms attack on the beat, an exponential release, a bar beat a
 * quarter stronger. `startBeatDriver` runs it against a playing video and
 * writes the intensity as `--beat` on a host element; CSS does the rest with
 * `transform` alone.
 *
 * Why the presented frame's clock rather than an audio analysis: the browser
 * keeps the picture aligned with the sound it outputs, output latency
 * included, so a title driven by the frame's `mediaTime` is as synchronous
 * as the picture is — and a FFT of the output would follow the loudness,
 * voice included, a frame late. `requestVideoFrameCallback` hands the
 * presented frame's media time; between two frames (24 fps) the driver
 * extrapolates on the monotonic clock. Without it (Firefox), `currentTime`.
 */

import type { BeatMap } from './beats-schema';

/**
 * Rise from the beat's instant to its peak: near-instant, so the eye sees the
 * hit ON the drum. 40 ms read late against the sound (a percussive visual
 * wants an attack and a release, not a swell).
 */
export const BEAT_ATTACK_MS = 12;
/**
 * What a frame callback writes is painted at the NEXT vsync: the value is
 * computed one display frame ahead (60 Hz) so the pulse lands with the frame
 * that shows the beat, not the one after.
 */
export const BEAT_PAINT_LEAD_MS = 16;
/** Time constant of the release after the peak. */
export const BEAT_DECAY_MS = 180;
/** A bar's first beat is lifted by this factor (clamped to 1). */
export const BEAT_BAR_GAIN = 1.25;
/** A change smaller than this is not written to the DOM. */
export const BEAT_WRITE_EPSILON = 0.005;
/**
 * The share of the full amplitude the QUIETEST beat still pulses at. The map's
 * weights are onset strengths scaled to their 95th percentile, so most beats
 * sit at 0.3–0.7: driven by the raw weight, the titles trembled on the loud
 * hits and barely moved otherwise (measured: peaks of 1.6 % where 4 % was
 * allowed). A beat is a beat — the floor keeps every one visible, the weight
 * only grades them (owner request for a more marked movement, 2026-10-01).
 */
export const BEAT_WEIGHT_FLOOR = 0.6;
/**
 * The hue drift of the signature gradient (effect J): a sine of this amplitude,
 * in degrees, over a cycle of `BEAT_HUE_CYCLE_BARS` bars — zero on the first
 * bar of the cycle, the full swing a quarter cycle in. Locked on the bars so
 * the colour breathes with the music's own phrase, never with the clock.
 */
export const BEAT_HUE_DEGREES = 8;
export const BEAT_HUE_CYCLE_BARS = 4;
/** A hue change smaller than this (degrees) is not written to the DOM. */
export const BEAT_HUE_WRITE_EPSILON = 0.05;
/**
 * The hero title's three lines beat IN TURN rather than together (owner
 * request, 2026-10-02): beat n of the map lifts line n mod `BEAT_TURNS`, and
 * each line keeps its OWN release — the envelope of the last beat that was
 * its turn — so a line handing over to the next never snaps back to rest.
 * Counted on the map's index, so a seek lands on the same line every time.
 */
export const BEAT_TURNS = 3;

export interface BeatTrack {
  /** The number of beats of the map. */
  readonly size: number;
  /** The title intensity at a playback time, in seconds, in [0, 1]. */
  intensityAt(seconds: number): number;
  /** The same envelope, from the bar beats ALONE — for what should pulse once a bar. */
  barIntensityAt(seconds: number): number;
  /** The hue drift at a playback time, in degrees, on the cycle of bars. */
  hueAt(seconds: number): number;
  /**
   * How far the piece is between two beats, in [0, 1]: 0 on a beat, 1 just
   * before the next — the arc of a jump that lands on the drum.
   */
  progressAt(seconds: number): number;
  /**
   * The envelope of the last beat whose turn is `turn` (index mod
   * `BEAT_TURNS`), in [0, 1] — silent until that turn has come once.
   */
  turnIntensityAt(seconds: number, turn: number): number;
}

type Beat = BeatMap['beats'][number];

/** The index of the last instant at or before `ms`, −1 when none (binary search). */
function lastAtOrBefore(times: readonly number[], ms: number): number {
  let low = 0;
  let high = times.length - 1;
  let found = -1;
  while (low <= high) {
    const mid = (low + high) >> 1;
    if (times[mid] <= ms) {
      found = mid;
      low = mid + 1;
    } else {
      high = mid - 1;
    }
  }
  return found;
}

/** The pulse of `beat` seen `ms` into the piece: attack, then release, in [0, 1]. */
function pulseOf(beat: Beat, ms: number): number {
  const [at, weight, bar] = beat;
  const elapsed = ms - at;
  const envelope =
    elapsed <= BEAT_ATTACK_MS
      ? elapsed / BEAT_ATTACK_MS
      : Math.exp(-(elapsed - BEAT_ATTACK_MS) / BEAT_DECAY_MS);
  const strength = BEAT_WEIGHT_FLOOR + (1 - BEAT_WEIGHT_FLOOR) * weight;
  return Math.min(1, strength * (bar ? BEAT_BAR_GAIN : 1) * envelope);
}

export function createBeatTrack(map: BeatMap): BeatTrack {
  const { beats } = map;
  const times = beats.map(beat => beat[0]);
  const bars = beats.filter(beat => beat[2]);
  const barTimes = bars.map(beat => beat[0]);

  return {
    size: beats.length,
    intensityAt(seconds: number): number {
      const ms = seconds * 1000;
      const index = lastAtOrBefore(times, ms);
      return index < 0 ? 0 : pulseOf(beats[index], ms);
    },
    barIntensityAt(seconds: number): number {
      const ms = seconds * 1000;
      const index = lastAtOrBefore(barTimes, ms);
      return index < 0 ? 0 : pulseOf(bars[index], ms);
    },
    hueAt(seconds: number): number {
      const ms = seconds * 1000;
      const index = lastAtOrBefore(barTimes, ms);
      if (index < 0) return 0;
      // The bar's length: the next bar's distance, or past the last bar the
      // previous one's — the drift goes on, it never jumps. A lone bar has no
      // length: the drift stays at its origin.
      const start = barTimes[index];
      const length =
        index + 1 < barTimes.length
          ? barTimes[index + 1] - start
          : index > 0
            ? start - barTimes[index - 1]
            : 0;
      const progress = length > 0 ? Math.min(1, (ms - start) / length) : 0;
      const phase = (index + progress) / BEAT_HUE_CYCLE_BARS;
      return BEAT_HUE_DEGREES * Math.sin(2 * Math.PI * phase);
    },
    progressAt(seconds: number): number {
      const ms = seconds * 1000;
      const index = lastAtOrBefore(times, ms);
      if (index < 0) return 0;
      // The interval to the next beat; past the last beat the previous one's
      // length, so the arc goes on once and lands for good. A lone beat has
      // no interval: the piece stays on the ground.
      const start = times[index];
      const length =
        index + 1 < times.length
          ? times[index + 1] - start
          : index > 0
            ? start - times[index - 1]
            : 0;
      return length > 0 ? Math.min(1, (ms - start) / length) : 0;
    },
    turnIntensityAt(seconds: number, turn: number): number {
      const ms = seconds * 1000;
      const index = lastAtOrBefore(times, ms);
      if (index < 0) return 0;
      // Walk back to the latest beat of this turn: at most BEAT_TURNS - 1 steps.
      const back = (((index - turn) % BEAT_TURNS) + BEAT_TURNS) % BEAT_TURNS;
      const own = index - back;
      return own < 0 ? 0 : pulseOf(beats[own], ms);
    },
  };
}

interface VideoFrameMetadataLike {
  mediaTime: number;
  /** When the frame holding `mediaTime` is shown — the anchor, when the browser says it. */
  expectedDisplayTime?: number;
}

type FrameClockVideo = HTMLVideoElement & {
  requestVideoFrameCallback?: (
    callback: (now: DOMHighResTimeStamp, metadata: VideoFrameMetadataLike) => void
  ) => number;
  cancelVideoFrameCallback?: (handle: number) => void;
};

export interface BeatDriverOptions {
  /** The monotonic clock the frame times are compared against (`performance.now`). */
  clock?: () => number;
  /** How far ahead of the clock the written value is computed (`BEAT_PAINT_LEAD_MS`). */
  paintLeadMs?: number;
}

/**
 * Drive `--beat`, `--beat-bar`, `--beat-hue`, `--beat-progress` and the
 * per-turn `--beat-turn-<n>` (n < `BEAT_TURNS`) on `host` from `video`'s
 * playback until the returned function is called. `host`
 * carries `data-beat` while the driver runs, so a stylesheet can scope the
 * choreography to that state alone.
 */
export function startBeatDriver(
  video: HTMLVideoElement,
  host: HTMLElement,
  track: BeatTrack,
  options: BeatDriverOptions = {}
): () => void {
  const clock = options.clock ?? (() => performance.now());
  const paintLeadMs = options.paintLeadMs ?? BEAT_PAINT_LEAD_MS;
  const frameVideo = video as FrameClockVideo;
  const hasFrameClock = typeof frameVideo.requestVideoFrameCallback === 'function';
  let stopped = false;
  let anchorMediaTime = video.currentTime;
  let anchorClock = clock();
  let frameHandle = 0;
  let rafHandle = 0;
  let written = -1;
  let writtenBar = -1;
  let writtenHue = Number.NaN;
  let writtenProgress = -1;
  const writtenTurns = Array.from({ length: BEAT_TURNS }, () => -1);

  const onFrame = (now: DOMHighResTimeStamp, metadata: VideoFrameMetadataLike): void => {
    anchorMediaTime = metadata.mediaTime;
    anchorClock = metadata.expectedDisplayTime ?? now;
    if (!stopped && frameVideo.requestVideoFrameCallback) {
      frameHandle = frameVideo.requestVideoFrameCallback(onFrame);
    }
  };

  const playbackTime = (): number => {
    if (!hasFrameClock || video.paused) return video.currentTime + paintLeadMs / 1000;
    const elapsedMs = clock() - anchorClock + paintLeadMs;
    return anchorMediaTime + (elapsedMs / 1000) * video.playbackRate;
  };

  const tick = (): void => {
    if (stopped) return;
    const at = playbackTime();
    const value = track.intensityAt(at);
    if (Math.abs(value - written) > BEAT_WRITE_EPSILON) {
      host.style.setProperty('--beat', value.toFixed(3));
      written = value;
    }
    const bar = track.barIntensityAt(at);
    if (Math.abs(bar - writtenBar) > BEAT_WRITE_EPSILON) {
      host.style.setProperty('--beat-bar', bar.toFixed(3));
      writtenBar = bar;
    }
    const hue = track.hueAt(at);
    if (!(Math.abs(hue - writtenHue) <= BEAT_HUE_WRITE_EPSILON)) {
      host.style.setProperty('--beat-hue', `${hue.toFixed(2)}deg`);
      writtenHue = hue;
    }
    const progress = track.progressAt(at);
    if (Math.abs(progress - writtenProgress) > BEAT_WRITE_EPSILON) {
      host.style.setProperty('--beat-progress', progress.toFixed(3));
      writtenProgress = progress;
    }
    for (let turn = 0; turn < BEAT_TURNS; turn++) {
      const value = track.turnIntensityAt(at, turn);
      if (Math.abs(value - writtenTurns[turn]) > BEAT_WRITE_EPSILON) {
        host.style.setProperty(`--beat-turn-${turn}`, value.toFixed(3));
        writtenTurns[turn] = value;
      }
    }
    rafHandle = requestAnimationFrame(tick);
  };

  host.setAttribute('data-beat', '');
  if (hasFrameClock && frameVideo.requestVideoFrameCallback) {
    frameHandle = frameVideo.requestVideoFrameCallback(onFrame);
  }
  rafHandle = requestAnimationFrame(tick);

  return () => {
    if (stopped) return;
    stopped = true;
    cancelAnimationFrame(rafHandle);
    if (frameHandle && frameVideo.cancelVideoFrameCallback) {
      frameVideo.cancelVideoFrameCallback(frameHandle);
    }
    host.style.removeProperty('--beat');
    host.style.removeProperty('--beat-bar');
    host.style.removeProperty('--beat-hue');
    host.style.removeProperty('--beat-progress');
    for (let turn = 0; turn < BEAT_TURNS; turn++) {
      host.style.removeProperty(`--beat-turn-${turn}`);
    }
    host.removeAttribute('data-beat');
  };
}
