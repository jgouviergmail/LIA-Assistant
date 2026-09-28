/**
 * The radio's wire contract (ADR-324): what the API says about a session and
 * its segments, and what the player tells it back.
 *
 * A session is produced ahead of the listener and played as a queue of short
 * MP3 segments; the player reports where it is, and every report is answered
 * with the session's state — the ready segments, the cost so far, the stop.
 */

export type RadioSessionStatus = 'starting' | 'on_air' | 'ending' | 'ended';

/**
 * The station music under a programme — mirrors `MusicMood` in
 * apps/api/src/domains/radio/formats.py; the web library holds tracks for each.
 */
export type MusicMood = 'morning' | 'news' | 'evening' | 'calm';

/** Where a sentence comes from — shown under the voice. */
export interface RadioSource {
  label: string;
  url: string | null;
  published_at: string | null;
  /** The newsroom story the page can open (`GET /radio/articles/{id}`); null for a record of the listener's. */
  article_id: string | null;
}

/** A role the listener gives a voice in the settings. */
export type RadioRole = 'host' | 'anchor' | 'expert' | 'columnist';
/** Every role heard on air: the listener's four, and the station's commentators (a
 * debate's, a discussion's), whom the station casts itself. */
export type RadioSpeakingRole = RadioRole | 'speaker_a' | 'speaker_b' | 'speaker_c';

/** One spoken line, when it starts in its segment, and what it rests on. */
export interface RadioTranscriptLine {
  role: RadioSpeakingRole;
  text: string;
  offset_s: number;
  sources: RadioSource[];
}

/** A segment ready to air. */
export interface RadioSegment {
  seq: number;
  format: string;
  /** The station music the player plays under it; null when unknown. */
  mood: MusicMood | null;
  title: string;
  duration_s: number;
  transcript: RadioTranscriptLine[];
}

/** The session, as every report answers it. */
export interface RadioSessionState {
  session_id: string;
  status: RadioSessionStatus;
  /** Ready segments the player has not reported as finished, ascending. */
  segments: RadioSegment[];
  /** What the session has cost so far, in euros (every family), or null. */
  cost_eur: number | null;
  /** The automatic stop (ISO instant), or null for none. */
  stop_at: string | null;
  /** Seconds before the first voice, estimated when the session started. */
  startup_estimate_s: number | null;
  /** Why the session ended (bounded vocabulary), once it has. */
  end_reason: string | null;
  /** The station music to play now — that of what airs next; null when unknown. */
  mood: MusicMood | null;
  /** The station's name, as its host says it; null when unknown. */
  station_name: string | null;
  /** What the planned listening (`cost_estimate_s`) will cost, estimated; null before enough radio was produced. */
  cost_estimate_eur: number | null;
  /** The listening the estimate covers: the timer's, else an hour. */
  cost_estimate_s: number | null;
  /**
   * Seconds of the station's music between two programmes (ADR-324 decision 36):
   * the player waits as long before the next one — a news flash never waits.
   * Absent from an answer that predates it: no rest.
   */
  segment_gap_s?: number;
  /**
   * A news flash to air NOW (ADR-324 decision 32): the player cuts the programme
   * on air for it and resumes that programme where it stopped. Absent or null
   * when none; never listed among `segments`.
   */
  flash?: RadioSegment | null;
}

/** What the listener may choose for one session, on top of their settings. */
export interface RadioStartOptions {
  /** Automatic stop in minutes; 0 for none; absent for the listener's setting. */
  timer_minutes?: number;
  /** Nothing personal airs (listening in company); absent for the setting. */
  public_mode?: boolean;
}

/** Where the listener is, as the player reports it. */
export interface RadioPlayhead {
  /** The segment playing, or the next one expected while waiting. */
  seq: number;
  position_s: number;
  /** A segment is being heard (false while paused, and while the music waits). */
  playing: boolean;
  /** The listener paused — over a segment or over the music: the automatic stop waits. */
  paused: boolean;
  /** The highest news flash played to its end — sent once one was (0 for none). */
  flash_heard?: number;
}

/* ------------------------------------------------------------------------ */
/* Settings (GET /radio/options, GET|PUT /radio/preferences) — mirrors      */
/* apps/api/src/domains/radio/{schemas,preferences}.py.                     */
/* ------------------------------------------------------------------------ */

export type RadioFrequency = 'off' | 'rare' | 'normal' | 'often';
export type RadioVerificationMode = 'off' | 'news' | 'all';

/** A format the listener may tune. */
export interface RadioFormatOption {
  format: string;
  default_frequency: RadioFrequency;
  label_key: string;
  /** The most stories one programme tells; null when it is not news. */
  stories_max: number | null;
}

/** A voice of the engine the radio speaks with. */
export interface RadioVoiceOption {
  voice_id: string;
  label: string;
  gender: string | null;
  language: string | null;
}

/** What the settings may offer — published because it is enforced. */
export interface RadioOptions {
  formats: RadioFormatOption[];
  frequencies: RadioFrequency[];
  sources: string[];
  verification_modes: RadioVerificationMode[];
  /** The verification of a listener who never chose (the instance's default). */
  verification_default: RadioVerificationMode;
  verification_checked: Record<RadioVerificationMode, string[]>;
  roles: RadioRole[];
  voices: RadioVoiceOption[];
  voice_id_max_chars: number;
  station_name_max_chars: number;
  timer_default_minutes: number;
  timer_max_minutes: number;
  custom_sources_max: number;
  source_address_max_chars: number;
  /** The longest name a site may be given. */
  source_title_max_chars: number;
  /** The local hour the journal's noon edition starts (ADR-324 decision 41). */
  noon_from_hour: number;
  /** The local hour the journal's evening edition starts. */
  evening_from_hour: number;
}

/** The listener's radio settings; a field left null or absent is the default. */
export interface RadioPreferences {
  frequencies: Record<string, RadioFrequency>;
  disabled_sources: string[];
  /** The base sources (by address) the listener unticked; every other one airs, translated. */
  disabled_feeds: string[];
  voices: Partial<Record<RadioRole, string>>;
  /** null = the instance's default. */
  verification: RadioVerificationMode | null;
  /** null = the instance's default; 0 = no automatic stop. */
  timer_minutes: number | null;
  public_mode: boolean;
  /** null = the personality the chat uses. */
  personality_id: string | null;
  /** null = the name the listener's language gives the station. */
  station_name: string | null;
}

/** How looking for a site's feed ended (POST /radio/sources/preview). */
export type RadioDiscoveryOutcome =
  | 'found'
  | 'not_public'
  | 'unreachable'
  | 'forbidden'
  | 'no_feed';

/** What looking for a site's feed found — shown before the site is added. */
export interface RadioDiscovery {
  outcome: RadioDiscoveryOutcome;
  feed_url: string | null;
  title: string | null;
  language: string | null;
  entries: number | null;
}

/** A site the listener added to their newsroom, and what it holds for them. */
export interface RadioCustomSource {
  id: string;
  feed_url: string;
  title: string;
  language: string | null;
  /** Paused: not read, not offered. */
  paused: boolean;
  /** Its last readings failed (the newsroom backs off). */
  failing: boolean;
  /** Stories it published within the window. */
  stories: number;
  /** Of those, the ones the listener never heard. */
  unheard: number;
}

/** A base source (a feed of the shipped catalogue), and what it holds for the listener. */
export interface RadioBaseSource {
  /** Its address — what the settings untick it by. */
  url: string;
  name: string;
  /** The language it publishes in (backend code). */
  language: string;
  /** Whether the listener's radio reads it (ticked). */
  heard: boolean;
  failing: boolean;
  stories: number;
  unheard: number;
}

/** Every source of the listener's newsroom (GET /radio/sources, ADR-324 decision 38). */
export interface RadioSources {
  base: RadioBaseSource[];
  own: RadioCustomSource[];
  /** Stories the station can air: those of the ticked and running sources. */
  stories: number;
  /** Of those, the ones the listener never heard. */
  unheard: number;
  /** The window counted: the oldest story a programme airs. */
  window_hours: number;
}

/** A story's article, as the page shows it under the transcript (GET /radio/articles/{id}). */
export interface RadioArticle {
  id: string;
  outlet: string;
  url: string;
  published_at: string;
  /** The headline — in the listener's language when translated. */
  title: string;
  /** The text, one blank line between paragraphs. */
  text: string;
  /** Whether the text is the whole article (else the outlet's summary). */
  complete: boolean;
  /** Whether the text stops before the article does. */
  cut: boolean;
  /** Whether the title and the text are a translation. */
  translated: boolean;
  /** The feed's language, when it declares one. */
  source_language: string | null;
  /** A translation was due and could not be made: the original is shown. */
  translation_failed: boolean;
  /** A translation was due and the listener's radio budget is spent: the original, no model asked. */
  budget_reached: boolean;
  /** What this reading cost the listener: 0 from the shared cache, null when unknown. */
  cost_eur: number | null;
}

/** What the listener's radio spent over the rolling day (GET /radio/budget, ADR-324 decision 37). */
export interface RadioBudget {
  /** The bound over the window, in euros (0 = none). */
  limit_eur: number;
  /** What the radio — its sessions and article translations — spent over the window. */
  spent_eur: number;
  /** The rolling window, in hours. */
  window_hours: number;
  /** While the bound is reached, when it lifts (ISO 8601); null otherwise. */
  lifts_at: string | null;
}
