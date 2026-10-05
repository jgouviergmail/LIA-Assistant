import { afterEach, expect, it, vi } from 'vitest';
import { SimliPlayout, pushDecoded } from '../playout';
import type { AvatarMedia } from '../engine';
import { AVATAR_PCM_LEAD_MAX_SECONDS } from '../../voice-output/types';

function target() {
  let clock = 0;
  let quiet = true;
  let audible: () => void = () => {};
  const packets: Uint8Array[] = [];
  const media: AvatarMedia = {
    ready: true,
    get clock() {
      return clock;
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
      audible = fn;
    },
  };
  return {
    media,
    ready: true,
    send: (packet: Uint8Array) => {
      packets.push(packet);
      return true;
    },
    packets,
    advance: (seconds: number) => {
      clock += seconds;
    },
    sound: () => {
      quiet = false;
      audible();
    },
    silence: () => {
      quiet = true;
    },
  };
}
afterEach(() => vi.useRealTimers());
it('waits for a valid 30-second buffered response past the old ten-second deadline', async () => {
  vi.useFakeTimers();
  const t = target();
  Object.defineProperty(t.media, 'clock', { get: () => performance.now() / 1000 });
  const phrase = new SimliPlayout(t, 16000, vi.fn());
  for (let i = 0; i < 6; i++) phrase.pushPcm(new Int16Array(80000).fill(100).buffer);
  t.sound();
  const done = vi.fn();
  const finish = phrase.finish().then(done);
  await vi.advanceTimersByTimeAsync(12000);
  expect(done).not.toHaveBeenCalled();
  await vi.advanceTimersByTimeAsync(18500);
  t.silence();
  await vi.advanceTimersByTimeAsync(40);
  await finish;
  expect(done).toHaveBeenCalledOnce();
  expect(t.packets.reduce((bytes, packet) => bytes + packet.length, 0)).toBe(30 * 32000);
});
it('bounds a genuinely frozen playback clock even after remote sound was heard', async () => {
  vi.useFakeTimers();
  const t = target();
  const phrase = new SimliPlayout(t, 16000, vi.fn());
  phrase.push([new Float32Array(16000).fill(0.01)]);
  t.sound();
  const rejected = expect(phrase.finish()).rejects.toThrow('avatar_clock_stalled');
  await vi.advanceTimersByTimeAsync(10100);
  await rejected;
  expect(t.media.mute).toHaveBeenCalled();
});
it('preserves quiet samples and an interior pause until the sample clock drains', async () => {
  vi.useFakeTimers();
  const t = target();
  const heard = vi.fn();
  const phrase = new SimliPlayout(t, 16000, heard);
  const pcm = new Float32Array(16000);
  pcm.fill(0.0005, 0, 4000);
  pcm.fill(0.0005, 12000);
  phrase.push([pcm]);
  const drained = vi.fn();
  const finish = phrase.finish().then(drained);
  t.advance(0.3);
  t.sound();
  expect(heard).toHaveBeenCalledTimes(1);
  await vi.advanceTimersByTimeAsync(500);
  t.advance(0.2);
  t.silence();
  await vi.advanceTimersByTimeAsync(100);
  expect(drained).not.toHaveBeenCalled();
  await vi.advanceTimersByTimeAsync(500);
  t.advance(2);
  await vi.advanceTimersByTimeAsync(40);
  await finish;
  expect(t.packets.reduce((bytes, packet) => bytes + packet.length, 0)).toBe(32000);
  expect(new DataView(t.packets[0].buffer).getInt16(0, true)).toBeGreaterThan(0);
});
it('cancellation drops every pending packet and mutes without closing any connection', async () => {
  vi.useFakeTimers();
  const t = target();
  const phrase = new SimliPlayout(t, 24000, vi.fn());
  phrase.push([new Float32Array(24000)]);
  const before = t.packets.length;
  phrase.cancel();
  await vi.advanceTimersByTimeAsync(3000);
  expect(t.packets).toHaveLength(before);
  expect(t.media.mute).toHaveBeenCalled();
  expect(() => phrase.push([new Float32Array(24)])).toThrow('avatar_phrase_closed');
});
it('does not mute a delayed remote phrase before any sound arrives or cap its observed delay', async () => {
  vi.useFakeTimers();
  const t = target();
  const phrase = new SimliPlayout(t, 16000, vi.fn());
  phrase.push([new Float32Array(8000).fill(0.02)]);
  const drained = vi.fn();
  const finish = phrase.finish().then(drained);
  await vi.advanceTimersByTimeAsync(1000);
  t.advance(2.6);
  await vi.advanceTimersByTimeAsync(40);
  expect(drained).not.toHaveBeenCalled();
  t.sound();
  t.advance(0.1);
  t.silence(); // A short pause still precedes the submitted tail.
  await vi.advanceTimersByTimeAsync(40);
  expect(drained).not.toHaveBeenCalled();
  t.advance(0.8);
  await vi.advanceTimersByTimeAsync(40);
  await finish;
  expect(drained).toHaveBeenCalledOnce();
});
it('bounds a provider which accepts voiced PCM but never returns sound', async () => {
  vi.useFakeTimers();
  const t = target();
  const phrase = new SimliPlayout(t, 16000, vi.fn());
  phrase.push([new Float32Array(1600).fill(0.02)]);
  const finish = phrase.finish();
  const rejected = expect(finish).rejects.toThrow('avatar_no_remote_sound');
  await vi.advanceTimersByTimeAsync(10_100);
  await rejected;
  expect(t.media.mute).toHaveBeenCalledOnce();
  expect(phrase.pendingBytes).toBe(0);
});

it('forwards a clip at once, flushes its tail at the clip end and reports the lead', () => {
  vi.useFakeTimers();
  const t = target();
  const phrase = new SimliPlayout(t, 16000, vi.fn());
  phrase.push([new Float32Array(16000).fill(0.01)]);
  const bytes = () => t.packets.reduce((total, packet) => total + packet.length, 0);
  // Five full packets left at once; 2 000 bytes wait in the packetizer.
  expect(bytes()).toBe(30000);
  expect(vi.getTimerCount()).toBe(0);
  expect(phrase.lead).toBeCloseTo(0.9375, 3);
  phrase.flushTail();
  expect(bytes()).toBe(32000);
  expect(phrase.lead).toBeCloseTo(1, 3);
  phrase.flushTail();
  expect(t.packets).toHaveLength(6);
  phrase.cancel();
  phrase.flushTail();
  expect(t.packets).toHaveLength(6);
});
it('pushDecoded holds a clip at the lead bound and resumes as the remote clock advances', async () => {
  vi.useFakeTimers();
  const t = target();
  const phrase = new SimliPlayout(t, 16000, vi.fn());
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
  const done = vi.fn();
  const pushing = pushDecoded(phrase, buffer, new AbortController().signal).then(done);
  await vi.advanceTimersByTimeAsync(100);
  const bytes = () => t.packets.reduce((total, packet) => total + packet.length, 0);
  const bound = AVATAR_PCM_LEAD_MAX_SECONDS * 32000;
  expect(bytes()).toBeGreaterThan(bound - 8000);
  expect(bytes()).toBeLessThanOrEqual(bound + 6000);
  expect(done).not.toHaveBeenCalled();
  t.advance(3);
  await vi.advanceTimersByTimeAsync(100);
  await pushing;
  expect(bytes()).toBe(192000);
  expect(phrase.lead).toBeCloseTo(3, 3);
});
