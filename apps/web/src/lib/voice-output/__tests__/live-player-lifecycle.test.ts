import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { RoutedLivePlayer } from '../live-player';
import { AvatarEngine, type AvatarMedia } from '../../avatars/engine';
import type { LivePlayer } from '../../live/session-controller';

class LocalPlayer implements LivePlayer {
  isSpeaking = false;
  changed: (value: boolean) => void = () => {};
  audible: (value: boolean) => void = () => {};
  warmup = vi.fn(async () => {});
  enqueue = vi.fn();
  flush = vi.fn();
  dispose = vi.fn();
  onSpeakingChange(fn: (value: boolean) => void) {
    this.changed = fn;
  }
  onAudibleChange(fn: (value: boolean) => void) {
    this.audible = fn;
  }
  activity(value: boolean) {
    this.isSpeaking = value;
    this.changed(value);
  }
}

function fixture() {
  let ready = false;
  let quiet = true;
  let heard = () => {};
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
    get quiet() {
      return quiet;
    },
    get clock() {
      return performance.now() / 1000;
    },
    video: vi.fn(),
    audio: vi.fn(),
    reset: vi.fn(),
    mute: vi.fn(),
    unlock: vi.fn(async () => {}),
    attach: vi.fn(),
    begin: fn => {
      heard = fn;
    },
  };
  const engine = new AvatarEngine({
    media: fn => {
      changed = fn;
      return media;
    },
    wire: () => wire,
    api: {
      start: vi.fn(async () => ({
        session_token: 'fixture',
        lease_id: 'lease',
        ice_servers: [],
        max_session_seconds: 3600,
      })),
      heartbeat: vi.fn(async () => {}),
      release: vi.fn(async () => true),
    },
  });
  let target: AvatarEngine | null = engine;
  const player = new RoutedLivePlayer(local, () => target);
  return {
    local,
    engine,
    wire,
    player,
    warm: () => {
      ready = true;
      changed();
    },
    heard: () => {
      quiet = false;
      heard();
    },
    silent: () => {
      quiet = true;
    },
    detach: () => {
      target = null;
    },
  };
}
async function settle() {
  for (let n = 0; n < 30; n++) await Promise.resolve();
}
async function active(f: ReturnType<typeof fixture>) {
  f.engine.setDemand({
    account: 'a',
    credential: 'v',
    face: 'f',
    source: 'live',
    live_id: 'live',
    connectSeconds: 15,
  });
  await settle();
  f.warm();
}
function close(f: ReturnType<typeof fixture>) {
  f.player.dispose();
  f.engine.dispose();
}
beforeEach(() => vi.useFakeTimers());
afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

it('holds the next cold route until local output drains, even if Simli becomes ready meanwhile', async () => {
  const f = fixture();
  const heard = vi.fn();
  f.player.onSpeakingChange(heard);
  f.player.enqueue(new ArrayBuffer(6000), 16000);
  f.local.activity(true);
  expect(f.player.isSpeaking).toBe(true);
  f.player.finishProduction();
  f.player.enqueue(new ArrayBuffer(6000), 16000);
  f.player.finishProduction();
  await active(f);
  f.local.activity(false);
  expect(f.local.enqueue).toHaveBeenCalledTimes(2);
  expect(f.wire.sendPcm).not.toHaveBeenCalled();
  expect(heard.mock.calls).toEqual([[true], [false]]);
  f.player.enqueue(new ArrayBuffer(6200), 16000);
  expect(f.wire.sendPcm).toHaveBeenCalledOnce();
  // Local provider events must never take over an avatar-owned phrase.
  f.local.activity(true);
  expect(heard.mock.calls).toEqual([[true], [false]]);
  close(f);
  await settle();
});

it('drains two complete productions in order and rejects late audible callbacks after flush', async () => {
  const f = fixture();
  await active(f);
  const listener = vi.fn();
  f.player.onSpeakingChange(listener);
  f.player.enqueue(new ArrayBuffer(6200), 16000);
  f.heard();
  expect(f.player.isSpeaking).toBe(true);
  f.player.finishProduction();
  f.player.finishProduction();
  f.player.enqueue(new ArrayBuffer(6200), 16000);
  f.player.finishProduction();
  // The first production's packet and its drained tail left at once; the
  // second production waits for the drain.
  expect(f.wire.sendPcm).toHaveBeenCalledTimes(2);
  f.silent();
  await vi.advanceTimersByTimeAsync(1500);
  expect(f.wire.sendPcm).toHaveBeenCalledTimes(4);
  await vi.advanceTimersByTimeAsync(1500);
  expect(f.player.isSpeaking).toBe(false);
  f.player.flush();
  f.heard();
  expect(f.player.isSpeaking).toBe(false);
  close(f);
  f.local.activity(true);
  f.local.audible(true);
  f.player.enqueue(new ArrayBuffer(6200), 16000);
  f.player.nativeSpeaking(true);
  f.player.finishProduction();
  expect(listener.mock.calls).toEqual([[true], [false]]);
  expect(f.local.dispose).toHaveBeenCalledOnce();
  f.player.dispose();
  expect(f.local.dispose).toHaveBeenCalledOnce();
  await settle();
});

it('does not resurrect queued responses when an earlier drain resolves after cancellation', async () => {
  const f = fixture();
  await active(f);
  const stream = vi.spyOn(f.engine, 'streaming');
  f.player.enqueue(new ArrayBuffer(6200), 16000);
  let resolve = () => {};
  vi.spyOn(stream.mock.results[0].value, 'finish').mockImplementation(
    () =>
      new Promise<void>(done => {
        resolve = done;
      })
  );
  f.player.finishProduction();
  f.player.enqueue(new ArrayBuffer(6200), 16000);
  f.player.flush();
  resolve();
  await settle();
  expect(stream).toHaveBeenCalledOnce();
  expect(f.wire.close).not.toHaveBeenCalled();
  close(f);
  await settle();
});

it('bounds the next response queue and recovers locally only at its boundary', async () => {
  const f = fixture();
  await active(f);
  const stream = vi.spyOn(f.engine, 'streaming');
  f.player.enqueue(new ArrayBuffer(6200), 16000);
  let reject: (error: Error) => void = () => {};
  vi.spyOn(stream.mock.results[0].value, 'finish').mockImplementation(
    () =>
      new Promise<void>((_done, fail) => {
        reject = fail;
      })
  );
  f.player.finishProduction();
  f.player.enqueue(new ArrayBuffer(160000), 16000);
  f.player.enqueue(new ArrayBuffer(2), 16000);
  expect(f.wire.close).toHaveBeenCalledOnce();
  expect(f.local.enqueue).not.toHaveBeenCalled();
  reject(new Error('fixture failure'));
  await settle();
  f.player.enqueue(new ArrayBuffer(6200), 16000);
  expect(f.local.enqueue).toHaveBeenCalledOnce();
  close(f);
  await settle();
});

it('a rejected drain terminates the failed output without replaying its prefix', async () => {
  const f = fixture();
  await active(f);
  const stream = vi.spyOn(f.engine, 'streaming');
  f.player.enqueue(new ArrayBuffer(6200), 16000);
  vi.spyOn(stream.mock.results[0].value, 'finish').mockRejectedValue(new Error('vendor detail'));
  f.player.finishProduction();
  await settle();
  expect(f.wire.close).toHaveBeenCalledOnce();
  expect(f.local.enqueue).not.toHaveBeenCalled();
  close(f);
  await settle();
});

it.each([NaN, 7999, 96001, 16000.5])('rejects an invalid PCM rate %s before routing', rate => {
  const f = fixture();
  f.detach();
  f.player.enqueue(new ArrayBuffer(2), rate);
  expect(f.local.enqueue).not.toHaveBeenCalled();
  f.player.enqueue(new ArrayBuffer(2), 16000);
  expect(f.local.enqueue).toHaveBeenCalledOnce();
  expect(f.player.diagnostics()).toBeNull();
  close(f);
});

it('invalid PCM and changing rates cannot splice into an already audible production', async () => {
  const f = fixture();
  await active(f);
  f.player.enqueue(new ArrayBuffer(6200), 16000);
  f.player.enqueue(new ArrayBuffer(2), 24000);
  f.player.enqueue(new ArrayBuffer(6200), 16000);
  expect(f.wire.close).toHaveBeenCalledOnce();
  expect(f.local.enqueue).not.toHaveBeenCalled();
  f.player.finishProduction();
  f.player.enqueue(new ArrayBuffer(0), 16000);
  f.player.enqueue(new ArrayBuffer(160002), 16000);
  expect(f.local.enqueue).not.toHaveBeenCalled();
  close(f);
  await settle();
});

it('a converter failure is isolated without any second audible destination', async () => {
  const f = fixture();
  await active(f);
  const stream = vi.spyOn(f.engine, 'streaming');
  f.player.enqueue(new ArrayBuffer(6200), 16000);
  vi.spyOn(stream.mock.results[0].value, 'pushPcm').mockImplementation(() => {
    throw new Error('fixture failure');
  });
  f.player.enqueue(new ArrayBuffer(6200), 16000);
  expect(f.wire.close).toHaveBeenCalledOnce();
  expect(f.local.enqueue).not.toHaveBeenCalled();
  close(f);
  await settle();
});
