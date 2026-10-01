/**
 * The wake-word engine (ADR-329): openWakeWord's streaming arithmetic, exactly.
 *
 * Every 1 280 samples (80 ms at 16 kHz) of int16 audio:
 *
 * 1. the melspectrogram of the LAST 1 760 samples (1 280 for the very first
 *    chunk, which has nothing before it) — 8 frames of 32 bins, transformed by
 *    `x / 10 + 2`;
 * 2. the embedding of the last 76 mel frames — the mel window starts filled
 *    with ones, as openWakeWord's does;
 * 3. the classifier's score of the last 16 embeddings — the window starts
 *    filled with zeros (openWakeWord seeds it with random embeddings no other
 *    runtime can reproduce; the warm-up gate of the policy makes the
 *    difference unobservable);
 * 4. the detection policy.
 *
 * A spoken command (« Stop ») is one more classifier over the SAME window of
 * embeddings, under its own policy: it adds a small network per chunk, never a
 * stage, and the phrase and a command never answer for each other.
 *
 * The three stages are behind `WakeWordRuntime`, so the arithmetic is tested
 * with a fake and held to the toolbox's reference by the golden fixture with
 * the real models. Pushes and resets are serialised: a stage call is
 * asynchronous, and a chunk must never be processed before the one it follows.
 */
import { WAKE_COMMANDS, type WakeCommand } from './commands';
import type { DetectionPolicy } from './policy';

export const SAMPLE_RATE = 16_000;
export const CHUNK_SAMPLES = 1280;
export const MEL_LOOKBACK_SAMPLES = 480;
export const MEL_BINS = 32;
export const MEL_WINDOW = 76;
export const EMBEDDINGS = 16;
export const EMBEDDING_DIM = 96;

/** The three ONNX stages. */
export interface WakeWordRuntime {
  /** Raw melspectrogram of int16-valued samples: `frames × 32`, untransformed. */
  melspectrogram(samples: Float32Array): Promise<Float32Array>;
  /** One embedding (96 values) of a `76 × 32` mel window. */
  embed(window: Float32Array): Promise<Float32Array>;
  /** The score of a `16 × 96` window of embeddings. */
  classify(features: Float32Array): Promise<number>;
  /** A spoken command's score of the same window (only for commands its manifest ships). */
  classifyCommand(command: WakeCommand, features: Float32Array): Promise<number>;
}

export interface ChunkResult {
  score: number;
  detected: boolean;
  /** The spoken commands this chunk detected. */
  commands: WakeCommand[];
}

export class WakeWordEngine {
  private raw: Int16Array = new Int16Array(0);
  private pending: Int16Array = new Int16Array(0);
  private mel: Float32Array = new Float32Array(MEL_WINDOW * MEL_BINS).fill(1);
  private features: Float32Array = new Float32Array(EMBEDDINGS * EMBEDDING_DIM);
  private queue: Promise<unknown> = Promise.resolve();

  constructor(
    private readonly runtime: WakeWordRuntime,
    private readonly policy: DetectionPolicy,
    private readonly commands: Partial<Record<WakeCommand, DetectionPolicy>> = {}
  ) {}

  /** Feed samples of any length; one result per completed chunk, in order. */
  push(samples: Int16Array): Promise<ChunkResult[]> {
    const copy = samples.slice();
    const run = this.queue.then(() => this.process(copy));
    // A failed push must not poison every later one: the next waits on the
    // settled chain, the caller of this one still sees its error.
    this.queue = run.catch(() => undefined);
    return run;
  }

  /**
   * Back to the state of a new engine (the policy's warm-up restarts too),
   * queued behind the pushes already asked: a chunk in flight finishes on the
   * old state, never half on each.
   */
  reset(): void {
    this.queue = this.queue.then(() => {
      this.raw = new Int16Array(0);
      this.pending = new Int16Array(0);
      this.mel = new Float32Array(MEL_WINDOW * MEL_BINS).fill(1);
      this.features = new Float32Array(EMBEDDINGS * EMBEDDING_DIM);
      this.policy.reset();
      for (const policy of Object.values(this.commands)) policy.reset();
    });
  }

  private async process(samples: Int16Array): Promise<ChunkResult[]> {
    this.pending = concat(this.pending, samples);
    const results: ChunkResult[] = [];
    while (this.pending.length >= CHUNK_SAMPLES) {
      const chunk = this.pending.subarray(0, CHUNK_SAMPLES);
      this.pending = this.pending.slice(CHUNK_SAMPLES);
      results.push(await this.chunk(chunk));
    }
    return results;
  }

  private async chunk(chunk: Int16Array): Promise<ChunkResult> {
    this.raw = concat(this.raw, chunk).slice(-(CHUNK_SAMPLES + MEL_LOOKBACK_SAMPLES));
    const frames = await this.runtime.melspectrogram(Float32Array.from(this.raw));
    const transformed = frames.map(value => value / 10 + 2);
    this.mel = shiftIn(this.mel, transformed);
    const embedding = await this.runtime.embed(this.mel);
    this.features = shiftIn(this.features, embedding);
    const score = await this.runtime.classify(this.features);
    const commands: WakeCommand[] = [];
    for (const command of WAKE_COMMANDS) {
      const policy = this.commands[command];
      if (policy && policy.push(await this.runtime.classifyCommand(command, this.features))) {
        commands.push(command);
      }
    }
    return { score, detected: this.policy.push(score), commands };
  }
}

function concat(a: Int16Array, b: Int16Array): Int16Array {
  const out = new Int16Array(a.length + b.length);
  out.set(a);
  out.set(b, a.length);
  return out;
}

/** Append `values` and drop as many from the front: a fixed-size window. */
function shiftIn(window: Float32Array, values: Float32Array): Float32Array {
  const out = new Float32Array(window.length);
  const kept = Math.max(0, window.length - values.length);
  out.set(window.subarray(window.length - kept));
  out.set(values.subarray(Math.max(0, values.length - window.length)), kept);
  return out;
}
