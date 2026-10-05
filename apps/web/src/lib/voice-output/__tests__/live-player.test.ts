import { afterEach, expect, it, vi } from 'vitest';
import { RoutedLivePlayer } from '../live-player';
import type { LivePlayer } from '../../live/session-controller';
import { AvatarEngine } from '../../avatars/engine';
import type { AvatarEngineDeps } from '../../avatars/engine';

function fixture() {
  let ready = false;
  let changed = () => {};
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
    media: fn => {
      changed = fn;
      return {
        get ready() {
          return ready;
        },
        clock: 0,
        quiet: true,
        video: vi.fn(),
        audio: vi.fn(),
        reset: vi.fn(),
        mute: vi.fn(),
        unlock: vi.fn(),
        attach: vi.fn(),
        begin: vi.fn(),
      };
    },
  };
  const engine = new AvatarEngine(deps);
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
afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});
it('keeps a cold PCM response local and routes the next production to one Simli sink', async () => {
  const f = fixture();
  f.engine.setDemand({
    account: 'a',
    credential: 'v',
    face: 'f',
    source: 'live',
    live_id: 'live',
    connectSeconds: 15,
  });
  await settle();
  f.player.enqueue(new ArrayBuffer(6000), 16000);
  f.ready();
  f.player.enqueue(new ArrayBuffer(6000), 16000);
  expect(f.local.enqueue).toHaveBeenCalledTimes(2);
  expect(f.wire.sendPcm).not.toHaveBeenCalled();
  f.player.finishProduction();
  f.player.enqueue(new ArrayBuffer(6000), 16000);
  expect(f.wire.sendPcm).toHaveBeenCalledTimes(1);
  expect(f.local.enqueue).toHaveBeenCalledTimes(2);
  f.player.flush();
  expect(f.wire.close).not.toHaveBeenCalled();
  f.player.dispose();
  f.engine.dispose();
});
it('never replays a possibly heard failed phrase locally and resumes at the next boundary', async () => {
  const f = fixture();
  f.engine.setDemand({
    account: 'a',
    credential: 'v',
    face: 'f',
    source: 'live',
    live_id: 'live',
    connectSeconds: 15,
  });
  await settle();
  f.ready();
  f.player.enqueue(new ArrayBuffer(6000), 16000);
  f.player.enqueue(new ArrayBuffer(3), 16000);
  expect(f.local.enqueue).not.toHaveBeenCalled();
  f.player.finishProduction();
  f.player.enqueue(new ArrayBuffer(6000), 16000);
  expect(f.local.enqueue).toHaveBeenCalledTimes(1);
  f.player.dispose();
  f.engine.dispose();
});

it('retains the next production EOF while the preceding Simli response is still draining', async () => {
  vi.useFakeTimers();
  const f = fixture();
  f.engine.setDemand({
    account: 'a',
    credential: 'v',
    face: 'f',
    source: 'live',
    live_id: 'live',
    connectSeconds: 15,
  });
  await settle();
  f.ready();
  const streaming = vi.spyOn(f.engine, 'streaming');
  f.player.enqueue(new ArrayBuffer(6000), 16000);
  const first = streaming.mock.results[0].value;
  let release = () => {};
  vi.spyOn(first, 'finish').mockImplementation(
    () =>
      new Promise<void>(resolve => {
        release = resolve;
      })
  );
  f.player.finishProduction();
  f.player.enqueue(new ArrayBuffer(6000), 16000);
  f.player.finishProduction();
  release();
  await settle();
  expect(streaming).toHaveBeenCalledTimes(2);
  // Finishing flushes the 97-tap FIR tail even while the remote output drains.
  expect(f.wire.sendPcm).toHaveBeenCalledWith(expect.objectContaining({ length: 6000 }));
  f.player.dispose();
  f.engine.dispose();
  await settle();
});
