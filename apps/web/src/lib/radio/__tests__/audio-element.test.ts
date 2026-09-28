/**
 * The player's voice element over the station's music: the permission taken in
 * the click, the music lowered under each segment and raised after it, only a
 * segment's end reported, and an undecodable segment never hangs the antenna.
 */
import { describe, expect, it } from 'vitest';

import { radioAudio, type MediaElement, type RadioMusic } from '../audio-element';
import type { MusicMood } from '../types';

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
