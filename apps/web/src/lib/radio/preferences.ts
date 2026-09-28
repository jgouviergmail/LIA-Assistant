/**
 * Editing the radio's settings — pure and immutable, one rule each (ADR-324).
 *
 * The API refuses what the radio cannot honour; these helpers never produce
 * it: a name holds nothing the API refuses and never passes its maximum, and a
 * base source is unticked once. A choice the helpers cannot make returns the
 * SAME object, so a caller can tell « nothing to save » by identity.
 */

import type { RadioFrequency, RadioPreferences, RadioRole } from './types';

/** The format tuned to a frequency. */
export function withFrequency(
  preferences: RadioPreferences,
  format: string,
  frequency: RadioFrequency
): RadioPreferences {
  return { ...preferences, frequencies: { ...preferences.frequencies, [format]: frequency } };
}

/** A personal source heard (or silenced) on the listener's programmes. */
export function withSourceHeard(
  preferences: RadioPreferences,
  source: string,
  heard: boolean
): RadioPreferences {
  const silenced = preferences.disabled_sources.includes(source);
  if (heard === !silenced) return preferences;
  const disabled_sources = heard
    ? preferences.disabled_sources.filter(item => item !== source)
    : [...preferences.disabled_sources, source];
  return { ...preferences, disabled_sources };
}

/** A base source heard (ticked) or not — by its address; every one is heard by default. */
export function withFeedHeard(
  preferences: RadioPreferences,
  url: string,
  heard: boolean
): RadioPreferences {
  const unticked = preferences.disabled_feeds.includes(url);
  if (heard === !unticked) return preferences;
  const disabled_feeds = heard
    ? preferences.disabled_feeds.filter(item => item !== url)
    : [...preferences.disabled_feeds, url];
  return { ...preferences, disabled_feeds };
}

/** What the API refuses in a name: markup, template braces, invisible characters. */
// Control, format (a zero-width space), surrogate and private-use characters —
// never « unassigned »: what this browser does not know yet, the API keeps too.
const NAME_REFUSED = /[<>{}\p{Cc}\p{Cf}\p{Cs}\p{Co}]/gu;

/**
 * A name as the listener typed it — their station's, a site's — minus what the
 * API refuses: every separator a single space, at most `max` characters, counted
 * as the API counts them, by code point, so a cut never leaves half a surrogate
 * pair (which the API refuses). Empty when nothing is left to say.
 */
export function speakableName(raw: string, max: number): string {
  const folded = raw.replace(/\s/g, ' ').replace(NAME_REFUSED, '').split(' ').filter(Boolean);
  return Array.from(folded.join(' ')).slice(0, max).join('').trimEnd();
}

/**
 * The station's name as the listener typed it (``speakableName``). Nothing left
 * to say is `null`: the name the listener's language gives the station.
 */
export function withStationName(
  preferences: RadioPreferences,
  raw: string,
  max: number
): RadioPreferences {
  const name = speakableName(raw, max);
  const station_name = name === '' ? null : name;
  if (station_name === preferences.station_name) return preferences;
  return { ...preferences, station_name };
}

/** The voice of a role; `null` hands the role back to the automatic cast. */
export function withVoice(
  preferences: RadioPreferences,
  role: RadioRole,
  voiceId: string | null
): RadioPreferences {
  const voices = { ...preferences.voices };
  if (voiceId === null) delete voices[role];
  else voices[role] = voiceId;
  return { ...preferences, voices };
}

/** The automatic stops offered (minutes), bounded by the published maximum. */
const TIMER_STEPS: readonly number[] = [15, 30, 45, 60, 90, 120];

/** The stops a setting may hold now: none, the steps under the maximum, and the stored one. */
export function timerChoices(stored: number | null, max: number): number[] {
  const choices = [0, ...TIMER_STEPS.filter(minutes => minutes <= max)];
  if (stored !== null && !choices.includes(stored)) choices.push(stored);
  return choices.sort((a, b) => a - b);
}
