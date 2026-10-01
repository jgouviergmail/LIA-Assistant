import { describe, expect, it } from 'vitest';

import {
  CHUNK_SAMPLES,
  EMBEDDING_DIM,
  EMBEDDINGS,
  MEL_BINS,
  MEL_WINDOW,
  WakeWordEngine,
  type WakeWordRuntime,
} from '../engine';
import type { WakeCommand } from '../commands';
import { DetectionPolicy } from '../policy';

/**
 * A deterministic stand-in for the three ONNX stages: each output is a plain
 * function of its input, so two streams agree exactly when the engine handed
 * the stages the same inputs. It also records what each stage received.
 */
class FakeRuntime implements WakeWordRuntime {
  readonly melInputs: number[] = [];
  readonly classifyInputs: Float32Array[] = [];
  readonly commandInputs: Array<{ command: WakeCommand; features: Float32Array }> = [];
  constructor(
    private readonly score: (features: Float32Array) => number = () => 0,
    private readonly commandScore: (command: WakeCommand, features: Float32Array) => number = () =>
      0
  ) {}

  async melspectrogram(samples: Float32Array): Promise<Float32Array> {
    this.melInputs.push(samples.length);
    const frames = 1 + Math.floor((samples.length - 512) / 160);
    const out = new Float32Array(frames * MEL_BINS);
    for (let f = 0; f < frames; f += 1) {
      let sum = 0;
      for (let i = 0; i < 512; i += 1) sum += samples[f * 160 + i];
      for (let b = 0; b < MEL_BINS; b += 1) out[f * MEL_BINS + b] = sum / 512 + b;
    }
    return out;
  }

  async embed(window: Float32Array): Promise<Float32Array> {
    expect(window.length).toBe(MEL_WINDOW * MEL_BINS);
    const out = new Float32Array(EMBEDDING_DIM);
    for (let i = 0; i < window.length; i += 1) out[i % EMBEDDING_DIM] += window[i] * ((i % 7) + 1);
    return out;
  }

  async classify(features: Float32Array): Promise<number> {
    expect(features.length).toBe(EMBEDDINGS * EMBEDDING_DIM);
    this.classifyInputs.push(features.slice());
    return this.score(features);
  }

  async classifyCommand(command: WakeCommand, features: Float32Array): Promise<number> {
    this.commandInputs.push({ command, features: features.slice() });
    return this.commandScore(command, features);
  }
}

const policy = (threshold = 0.5) =>
  new DetectionPolicy({ threshold, patience: 1, refractoryChunks: 25, warmupChunks: 25 });

function noise(samples: number, seed = 1): Int16Array {
  let state = seed;
  return Int16Array.from({ length: samples }, () => {
    state = (state * 1103515245 + 12345) & 0x7fffffff;
    return (state % 6000) - 3000;
  });
}

describe('WakeWordEngine', () => {
  it('scores one chunk per 1 280 samples, whatever the push sizes', async () => {
    const audio = noise(CHUNK_SAMPLES * 40 + 300);
    const whole = new FakeRuntime(f => f[0]);
    const pieces = new FakeRuntime(f => f[0]);
    const one = new WakeWordEngine(whole, policy());
    const many = new WakeWordEngine(pieces, policy());

    const a = await one.push(audio);
    const b: number[] = [];
    for (let i = 0; i < audio.length; i += 333) {
      for (const result of await many.push(audio.subarray(i, i + 333))) b.push(result.score);
    }
    expect(a).toHaveLength(40);
    expect(b).toEqual(a.map(result => result.score));
    expect(pieces.classifyInputs).toEqual(whole.classifyInputs);
  });

  it('computes the mel of the last 1 760 samples — 1 280 for the very first chunk', async () => {
    const runtime = new FakeRuntime();
    const engine = new WakeWordEngine(runtime, policy());
    await engine.push(noise(CHUNK_SAMPLES * 3));
    expect(runtime.melInputs).toEqual([1280, 1760, 1760]);
  });

  it('starts every classifier window from zeros and the mel window from ones', async () => {
    const runtime = new FakeRuntime();
    const engine = new WakeWordEngine(runtime, policy());
    await engine.push(new Int16Array(CHUNK_SAMPLES));
    const first = runtime.classifyInputs[0];
    // fifteen seeded embeddings, then the first real one in the last slot
    expect(Array.from(first.subarray(0, 15 * EMBEDDING_DIM)).every(v => v === 0)).toBe(true);
    expect(Array.from(first.subarray(15 * EMBEDDING_DIM)).some(v => v !== 0)).toBe(true);
  });

  it('never detects during the warm-up, then detects and goes quiet for the refractory period', async () => {
    const engine = new WakeWordEngine(new FakeRuntime(() => 0.9), policy());
    const results = await engine.push(noise(CHUNK_SAMPLES * 60));
    const detections = results.flatMap((result, index) => (result.detected ? [index + 1] : []));
    expect(detections).toEqual([25, 51]);
  });

  it('reset() gives the same scores for the same audio as a new engine', async () => {
    const audio = noise(CHUNK_SAMPLES * 30, 7);
    const runtime = new FakeRuntime(f => f[3]);
    const engine = new WakeWordEngine(runtime, policy());
    const first = await engine.push(audio);
    await engine.push(noise(CHUNK_SAMPLES * 5, 9));
    engine.reset();
    const again = await engine.push(audio);
    expect(again.map(r => r.score)).toEqual(first.map(r => r.score));
  });

  it('a reset asked while a push is in flight applies after it, never in its middle', async () => {
    // The worker handles messages concurrently: a `reset` may arrive while a
    // chunk awaits a stage. Applied mid-chunk, the stale chunk would land in the
    // fresh windows and count as the first chunk of the warm-up.
    const audio = noise(CHUNK_SAMPLES * 30, 11);
    const reference = await new WakeWordEngine(new FakeRuntime(f => f[2]), policy()).push(audio);

    const runtime = new FakeRuntime(f => f[2]);
    const engine = new WakeWordEngine(runtime, policy());
    const stale = engine.push(noise(CHUNK_SAMPLES * 4, 5));
    engine.reset();
    const fresh = engine.push(audio);
    await stale;
    expect((await fresh).map(r => r.score)).toEqual(reference.map(r => r.score));
  });

  it('processes concurrent pushes in order, never interleaved', async () => {
    const audio = noise(CHUNK_SAMPLES * 12, 3);
    const sequential = new WakeWordEngine(new FakeRuntime(f => f[5]), policy());
    const expected = await sequential.push(audio);

    const concurrent = new WakeWordEngine(new FakeRuntime(f => f[5]), policy());
    const parts = [0, 1, 2, 3].map(i =>
      audio.subarray(i * 3 * CHUNK_SAMPLES, (i + 1) * 3 * CHUNK_SAMPLES)
    );
    const results = (await Promise.all(parts.map(part => concurrent.push(part)))).flat();
    expect(results.map(r => r.score)).toEqual(expected.map(r => r.score));
  });
});

describe('WakeWordEngine — spoken commands', () => {
  const commandIndices = (results: Array<{ commands: WakeCommand[] }>) =>
    results.flatMap((result, index) => (result.commands.includes('stop') ? [index + 1] : []));

  it('scores a command on the very embeddings the phrase is scored on', async () => {
    const runtime = new FakeRuntime(f => f[1]);
    const engine = new WakeWordEngine(runtime, policy(), { stop: policy() });
    await engine.push(noise(CHUNK_SAMPLES * 5, 13));
    // One embedding pass serves both: the command adds a classifier, never a stage.
    expect(runtime.melInputs).toHaveLength(5);
    expect(runtime.commandInputs.map(input => input.command)).toEqual(Array(5).fill('stop'));
    expect(runtime.commandInputs.map(input => input.features)).toEqual(runtime.classifyInputs);
  });

  it('detects a command under its own policy, and never as the phrase', async () => {
    const runtime = new FakeRuntime(
      () => 0,
      () => 0.9
    );
    const engine = new WakeWordEngine(runtime, policy(), { stop: policy() });
    const results = await engine.push(noise(CHUNK_SAMPLES * 60));
    expect(commandIndices(results)).toEqual([25, 51]);
    expect(results.some(result => result.detected)).toBe(false);
  });

  it('never reports the phrase as a command', async () => {
    const engine = new WakeWordEngine(new FakeRuntime(() => 0.9), policy(), { stop: policy() });
    const results = await engine.push(noise(CHUNK_SAMPLES * 30));
    expect(commandIndices(results)).toEqual([]);
    expect(results.filter(result => result.detected)).toHaveLength(1);
  });

  it("restarts a command's warm-up on reset, like the phrase's", async () => {
    const engine = new WakeWordEngine(
      new FakeRuntime(
        () => 0,
        () => 0.9
      ),
      policy(),
      { stop: policy() }
    );
    await engine.push(noise(CHUNK_SAMPLES * 30));
    engine.reset();
    expect(commandIndices(await engine.push(noise(CHUNK_SAMPLES * 30)))).toEqual([25]);
  });

  it('scores no command when the model ships none', async () => {
    const runtime = new FakeRuntime();
    const results = await new WakeWordEngine(runtime, policy()).push(noise(CHUNK_SAMPLES * 3));
    expect(runtime.commandInputs).toEqual([]);
    expect(results.every(result => result.commands.length === 0)).toBe(true);
  });
});
