import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { RoutedLivePlayer } from '../live-player';
import { AvatarEngine } from '../../avatars/engine';
import type { AvatarEngineDeps } from '../../avatars/engine';
import type { LivePlayer } from '../../live/session-controller';

// Decoder DOM ownership is tested separately; this suite isolates PCM clocks.
vi.mock('../rtc-audio-activation', () => ({ activateRtcAudio: () => () => {} }));

class Node {
  connect = vi.fn();
  disconnect = vi.fn();
  gain = { value: 1 };
}
class Context {
  static instances: Context[] = [];
  state = 'running';
  sampleRate = 48000;
  destination = new Node();
  audioWorklet = { addModule: vi.fn(async () => {}) };
  async resume() {}
  async close() {}
  createMediaStreamSource() {
    return new Node();
  }
  createGain() {
    return new Node();
  }
  constructor() {
    Context.instances.push(this);
  }
}
class CaptureNode extends Node {
  static instances: CaptureNode[] = [];
  epoch = 0;
  port: {
    onmessage: ((event: { data: unknown }) => void) | null;
    postMessage: (message: { epoch: number }) => void;
  } = {
    onmessage: null,
    postMessage: message => {
      this.epoch = message.epoch;
    },
  };
  emit(pcm: ArrayBuffer) {
    this.port.onmessage?.({ data: { pcm, epoch: this.epoch } });
  }
  constructor() {
    super();
    CaptureNode.instances.push(this);
  }
}
beforeEach(() => {
  vi.useFakeTimers();
  CaptureNode.instances = [];
  Context.instances = [];
  vi.stubGlobal('AudioContext', Context);
  vi.stubGlobal('AudioWorkletNode', CaptureNode);
  vi.stubGlobal('MediaStream', class {});
  vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:native-fixture');
  vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue();
  vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => {});
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});
async function settle() {
  for (let n = 0; n < 30; n++) await Promise.resolve();
}
function fixture() {
  let notify: (speaking: boolean) => void = () => {};
  const local: LivePlayer = {
    isSpeaking: false,
    warmup: vi.fn(async () => {}),
    enqueue: vi.fn(),
    flush: vi.fn(),
    dispose: vi.fn(),
    onSpeakingChange: vi.fn(),
    onAudibleChange: fn => {
      notify = fn;
    },
  };
  const wire = {
    connect: vi.fn(async () => {}),
    close: vi.fn(),
    skip: vi.fn(),
    sendPcm: vi.fn(() => true),
  };
  const deps: AvatarEngineDeps = {
    api: {
      start: vi.fn(async () => ({
        session_token: 'fixture',
        lease_id: 'lease',
        ice_servers: [],
        max_session_seconds: 3600,
      })),
      heartbeat: vi.fn(),
      release: vi.fn(async () => true),
    },
    wire: () => wire,
    media: () => ({
      ready: true,
      get clock() {
        return performance.now() / 1000;
      },
      quiet: true,
      video: vi.fn(),
      audio: vi.fn(),
      reset: vi.fn(),
      mute: vi.fn(),
      unlock: vi.fn(),
      attach: vi.fn(),
      begin: vi.fn(),
    }),
  };
  const engine = new AvatarEngine(deps);
  const player = new RoutedLivePlayer(local, () => engine);
  return { engine, player, local, wire, activity: (speaking: boolean) => notify(speaking) };
}
it('preserves native playback for opt-out and hot opt-in waits for a new request', async () => {
  const f = fixture();
  await f.player.warmup();
  const release = f.player.attachRemoteStream(new MediaStream());
  expect(HTMLMediaElement.prototype.play).toHaveBeenCalledTimes(1);
  expect(CaptureNode.instances).toHaveLength(0);
  f.player.nativeSpeaking(true);
  f.engine.setPermission(true);
  f.player.prepareNativeResponse();
  expect(CaptureNode.instances).toHaveLength(0);
  f.player.nativeSpeaking(false);
  await settle();
  expect(CaptureNode.instances).toHaveLength(1);
  expect(HTMLMediaElement.prototype.pause).toHaveBeenCalled();
  release();
  f.player.dispose();
  f.engine.dispose();
});
it('captures weak native speech before the SDK threshold and keeps every interior silence block', async () => {
  const f = fixture();
  f.engine.setPermission(true);
  f.engine.setDemand({
    account: 'a',
    credential: 'v',
    face: 'f',
    source: 'live',
    live_id: 'live',
    connectSeconds: 15,
  });
  await settle();
  await f.player.warmup();
  const release = f.player.attachRemoteStream(new MediaStream());
  await settle();
  const node = CaptureNode.instances[0];
  node.emit(new ArrayBuffer(2048));
  const weak = new Int16Array(1024).fill(33).buffer;
  for (let n = 0; n < 9; n++) node.emit(weak);
  expect(f.wire.sendPcm).toHaveBeenCalledTimes(1);
  expect(f.local.enqueue).not.toHaveBeenCalled();
  f.player.nativeSpeaking(false);
  for (let n = 0; n < 9; n++) node.emit(new ArrayBuffer(2048));
  // Two packets of speech and silence, then the pause flushes the held tail.
  await vi.advanceTimersByTimeAsync(200);
  expect(f.wire.sendPcm).toHaveBeenCalledTimes(3);
  expect(f.wire.close).not.toHaveBeenCalled();
  release();
  f.player.dispose();
  f.engine.dispose();
});
it('local native activity comes from rendered PCM and late callbacks cannot resurrect an interruption', async () => {
  const f = fixture();
  f.engine.setPermission(true);
  await f.player.warmup();
  const release = f.player.attachRemoteStream(new MediaStream());
  await settle();
  const listener = vi.fn();
  f.player.onSpeakingChange(listener);
  const node = CaptureNode.instances[0];
  const port = node.port;
  node.emit(new Int16Array(1024).fill(33).buffer);
  f.activity(true);
  expect(f.player.isSpeaking).toBe(true);
  f.player.nativeSpeaking(false);
  expect(f.player.isSpeaking).toBe(true);
  f.activity(false);
  expect(f.player.isSpeaking).toBe(false);
  f.player.flush();
  const old = port.onmessage;
  release();
  old?.({ data: { pcm: new Int16Array(1024).fill(33).buffer, epoch: 0 } });
  expect(f.local.enqueue).toHaveBeenCalledTimes(1);
  f.player.dispose();
  f.engine.dispose();
});
it('drops residual native speech after interruption until a quiet block marks the next sound', async () => {
  const f = fixture();
  f.engine.setPermission(true);
  await f.player.warmup();
  const release = f.player.attachRemoteStream(new MediaStream());
  await settle();
  const node = CaptureNode.instances[0];
  const speech = new Int16Array(1024).fill(33).buffer;
  node.emit(speech);
  f.player.flush();
  const before = vi.mocked(f.local.enqueue).mock.calls.length;
  node.emit(speech);
  node.emit(speech);
  expect(f.local.enqueue).toHaveBeenCalledTimes(before);
  node.emit(new ArrayBuffer(2048));
  node.emit(speech);
  expect(vi.mocked(f.local.enqueue).mock.calls.length).toBeGreaterThan(before);
  release();
  f.player.dispose();
  f.engine.dispose();
});

it('an old stream release cannot cut its replacement and a disposed player cannot attach again', async () => {
  const f = fixture();
  f.engine.setPermission(true);
  await f.player.warmup();
  const oldRelease = f.player.attachRemoteStream(new MediaStream());
  await settle();
  const release = f.player.attachRemoteStream(new MediaStream());
  await settle();
  const node = CaptureNode.instances[1];
  oldRelease();
  node.emit(new Int16Array(1024).fill(33).buffer);
  expect(f.local.enqueue).toHaveBeenCalledTimes(1);
  release();
  expect(vi.getTimerCount()).toBe(0);
  f.player.dispose();
  f.player.attachRemoteStream(new MediaStream())();
  await settle();
  expect(CaptureNode.instances).toHaveLength(2);
  expect(HTMLMediaElement.prototype.play).not.toHaveBeenCalled();
  f.engine.dispose();
});

it('an idle opt-in captures immediately, while revoking a pending opt-in preserves native playback', async () => {
  const f = fixture();
  await f.player.warmup();
  const release = f.player.attachRemoteStream(new MediaStream());
  f.player.prepareNativeResponse();
  expect(CaptureNode.instances).toHaveLength(0);
  f.player.nativeSpeaking(true);
  f.engine.setPermission(true);
  f.player.prepareNativeResponse();
  f.engine.setPermission(false);
  f.player.nativeSpeaking(false);
  await settle();
  expect(CaptureNode.instances).toHaveLength(0);
  f.engine.setPermission(true);
  f.player.prepareNativeResponse();
  await settle();
  expect(CaptureNode.instances).toHaveLength(1);
  release();
  f.player.prepareNativeResponse();
  f.player.dispose();
  f.engine.dispose();
});

it('capture failure keeps the original native stream audible locally and cleans up on release', async () => {
  const f = fixture();
  f.engine.setPermission(true);
  await f.player.warmup();
  Context.instances[0].audioWorklet.addModule.mockRejectedValue(new Error('private vendor detail'));
  const release = f.player.attachRemoteStream(new MediaStream());
  await settle();
  const listener = vi.fn();
  f.player.onSpeakingChange(listener);
  f.player.nativeSpeaking(true);
  expect(f.player.isSpeaking).toBe(true);
  f.player.nativeSpeaking(false);
  expect(f.player.isSpeaking).toBe(false);
  expect(f.local.enqueue).not.toHaveBeenCalled();
  release();
  f.player.dispose();
  f.engine.dispose();
  expect(vi.getTimerCount()).toBe(0);
});

it('a new native generation drains the previous PCM tail after actual local silence', async () => {
  const f = fixture();
  f.engine.setPermission(true);
  await f.player.warmup();
  const release = f.player.attachRemoteStream(new MediaStream());
  await settle();
  const node = CaptureNode.instances[0];
  node.emit(new Int16Array(1024).fill(33).buffer);
  f.activity(true);
  f.player.nativeSpeaking(false);
  f.activity(false);
  const finished = vi.spyOn(f.player, 'finishProduction');
  f.player.nativeSpeaking(true);
  expect(finished).toHaveBeenCalledOnce();
  node.emit(new Int16Array(1024).fill(33).buffer);
  expect(f.local.enqueue).toHaveBeenCalledTimes(2);
  release();
  f.player.nativeSpeaking(true);
  expect(f.player.isSpeaking).toBe(false);
  f.player.dispose();
  f.engine.dispose();
});

it('avatar native activity follows remote playout and late local activity cannot override it', async () => {
  const f = fixture();
  f.engine.setPermission(true);
  f.engine.setDemand({
    account: 'a',
    credential: 'v',
    face: 'f',
    source: 'live',
    live_id: 'live',
    connectSeconds: 15,
  });
  await settle();
  await f.player.warmup();
  const release = f.player.attachRemoteStream(new MediaStream());
  await settle();
  Object.defineProperty(f.engine.media, 'quiet', { value: false, configurable: true });
  const listener = vi.fn();
  f.player.onSpeakingChange(listener);
  const node = CaptureNode.instances[0];
  node.emit(new Int16Array(1024).fill(33).buffer);
  await vi.advanceTimersByTimeAsync(20);
  expect(f.player.isSpeaking).toBe(true);
  f.activity(false);
  expect(f.player.isSpeaking).toBe(true);
  Object.defineProperty(f.engine.media, 'quiet', { value: true });
  await vi.advanceTimersByTimeAsync(20);
  expect(f.player.isSpeaking).toBe(false);
  release();
  f.player.dispose();
  f.engine.dispose();
  await settle();
});

it('an old autoplay rejection cannot silence a replacement native stream', async () => {
  const f = fixture();
  let reject: (error: Error) => void = () => {};
  vi.mocked(HTMLMediaElement.prototype.play).mockImplementationOnce(
    () =>
      new Promise<void>((_resolve, fail) => {
        reject = fail;
      })
  );
  f.player.attachRemoteStream(new MediaStream());
  const release = f.player.attachRemoteStream(new MediaStream());
  f.player.nativeSpeaking(true);
  reject(new Error('autoplay refused'));
  await settle();
  expect(f.player.isSpeaking).toBe(true);
  release();
  f.player.dispose();
  f.engine.dispose();
});

it('a current autoplay rejection leaves native activity quiet and releases its DOM element', async () => {
  const f = fixture();
  vi.mocked(HTMLMediaElement.prototype.play).mockRejectedValueOnce(new Error('autoplay refused'));
  const release = f.player.attachRemoteStream(new MediaStream());
  f.player.nativeSpeaking(true);
  await settle();
  expect(f.player.isSpeaking).toBe(false);
  release();
  expect(document.querySelector('audio')).toBeNull();
  f.player.dispose();
  f.engine.dispose();
});
