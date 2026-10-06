/**
 * The player's voice element over the station's music: the permission taken in
 * the click, the music lowered under each segment and raised after it, only a
 * segment's end reported, and an undecodable segment never hangs the antenna.
 */
import { readFileSync } from 'node:fs';
import { URL as FileURL } from 'node:url';
import { describe, expect, it } from 'vitest';

import { radioAudio, type MediaElement, type RadioMusic } from '../audio-element';
import type { MusicMood } from '../types';
import { MUSIC_LIBRARY } from '../music-library';
import { unlockMedia } from '../web-audio';

class FakeMedia implements MediaElement {
  src = '';
  currentTime = 0;
  refuse = false;
  plays: string[] = [];
  paused = 0;
  private listeners = new Map<string, Array<() => void>>();

  play(): Promise<void> {
    this.plays.push(this.src);
    return this.refuse ? Promise.reject(new Error('NotAllowedError')) : Promise.resolve();
  }

  pause(): void {
    this.paused += 1;
  }

  load(): void {}

  removeAttribute(name: string): void {
    if (name === 'src') this.src = '';
  }

  addEventListener(type: 'ended' | 'error', listener: () => void): void {
    this.listeners.set(type, [...(this.listeners.get(type) ?? []), listener]);
  }

  fire(type: 'ended' | 'error'): void {
    for (const listener of this.listeners.get(type) ?? []) listener();
  }
}

class FakeMusic implements RadioMusic {
  calls: string[] = [];

  unlock(): void {
    this.calls.push('unlock');
  }

  play(mood: MusicMood): void {
    this.calls.push(`play:${mood}`);
  }

  duck(under: boolean): void {
    this.calls.push(under ? 'duck' : 'unduck');
  }

  pause(): void {
    this.calls.push('pause');
  }

  resume(): void {
    this.calls.push('resume');
  }

  stop(): void {
    this.calls.push('stop');
  }
}

function setUp() {
  const media = new FakeMedia();
  const music = new FakeMusic();
  const audio = radioAudio(media, music);
  const ended: string[] = [];
  audio.onSegmentEnded(() => ended.push(media.src));
  return { media, music, audio, ended };
}

describe('radioAudio', () => {
  it('takes the permission to play for the voice and the music inside the click', async () => {
    const { media, music, audio, ended } = setUp();
    audio.begin();
    expect(media.plays).toHaveLength(1);
    expect(media.plays[0]).toMatch(/^data:audio\/wav;base64,/);
    expect(music.calls).toEqual(['unlock']);
    await Promise.resolve();
    media.fire('ended');
    expect(ended).toEqual([]); // the permission's silence is no segment
  });

  it('hands the mood to the music', () => {
    const { music, audio } = setUp();
    audio.music('news');
    expect(music.calls).toEqual(['play:news']);
  });

  it('lowers the music under a segment and raises it when the segment ends', async () => {
    const { media, music, audio, ended } = setUp();
    await audio.playSegment('blob:1');
    expect(music.calls).toEqual(['duck']);
    media.fire('ended');
    media.fire('ended');
    expect(music.calls).toEqual(['duck', 'unduck']);
    expect(ended).toEqual(['blob:1']);
  });

  it('reports a segment the element cannot decode as ended, the music raised', async () => {
    const { media, music, audio, ended } = setUp();
    await audio.playSegment('blob:2');
    media.fire('error');
    expect(ended).toEqual(['blob:2']);
    expect(music.calls.at(-1)).toBe('unduck');
  });

  it('lets a refused play reach the player, raises the music and forgets that segment', async () => {
    const { media, music, audio, ended } = setUp();
    media.refuse = true;
    await expect(audio.playSegment('blob:3')).rejects.toThrow('NotAllowedError');
    expect(music.calls).toEqual(['duck', 'unduck']);
    media.fire('ended');
    expect(ended).toEqual([]);
  });

  it('pauses and resumes the voice with the music, the voice only when a segment was on air', async () => {
    const { media, music, audio } = setUp();
    audio.pause();
    await audio.resume();
    expect(media.plays).toEqual([]);
    await audio.playSegment('blob:4');
    audio.pause();
    await audio.resume();
    expect(media.plays).toEqual(['blob:4', 'blob:4']);
    expect(music.calls).toEqual(['pause', 'resume', 'duck', 'pause', 'resume']);
  });

  it('stops for good: the music goes out and nothing is reported after', async () => {
    const { media, music, audio, ended } = setUp();
    await audio.playSegment('blob:5');
    audio.stop();
    media.fire('ended');
    expect(ended).toEqual([]);
    expect(media.src).toBe('');
    expect(music.calls.at(-1)).toBe('stop');
  });

  it('resumes a programme a news flash cut where it stopped, a new one from its start', async () => {
    const { audio, media } = setUp();
    media.currentTime = 3;
    await audio.playSegment('blob:programme', 12.5);
    expect(media.src).toBe('blob:programme');
    expect(media.currentTime).toBe(12.5);

    media.currentTime = 4;
    await audio.playSegment('blob:next');
    expect(media.currentTime).toBe(4); // untouched: a new source starts at its beginning
  });
});

class DeferredMedia extends FakeMedia {
  readonly readiness = Promise.withResolvers<void>();

  override play(): Promise<void> {
    this.plays.push(this.src);
    return this.readiness.promise;
  }
}

function emittedWav(media: FakeMedia): Uint8Array {
  expect(media.src).toMatch(/^data:audio\/wav;base64,/);
  return Uint8Array.from(atob(media.src.slice('data:audio/wav;base64,'.length)), character =>
    character.charCodeAt(0)
  );
}

describe('native media priming', () => {
  it('emits a cached tenth of a second of silent stereo PCM', async () => {
    const media = new FakeMedia();
    const second = new FakeMedia();
    unlockMedia(media);
    unlockMedia(second);
    expect(media.plays).toEqual([media.src]);
    expect(second.src).toBe(media.src);
    const bytes = emittedWav(media);
    const header = new DataView(bytes.buffer);
    expect(String.fromCharCode(...bytes.subarray(0, 4))).toBe('RIFF');
    expect(String.fromCharCode(...bytes.subarray(8, 12))).toBe('WAVE');
    expect(header.getUint16(20, true)).toBe(1);
    expect(header.getUint16(22, true)).toBe(2);
    expect(header.getUint32(24, true)).toBe(8000);
    expect(header.getUint16(34, true)).toBe(8);
    expect(header.getUint16(32, true)).toBe(2);
    expect(header.getUint32(28, true)).toBe(16000);
    expect(header.getUint32(4, true)).toBe(bytes.byteLength - 8);
    expect(header.getUint32(40, true)).toBe(bytes.byteLength - 44);
    expect(header.getUint32(40, true) / header.getUint32(28, true)).toBe(0.1);
    expect(bytes.subarray(44).every(sample => sample === 128)).toBe(true);
    await Promise.resolve();
  });

  it('primes the same channel count as every shipped music track', async () => {
    const media = new FakeMedia();
    unlockMedia(media);
    const primingChannels = new DataView(emittedWav(media).buffer).getUint16(22, true);
    const tracks = Object.values(MUSIC_LIBRARY).flat();
    expect(tracks.length).toBeGreaterThan(0);
    for (const track of tracks) {
      const bytes = readFileSync(new FileURL(`../../../../public${track.file}`, import.meta.url));
      let offset = 0;
      if (bytes.toString('ascii', 0, 3) === 'ID3') {
        const size =
          ((bytes.readUInt8(6) & 127) << 21) |
          ((bytes.readUInt8(7) & 127) << 14) |
          ((bytes.readUInt8(8) & 127) << 7) |
          (bytes.readUInt8(9) & 127);
        offset = 10 + size + (bytes.readUInt8(5) & 16 ? 10 : 0);
      }
      const header = bytes.readUInt32BE(offset);
      expect(header >>> 21, track.file).toBe(2047);
      const trackChannels = ((header >>> 6) & 3) === 3 ? 1 : 2;
      expect(primingChannels, track.file).toBe(trackChannels);
    }
    await Promise.resolve();
  });

  it('pauses a completed priming play once when silence is still selected', async () => {
    const media = new DeferredMedia();
    unlockMedia(media);
    expect(media.paused).toBe(0);
    media.readiness.resolve();
    await media.readiness.promise;
    expect(media.paused).toBe(1);
  });

  it('never pauses a new segment when an earlier priming play resolves', async () => {
    const media = new DeferredMedia();
    unlockMedia(media);
    media.src = 'blob:next-segment';
    media.readiness.resolve();
    await media.readiness.promise;
    expect(media.paused).toBe(0);
    expect(media.src).toBe('blob:next-segment');
  });
});
