/**
 * LIA's voices for one person (ADR-345 amendment 2026-10-14) — the wire shape
 * of `/voice/lia-voices`. The voices offered are the engine's that speaks in the
 * chat, with the person's language rule applied by the server; a gender left
 * null speaks with the administrator's voice.
 */

import type { VoiceOption } from '@/types/llm-config';

/** LIA's two voices, as the avatar's gender picks one. */
export type LiaVoiceGender = 'male' | 'female';

export const LIA_VOICE_GENDERS: readonly LiaVoiceGender[] = ['male', 'female'];

/** The person's choice: a voice per gender, null for the administrator's. */
export interface LiaVoiceChoice {
  male: string | null;
  female: string | null;
}

export interface LiaVoices extends LiaVoiceChoice {
  /** Whether LIA speaks on this instance at all. */
  available: boolean;
  /** The engine that speaks in the chat (provider/model). */
  engine: string;
  provider: string;
  /** The voices the person may choose, those native to their language first. */
  voices: VoiceOption[];
  /** The administrator's voice for each gender. */
  default_male: VoiceOption;
  default_female: VoiceOption;
}
