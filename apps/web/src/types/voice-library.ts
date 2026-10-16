/**
 * The instance's Fish Audio voice library (ADR-345) — the wire shapes of
 * `/admin/voice/fishaudio/library`. Every bound the routes enforce travels in
 * `bounds` (ADR-184): the page offers exactly what the API accepts.
 */

/** The languages a design or a transcript may be asked in: the interface's six. */
export type LibraryLanguage = 'en' | 'fr' | 'de' | 'es' | 'it' | 'zh';

/** One voice the account owns. */
export interface LibraryVoice {
  voice_id: string;
  title: string;
  /** The vendor's state: `created`, `training`, `trained` or `failed`. */
  state: string;
  languages: string[];
  created_at: string | null;
  /** The TTS slots speaking with it — a voice in use cannot be deleted. */
  used_by_slots: string[];
}

export interface VoiceLibraryBounds {
  samples_max: number;
  sample_max_bytes: number;
  total_max_bytes: number;
  sample_extensions: string[];
  title_max_chars: number;
  instruction_max_chars: number;
  preview_max_chars: number;
  candidates_max: number;
  prefill_max_seconds: number;
}

export interface VoiceLibrary {
  configured: boolean;
  creation_enabled: boolean;
  prefill_available: boolean;
  design_cost_usd: number;
  candidate_ttl_seconds: number;
  voices: LibraryVoice[];
  bounds: VoiceLibraryBounds;
}

/** The public voices the instance pinned, for every voice slot (amendment 2026-10-14). */
export interface PinnedVoices {
  /** In the order they were pinned. */
  voice_ids: string[];
  /** How many voices may be pinned. */
  max_pins: number;
}

/** One designed voice, to listen to before saving it. */
export interface DesignCandidate {
  candidate_id: string;
  duration_ms: number;
  text: string | null;
  language: string | null;
  /** Its preview, a base64 WAV file. */
  audio_base64: string;
}

export interface DesignResult {
  candidates: DesignCandidate[];
  cost_usd: number;
  expires_in_seconds: number;
}

export interface DesignRequest {
  instruction: string;
  preview_text: string | null;
  language: LibraryLanguage | null;
  count: number;
}

/** A clone as the form collects it: one transcript per recording, possibly empty. */
export interface CloneRequest {
  title: string;
  samples: File[];
  texts: string[];
  enhanceAudioQuality: boolean;
  consent: boolean;
}
