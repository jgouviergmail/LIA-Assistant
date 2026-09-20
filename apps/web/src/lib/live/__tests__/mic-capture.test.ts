/**
 * startMicCapture — 16 kHz int16 chunks from the shared worklet, mutable, stoppable.
 *
 *  - the worklet is loaded at the LIVE chunk size, never the push-to-talk's;
 *  - chunks reach the caller while unmuted and are dropped while muted;
 *  - `stop()` releases the track, the node and the context, in that order;
 *  - a refused microphone rejects with the browser's own error (the caller
 *    names the outcome `mic_denied`), and nothing is left open.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

const SAMPLE_RATE = 16000;
const CHUNK_SAMPLES = 640;

import { startMicCapture } from '../mic-capture';

const track = { stop: vi.fn(), enabled: true };
const stream = { getTracks: () => [track], getAudioTracks: () => [track] };
let port: { onmessage: ((e: { data: ArrayBuffer }) => void) | null };
let workletUrls: string[];
let contexts: FakeContext[];

class FakeWorkletNode {
  port = port;
  connect = vi.fn();
  disconnect = vi.fn();
  constructor(
    readonly context: unknown,
    readonly name: string
  ) {}
}

class FakeContext {
  audioWorklet = {
    addModule: vi.fn(async (url: string) => {
      workletUrls.push(url);
    }),
  };
  source = { connect: vi.fn(), disconnect: vi.fn() };
  createMediaStreamSource = vi.fn(() => this.source);
  close = vi.fn(async () => {});
  constructor(readonly options?: { sampleRate?: number }) {
    contexts.push(this);
  }
}

describe('startMicCapture', () => {
  const g = globalThis as Record<string, unknown>;
  const real = { AudioContext: g.AudioContext, AudioWorkletNode: g.AudioWorkletNode };
  const realCreateObjectURL = URL.createObjectURL;
  beforeEach(() => {
    port = { onmessage: null };
    workletUrls = [];
    contexts = [];
    g.AudioContext = FakeContext;
    g.AudioWorkletNode = FakeWorkletNode;
    URL.createObjectURL = () => `blob:chunk-${Date.now()}`;
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: { getUserMedia: vi.fn(async () => stream) },
    });
  });
  afterEach(() => {
    g.AudioContext = real.AudioContext;
    g.AudioWorkletNode = real.AudioWorkletNode;
    URL.createObjectURL = realCreateObjectURL;
    track.stop.mockClear();
  });

  it('delivers chunks, drops them while muted, releases everything on stop', async () => {
    const onChunk = vi.fn();
    const capture = await startMicCapture({
      sampleRate: SAMPLE_RATE,
      chunkSamples: CHUNK_SAMPLES,
      onChunk,
    });
    expect(contexts[0].options?.sampleRate).toBe(SAMPLE_RATE);
    expect(capture.stream).toBe(stream);
    expect(workletUrls).toHaveLength(1);
    const chunk = new Int16Array(CHUNK_SAMPLES).buffer;
    port.onmessage?.({ data: chunk });
    expect(onChunk).toHaveBeenCalledWith(chunk);
    capture.mute(true);
    port.onmessage?.({ data: chunk });
    expect(onChunk).toHaveBeenCalledTimes(1);
    capture.mute(false);
    port.onmessage?.({ data: chunk });
    expect(onChunk).toHaveBeenCalledTimes(2);
    await capture.stop();
    expect(track.stop).toHaveBeenCalledTimes(1);
    expect(contexts[0].source.disconnect).toHaveBeenCalled();
    expect(contexts[0].close).toHaveBeenCalled();
    port.onmessage?.({ data: chunk });
    expect(onChunk).toHaveBeenCalledTimes(2);
  });

  it('propagates a refused microphone and opens nothing', async () => {
    const denied = Object.assign(new Error('denied'), { name: 'NotAllowedError' });
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: { getUserMedia: vi.fn(async () => Promise.reject(denied)) },
    });
    await expect(
      startMicCapture({ sampleRate: SAMPLE_RATE, chunkSamples: CHUNK_SAMPLES, onChunk: vi.fn() })
    ).rejects.toBe(denied);
    expect(contexts).toHaveLength(0);
  });

  it('opens the microphone alone, no worklet, for a transport that carries the audio', async () => {
    // A native transport (WebRTC) takes the STREAM; a mute disables the track
    // rather than dropping chunks, and stop still releases the track.
    track.enabled = true;
    const capture = await startMicCapture({
      sampleRate: 24000,
      chunkSamples: 480,
      onChunk: vi.fn(),
      pcm: false,
    });
    expect(contexts).toHaveLength(0);
    expect(workletUrls).toHaveLength(0);
    expect(capture.stream).toBe(stream);
    capture.mute(true);
    expect(track.enabled).toBe(false);
    capture.mute(false);
    expect(track.enabled).toBe(true);
    await capture.stop();
    expect(track.stop).toHaveBeenCalledTimes(1);
  });

  it('releases the track when the worklet fails to load', async () => {
    const failing = class extends FakeContext {
      audioWorklet = { addModule: vi.fn(async () => Promise.reject(new Error('no worklet'))) };
    };
    g.AudioContext = failing;
    await expect(
      startMicCapture({ sampleRate: SAMPLE_RATE, chunkSamples: CHUNK_SAMPLES, onChunk: vi.fn() })
    ).rejects.toThrow('no worklet');
    expect(track.stop).toHaveBeenCalledTimes(1);
    expect(contexts[0].close).toHaveBeenCalled();
  });

  it('releases the track when the audio context itself refuses the rate', async () => {
    // `new AudioContext({ sampleRate })` can throw (an unsupported rate): the
    // stream was already open, and a refused context must not leave the
    // microphone light on.
    g.AudioContext = class {
      constructor() {
        throw new DOMException('rate', 'NotSupportedError');
      }
    };
    await expect(
      startMicCapture({ sampleRate: SAMPLE_RATE, chunkSamples: CHUNK_SAMPLES, onChunk: vi.fn() })
    ).rejects.toThrow('rate');
    expect(track.stop).toHaveBeenCalledTimes(1);
  });
});
