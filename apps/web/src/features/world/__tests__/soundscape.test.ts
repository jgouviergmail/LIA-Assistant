import { afterEach, expect, it, vi } from 'vitest';
import {
  Soundscape,
  WORLD_AUDIO_CACHE_BYTES,
  type SoundBackend,
  type DecodedSound,
  type SoundVoice,
} from '../audio/soundscape';
import type { SoundId } from '../audio/catalogue';
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<T>((a, b) => {
    resolve = a;
    reject = b;
  });
  return { promise, resolve, reject };
}
function setup(now: () => number = () => 5000) {
  const playing: { id: SoundId; loop: boolean; level: number; stopped: boolean }[] = [];
  const requests: {
    id: SoundId;
    signal: AbortSignal;
    response: ReturnType<typeof deferred<DecodedSound>>;
  }[] = [];
  const clip = (id: SoundId): DecodedSound => ({
    bytes: 3_000_000,
    duration: 30,
    start(loop, offset) {
      expect(offset).toBeGreaterThanOrEqual(0);
      expect(offset).toBeLessThan(30);
      const state = { id, loop, level: 0, stopped: false };
      playing.push(state);
      const voice: SoundVoice = {
        fade: level => {
          state.level = level;
        },
        stop: () => {
          state.stopped = true;
        },
      };
      return voice;
    },
  });
  const backend: SoundBackend = {
    activate: vi.fn(async () => true),
    setVolume: vi.fn(),
    load: vi.fn((id, signal) => {
      const response = deferred<DecodedSound>();
      requests.push({ id, signal, response });
      return response.promise;
    }),
    suspend: vi.fn(),
    destroy: vi.fn(),
  };
  const sound = new Soundscape(backend, { random: () => 0.5, now });
  return { sound, backend, playing, requests, clip };
}
afterEach(() => vi.useRealTimers());
it('loads nothing before a deliberate enable, and refuses stale room completions', async () => {
  const s = setup();
  await s.sound.select('birds');
  expect(s.requests).toHaveLength(0);
  const enabled = s.sound.enable();
  await Promise.resolve();
  expect(s.requests[0].id).toBe('birds');
  const latest = s.sound.select('mystic');
  expect(s.requests[0].signal.aborted).toBe(true);
  s.requests[0].response.resolve(s.clip('birds'));
  s.requests[1].response.resolve(s.clip('mystic'));
  await Promise.all([enabled, latest]);
  expect(s.playing.map(p => p.id)).toEqual(['mystic']);
  s.sound.destroy();
});
it('crossfades and keeps decoded audio bounded while visiting many rooms; silence stops the former bed', async () => {
  const s = setup();
  await s.sound.enable();
  for (const id of ['birds', 'mystic', 'gym', 'studio'] as const) {
    const change = s.sound.select(id);
    s.requests.at(-1)!.response.resolve(s.clip(id));
    await change;
  }
  expect(s.sound.decodedBytes).toBeLessThanOrEqual(WORLD_AUDIO_CACHE_BYTES);
  expect(s.playing.filter(v => !v.stopped).map(v => v.id)).toEqual(['studio']);
  await s.sound.select(null);
  expect(s.playing.every(v => v.stopped)).toBe(true);
  s.sound.destroy();
  expect(s.sound.decodedBytes).toBe(0);
});
it('mute and authority/visibility pause abort in-flight work and prevent delayed sound', async () => {
  const s = setup();
  await s.sound.enable();
  const first = s.sound.select('birds');
  s.sound.pause(true);
  expect(s.requests[0].signal.aborted).toBe(true);
  s.requests[0].response.resolve(s.clip('birds'));
  await first;
  expect(s.playing).toHaveLength(0);
  s.sound.disable();
  await s.sound.select('mystic');
  expect(s.requests).toHaveLength(1);
  s.sound.destroy();
  expect(s.backend.destroy).toHaveBeenCalledOnce();
});
it('contains decode failures and closed contexts, then recovers on a new scene', async () => {
  const s = setup();
  await s.sound.enable();
  const failed = s.sound.select('birds');
  s.requests[0].response.reject(new Error('decode'));
  await failed;
  expect(s.playing).toHaveLength(0);
  const retry = s.sound.select('mystic');
  s.requests[1].response.resolve(s.clip('mystic'));
  await retry;
  expect(s.playing.at(-1)?.id).toBe('mystic');
  s.sound.destroy();
  const unavailable = setup();
  vi.mocked(unavailable.backend.activate).mockResolvedValue(false);
  expect(await unavailable.sound.enable()).toBe(false);
  expect(unavailable.requests).toHaveLength(0);
  unavailable.sound.destroy();
});
it('rings the phone occasionally and cancels its timer on leaving; notification bursts yield one cue', async () => {
  vi.useFakeTimers();
  const s = setup();
  await s.sound.select('phone');
  await s.sound.enable();
  expect(s.requests).toHaveLength(0);
  await vi.advanceTimersByTimeAsync(30000);
  expect(s.requests[0].id).toBe('phone');
  s.requests[0].response.resolve(s.clip('phone'));
  await Promise.resolve();
  await Promise.resolve();
  expect(s.playing[0].loop).toBe(false);
  await s.sound.select(null);
  await vi.advanceTimersByTimeAsync(100000);
  expect(s.requests).toHaveLength(1);
  const ping = s.sound.notify();
  const duplicate = s.sound.notify();
  expect(s.requests.at(-1)?.id).toBe('message');
  expect(s.requests).toHaveLength(2);
  s.requests[1].response.resolve(s.clip('message'));
  await Promise.all([ping, duplicate]);
  expect(s.playing.filter(p => p.id === 'message')).toHaveLength(1);
  s.sound.destroy();
});
it('a late notification never plays after mute or shutdown', async () => {
  const s = setup();
  await s.sound.enable();
  const pending = s.sound.notify();
  s.sound.disable();
  s.requests[0].response.resolve(s.clip('message'));
  await pending;
  expect(s.playing).toHaveLength(0);
  s.sound.destroy();
  await s.sound.notify();
  expect(s.requests).toHaveLength(1);
});

it('serializes repeated gestures during one room load, and resuspends a late activation after mute', async () => {
  const s = setup();
  await s.sound.select('birds');
  const first = s.sound.enable();
  await Promise.resolve();
  const repeated = s.sound.enable();
  await Promise.resolve();
  expect(s.requests).toHaveLength(1);
  s.requests[0].response.resolve(s.clip('birds'));
  await Promise.all([first, repeated]);
  s.sound.destroy();
  const late = setup(),
    activation = deferred<boolean>();
  vi.mocked(late.backend.activate).mockReturnValue(activation.promise);
  const enabled = late.sound.enable();
  late.sound.disable();
  activation.resolve(true);
  expect(await enabled).toBe(false);
  expect(late.backend.suspend).toHaveBeenCalledTimes(2);
  late.sound.destroy();
});

it('reuses decoded sounds and rejects invalid payload dimensions without starting a source', async () => {
  const s = setup();
  await s.sound.enable();
  for (const id of ['birds', 'mystic', 'gym'] as const) {
    const selected = s.sound.select(id);
    s.requests.at(-1)!.response.resolve({ ...s.clip(id), bytes: 1000 });
    await selected;
  }
  await s.sound.select('birds');
  expect(s.requests).toHaveLength(3);
  const bad = s.sound.select('rain');
  s.requests.at(-1)!.response.resolve({ ...s.clip('rain'), duration: Number.NaN });
  await bad;
  expect(s.playing.filter(p => !p.stopped)).toHaveLength(0);
  const recovery = s.sound.select('studio');
  s.requests.at(-1)!.response.resolve(s.clip('studio'));
  await recovery;
  expect(s.playing.at(-1)?.id).toBe('studio');
  s.sound.destroy();
});
it('drops a cue whose decode finishes too late and contains a rejected browser activation', async () => {
  let now = 1000;
  const s = setup(() => now);
  await s.sound.enable();
  const ping = s.sound.notify();
  now = 5000;
  s.requests[0].response.resolve(s.clip('message'));
  await ping;
  expect(s.playing).toHaveLength(0);
  s.sound.destroy();
  s.sound.destroy();
  expect(s.backend.destroy).toHaveBeenCalledOnce();
  expect(await s.sound.enable()).toBe(false);
  s.sound.pause(false);
  await s.sound.select('birds');
  expect(s.requests).toHaveLength(1);
  const failed = setup();
  vi.mocked(failed.backend.activate).mockRejectedValue(new Error('blocked'));
  expect(await failed.sound.enable()).toBe(false);
  failed.sound.destroy();
});

it('changes only its owned master volume without enabling, decoding, or restarting a room', async () => {
  const s = setup();
  s.sound.setVolume(-1);
  expect(s.backend.setVolume).toHaveBeenLastCalledWith(0);
  s.sound.setVolume(3);
  expect(s.backend.setVolume).toHaveBeenLastCalledWith(1);
  s.sound.setVolume(0.25);
  s.sound.setVolume(Number.NaN);
  expect(s.backend.setVolume).toHaveBeenLastCalledWith(0.25);
  expect(s.backend.activate).not.toHaveBeenCalled();
  expect(s.requests).toHaveLength(0);
  await s.sound.enable();
  const selected = s.sound.select('studio');
  s.requests[0].response.resolve(s.clip('studio'));
  await selected;
  s.sound.setVolume(0);
  s.sound.setVolume(0.4);
  expect(s.backend.setVolume).toHaveBeenLastCalledWith(0.4);
  expect(s.playing).toHaveLength(1);
  expect(s.requests).toHaveLength(1);
  expect(s.playing[0].stopped).toBe(false);
  s.sound.destroy();
  const calls = vi.mocked(s.backend.setVolume).mock.calls.length;
  s.sound.setVolume(0.8);
  expect(s.backend.setVolume).toHaveBeenCalledTimes(calls);
});
