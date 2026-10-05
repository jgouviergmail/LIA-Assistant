import { afterEach, expect, it, vi } from 'vitest';
import { AvatarEngine, type AvatarEngineDeps, type AvatarMedia } from '../engine';
import { AVATAR_LIVE_START_WAIT_MS, awaitAvatarReady, mountAvatarEngine } from '../runtime';

vi.mock('@/lib/logger', () => ({ logger: { warn: vi.fn(), debug: vi.fn(), info: vi.fn() } }));

const liveDemand = {
  account: 'a',
  credential: 'v',
  face: 'f',
  source: 'live' as const,
  live_id: 'live',
  connectSeconds: 15,
};
function fixture(start: AvatarEngineDeps['api']['start'] = async () => session) {
  let ready = false;
  let changed = () => {};
  const media: AvatarMedia = {
    get ready() {
      return ready;
    },
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
  const engine = new AvatarEngine({
    api: { start, heartbeat: vi.fn(async () => {}), release: vi.fn(async () => true) },
    wire: () => ({
      connect: vi.fn(async () => {}),
      close: vi.fn(),
      skip: vi.fn(),
      sendPcm: vi.fn(() => true),
    }),
    media: fn => {
      changed = fn;
      return media;
    },
  });
  const unmount = mountAvatarEngine(engine);
  return {
    engine,
    ready: () => {
      ready = true;
      changed();
    },
    dispose: () => {
      unmount();
      engine.dispose();
    },
  };
}
const session = { session_token: 'fixture', lease_id: 'lease', ice_servers: [], max_session_seconds: 3600 };
async function settle() {
  for (let n = 0; n < 30; n++) await Promise.resolve();
}
let dispose = () => {};
afterEach(() => {
  dispose();
  vi.useRealTimers();
});

it('resolves at once without an avatar demand', async () => {
  await expect(awaitAvatarReady()).resolves.toBeUndefined();
  const f = fixture();
  dispose = f.dispose;
  await expect(awaitAvatarReady()).resolves.toBeUndefined();
});

it('waits for a connecting avatar until it is ready', async () => {
  const f = fixture();
  dispose = f.dispose;
  f.engine.setDemand(liveDemand);
  const settled = vi.fn();
  const waiting = awaitAvatarReady().then(settled);
  await settle();
  expect(f.engine.state).toBe('connecting');
  expect(settled).not.toHaveBeenCalled();
  f.ready();
  await waiting;
  expect(f.engine.ready).toBe(true);
});

it('gives up with an avatar that cannot open, and at its bound', async () => {
  vi.useFakeTimers();
  const refused = fixture(async () => {
    throw new Error('fixture refusal');
  });
  dispose = refused.dispose;
  refused.engine.setDemand(liveDemand);
  const waiting = awaitAvatarReady();
  await settle();
  expect(refused.engine.state).toBe('unavailable');
  await expect(waiting).resolves.toBeUndefined();
  refused.dispose();

  const slow = fixture(() => new Promise(() => {}));
  dispose = slow.dispose;
  // The engine's own connection deadline normally settles the wait first;
  // a longer one leaves the wait's bound to do it.
  slow.engine.setDemand({ ...liveDemand, connectSeconds: 30 });
  const bounded = vi.fn();
  const pending = awaitAvatarReady().then(bounded);
  await settle();
  await vi.advanceTimersByTimeAsync(AVATAR_LIVE_START_WAIT_MS - 10);
  expect(bounded).not.toHaveBeenCalled();
  await vi.advanceTimersByTimeAsync(20);
  await pending;
  expect(bounded).toHaveBeenCalledOnce();
});
