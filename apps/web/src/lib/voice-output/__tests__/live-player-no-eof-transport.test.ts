import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { RoutedLivePlayer } from '../live-player';
import { AvatarEngine, type AvatarMedia } from '../../avatars/engine';
import type { LivePlayer } from '../../live/session-controller';
import { LIVE_PCM_PRODUCTION_HOLD_MS, LIVE_PCM_TAIL_HOLD_MS } from '../types';

// ElevenLabs over WebSocket emits no generation-complete signal: its
// `agent_response` precedes the audio chunks (vendor protocol), so the only
// production boundary the player can observe is its own drain.
class LocalPlayer implements LivePlayer {
  isSpeaking = false;
  changed: (value: boolean) => void = () => {};
  warmup = vi.fn(async () => {});
  enqueue = vi.fn();
  flush = vi.fn();
  dispose = vi.fn();
  onSpeakingChange(fn: (value: boolean) => void) {
    this.changed = fn;
  }
  activity(value: boolean) {
    this.isSpeaking = value;
    this.changed(value);
  }
}
function fixture() {
  let ready = false;
  let changed = () => {};
  const local = new LocalPlayer();
  const wire = {
    connect: vi.fn(async () => {}),
    close: vi.fn(),
    skip: vi.fn(),
    sendPcm: vi.fn(() => true),
  };
  const media: AvatarMedia = {
    get ready() {
      return ready;
    },
    quiet: true,
    get clock() {
      return performance.now() / 1000;
    },
    video: vi.fn(),
    audio: vi.fn(),
    reset: vi.fn(),
    mute: vi.fn(),
    unlock: vi.fn(async () => {}),
    attach: vi.fn(),
    begin: vi.fn(),
  };
  const engine = new AvatarEngine({
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
    media: fn => {
      changed = fn;
      return media;
    },
  });
  const player = new RoutedLivePlayer(local, () => engine);
  return {
    local,
    wire,
    engine,
    player,
    ready: () => {
      ready = true;
      changed();
    },
  };
}
async function settle() {
  for (let i = 0; i < 30; i++) await Promise.resolve();
}
const liveDemand = {
  account: 'a',
  credential: 'v',
  face: 'f',
  source: 'live' as const,
  live_id: 'live',
  connectSeconds: 15,
};
beforeEach(() => vi.useFakeTimers());
afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

it('a local production that drained gives the NEXT production to a ready Simli, with no transport EOF', async () => {
  const f = fixture();
  f.engine.setDemand(liveDemand);
  await settle();
  // Cold: the first reply reaches the local player while Simli connects.
  f.player.enqueue(new ArrayBuffer(6000), 16000);
  f.local.activity(true);
  f.ready();
  f.player.enqueue(new ArrayBuffer(6000), 16000);
  expect(f.local.enqueue).toHaveBeenCalledTimes(2);
  // The local player drains its queue: that reply is over. No
  // `finishProduction()` ever comes from this transport.
  f.local.activity(false);
  await vi.advanceTimersByTimeAsync(LIVE_PCM_PRODUCTION_HOLD_MS + 20);
  // The person asks again; this reply must reach Simli.
  f.player.enqueue(new ArrayBuffer(6000), 16000);
  expect(f.wire.sendPcm).toHaveBeenCalledTimes(1);
  expect(f.local.enqueue).toHaveBeenCalledTimes(2);
  f.player.dispose();
  f.engine.dispose();
});

it('a pause in the provider stream flushes the held tail at once, and ends the production only after the hold', async () => {
  const f = fixture();
  f.engine.setDemand(liveDemand);
  await settle();
  f.ready();
  const listener = vi.fn();
  f.player.onSpeakingChange(listener);
  const stream = vi.spyOn(f.engine, 'streaming');
  f.player.enqueue(new ArrayBuffer(6200), 16000);
  // 6 000 bytes left as a packet; 200 bytes wait for the next chunk.
  expect(f.wire.sendPcm).toHaveBeenCalledTimes(1);
  await vi.advanceTimersByTimeAsync(LIVE_PCM_TAIL_HOLD_MS + 10);
  expect(f.wire.sendPcm).toHaveBeenCalledTimes(2);
  expect(stream).toHaveBeenCalledOnce();
  // A chunk inside the hold keeps the same production.
  f.player.enqueue(new ArrayBuffer(6000), 16000);
  expect(f.wire.sendPcm).toHaveBeenCalledTimes(3);
  await vi.advanceTimersByTimeAsync(LIVE_PCM_PRODUCTION_HOLD_MS - 100);
  expect(stream).toHaveBeenCalledOnce();
  // Past the hold the production ends; its drain waits for the remote clock
  // (never heard here, so the default onset allowance applies).
  await vi.advanceTimersByTimeAsync(200);
  expect(stream).toHaveBeenCalledOnce();
  await vi.advanceTimersByTimeAsync(1500);
  await settle();
  f.player.enqueue(new ArrayBuffer(6000), 16000);
  expect(stream).toHaveBeenCalledTimes(2);
  expect(f.wire.close).not.toHaveBeenCalled();
  f.player.dispose();
  f.engine.dispose();
  expect(vi.getTimerCount()).toBe(0);
});
