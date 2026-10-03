/**
 * The beat engine turns a beat map and a playback time into one intensity
 * (ADR-330): a short attack on the beat, an exponential release, a bar beat
 * slightly stronger. Pure, so the choreography is testable to the millisecond.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { BeatMap } from '../beats-schema';
import {
  BEAT_ATTACK_MS,
  BEAT_BAR_GAIN,
  BEAT_DECAY_MS,
  BEAT_HUE_CYCLE_BARS,
  BEAT_HUE_DEGREES,
  BEAT_TURNS,
  BEAT_WEIGHT_FLOOR,
  createBeatTrack,
  startBeatDriver,
} from '../beat-sync';

/** The strength a beat of `weight` pulses at: the quietest hit still moves. */
const pulse = (weight: number) => BEAT_WEIGHT_FLOOR + (1 - BEAT_WEIGHT_FLOOR) * weight;

const MAP: BeatMap = {
  version: 1,
  beats: [
    [1000, 0.5, true],
    [1464, 0.6, false],
    [1929, 0.7, false],
    [2393, 0.8, false],
    [2858, 0.8, true],
  ],
};

describe('createBeatTrack', () => {
  const track = createBeatTrack(MAP);

  it('is silent before the first beat and on an empty map', () => {
    expect(track.intensityAt(0)).toBe(0);
    expect(track.intensityAt(0.999)).toBe(0);
    expect(createBeatTrack({ version: 1, beats: [] }).intensityAt(5)).toBe(0);
  });

  it('reaches the beat strength at the end of the attack — a floor lifts the quiet ones', () => {
    expect(BEAT_WEIGHT_FLOOR).toBeGreaterThan(0);
    expect(BEAT_WEIGHT_FLOOR).toBeLessThan(1);
    expect(track.intensityAt(1.464 + BEAT_ATTACK_MS / 1000)).toBeCloseTo(pulse(0.6), 5);
    expect(track.intensityAt(1.464 + BEAT_ATTACK_MS / 2000)).toBeCloseTo(pulse(0.6) / 2, 5);
    // A beat of weight 0 still pulses at the floor; weight 1 at the full amplitude.
    const quiet = createBeatTrack({
      version: 1,
      beats: [
        [1000, 0, false],
        [2000, 1, false],
      ],
    });
    expect(quiet.intensityAt(1 + BEAT_ATTACK_MS / 1000)).toBeCloseTo(BEAT_WEIGHT_FLOOR, 5);
    expect(quiet.intensityAt(2 + BEAT_ATTACK_MS / 1000)).toBeCloseTo(1, 5);
  });

  it('releases exponentially and is nearly gone after four decay constants', () => {
    const peak = 1.464 + BEAT_ATTACK_MS / 1000;
    const afterOneTau = track.intensityAt(peak + BEAT_DECAY_MS / 1000);
    expect(afterOneTau).toBeCloseTo(pulse(0.6) * Math.exp(-1), 5);
    // Measured from the LAST beat, so no later beat takes over the release.
    const lastPeak = 2.858 + BEAT_ATTACK_MS / 1000;
    // e^-4 of a full-strength beat (the bar gain clamps the last one at 1): under 3 %.
    expect(track.intensityAt(lastPeak + (4 * BEAT_DECAY_MS) / 1000)).toBeLessThan(0.03);
  });

  it('lifts a bar beat, clamped to one', () => {
    const peak = 1 + BEAT_ATTACK_MS / 1000;
    expect(track.intensityAt(peak)).toBeCloseTo(Math.min(1, pulse(0.5) * BEAT_BAR_GAIN), 5);
    expect(BEAT_BAR_GAIN).toBeGreaterThan(1);
    expect(track.intensityAt(2.858 + BEAT_ATTACK_MS / 1000)).toBe(1);
  });

  it('follows the bar beats alone in its bar intensity: an ordinary beat adds nothing', () => {
    const peak = 1 + BEAT_ATTACK_MS / 1000;
    expect(track.barIntensityAt(0.5)).toBe(0);
    expect(track.barIntensityAt(peak)).toBeCloseTo(track.intensityAt(peak), 9);
    // At the second beat's own peak the bar envelope is the FIRST bar's release.
    const secondPeak = 1.464 + BEAT_ATTACK_MS / 1000;
    const elapsed = secondPeak * 1000 - 1000;
    const expected =
      Math.min(1, pulse(0.5) * BEAT_BAR_GAIN) *
      Math.exp(-(elapsed - BEAT_ATTACK_MS) / BEAT_DECAY_MS);
    expect(track.barIntensityAt(secondPeak)).toBeCloseTo(expected, 9);
    expect(track.barIntensityAt(secondPeak)).toBeLessThan(track.intensityAt(secondPeak));
    expect(createBeatTrack({ version: 1, beats: [[1000, 1, false]] }).barIntensityAt(2)).toBe(0);
  });

  it('drifts the hue on a cycle of bars: zero on a bar, the full swing a quarter cycle in, continuous', () => {
    expect(BEAT_HUE_CYCLE_BARS).toBe(4);
    expect(track.hueAt(0.5)).toBe(0);
    expect(track.hueAt(1.0)).toBeCloseTo(0, 9);
    // Half-way through the first bar (bars at 1.000 s and 2.858 s): an eighth of the cycle.
    const halfBar = 1 + 1.858 / 2;
    expect(track.hueAt(halfBar)).toBeCloseTo(BEAT_HUE_DEGREES * Math.sin(Math.PI / 4), 6);
    // The second bar opens a quarter of the way through the cycle: the full swing.
    expect(track.hueAt(2.858)).toBeCloseTo(BEAT_HUE_DEGREES, 6);
    expect(track.hueAt(2.857)).toBeCloseTo(track.hueAt(2.858), 2);
    // Past the last bar the drift goes on at the last bar's length, never jumps.
    expect(track.hueAt(2.858 + 1.858 / 2)).toBeCloseTo(
      BEAT_HUE_DEGREES * Math.sin(2 * Math.PI * (1.5 / BEAT_HUE_CYCLE_BARS)),
      6
    );
    expect(createBeatTrack({ version: 1, beats: [[1000, 1, false]] }).hueAt(2)).toBe(0);
  });

  it('measures the progress between two beats: zero on the beat, one just before the next', () => {
    expect(track.progressAt(0.5)).toBe(0);
    expect(track.progressAt(1.0)).toBe(0);
    expect(track.progressAt(1.232)).toBeCloseTo(0.5, 6);
    expect(track.progressAt(1.4639)).toBeCloseTo(0.9998, 3);
    expect(track.progressAt(1.464)).toBe(0);
    // Past the last beat the arc goes on at the last interval's length, then lands for good.
    expect(track.progressAt(2.858 + 0.465 / 2)).toBeCloseTo(0.5, 6);
    expect(track.progressAt(10)).toBe(1);
    expect(createBeatTrack({ version: 1, beats: [] }).progressAt(5)).toBe(0);
    expect(createBeatTrack({ version: 1, beats: [[1000, 1, false]] }).progressAt(5)).toBe(0);
  });

  it('hands each beat to the next line in turn, every line keeping its own release', () => {
    expect(BEAT_TURNS).toBe(3);
    const peak = (index: number) => MAP.beats[index][0] / 1000 + BEAT_ATTACK_MS / 1000;
    // Before the first beat no line moves.
    for (let turn = 0; turn < BEAT_TURNS; turn++) expect(track.turnIntensityAt(0.5, turn)).toBe(0);
    // Beat 0 (a bar) is line 0's; lines 1 and 2 have not had their turn yet.
    expect(track.turnIntensityAt(peak(0), 0)).toBeCloseTo(track.intensityAt(peak(0)), 5);
    expect(track.turnIntensityAt(peak(0), 1)).toBe(0);
    expect(track.turnIntensityAt(peak(0), 2)).toBe(0);
    // Beat 1 is line 1's at full strength while line 0 is still releasing beat 0.
    expect(track.turnIntensityAt(peak(1), 1)).toBeCloseTo(pulse(0.6), 5);
    const release = track.turnIntensityAt(peak(1), 0);
    expect(release).toBeGreaterThan(0);
    expect(release).toBeLessThan(track.turnIntensityAt(peak(0), 0));
    // Beats 3 and 4 wrap around: line 0 then line 1 again.
    expect(track.turnIntensityAt(peak(3), 0)).toBeCloseTo(pulse(0.8), 5);
    expect(track.turnIntensityAt(peak(4), 1)).toBeCloseTo(
      Math.min(1, pulse(0.8) * BEAT_BAR_GAIN),
      5
    );
    // Whatever the instant, the line whose turn it is carries the overall pulse.
    for (let index = 0; index < MAP.beats.length; index++) {
      expect(track.turnIntensityAt(peak(index), index % BEAT_TURNS)).toBeCloseTo(
        track.intensityAt(peak(index)),
        5
      );
    }
  });

  it('finds the governing beat by binary search exactly as a linear scan would', () => {
    const times = [1.0, 1.2, 1.463, 1.464, 1.5, 2.0, 2.4, 2.9, 10, 60];
    for (const t of times) {
      const ms = t * 1000;
      let governing: BeatMap['beats'][number] | null = null;
      for (const beat of MAP.beats) if (beat[0] <= ms) governing = beat;
      const expected = (() => {
        if (!governing) return 0;
        const elapsed = ms - governing[0];
        const envelope =
          elapsed <= BEAT_ATTACK_MS
            ? elapsed / BEAT_ATTACK_MS
            : Math.exp(-(elapsed - BEAT_ATTACK_MS) / BEAT_DECAY_MS);
        return Math.min(1, pulse(governing[1]) * (governing[2] ? BEAT_BAR_GAIN : 1) * envelope);
      })();
      expect(track.intensityAt(t)).toBeCloseTo(expected, 9);
    }
  });
});

describe('startBeatDriver', () => {
  const track = createBeatTrack(MAP);
  let frames: FrameRequestCallback[];
  let cancelled: number[];

  beforeEach(() => {
    frames = [];
    cancelled = [];
    vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => frames.push(cb));
    vi.stubGlobal('cancelAnimationFrame', (id: number) => cancelled.push(id));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  function runNextFrame(now = 0) {
    const cb = frames.shift();
    if (!cb) throw new Error('no frame scheduled');
    cb(now);
  }

  it('reads the frame clock when the browser exposes it and writes one property on the host', () => {
    const video = document.createElement('video');
    const host = document.createElement('main');
    const frameCallbacks: Array<(now: number, meta: { mediaTime: number }) => void> = [];
    Object.assign(video, {
      requestVideoFrameCallback: (cb: (now: number, meta: { mediaTime: number }) => void) =>
        frameCallbacks.push(cb),
      cancelVideoFrameCallback: vi.fn(),
    });
    Object.defineProperty(video, 'paused', { value: false, configurable: true });
    let clock = 1000;

    const stop = startBeatDriver(video, host, track, { clock: () => clock, paintLeadMs: 0 });
    expect(host.hasAttribute('data-beat')).toBe(true);

    // The presented frame is the beat at 1.464 s; one attack later the title peaks.
    frameCallbacks.shift()?.(1000, { mediaTime: 1.464 });
    clock = 1000 + BEAT_ATTACK_MS;
    runNextFrame(clock);
    expect(host.style.getPropertyValue('--beat')).toBe(pulse(0.6).toFixed(3));
    // The bar envelope and the hue ride the same tick, from the same instant.
    const at = 1.464 + BEAT_ATTACK_MS / 1000;
    expect(host.style.getPropertyValue('--beat-bar')).toBe(track.barIntensityAt(at).toFixed(3));
    expect(host.style.getPropertyValue('--beat-hue')).toBe(`${track.hueAt(at).toFixed(2)}deg`);
    expect(host.style.getPropertyValue('--beat-progress')).toBe(track.progressAt(at).toFixed(3));
    for (let turn = 0; turn < BEAT_TURNS; turn++) {
      expect(host.style.getPropertyValue(`--beat-turn-${turn}`)).toBe(
        track.turnIntensityAt(at, turn).toFixed(3)
      );
    }
    // The beat at 1.464 s is the map's second: line 1's turn.
    expect(host.style.getPropertyValue('--beat-turn-1')).toBe(pulse(0.6).toFixed(3));

    stop();
    expect(host.hasAttribute('data-beat')).toBe(false);
    expect(host.style.getPropertyValue('--beat')).toBe('');
    expect(host.style.getPropertyValue('--beat-bar')).toBe('');
    expect(host.style.getPropertyValue('--beat-hue')).toBe('');
    expect(host.style.getPropertyValue('--beat-progress')).toBe('');
    for (let turn = 0; turn < BEAT_TURNS; turn++) {
      expect(host.style.getPropertyValue(`--beat-turn-${turn}`)).toBe('');
    }
    expect(cancelled).toHaveLength(1);
  });

  it('anchors on the time the frame is DISPLAYED, not on the callback, when the browser says it', () => {
    const video = document.createElement('video');
    const host = document.createElement('main');
    const frameCallbacks: Array<
      (now: number, meta: { mediaTime: number; expectedDisplayTime?: number }) => void
    > = [];
    Object.assign(video, {
      requestVideoFrameCallback: (
        cb: (now: number, meta: { mediaTime: number; expectedDisplayTime?: number }) => void
      ) => frameCallbacks.push(cb),
      cancelVideoFrameCallback: vi.fn(),
    });
    Object.defineProperty(video, 'paused', { value: false, configurable: true });
    let clock = 1000;
    const stop = startBeatDriver(video, host, track, { clock: () => clock, paintLeadMs: 0 });

    // Called at 1000, but the frame holding 1.464 s is shown at 1010: the peak
    // of the attack is reached at 1010 + attack, not 1000 + attack.
    frameCallbacks.shift()?.(1000, { mediaTime: 1.464, expectedDisplayTime: 1010 });
    clock = 1010 + BEAT_ATTACK_MS;
    runNextFrame(clock);
    expect(host.style.getPropertyValue('--beat')).toBe(pulse(0.6).toFixed(3));
    stop();
  });

  it('paints one display frame ahead: what is written now shows at the next vsync', () => {
    const video = document.createElement('video');
    const host = document.createElement('main');
    const frameCallbacks: Array<(now: number, meta: { mediaTime: number }) => void> = [];
    Object.assign(video, {
      requestVideoFrameCallback: (cb: (now: number, meta: { mediaTime: number }) => void) =>
        frameCallbacks.push(cb),
      cancelVideoFrameCallback: vi.fn(),
    });
    Object.defineProperty(video, 'paused', { value: false, configurable: true });
    let clock = 1000;
    const stop = startBeatDriver(video, host, track, { clock: () => clock, paintLeadMs: 16 });

    frameCallbacks.shift()?.(1000, { mediaTime: 1.464 });
    // With a 16 ms lead, the value written 16 ms BEFORE the peak is the peak.
    clock = 1000 + BEAT_ATTACK_MS - 16;
    runNextFrame(clock);
    expect(host.style.getPropertyValue('--beat')).toBe(pulse(0.6).toFixed(3));
    stop();
  });

  it('falls back to currentTime without the frame clock, and only writes when the value moves', () => {
    const video = document.createElement('video');
    const host = document.createElement('main');
    video.currentTime = 1.464 + BEAT_ATTACK_MS / 1000;

    const stop = startBeatDriver(video, host, track, { paintLeadMs: 0 });
    runNextFrame();
    expect(host.style.getPropertyValue('--beat')).toBe(pulse(0.6).toFixed(3));

    const writes = vi.spyOn(host.style, 'setProperty');
    runNextFrame();
    expect(writes).not.toHaveBeenCalled();

    video.currentTime = 10;
    runNextFrame();
    expect(host.style.getPropertyValue('--beat')).toBe('0.000');
    stop();
  });
});
