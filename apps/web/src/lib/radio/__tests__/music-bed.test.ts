/**
 * The station's music (ADR-324, decision 28): started once, never silent between
 * programmes, handed from track to track and mood to mood by crossfades, lowered
 * under every voice — and quiet at once when the listener stops.
 */
import { describe, expect, it } from 'vitest';

import {
  MUSIC_CROSSFADE_S,
  MUSIC_DUCK_ATTACK_S,
  MUSIC_DUCK_RELEASE_S,
  MUSIC_DUCKED_LEVEL,
  MUSIC_FADE_IN_S,
  MUSIC_STOP_FADE_S,
  MusicBed,
  type MusicChannel,
} from '../music-bed';
import type { MusicTrack } from '../music-library';
import type { MusicMood } from '../types';

function tracks(mood: string, count: number): MusicTrack[] {
  return Array.from({ length: count }, (_, index) => ({
    file: `/radio/music/${mood}/${mood}-${index + 1}.mp3`,
    duration_s: 120,
  }));
}

const LIBRARY: Record<MusicMood, MusicTrack[]> = {
  morning: tracks('morning', 3),
  news: tracks('news', 3),
  evening: tracks('evening', 3),
  calm: tracks('calm', 3),
};

class FakeChannel implements MusicChannel {
  events: string[] = [];
  currentTime = 0;
  duration = 120;
  private progress: () => void = () => undefined;

  unlock(): void {
    this.events.push('unlock');
  }

  load(url: string): void {
    this.events.push(`load:${url}`);
    this.currentTime = 0;
  }

  play(): Promise<void> {
    this.events.push('play');
    return Promise.resolve();
  }

  pause(): void {
    this.events.push('pause');
  }

  fade(level: number, seconds: number): void {
    this.events.push(`fade:${level}@${seconds}`);
  }

  onProgress(listener: () => void): void {
    this.progress = listener;
  }

  /** The element reports where it is. */
  at(seconds: number): void {
    this.currentTime = seconds;
    this.progress();
  }

  loaded(): string[] {
    return this.events.filter(event => event.startsWith('load:')).map(event => event.slice(5));
  }
}

function seeded(): () => number {
  let seed = 7;
  return () => {
    seed = (seed * 16807) % 2147483647;
    return (seed - 1) / 2147483646;
  };
}

function bed(library: Record<MusicMood, MusicTrack[]> = LIBRARY, random = seeded()) {
  const channels = [new FakeChannel(), new FakeChannel()] as const;
  const master: string[] = [];
  const pending: Array<() => void> = [];
  let woken = 0;
  const music = new MusicBed({
    channels,
    master: { fade: (level, seconds) => master.push(`${level}@${seconds}`) },
    library,
    wake: () => {
      woken += 1;
    },
    random,
    later: callback => {
      pending.push(callback);
    },
  });
  return {
    music,
    channels,
    master,
    woken: () => woken,
    flush: () => {
      for (const callback of pending.splice(0)) callback();
    },
  };
}

/** The tracks loaded on either deck, in the order they were loaded. */
function played(channels: readonly [FakeChannel, FakeChannel]): string[] {
  const order: string[] = [];
  const cursors = [0, 0];
  // Each handover alternates decks, starting on deck 0.
  for (let deck = 0; ; deck = 1 - deck) {
    const next = channels[deck].loaded()[cursors[deck]];
    if (next === undefined) return order;
    order.push(next);
    cursors[deck] += 1;
  }
}

describe('MusicBed', () => {
  it('plays nothing until asked, and takes the permission to play inside the click', () => {
    const { music, channels, woken } = bed();
    music.unlock();
    expect(woken()).toBe(1);
    expect(channels.map(channel => channel.events)).toEqual([['unlock'], ['unlock']]);
  });

  it('starts the first mood on one deck, faded in, at full level', () => {
    const { music, channels, master } = bed();
    music.play('news');
    const [first] = channels[0].loaded();
    expect(first).toMatch(/^\/radio\/music\/news\/news-\d\.mp3$/);
    expect(channels[0].events).toEqual([
      'fade:0@0',
      `load:${first}`,
      'play',
      `fade:1@${MUSIC_FADE_IN_S}`,
    ]);
    expect(master).toEqual(['1@0']);
    expect(channels[1].events).toEqual([]);
  });

  it('changes nothing when the mood it already plays is asked again', () => {
    const { music, channels } = bed();
    music.play('news');
    const before = channels.map(channel => [...channel.events]);
    music.play('news');
    expect(channels.map(channel => channel.events)).toEqual(before);
  });

  it('crossfades to a new mood: the other deck brings it in, the first fades out then pauses', () => {
    const { music, channels, flush } = bed();
    music.play('news');
    music.play('evening');
    const [incoming] = channels[1].loaded();
    expect(incoming).toMatch(/\/evening\//);
    expect(channels[1].events.slice(-2)).toEqual(['play', `fade:1@${MUSIC_CROSSFADE_S}`]);
    expect(channels[0].events.at(-1)).toBe(`fade:0@${MUSIC_CROSSFADE_S}`);
    flush();
    expect(channels[0].events.at(-1)).toBe('pause');
    expect(channels[1].events.at(-1)).not.toBe('pause');
  });

  it('hands a track about to end to the next one of its mood, every track once before any repeats', () => {
    const { music, channels } = bed();
    music.play('calm');
    for (let handover = 0; handover < 5; handover += 1) {
      const deck = handover % 2;
      channels[deck].at(120 - MUSIC_CROSSFADE_S + 0.1);
    }
    const order = played(channels);
    expect(order).toHaveLength(6);
    expect(new Set(order.slice(0, 3)).size).toBe(3);
    expect(new Set(order.slice(3, 6)).size).toBe(3);
    for (let index = 1; index < order.length; index += 1) {
      expect(order[index]).not.toBe(order[index - 1]);
    }
  });

  it('never opens a new bag on the track just heard', () => {
    // Two tracks; the first bag keeps its order, the second is reversed — so,
    // left as drawn, the second bag would open on the track that just played.
    const draws = [0.99, 0];
    const { music, channels } = bed(
      { ...LIBRARY, calm: tracks('calm', 2) },
      () => draws.shift() ?? 0
    );
    music.play('calm');
    for (let handover = 0; handover < 2; handover += 1) {
      channels[handover % 2].at(120 - MUSIC_CROSSFADE_S + 0.1);
    }
    const order = played(channels);
    expect(order).toHaveLength(3);
    expect(order[2]).not.toBe(order[1]);
  });

  it('never pauses the deck a quick second change of mood brought back', () => {
    const { music, channels, flush } = bed();
    music.play('news'); // deck 0
    music.play('evening'); // deck 1 in, deck 0 out
    music.play('news'); // deck 0 back in, deck 1 out — before deck 0 was paused
    flush();
    expect(channels[0].events.at(-1)).not.toBe('pause');
    expect(channels[1].events.at(-1)).toBe('pause');
  });

  it('ignores the deck that already handed over, and a track far from its end', () => {
    const { music, channels } = bed();
    music.play('calm');
    channels[0].at(30);
    expect(channels[1].loaded()).toEqual([]);
    channels[0].at(120 - MUSIC_CROSSFADE_S + 0.1);
    channels[0].at(120);
    expect(channels[1].loaded()).toHaveLength(1);
    expect(channels[0].loaded()).toHaveLength(1);
  });

  it('lowers the music under a voice and raises it after', () => {
    const { music, master } = bed();
    music.play('morning');
    music.duck(true);
    music.duck(false);
    expect(master.slice(-2)).toEqual([
      `${MUSIC_DUCKED_LEVEL}@${MUSIC_DUCK_ATTACK_S}`,
      `1@${MUSIC_DUCK_RELEASE_S}`,
    ]);
  });

  it('fades everything out on a stop, pauses both decks after the fade, and starts afresh after', () => {
    const { music, channels, master, flush } = bed();
    music.play('news');
    music.stop();
    expect(master.at(-1)).toBe(`0@${MUSIC_STOP_FADE_S}`);
    flush();
    expect(channels.map(channel => channel.events.at(-1))).toEqual(['pause', 'pause']);
    music.play('calm');
    expect(master.at(-1)).toBe('1@0');
    expect(channels[0].loaded().at(-1)).toMatch(/\/calm\//);
  });

  it('never lets a fade scheduled before a stop silence the music started after it', () => {
    const { music, channels, flush } = bed();
    music.play('news');
    music.play('evening');
    music.stop();
    music.play('calm');
    const active = channels[1].events.at(-1)?.startsWith('fade:1') ? 1 : 0;
    flush();
    expect(channels[active].events.at(-1)).not.toBe('pause');
  });

  it('pauses with the listener and resumes the deck that was playing', () => {
    const { music, channels } = bed();
    music.play('news');
    music.pause();
    expect(channels.map(channel => channel.events.at(-1))).toEqual(['pause', 'pause']);
    music.resume();
    expect(channels[0].events.at(-1)).toBe('play');
    music.stop();
    const count = channels[0].events.length;
    music.resume();
    expect(channels[0].events).toHaveLength(count);
  });
});
