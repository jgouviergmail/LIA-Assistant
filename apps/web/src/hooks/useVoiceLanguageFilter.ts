/**
 * The state of a voice picker's language filter (ADR-345 amendment 2026-10-14):
 * on by default, offered only where it narrows the list, and never hiding the
 * voices the form holds.
 */
import { useState } from 'react';

import { languageNarrows, voicesInLanguage, type LanguageTaggedVoice } from '@/lib/voice-language';

export interface VoiceLanguageFilterState<T extends LanguageTaggedVoice> {
  /** The voices the picker shows. */
  shown: T[];
  /** Whether the filter is worth offering at all. */
  narrows: boolean;
  /** Whether it is on. */
  only: boolean;
  setOnly: (only: boolean) => void;
}

/**
 * @param voices The voices the server offers.
 * @param language The reader's language.
 * @param keep The voices the form holds — shown whatever their language.
 */
export function useVoiceLanguageFilter<T extends LanguageTaggedVoice>(
  voices: readonly T[],
  language: string,
  keep: readonly (string | null | undefined)[]
): VoiceLanguageFilterState<T> {
  const [only, setOnly] = useState(true);
  const narrows = languageNarrows(voices, language);
  const shown = narrows && only ? voicesInLanguage(voices, language, keep) : [...voices];
  return { shown, narrows, only, setOnly };
}
