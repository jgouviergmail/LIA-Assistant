/**
 * "Still recording?" — the guard against the forgotten stop (ADR-258).
 *
 * A recording nobody stops keeps uploading silence for hours, and the minutes
 * it produces are billed by the audio hour. The watchdog watches the level the
 * source reports and, after `promptAfterMs` of continuous silence, asks ONCE
 * whether to continue; a reply (continue) rearms it, speech resets it.
 *
 * Pure and clock-injected so the two-hour path is a unit test, not a wait.
 */

export type WatchdogVerdict = 'speech' | 'silence' | 'prompt';

export interface SilenceWatchdogOptions {
  /** RMS below which a reading counts as silence. */
  thresholdRms: number;
  /** Continuous silence before the prompt fires. */
  promptAfterMs: number;
}

export class SilenceWatchdog {
  private silentSince: number | null = null;
  private prompted = false;

  constructor(private readonly options: SilenceWatchdogOptions) {}

  /**
   * Feed one level reading.
   *
   * @param rms - Level in [0, 1].
   * @param nowMs - Monotonic clock, milliseconds.
   * @returns `'prompt'` exactly once per silent stretch, `'silence'` while
   *   silent, `'speech'` otherwise.
   */
  feed(rms: number, nowMs: number): WatchdogVerdict {
    if (rms >= this.options.thresholdRms) {
      this.silentSince = null;
      this.prompted = false;
      return 'speech';
    }
    if (this.silentSince === null) this.silentSince = nowMs;
    if (!this.prompted && nowMs - this.silentSince >= this.options.promptAfterMs) {
      this.prompted = true;
      return 'prompt';
    }
    return 'silence';
  }

  /** The user chose to continue: measure a fresh stretch from now. */
  acknowledge(nowMs: number): void {
    this.silentSince = nowMs;
    this.prompted = false;
  }

  /** Milliseconds of continuous silence so far, for the banner. */
  silentFor(nowMs: number): number {
    return this.silentSince === null ? 0 : nowMs - this.silentSince;
  }
}
