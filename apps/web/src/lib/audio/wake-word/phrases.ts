/**
 * The wake phrase and the stop word of each interface language (ADR-329, spec
 * A6 and the amendment of 2026-10-01).
 *
 * A phrase is a TRAINED model, never a free entry: these are the phrases the
 * toolbox trains (`scripts/wake-word/wakeword/languages.py`), and every
 * shipped manifest is held to these tables by `shipped-models.test.ts`. The
 * tables let a screen name the words before any model is loaded (the
 * settings); the detector reports the loaded model's own phrase, the same.
 */
import type { Language } from '@/i18n/settings';

import { wakeLanguageOf } from './manifest';

export const WAKE_PHRASES: Record<Language, string> = {
  fr: 'Dis LIA',
  en: 'Hey LIA',
  de: 'Hey LIA',
  es: 'Oye LIA',
  it: 'Ehi LIA',
  zh: '嗨 LIA',
};

/** The word that cuts LIA's voice while she reads an answer aloud (owner choice, 2026-10-01). */
export const STOP_WORDS: Record<Language, string> = {
  fr: 'Stop',
  en: 'Stop',
  de: 'Stopp',
  es: 'Detente',
  it: 'Stop',
  zh: '停下',
};

/** The phrase of an interface language (any regional variant), or null without a model. */
export function wakePhraseOf(language: string | null | undefined): string | null {
  const wakeLanguage = wakeLanguageOf(language);
  return wakeLanguage ? WAKE_PHRASES[wakeLanguage] : null;
}

/** The stop word of an interface language (any regional variant), or null without a model. */
export function stopWordOf(language: string | null | undefined): string | null {
  const wakeLanguage = wakeLanguageOf(language);
  return wakeLanguage ? STOP_WORDS[wakeLanguage] : null;
}
