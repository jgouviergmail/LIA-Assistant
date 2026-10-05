import { afterEach, expect, it, vi } from 'vitest';
import { AvatarEngine } from '../engine';
import type { AvatarEngineDeps, AvatarMedia, AvatarWire } from '../engine';
import type { AvatarDemand } from '../activation-policy';
import type { AvatarSession } from '../types';
import type { SimliTransportEvents } from '../simli-transport';
import { logger } from '@/lib/logger';
import { AvatarStartError } from '../api';
vi.mock('@/lib/logger', () => ({ logger: { warn: vi.fn(), debug: vi.fn() } }));

const demand: AvatarDemand = {
  account: 'a',
  credential: 'v',
  face: 'f',
  source: 'comments',
  connectSeconds: 15,
};
const session: AvatarSession = {
  session_token: 'transient-fixture',
  lease_id: 'l',
  ice_servers: [],
  max_session_seconds: 3600,
};
async function settle() {
  for (let i = 0; i < 30; i++) await Promise.resolve();
}
function fixture() {
  const media: AvatarMedia = {
    ready: false,
    clock: 0,
    quiet: true,
    video: vi.fn(),
    audio: vi.fn(),
    reset: vi.fn(),
    mute: vi.fn(),
    unlock: vi.fn(async () => {}),
    attach: vi.fn(),
    begin: vi.fn(),
  };
  let changed = () => {};
  let callbacks: SimliTransportEvents | null = null;
  const wire: AvatarWire = {
    connect: vi.fn(async () => {}),
    close: vi.fn(),
    skip: vi.fn(),
    sendPcm: vi.fn(() => true),
  };
  const deps: AvatarEngineDeps = {
    api: {
      start: vi.fn(async () => session),
      heartbeat: vi.fn(async () => {}),
      release: vi.fn(async () => true),
    },
    wire: events => {
      callbacks = events;
      return wire;
    },
    media: fn => {
      changed = fn;
      return media;
    },
  };
  const engine = new AvatarEngine(deps);
  return { engine, media, wire, deps, changed: () => changed(), callbacks: () => callbacks };
}
afterEach(() => vi.useRealTimers());
it('reports only a fixed lifecycle failure code when the transport closes', async () => {
  const f = fixture();
  f.engine.setDemand(demand);
  await settle();
  f.callbacks()?.onClosed();
  await settle();
  expect(logger.warn).toHaveBeenCalledWith('avatar_unavailable', {
    component: 'AvatarEngine',
    code: 'avatar_transport_closed',
  });
  expect(JSON.stringify(vi.mocked(logger.warn).mock.calls)).not.toContain('transient-fixture');
  f.engine.dispose();
});
it('does not route audio on socket readiness and never opens on each phrase', async () => {
  const f = fixture();
  f.engine.setDemand(demand);
  await settle();
  expect(f.deps.api.start).toHaveBeenCalledTimes(1);
  expect(f.engine.state).toBe('connecting');
  expect(f.engine.ready).toBe(false);
  Object.defineProperty(f.media, 'ready', { value: true });
  f.changed();
  expect(f.engine.ready).toBe(true);
  f.engine.setDemand({ ...demand });
  await settle();
  expect(f.deps.api.start).toHaveBeenCalledTimes(1);
  f.engine.dispose();
});
it('hands the same face to Live without closing and closes at standby', async () => {
  const f = fixture();
  f.engine.setDemand(demand);
  await settle();
  f.engine.setDemand({ ...demand, source: 'live', live_id: 'live-id' });
  await settle();
  expect(f.deps.api.start).toHaveBeenCalledTimes(1);
  expect(f.wire.skip).toHaveBeenCalled();
  expect(f.wire.close).not.toHaveBeenCalled();
  f.engine.setDemand(null);
  await settle();
  expect(f.wire.close).toHaveBeenCalledTimes(1);
  expect(f.deps.api.release).toHaveBeenCalledTimes(1);
  expect(f.engine.state).toBe('off');
});
it('closes a late minted token without opening a peer after mode deactivation', async () => {
  const f = fixture();
  let resolve: (value: AvatarSession) => void = () => {};
  vi.mocked(f.deps.api.start).mockImplementation(
    () =>
      new Promise(done => {
        resolve = done;
      })
  );
  f.engine.setDemand(demand);
  await settle();
  f.engine.setDemand(null);
  await settle();
  resolve(session);
  await settle();
  expect(f.wire.connect).not.toHaveBeenCalled();
  expect(f.deps.api.release).toHaveBeenCalled();
  expect(f.engine.state).toBe('off');
});
it('does not retry an ambiguous paid POST or a failed remote release', async () => {
  vi.useFakeTimers();
  const f = fixture();
  vi.mocked(f.deps.api.start).mockRejectedValue(new Error('untrusted vendor detail'));
  vi.mocked(f.deps.api.release).mockResolvedValue(false);
  f.engine.setDemand(demand);
  await settle();
  await vi.advanceTimersByTimeAsync(60_000);
  expect(f.engine.state).toBe('unavailable');
  expect(f.deps.api.start).toHaveBeenCalledTimes(1);
  f.engine.dispose();
});
it('lets a human retry a definite pre-mint refusal without quarantining an attempt that created no session', async () => {
  const f = fixture();
  vi.mocked(f.deps.api.start).mockRejectedValueOnce(
    new AvatarStartError('avatar_start_rate_limited', true)
  );
  vi.mocked(f.deps.api.release).mockResolvedValue(false);
  f.engine.setDemand(demand);
  await settle();
  expect(f.engine.failure).toBe('avatar_start_rate_limited');
  expect(f.deps.api.release).not.toHaveBeenCalled();
  expect(f.deps.api.start).toHaveBeenCalledOnce();
  await f.engine.retry();
  expect(f.deps.api.start).toHaveBeenCalledTimes(2);
  f.engine.dispose();
});
it('renews sequentially at the finite provider cap and refuses overlap when closure is unknown', async () => {
  vi.useFakeTimers();
  const f = fixture();
  vi.mocked(f.deps.api.start).mockResolvedValue({ ...session, max_session_seconds: 30 });
  f.engine.setDemand(demand);
  await settle();
  Object.defineProperty(f.media, 'ready', { value: true });
  f.changed();
  vi.mocked(f.deps.api.release).mockResolvedValue(false);
  await vi.advanceTimersByTimeAsync(16_000);
  expect(f.wire.close).toHaveBeenCalledTimes(1);
  expect(f.deps.api.start).toHaveBeenCalledTimes(1);
  expect(f.engine.state).toBe('unavailable');
  f.engine.dispose();
});
it('bounds a socket/first-frame stall without aborting media that only needs a gesture', async () => {
  vi.useFakeTimers();
  const f = fixture();
  f.engine.setDemand(demand);
  await settle();
  Object.defineProperty(f.media, 'connected', { value: true });
  f.changed();
  await vi.advanceTimersByTimeAsync(16_000);
  expect(f.engine.state).toBe('connecting');
  expect(f.wire.close).not.toHaveBeenCalled();
  f.engine.dispose();
  await settle();
  const stalled = fixture();
  stalled.engine.setDemand(demand);
  await settle();
  await vi.advanceTimersByTimeAsync(16_000);
  expect(stalled.engine.state).toBe('unavailable');
  expect(stalled.wire.close).toHaveBeenCalledTimes(1);
  stalled.engine.dispose();
});

it('an intentional comments-to-Live interruption keeps the ready connection alive', async () => {
  vi.useFakeTimers();
  const f = fixture();
  f.engine.setDemand(demand);
  await settle();
  Object.defineProperty(f.media, 'ready', { value: true });
  f.changed();
  // Six seconds of speech: the bounded lead holds the feed mid-clip on a
  // remote clock that never advances, exactly where the mode switch lands.
  const samples = new Float32Array(96000).fill(0.01);
  const buffer: AudioBuffer = {
    sampleRate: 16000,
    numberOfChannels: 1,
    length: 96000,
    duration: 6,
    getChannelData: () => samples,
    copyFromChannel: vi.fn(),
    copyToChannel: vi.fn(),
  };
  const phrase = f.engine.openPhrase(16000, vi.fn());
  const feeding = phrase.feed(buffer, new AbortController().signal);
  const verdict = expect(feeding).rejects.toThrow('avatar_playback_failed');
  await settle();
  expect(f.wire.sendPcm).toHaveBeenCalled();
  f.engine.setDemand({ ...demand, source: 'live', live_id: 'live' });
  await settle();
  await vi.advanceTimersByTimeAsync(40);
  await verdict;
  expect(f.wire.skip).toHaveBeenCalled();
  expect(f.wire.close).not.toHaveBeenCalled();
  expect(f.engine.ready).toBe(true);
  expect(f.deps.api.start).toHaveBeenCalledOnce();
  f.engine.dispose();
  await settle();
});

it('a drain interrupted by a new production resolves quietly and keeps the connection', async () => {
  vi.useFakeTimers();
  const f = fixture();
  f.engine.setDemand(demand);
  await settle();
  Object.defineProperty(f.media, 'ready', { value: true });
  f.changed();
  const samples = new Float32Array(16000).fill(0.01);
  const buffer: AudioBuffer = {
    sampleRate: 16000,
    numberOfChannels: 1,
    length: 16000,
    duration: 1,
    getChannelData: () => samples,
    copyFromChannel: vi.fn(),
    copyToChannel: vi.fn(),
  };
  const phrase = f.engine.openPhrase(16000, vi.fn());
  await phrase.feed(buffer, new AbortController().signal);
  vi.mocked(logger.warn).mockClear();
  const draining = phrase.finish();
  // The remote never reaches its clock: the person starts another answer.
  f.engine.interrupt();
  await vi.advanceTimersByTimeAsync(40);
  await expect(draining).resolves.toBeUndefined();
  expect(f.wire.skip).toHaveBeenCalled();
  expect(f.wire.close).not.toHaveBeenCalled();
  expect(f.engine.ready).toBe(true);
  expect(logger.warn).not.toHaveBeenCalledWith('avatar_unavailable', expect.anything());
  f.engine.dispose();
  await settle();
});
