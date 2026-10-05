import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { BrowserAvatarMedia } from '../browser-media';

// A Live session starts cold: the gesture (and its `unlock()`) happens BEFORE
// Simli's stream exists. The stream then arrives while the person only speaks.
class Node {
  connect = vi.fn();
  disconnect = vi.fn();
  gain = { value: 0 };
  fftSize = 256;
  getFloatTimeDomainData(array: Float32Array) {
    array.fill(0);
  }
}
class Context {
  state = 'suspended';
  currentTime = 0;
  destination = new Node();
  onstatechange: (() => void) | null = null;
  createGain() {
    return new Node();
  }
  createAnalyser() {
    return new Node();
  }
  createMediaStreamSource() {
    return new Node();
  }
  async resume() {
    this.state = 'running';
    this.onstatechange?.();
  }
  close = vi.fn(async () => {});
}
beforeEach(() => {
  vi.stubGlobal('AudioContext', Context);
  vi.stubGlobal('MediaStream', class {});
  vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue();
  vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => {});
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function attachedVideo(media: BrowserAvatarMedia) {
  const video = document.createElement('video');
  let frame: VideoFrameRequestCallback = () => {};
  Object.defineProperty(video, 'requestVideoFrameCallback', {
    value: (callback: VideoFrameRequestCallback) => {
      frame = callback;
      return 1;
    },
  });
  Object.defineProperty(video, 'cancelVideoFrameCallback', { value: vi.fn() });
  media.attach(video);
  return {
    video,
    render: () =>
      frame(0, {
        expectedDisplayTime: 0,
        height: 100,
        mediaTime: 0,
        presentationTime: 0,
        presentedFrames: 1,
        width: 100,
      }),
  };
}

it('a gesture unlock made before the stream exists still makes the later stream ready', async () => {
  const media = new BrowserAvatarMedia(vi.fn());
  const { render } = attachedVideo(media);
  // The Live start button: `RoutedLivePlayer.warmup()` unlocks here, cold.
  await media.unlock();
  // ~4.4 s later Simli's tracks arrive and the first frame renders; the
  // person is speaking into the microphone and clicks nothing.
  const stream = new MediaStream();
  media.video(stream);
  media.audio(stream);
  render();
  for (let n = 0; n < 10; n++) await Promise.resolve();
  expect(media.ready).toBe(true);
});

it('a stream arriving before any gesture waits for one, as the browser requires', async () => {
  const media = new BrowserAvatarMedia(vi.fn());
  const { render } = attachedVideo(media);
  const stream = new MediaStream();
  media.video(stream);
  media.audio(stream);
  render();
  for (let n = 0; n < 10; n++) await Promise.resolve();
  expect(media.ready).toBe(false);
  await media.unlock();
  expect(media.ready).toBe(true);
});

it('readiness never depends on an unmuted play(): a refused one leaves the element muted and the output ready', async () => {
  vi.mocked(HTMLMediaElement.prototype.play).mockRejectedValue(
    new DOMException('play() failed because the user did not interact', 'NotAllowedError')
  );
  const media = new BrowserAvatarMedia(vi.fn());
  const { video, render } = attachedVideo(media);
  await media.unlock();
  const stream = new MediaStream();
  media.video(stream);
  media.audio(stream);
  render();
  for (let n = 0; n < 10; n++) await Promise.resolve();
  expect(media.ready).toBe(true);
  expect(video.muted).toBe(true);
});
