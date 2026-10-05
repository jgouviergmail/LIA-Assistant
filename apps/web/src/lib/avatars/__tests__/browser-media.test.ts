import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { BrowserAvatarMedia } from '../browser-media';

class Node {
  connect = vi.fn();
  disconnect = vi.fn();
  gain = { value: 0 };
  fftSize = 256;
  getFloatTimeDomainData(array: Float32Array) {
    array.fill(0.00001);
  }
}
beforeEach(() => {
  vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue();
  vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => {});
});
class Context {
  static instances: Context[] = [];
  state = 'suspended';
  currentTime = 0;
  destination = new Node();
  onstatechange: (() => void) | null = null;
  gain = new Node();
  analyser = new Node();
  source = new Node();
  constructor() {
    Context.instances.push(this);
  }
  createGain() {
    return this.gain;
  }
  createAnalyser() {
    return this.analyser;
  }
  createMediaStreamSource() {
    return this.source;
  }
  async resume() {
    this.state = 'running';
    this.onstatechange?.();
  }
  close = vi.fn(async () => {});
}
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});
it('requires a rendered frame and a running context; the element stays muted and the graph renders the phrase', async () => {
  vi.useFakeTimers();
  Context.instances = [];
  vi.stubGlobal('AudioContext', Context);
  const media = new BrowserAvatarMedia(vi.fn());
  vi.stubGlobal('MediaStream', class {});
  const stream = new MediaStream();
  const video = document.createElement('video');
  let frame: VideoFrameRequestCallback = () => {};
  Object.defineProperty(video, 'requestVideoFrameCallback', {
    value: (callback: VideoFrameRequestCallback) => {
      frame = callback;
      return 1;
    },
  });
  Object.defineProperty(video, 'cancelVideoFrameCallback', { value: vi.fn() });
  vi.spyOn(video, 'play').mockResolvedValue();
  media.attach(video);
  media.video(stream);
  media.audio(stream);
  expect(media.ready).toBe(false);
  await media.unlock();
  expect(media.ready).toBe(false);
  frame(0, {
    expectedDisplayTime: 0,
    height: 100,
    mediaTime: 0,
    presentationTime: 0,
    presentedFrames: 1,
    width: 100,
  });
  expect(media.ready).toBe(true);
  expect(video.muted).toBe(true);
  expect(video.playsInline).toBe(true);
  const heard = vi.fn();
  media.begin(heard);
  // The remote audio is rendered by the gesture-resumed context, never by
  // unmuting the element (a `play()` with sound outside a gesture is what a
  // real Chrome refused on 2026-10-04 while a headless one accepted it).
  expect(video.muted).toBe(true);
  expect(Context.instances[0].gain.gain.value).toBe(1);
  await vi.advanceTimersByTimeAsync(60);
  expect(heard).toHaveBeenCalledTimes(1);
  media.mute();
  expect(video.muted).toBe(true);
  expect(Context.instances[0].gain.gain.value).toBe(0);
  media.reset();
  expect(Context.instances[0].close).not.toHaveBeenCalled();
  media.reset(true);
  expect(Context.instances[0].close).toHaveBeenCalledTimes(1);
});
