/**
 * The station's music (ADR-324, decision 28): a dozen instrumental tracks per
 * mood, generated once with Lyria and shipped under `public/radio/music/`
 * (`scripts/assets/generate_radio_music.py`; their provenance beside them).
 * Served by this origin, so the player can lower them under a voice through Web
 * Audio on every engine — Safari included — with no third party in the loop.
 *
 * Checked from the backend (`test_music_library.py`): every mood the station
 * names has its tracks, and every file ships exactly as generated.
 */
import library from '@/data/radio/music-library.json';

import type { MusicMood } from './types';

/** One track of the library. */
export interface MusicTrack {
  /** Where this origin serves it. */
  file: string;
  duration_s: number;
}

/** Every mood's tracks — a mood the data lacks is a compile error here. */
export const MUSIC_LIBRARY: Readonly<Record<MusicMood, readonly MusicTrack[]>> = library.moods;
