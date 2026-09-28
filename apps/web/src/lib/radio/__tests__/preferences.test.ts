/**
 * Editing the radio's settings never produces what the API refuses: a base
 * source is unticked once, a name holds nothing the API refuses and never passes
 * its maximum, and a change without effect is the same object.
 */
import { describe, expect, it } from 'vitest';

import {
  speakableName,
  withFeedHeard,
  withSourceHeard,
  withStationName,
  withVoice,
} from '../preferences';
import { radioPreferences as preferences } from './fixtures';

const WIRE = 'https://feeds.example/world.xml';

describe('base sources', () => {
  it('unticks a base source once and ticks it back; every one is heard by default', () => {
    const unticked = withFeedHeard(preferences(), WIRE, false);
    expect(unticked.disabled_feeds).toEqual([WIRE]);
    expect(withFeedHeard(unticked, WIRE, false)).toBe(unticked);
    expect(withFeedHeard(unticked, WIRE, true).disabled_feeds).toEqual([]);
    const every = preferences();
    expect(withFeedHeard(every, WIRE, true)).toBe(every);
  });
});

describe('names', () => {
  it('folds a site’s name like the station’s, and says when nothing is left', () => {
    expect(speakableName('  My   <blog>​ ', 120)).toBe('My blog');
    expect(speakableName(' {} ', 120)).toBe('');
    expect(speakableName('x'.repeat(130), 120)).toHaveLength(120);
  });
});

describe('sources and voices', () => {
  it('silences a source and hears it again; a choice without effect is the same object', () => {
    const silenced = withSourceHeard(preferences(), 'health', false);
    expect(silenced.disabled_sources).toEqual(['health']);
    expect(withSourceHeard(silenced, 'health', false)).toBe(silenced);
    expect(withSourceHeard(silenced, 'health', true).disabled_sources).toEqual([]);
  });

  it('keeps the station’s name as the listener wrote it, minus what the API refuses', () => {
    const name = (raw: string) => withStationName(preferences(), raw, 40).station_name;
    expect(name('  Radio   Alex ')).toBe('Radio Alex');
    expect(name('Radio\tAlex')).toBe('Radio Alex'); // a pasted tab separates, never glues
    expect(name('Radio <Alex>\u200b{x}')).toBe('Radio Alexx');
    expect(name('Radio \ue000Alex')).toBe('Radio Alex'); // private use: refused by the API
    // A character this browser's Unicode does not know (yet): the API keeps it
    // too, so the page never strips what the server would have accepted.
    expect(name('Radio \u0378')).toBe('Radio \u0378');
    // Nothing left to say: the language's own name again.
    const named = withStationName(preferences(), 'Radio Alex', 40);
    expect(withStationName(named, '   ', 40).station_name).toBeNull();
    // A name that does not change is the same object: no save.
    expect(withStationName(named, ' Radio Alex ', 40)).toBe(named);
  });

  it('holds the published maximum as the API counts it, by character', () => {
    expect(withStationName(preferences(), 'x'.repeat(50), 40).station_name).toBe('x'.repeat(40));
    // An emoji is one character to the API and two code units to JavaScript:
    // never cut in half (a lone surrogate is refused), never counted twice.
    expect(withStationName(preferences(), '📻'.repeat(41), 40).station_name).toBe('📻'.repeat(40));
    // A cut that lands after a space leaves no trailing space.
    expect(withStationName(preferences(), `${'x'.repeat(39)} y`, 40).station_name).toBe(
      'x'.repeat(39)
    );
  });

  it('hands a role back to the automatic cast', () => {
    const chosen = withVoice(preferences(), 'host', 'fr-A');
    expect(chosen.voices).toEqual({ host: 'fr-A' });
    expect(withVoice(chosen, 'host', null).voices).toEqual({});
  });
});
