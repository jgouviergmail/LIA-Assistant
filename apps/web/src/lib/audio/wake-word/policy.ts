/**
 * When a score becomes a detection (ADR-329) — the rule the toolbox measured the
 * model under (`scripts/wake-word/wakeword/features.py::Policy`), chunk by chunk.
 *
 * A chunk fires when it and the `patience - 1` chunks before it reached the
 * threshold, none of them inside the warm-up (the first chunks whose classifier
 * input still holds the engine's seeded state), and the last detection is more
 * than `refractoryChunks` back: one phrase, one wake. The golden fixture holds
 * this implementation and the toolbox's to the same detections.
 */

export interface DetectionPolicyOptions {
  threshold: number;
  patience: number;
  refractoryChunks: number;
  warmupChunks: number;
}

export class DetectionPolicy {
  private chunk = 0;
  private run = 0;
  private lastDetection = Number.NEGATIVE_INFINITY;

  constructor(private readonly options: DetectionPolicyOptions) {}

  /** The next chunk's score; true when this chunk is a detection. */
  push(score: number): boolean {
    this.chunk += 1;
    if (this.chunk < this.options.warmupChunks) return false;
    this.run = score >= this.options.threshold ? this.run + 1 : 0;
    if (this.chunk - this.lastDetection <= this.options.refractoryChunks) return false;
    if (this.run < this.options.patience) return false;
    // `run` is NOT reset: it counts consecutive chunks above the threshold,
    // which a detection does not interrupt (the toolbox's sliding window).
    this.lastDetection = this.chunk;
    return true;
  }

  /** A new stream: the warm-up starts again, no detection is remembered. */
  reset(): void {
    this.chunk = 0;
    this.run = 0;
    this.lastDetection = Number.NEGATIVE_INFINITY;
  }
}
