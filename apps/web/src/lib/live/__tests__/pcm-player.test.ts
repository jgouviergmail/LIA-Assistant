/**
 * PcmStreamPlayer — ONE worklet reading a queue of chunks continuously
 * (the shape that sidesteps Chrome 152's repeated render block on a
 * scheduled chunk start), instant flush on interruption.
 *
 *  - the worklet source itself: chunks at 24 kHz come out at the context's
 *    48 kHz as a CONTINUOUS ramp across the chunk boundary (no scheduling, no
 *    per-chunk resampling edge), silence when the queue is empty, ONE
 *    `drained` report naming the last chunk once the queue ran dry, and a
 *    flush that empties everything at once;
 *  - the main thread: the context is opened and resumed on the gesture and
 *    the module loaded ONCE; a chunk is converted to floats and TRANSFERRED
 *    with a sequence number; `isSpeaking` rises on the first chunk and falls
 *    on the worklet's report for the LAST chunk handed over — a report about
 *    an older chunk is ignored; a chunk before `warmup()` is dropped, never
 *    thrown on; `dispose()` closes the context and reports nothing further.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import {
  PCM_PLAYER_PROCESSOR_NAME,
  PcmStreamPlayer,
  buildPcmPlayerWorkletSource,
} from '../pcm-player';

// -- the worklet, run outside any AudioWorklet global ---------------------------

interface ProcessorLike {
  port: {
    onmessage: ((event: { data: unknown }) => void) | null;
    postMessage: (m: unknown) => void;
  };
  process(inputs: Float32Array[][], outputs: Float32Array[][]): boolean;
}

/** Evaluate the shipped source with the worklet globals stubbed at `contextRate`. */
function instantiate(contextRate: number): { processor: ProcessorLike; posted: unknown[] } {
  const posted: unknown[] = [];
  const registered: Record<string, new () => ProcessorLike> = {};
  class AudioWorkletProcessor {
    port = {
      onmessage: null as ((event: { data: unknown }) => void) | null,
      postMessage: (m: unknown) => posted.push(m),
    };
  }
  const factory = new Function(
    'AudioWorkletProcessor',
    'registerProcessor',
    'sampleRate',
    buildPcmPlayerWorkletSource()
  );
  factory(
    AudioWorkletProcessor,
    (name: string, cls: new () => ProcessorLike) => {
      registered[name] = cls;
    },
    contextRate
  );
  const Processor = registered[PCM_PLAYER_PROCESSOR_NAME];
  return { processor: new Processor(), posted };
}

function render(processor: ProcessorLike, frames: number): Float32Array {
  const out = new Float32Array(frames);
  processor.process([], [[out]]);
  return out;
}

function ramp(from: number, count: number, step: number): Float32Array {
  return Float32Array.from({ length: count }, (_, i) => from + i * step);
}

describe('the worklet source', () => {
  it('reads 24 kHz chunks out at 48 kHz as one continuous ramp across the chunk boundary', () => {
    const { processor } = instantiate(48000);
    // Two chunks of a single ramp 0, 0.01, 0.02 … split in the middle.
    const first = ramp(0, 64, 0.01);
    const second = ramp(0.64, 64, 0.01);
    processor.port.onmessage?.({ data: { type: 'chunk', seq: 1, rate: 24000, samples: first } });
    processor.port.onmessage?.({ data: { type: 'chunk', seq: 2, rate: 24000, samples: second } });
    const out = render(processor, 256);
    // Every output step is half an input step: linear interpolation at 2×.
    for (let i = 1; i < 255; i++) expect(out[i] - out[i - 1]).toBeCloseTo(0.005, 6);
    // The boundary (input sample 64 = output 128) is on the same line.
    expect(out[128]).toBeCloseTo(0.64, 6);
    expect(out[127]).toBeCloseTo(0.635, 6);
  });

  it('is silent while the queue is empty, and reports the last chunk once drained', () => {
    const { processor, posted } = instantiate(48000);
    expect(Array.from(render(processor, 128))).toEqual(new Array(128).fill(0));
    expect(posted).toEqual([]);
    processor.port.onmessage?.({
      data: { type: 'chunk', seq: 7, rate: 24000, samples: ramp(0.5, 32, 0) },
    });
    // 32 samples at 24 kHz = 64 frames at 48 kHz: the first block holds them all.
    const block = render(processor, 128);
    expect(block[0]).toBeCloseTo(0.5, 6);
    expect(block[63]).toBeCloseTo(0.5, 6);
    expect(block[64]).toBe(0);
    expect(posted).toEqual([{ type: 'drained', seq: 7 }]);
    render(processor, 128);
    expect(posted).toHaveLength(1);
  });

  it('a flush drops everything handed over, at once', () => {
    const { processor, posted } = instantiate(48000);
    processor.port.onmessage?.({
      data: { type: 'chunk', seq: 1, rate: 24000, samples: ramp(0.3, 4800, 0) },
    });
    render(processor, 128);
    processor.port.onmessage?.({ data: { type: 'flush' } });
    expect(Array.from(render(processor, 128))).toEqual(new Array(128).fill(0));
    // Nothing was drained by the flush: the main thread already knows.
    expect(posted).toEqual([]);
  });

  it('follows the chunk rate: 16 kHz chunks are read at two thirds of a sample per frame at 24 kHz', () => {
    const { processor } = instantiate(24000);
    processor.port.onmessage?.({
      data: { type: 'chunk', seq: 1, rate: 16000, samples: ramp(0, 32, 0.03) },
    });
    const out = render(processor, 48);
    expect(out[3]).toBeCloseTo(0.06, 6); // frame 3 → input position 2.0
    expect(out[46]).toBeCloseTo((0.03 * (46 * 2)) / 3, 6); // position 30.667, between two samples
    // Past the last sample with no chunk behind it, the tail is HELD, never extrapolated.
    expect(out[47]).toBeCloseTo(0.93, 6);
  });
});

// -- the main thread -------------------------------------------------------------

class FakePort {
  onmessage: ((event: MessageEvent<unknown>) => void) | null = null;
  posted: Array<{ message: unknown; transfer: unknown[] | undefined }> = [];
  postMessage(message: unknown, transfer?: unknown[]) {
    this.posted.push({ message, transfer });
  }
  /** What the worklet would say once its queue ran dry after chunk `seq`. */
  drain(seq: number) {
    this.onmessage?.({ data: { type: 'drained', seq } } as MessageEvent<unknown>);
  }
}

class FakeWorkletNode {
  static instances: FakeWorkletNode[] = [];
  port = new FakePort();
  connected: unknown[] = [];
  disconnected = 0;
  constructor(
    public context: FakeAudioContext,
    public name: string,
    public options: unknown
  ) {
    FakeWorkletNode.instances.push(this);
  }
  connect(destination: unknown) {
    this.connected.push(destination);
  }
  disconnect() {
    this.disconnected += 1;
  }
}

class FakeAudioContext {
  static instances: FakeAudioContext[] = [];
  state: 'running' | 'suspended' | 'closed' = 'suspended';
  destination = { kind: 'destination' };
  readonly sampleRate = 48000;
  modules: string[] = [];
  closed = false;
  audioWorklet = { addModule: async (url: string) => void this.modules.push(url) };
  constructor() {
    FakeAudioContext.instances.push(this);
  }
  async resume() {
    this.state = 'running';
  }
  async close() {
    this.closed = true;
    this.state = 'closed';
  }
}

describe('PcmStreamPlayer', () => {
  const realContext = globalThis.AudioContext;
  const realNode = globalThis.AudioWorkletNode;
  const realCreate = URL.createObjectURL;
  beforeEach(() => {
    FakeAudioContext.instances = [];
    FakeWorkletNode.instances = [];
    (globalThis as { AudioContext: unknown }).AudioContext = FakeAudioContext;
    (globalThis as { AudioWorkletNode: unknown }).AudioWorkletNode = FakeWorkletNode;
    URL.createObjectURL = vi.fn(() => 'blob:lia/pcm-player');
  });
  afterEach(() => {
    (globalThis as { AudioContext: unknown }).AudioContext = realContext;
    (globalThis as { AudioWorkletNode: unknown }).AudioWorkletNode = realNode;
    URL.createObjectURL = realCreate;
  });

  it('opens the context on warmup, resumes it, loads the module once and wires one mono node', async () => {
    const player = new PcmStreamPlayer();
    await player.warmup();
    const context = FakeAudioContext.instances[0];
    expect(context.state).toBe('running');
    expect(context.modules).toEqual(['blob:lia/pcm-player']);
    const node = FakeWorkletNode.instances[0];
    expect(node.name).toBe(PCM_PLAYER_PROCESSOR_NAME);
    expect(node.options).toEqual({
      numberOfInputs: 0,
      numberOfOutputs: 1,
      outputChannelCount: [1],
    });
    expect(node.connected).toEqual([context.destination]);
    await player.warmup();
    expect(FakeAudioContext.instances).toHaveLength(1);
    expect(FakeWorkletNode.instances).toHaveLength(1);
    expect(context.modules).toHaveLength(1);
  });

  it('hands each chunk over as transferred floats with a sequence number, and flushes through the port', async () => {
    const player = new PcmStreamPlayer();
    await player.warmup();
    const port = FakeWorkletNode.instances[0].port;
    player.enqueue(new Int16Array([-32768, 0, 32767]).buffer, 24000);
    player.enqueue(new Int16Array([16384]).buffer, 24000);
    const first = port.posted[0].message as {
      type: string;
      seq: number;
      rate: number;
      samples: Float32Array;
    };
    expect(first.type).toBe('chunk');
    expect(first.seq).toBe(1);
    expect(first.rate).toBe(24000);
    expect(first.samples[0]).toBe(-1);
    expect(first.samples[1]).toBe(0);
    expect(first.samples[2]).toBeCloseTo(1, 3);
    expect(port.posted[0].transfer).toEqual([first.samples.buffer]);
    expect((port.posted[1].message as { seq: number }).seq).toBe(2);
    player.flush();
    expect(port.posted[2].message).toEqual({ type: 'flush' });
  });

  it('speaks from the first chunk until the worklet drained the LAST one; an older report is ignored', async () => {
    const player = new PcmStreamPlayer();
    const edges = vi.fn();
    player.onSpeakingChange(edges);
    await player.warmup();
    const port = FakeWorkletNode.instances[0].port;
    player.enqueue(new Int16Array(2400).buffer, 24000);
    player.enqueue(new Int16Array(2400).buffer, 24000);
    expect(player.isSpeaking).toBe(true);
    expect(edges).toHaveBeenCalledTimes(1);
    // The worklet ran dry after chunk 1 while chunk 2 was on its way: stale.
    port.drain(1);
    expect(player.isSpeaking).toBe(true);
    port.drain(2);
    expect(player.isSpeaking).toBe(false);
    expect(edges).toHaveBeenLastCalledWith(false);
    expect(edges).toHaveBeenCalledTimes(2);
    // A flush ends the speech at once, without waiting for any report.
    player.enqueue(new Int16Array(2400).buffer, 24000);
    expect(player.isSpeaking).toBe(true);
    player.flush();
    expect(player.isSpeaking).toBe(false);
  });

  it('drops a chunk before warmup and stops reporting after dispose', async () => {
    const player = new PcmStreamPlayer();
    const edges = vi.fn();
    player.onSpeakingChange(edges);
    player.enqueue(new Int16Array(240).buffer, 24000);
    expect(player.isSpeaking).toBe(false);
    expect(FakeAudioContext.instances).toHaveLength(0);
    await player.warmup();
    player.enqueue(new Int16Array(240).buffer, 24000);
    player.dispose();
    expect(FakeAudioContext.instances[0].closed).toBe(true);
    expect(FakeWorkletNode.instances[0].disconnected).toBe(1);
    expect(edges).toHaveBeenLastCalledWith(false);
    edges.mockClear();
    player.enqueue(new Int16Array(240).buffer, 24000);
    expect(edges).not.toHaveBeenCalled();
    expect(player.isSpeaking).toBe(false);
  });
});
