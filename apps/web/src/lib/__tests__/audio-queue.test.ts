import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { AudioQueue } from '../audio-queue';

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<T>((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}

type DecodedAudio = { text: string };

class FakeSource {
  buffer: DecodedAudio | null = null;
  onended: (() => void) | null = null;
  connect = vi.fn();
  disconnect = vi.fn();
  start = vi.fn();
  stop = vi.fn();

  finish() {
    this.onended?.();
  }
}

class FakeContext {
  static latest: FakeContext;
  state: AudioContextState = 'running';
  destination = {};
  sources: FakeSource[] = [];
  addEventListener = vi.fn();
  removeEventListener = vi.fn();
  resume = vi.fn(async () => {
    this.state = 'running';
  });
  close = vi.fn(async () => {
    this.state = 'closed';
  });
  decodeAudioData = vi.fn(
    async (buffer: ArrayBuffer): Promise<DecodedAudio> => ({
      text: String.fromCharCode(...new Uint8Array(buffer)),
    })
  );

  constructor() {
    FakeContext.latest = this;
  }

  createBufferSource() {
    const source = new FakeSource();
    this.sources.push(source);
    return source;
  }
}

// Let pending resume/decode continuations settle without ending any audio source.
async function settle() {
  for (let i = 0; i < 30; i++) await Promise.resolve();
}

describe('AudioQueue sequential playback', () => {
  let queue: AudioQueue;

  beforeEach(() => {
    vi.stubGlobal('AudioContext', FakeContext);
    queue = new AudioQueue();
  });

  afterEach(() => {
    queue.dispose();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it.each([false, true])('plays a burst once, in order (initialized: %s)', async initialized => {
    if (initialized) await queue.initialize();
    const complete = vi.fn();
    queue.setOnPlaybackComplete(complete);

    await Promise.all(['first', 'second', 'third'].map(text => queue.enqueue(btoa(text))));
    await settle();
    const context = FakeContext.latest;

    for (const [index, text] of ['first', 'second', 'third'].entries()) {
      expect(context.sources).toHaveLength(index + 1);
      expect(context.sources[index].buffer?.text).toBe(text);
      expect(context.sources[index].start).toHaveBeenCalledTimes(1);
      expect(complete).not.toHaveBeenCalled();
      context.sources[index].finish();
      await settle();
    }
    expect(queue.playing).toBe(false);
    expect(queue.queueLength).toBe(0);
    expect(complete).toHaveBeenCalledTimes(1);
  });

  it('does not start audio whose decoding finishes after stop, or disturb the next turn', async () => {
    await queue.initialize();
    const context = FakeContext.latest;
    const decoding = deferred<DecodedAudio>();
    context.decodeAudioData.mockReturnValueOnce(decoding.promise);
    await queue.enqueue(btoa('old'));
    await settle();
    queue.stop();
    await queue.enqueue(btoa('new'));
    await settle();

    decoding.resolve({ text: 'old' });
    await settle();
    expect(context.sources).toHaveLength(1);
    expect(context.sources[0].buffer?.text).toBe('new');
    expect(queue.playing).toBe(true);
  });

  it('ignores a stale end event after stopping and starting a new turn', async () => {
    await queue.enqueue(btoa('old'));
    await settle();
    const context = FakeContext.latest;
    const oldSource = context.sources[0];
    const delayedEnd = oldSource.onended;
    queue.stop();
    await Promise.all(['new', 'next'].map(text => queue.enqueue(btoa(text))));
    await settle();
    delayedEnd?.();
    await settle();

    expect(oldSource.stop).toHaveBeenCalledTimes(1);
    expect(context.sources).toHaveLength(2);
    expect(context.sources[1].buffer?.text).toBe('new');
    context.sources[1].finish();
    await settle();
    expect(context.sources[2].buffer?.text).toBe('next');
  });

  it('retains suspended chunks and resumes them only once on a user gesture', async () => {
    await queue.initialize();
    const context = FakeContext.latest;
    context.state = 'suspended';
    context.resume.mockImplementation(async () => {});
    await Promise.all(['first', 'second'].map(text => queue.enqueue(btoa(text))));
    await settle();
    expect(context.sources).toHaveLength(0);
    expect(queue.queueLength).toBe(2);

    context.resume.mockImplementation(async () => {
      context.state = 'running';
    });
    await Promise.all([queue.resumePlayback(), queue.resumePlayback()]);
    await settle();
    expect(context.sources).toHaveLength(1);
    expect(context.sources[0].buffer?.text).toBe('first');
  });

  it('skips an undecodable chunk and keeps subsequent playback sequential', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    await queue.initialize();
    const context = FakeContext.latest;
    const onError = vi.fn();
    queue.setOnError(onError);
    context.decodeAudioData.mockRejectedValueOnce(new Error('invalid audio'));
    await Promise.all(['broken', 'second', 'third'].map(text => queue.enqueue(btoa(text))));
    await settle();
    expect(onError).toHaveBeenCalledTimes(1);
    expect(context.sources).toHaveLength(1);
    expect(context.sources[0].buffer?.text).toBe('second');
    context.sources[0].finish();
    await settle();
    expect(context.sources[1].buffer?.text).toBe('third');
  });

  it('discards enqueues still initializing when playback is stopped', async () => {
    const resume = deferred<void>();
    const enqueue = queue.enqueue(btoa('old'));
    FakeContext.latest.state = 'suspended';
    FakeContext.latest.resume.mockReturnValue(resume.promise);
    queue.stop();
    resume.resolve();
    await enqueue;
    await settle();
    expect(queue.queueLength).toBe(0);
    expect(FakeContext.latest.sources).toHaveLength(0);
  });
});
