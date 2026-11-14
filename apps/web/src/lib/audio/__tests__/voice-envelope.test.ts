/**
 * The voice LIA speaks with, as a level read off the sound itself (ADR-294,
 * follow-up of 2026-11-13). Every voice output taps its sound into one door; the
 * face reads one level. A tap is a parallel branch: the sound plays as before.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  VOICE_BLIND_AFTER_MS,
  VOICE_CEILING_DB,
  VOICE_FLOOR_DB,
  VOICE_LEAD_MS,
  tapVoice,
  tapVoiceStream,
  voiceLevel,
  type AnalyserLike,
  type TappableNode,
} from '../voice-envelope';

/** What an `AnalyserNode` accepts as `fftSize`: a power of two from 32 to 32 768. */
function checkedFftSize(value: number): number {
  if (value < 32 || value > 32_768 || (value & (value - 1)) !== 0)
    throw new DOMException('fftSize out of range', 'IndexSizeError');
  return value;
}

/** An analyser whose waveform is a sine of the amplitude the test sets. */
function analyser(amplitude = 0): AnalyserLike & { amplitude: number; disconnected: number } {
  let size = 2048;
  return {
    amplitude,
    disconnected: 0,
    get fftSize() {
      return size;
    },
    set fftSize(value: number) {
      size = checkedFftSize(value);
    },
    smoothingTimeConstant: 0.8,
    getFloatTimeDomainData(array: Float32Array<ArrayBuffer>) {
      for (let index = 0; index < array.length; index += 1)
        array[index] = this.amplitude * Math.sin((2 * Math.PI * index) / 32);
    },
    disconnect() {
      this.disconnected += 1;
    },
  };
}

/**
 * An analyser that sounds only between two moments of its buffer, counted in samples
 * back from the newest one: what was rendered then, and nothing since or before.
 */
function band(fromAgo: number, toAgo: number, amplitude = 0.2): AnalyserLike {
  let size = 2048;
  return {
    get fftSize() {
      return size;
    },
    set fftSize(value: number) {
      size = checkedFftSize(value);
    },
    smoothingTimeConstant: 0.8,
    getFloatTimeDomainData(array: Float32Array<ArrayBuffer>) {
      for (let index = 0; index < array.length; index += 1) {
        const ago = array.length - index;
        const sounding = ago <= fromAgo && ago > toAgo;
        array[index] = sounding ? amplitude * Math.sin((2 * Math.PI * index) / 32) : 0;
      }
    },
    disconnect: () => undefined,
  };
}

/** What a tap reads of an audio context, set by the test. */
interface Context {
  state: AudioContextState;
  sampleRate: number;
  baseLatency?: number;
  outputLatency?: number;
}

function node(
  tap: AnalyserLike,
  context: Context = { state: 'running', sampleRate: 48_000 }
): TappableNode & { connected: number; released: number } {
  return {
    connected: 0,
    released: 0,
    context: {
      get state() {
        return context.state;
      },
      get sampleRate() {
        return context.sampleRate;
      },
      get baseLatency() {
        return context.baseLatency;
      },
      get outputLatency() {
        return context.outputLatency;
      },
      createAnalyser: () => tap,
    },
    connect() {
      this.connected += 1;
    },
    disconnect() {
      this.released += 1;
    },
  };
}

/** The dBFS of a sine of this peak amplitude (its RMS is the peak over √2). */
const dbOf = (peak: number) => 20 * Math.log10(peak / Math.SQRT2);

const releases: (() => void)[] = [];
afterEach(() => {
  for (const release of releases.splice(0)) release();
});

describe('the voice level', () => {
  it('says nothing when no voice is playing: the face then speaks on its own', () => {
    expect(voiceLevel()).toBeNull();
  });

  it('reads the level off the sound, from silence to a full voice', () => {
    const tap = analyser(0);
    const source = node(tap);
    releases.push(tapVoice(source));
    expect(source.connected).toBe(1);
    // A tap is quick: no smoothing of its own.
    expect(tap.smoothingTimeConstant).toBe(0);

    expect(voiceLevel()).toBe(0);
    tap.amplitude = 10 ** (VOICE_FLOOR_DB / 20) * Math.SQRT2 * 0.5;
    expect(voiceLevel()).toBe(0);
    tap.amplitude = 10 ** (VOICE_CEILING_DB / 20) * Math.SQRT2 * 2;
    expect(voiceLevel()).toBe(1);
    // In between it rises with the sound.
    const levels = [0.02, 0.05, 0.1, 0.2].map(peak => {
      tap.amplitude = peak;
      return voiceLevel() ?? -1;
    });
    for (let index = 1; index < levels.length; index += 1)
      expect(levels[index]).toBeGreaterThan(levels[index - 1]);
    tap.amplitude = 0.1;
    expect(voiceLevel()).toBeCloseTo(
      (dbOf(0.1) - VOICE_FLOOR_DB) / (VOICE_CEILING_DB - VOICE_FLOOR_DB),
      2
    );
  });

  it('reads a short window, about a frame of speech: what was rendered just now', () => {
    releases.push(tapVoice(node(band(512, 0))));
    expect(voiceLevel()).toBeGreaterThan(0.5);
    releases.splice(0).forEach(release => release());
    releases.push(tapVoice(node(band(20_000, 512))));
    expect(voiceLevel()).toBe(0);
  });

  it('reads what the person hears when the face shows it: the latency back, less the delay of the face', () => {
    // At 48 kHz, 0.1 s of latency less the face's delay: the sound rendered then is
    // the sound heard when this frame is on screen.
    const back = Math.round((0.1 - VOICE_LEAD_MS / 1000) * 48_000);
    const context: Context = { state: 'running', sampleRate: 48_000 };
    releases.push(tapVoice(node(band(back + 512, back), context)));
    expect(voiceLevel()).toBe(0);
    context.outputLatency = 0.1;
    expect(voiceLevel()).toBeGreaterThan(0.5);
    // The context's own processing is part of the way, before the device's.
    context.outputLatency = 0.06;
    context.baseLatency = 0.04;
    expect(voiceLevel()).toBeGreaterThan(0.5);
    // A moment later or earlier is another sound.
    context.baseLatency = 0.07;
    expect(voiceLevel()).toBe(0);
  });

  it('never reads a sound not rendered yet: a quick device reads the newest one', () => {
    const context: Context = { state: 'running', sampleRate: 48_000, outputLatency: 0.01 };
    releases.push(tapVoice(node(band(512, 0), context)));
    expect(voiceLevel()).toBeGreaterThan(0.5);
  });

  it('reaches as far back as a wireless headset lags, and no further than a tap holds', () => {
    // 0.3 s at 48 kHz: a Bluetooth headset.
    const back = Math.round((0.3 - VOICE_LEAD_MS / 1000) * 48_000);
    const context: Context = { state: 'running', sampleRate: 48_000, outputLatency: 0.3 };
    releases.push(tapVoice(node(band(back + 512, back), context)));
    expect(voiceLevel()).toBeGreaterThan(0.5);
    releases.splice(0).forEach(release => release());
    // A latency no device has, or no number at all: read within what the tap holds.
    const absurd: Context = { state: 'running', sampleRate: 96_000, outputLatency: 5 };
    releases.push(tapVoice(node(analyser(0.2), absurd)));
    expect(voiceLevel()).toBeGreaterThan(0.5);
    absurd.outputLatency = Number.NaN;
    expect(voiceLevel()).toBeGreaterThan(0.5);
  });

  it('hears the loudest of the voices playing at once', () => {
    const quiet = analyser(0.01);
    const loud = analyser(0.2);
    releases.push(tapVoice(node(quiet)), tapVoice(node(loud)));
    const both = voiceLevel() ?? -1;
    loud.amplitude = 0;
    expect(both).toBeGreaterThan(voiceLevel() ?? 2);
  });

  it('lets a voice go when it ends, and only that one', () => {
    const first = analyser(0.2);
    const second = analyser(0.2);
    const firstNode = node(first);
    const releaseFirst = tapVoice(firstNode);
    releases.push(tapVoice(node(second)));
    releaseFirst();
    releaseFirst();
    // Disconnected once, from its own analyser alone: the sound path is untouched.
    expect(firstNode.released).toBe(1);
    expect(first.disconnected).toBe(1);
    expect(voiceLevel()).not.toBeNull();
    second.amplitude = 0;
    expect(voiceLevel()).toBe(0);
  });

  it('hears nothing from a context that is not running: neither silence nor a level', () => {
    // A suspended context feeds its analyser nothing, whatever the speakers play.
    const context: Context = { state: 'suspended', sampleRate: 48_000 };
    const quiet = analyser(0);
    releases.push(tapVoice(node(analyser(0.2), context)));
    expect(voiceLevel()).toBeNull();
    releases.push(tapVoice(node(quiet)));
    expect(voiceLevel()).toBe(0);
    context.state = 'running';
    expect(voiceLevel()).toBeGreaterThan(0.5);
    context.state = 'closed';
    expect(voiceLevel()).toBe(0);
  });

  it('hears nothing from an analyser whose reading is no number', () => {
    const broken = analyser(Number.NaN);
    releases.push(tapVoice(node(broken)));
    expect(voiceLevel()).toBeNull();
    releases.push(tapVoice(node(analyser(0.2))));
    expect(voiceLevel()).toBeGreaterThan(0.5);
  });

  it('hears nothing from an analyser that cannot be read, and never throws to the face', () => {
    const unreadable = analyser(0.2);
    unreadable.getFloatTimeDomainData = () => {
      throw new TypeError('no float time domain here');
    };
    releases.push(tapVoice(node(unreadable)));
    expect(() => voiceLevel()).not.toThrow();
    expect(voiceLevel()).toBeNull();
  });

  it('taps a voice another sink plays on the context its caller lends', () => {
    const tap = analyser(0.2);
    const source = node(tap);
    const stream = { id: 'remote-voice' } as const;
    const lent = { createMediaStreamSource: vi.fn(() => source) };
    releases.push(tapVoiceStream(lent, stream));
    expect(lent.createMediaStreamSource).toHaveBeenCalledWith(stream);
    expect(source.connected).toBe(1);
    expect(voiceLevel()).toBeGreaterThan(0.5);
  });

  it('never stops a voice from playing when its stream cannot be tapped', () => {
    const lent = {
      createMediaStreamSource: () => {
        throw new Error('no audio track');
      },
    };
    const release = tapVoiceStream(lent, { id: 'silent' });
    expect(voiceLevel()).toBeNull();
    expect(() => release()).not.toThrow();
  });

  it('never stops a voice from playing when its sound cannot be tapped', () => {
    const broken: TappableNode = {
      context: {
        state: 'running',
        sampleRate: 48_000,
        createAnalyser: () => {
          throw new Error('no analyser here');
        },
      },
      connect: vi.fn(),
      disconnect: vi.fn(),
    };
    const release = tapVoice(broken);
    expect(voiceLevel()).toBeNull();
    expect(() => release()).not.toThrow();
  });
});

describe('a tap that hears nothing at all', () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ['performance'] });
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  /** The face listens, frame after frame, for this long: what it heard each time. */
  function listen(ms: number, frameMs = 16): (number | null)[] {
    const heard: (number | null)[] = [];
    for (let at = 0; at < ms; at += frameMs) {
      heard.push(voiceLevel());
      vi.advanceTimersByTime(frameMs);
    }
    return heard;
  }

  it('is a silence while a voice may still be starting, then blind: the face speaks on its own', () => {
    releases.push(tapVoice(node(analyser(0))));
    expect(new Set(listen(VOICE_BLIND_AFTER_MS - 50))).toEqual(new Set([0]));
    listen(100);
    expect(voiceLevel()).toBeNull();
    // A voice that is heard beside it is heard all the same.
    releases.push(tapVoice(node(analyser(0.2))));
    expect(voiceLevel()).toBeGreaterThan(0.5);
  });

  it('trusts a tap that heard its voice once, through every silence after', () => {
    const tap = analyser(0.2);
    releases.push(tapVoice(node(tap)));
    expect(voiceLevel()).toBeGreaterThan(0.5);
    tap.amplitude = 0;
    expect(new Set(listen(3 * VOICE_BLIND_AFTER_MS))).toEqual(new Set([0]));
  });

  it('takes a voice too quiet to open the mouth for a sound all the same: such a tap is never blind', () => {
    // About -50 dBFS: below the floor, far above the zeros of a blind analyser.
    expect(VOICE_FLOOR_DB).toBeGreaterThan(-50);
    releases.push(tapVoice(node(analyser(10 ** (-50 / 20) * Math.SQRT2))));
    expect(new Set(listen(3 * VOICE_BLIND_AFTER_MS))).toEqual(new Set([0]));
  });

  it('counts the time the face listens, never a pause between two speeches', () => {
    releases.push(tapVoice(node(analyser(0))));
    listen(VOICE_BLIND_AFTER_MS / 2);
    // The face did not speak for a minute: nobody listened.
    vi.advanceTimersByTime(60_000);
    expect(new Set(listen(VOICE_BLIND_AFTER_MS / 2 - 200))).toEqual(new Set([0]));
  });
});
