import { afterEach, expect, it, vi } from 'vitest';
import { AvatarEngine } from '../../avatars/engine';
import { RoutedLivePlayer } from '../live-player';
import type { LivePlayer } from '../../live/session-controller';

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});
async function settle() {
  for (let i = 0; i < 30; i++) await Promise.resolve();
}
function fixture() {
  let onAudible = () => {};
  let quiet = true;
  const local: LivePlayer = {
    isSpeaking: false,
    warmup: vi.fn(async () => {}),
    enqueue: vi.fn(),
    flush: vi.fn(),
    dispose: vi.fn(),
    onSpeakingChange: vi.fn(),
  };
  const wire = {
    connect: vi.fn(async () => {}),
    close: vi.fn(),
    skip: vi.fn(),
    sendPcm: vi.fn((_packet: Uint8Array) => true),
  };
  const api = {
    start: vi.fn(async () => ({
      session_token: 'diagnostic',
      lease_id: 'diagnostic',
      ice_servers: [],
      max_session_seconds: 600,
    })),
    heartbeat: vi.fn(async () => {}),
    release: vi.fn(async () => true),
  };
  const engine = new AvatarEngine({
    api,
    wire: () => wire,
    media: () => ({
      ready: true,
      get clock() {
        return performance.now() / 1000;
      },
      get quiet() {
        return quiet;
      },
      video: vi.fn(),
      audio: vi.fn(),
      reset: vi.fn(),
      mute: vi.fn(),
      attach: vi.fn(),
      unlock: vi.fn(async () => {}),
      begin: fn => {
        onAudible = fn;
      },
    }),
  });
  const player = new RoutedLivePlayer(local, () => engine);
  return {
    api,
    engine,
    player,
    wire,
    local,
    heard: () => {
      quiet = false;
      onAudible();
    },
    silence: () => {
      quiet = true;
    },
  };
}
async function start(f: ReturnType<typeof fixture>) {
  f.engine.setDemand({
    account: 'diagnostic',
    credential: 'v',
    face: 'f',
    source: 'live',
    live_id: 'live',
    connectSeconds: 15,
  });
  await settle();
  expect(f.engine.ready).toBe(true);
}
function pcm(seconds: number) {
  return new Int16Array(16000 * seconds).fill(400).buffer;
}
it.each([12, 30])(
  'preserves every sample of a valid %i-second burst and keeps the avatar session',
  async seconds => {
    vi.useFakeTimers();
    const f = fixture();
    await start(f);
    for (let left = seconds; left > 0; left -= 4) {
      f.player.enqueue(pcm(Math.min(left, 4)), 16000);
      await vi.advanceTimersByTimeAsync(100);
    }
    f.heard();
    await vi.advanceTimersByTimeAsync(seconds * 1000 + 1500);
    f.silence();
    await vi.advanceTimersByTimeAsync(200);
    await settle();
    expect(f.wire.close).not.toHaveBeenCalled();
    expect(f.engine.state).toBe('ready');
    expect(f.api.start).toHaveBeenCalledOnce();
    expect(
      f.wire.sendPcm.mock.calls.reduce((bytes, [packet]) => bytes + packet.byteLength, 0)
    ).toBe(seconds * 16000 * 2);
    f.player.enqueue(pcm(1), 16000);
    expect(f.local.enqueue).not.toHaveBeenCalled();
    f.player.dispose();
    f.engine.dispose();
    await settle();
  }
);
it('keeps the Simli session for a short answer whose output actually drains', async () => {
  vi.useFakeTimers();
  const f = fixture();
  await start(f);
  f.player.enqueue(pcm(3), 16000);
  f.heard();
  await vi.advanceTimersByTimeAsync(3200);
  f.silence();
  await vi.advanceTimersByTimeAsync(100);
  await settle();
  expect(f.wire.close).not.toHaveBeenCalled();
  expect(f.engine.state).toBe('ready');
  f.player.dispose();
  f.engine.dispose();
  await settle();
});
