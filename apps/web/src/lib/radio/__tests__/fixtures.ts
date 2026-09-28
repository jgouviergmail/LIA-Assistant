/**
 * Typed builders of the radio's settings payloads, shared by the tests.
 *
 * They return the declared wire types with no assertion: a field the API adds
 * must be added here too, or the tests stop compiling.
 */
import type {
  RadioBaseSource,
  RadioCustomSource,
  RadioOptions,
  RadioPreferences,
  RadioSources,
} from '../types';

export function radioPreferences(over: Partial<RadioPreferences> = {}): RadioPreferences {
  return {
    frequencies: {},
    disabled_sources: [],
    disabled_feeds: [],
    voices: {},
    verification: null,
    timer_minutes: null,
    public_mode: false,
    personality_id: null,
    station_name: null,
    ...over,
  };
}

export function radioOptions(over: Partial<RadioOptions> = {}): RadioOptions {
  return {
    formats: [
      {
        format: 'headlines',
        default_frequency: 'normal',
        label_key: 'radio.formats.headlines',
        stories_max: 5,
      },
      {
        format: 'column',
        default_frequency: 'rare',
        label_key: 'radio.formats.column',
        stories_max: 1,
      },
    ],
    frequencies: ['off', 'rare', 'normal', 'often'],
    sources: ['agenda', 'mails', 'sent_mails', 'health'],
    verification_modes: ['off', 'news', 'all'],
    verification_default: 'news',
    verification_checked: {
      off: [],
      news: ['headlines', 'column'],
      all: ['headlines', 'column', 'journal'],
    },
    roles: ['host', 'anchor', 'expert', 'columnist'],
    voices: [
      { voice_id: 'fr-A', label: 'Aria', gender: 'female', language: 'fr' },
      { voice_id: 'fr-B', label: 'Bruno', gender: 'male', language: 'fr' },
    ],
    voice_id_max_chars: 100,
    station_name_max_chars: 40,
    timer_default_minutes: 30,
    timer_max_minutes: 120,
    custom_sources_max: 20,
    source_address_max_chars: 2048,
    source_title_max_chars: 120,
    noon_from_hour: 12,
    evening_from_hour: 18,
    ...over,
  };
}

export function radioBaseSource(over: Partial<RadioBaseSource> = {}): RadioBaseSource {
  return {
    url: 'https://feeds.example/world.xml',
    name: 'World Wire',
    language: 'en',
    heard: true,
    failing: false,
    stories: 12,
    unheard: 5,
    ...over,
  };
}

export function radioOwnSource(over: Partial<RadioCustomSource> = {}): RadioCustomSource {
  return {
    id: 'site-1',
    feed_url: 'https://blog.example/feed',
    title: 'My blog',
    language: 'fr',
    paused: false,
    failing: false,
    stories: 3,
    unheard: 2,
    ...over,
  };
}

export function radioSources(over: Partial<RadioSources> = {}): RadioSources {
  return {
    base: [radioBaseSource()],
    own: [radioOwnSource()],
    stories: 15,
    unheard: 7,
    window_hours: 48,
    ...over,
  };
}
