/**
 * The wake phrase and the stop command of each interface language (ADR-329,
 * spec A6 and the amendments of 2026-10-01 and 2026-10-02).
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

/**
 * What cuts LIA's voice while she reads an answer aloud: her name, then the word
 * (owner decision, 2026-10-02) — a bare « stop », one syllable, was found one
 * time in two and fired on songs.
 */
export const STOP_WORDS: Record<Language, string> = {
  fr: 'LIA, stop',
  en: 'LIA, stop',
  de: 'LIA, stopp',
  es: 'LIA, detente',
  it: 'LIA, stop',
  zh: 'LIA，停下',
};

/** The phrase of an interface language (any regional variant), or null without a model. */
export function wakePhraseOf(language: string | null | undefined): string | null {
  const wakeLanguage = wakeLanguageOf(language);
  return wakeLanguage ? WAKE_PHRASES[wakeLanguage] : null;
}

/** The stop command of an interface language (any regional variant), or null without a model. */
export function stopWordOf(language: string | null | undefined): string | null {
  const wakeLanguage = wakeLanguageOf(language);
  return wakeLanguage ? STOP_WORDS[wakeLanguage] : null;
}
