import { describe, expect, it } from 'vitest';

import { languages } from '@/i18n/settings';

import { WAKE_SHIPPED_LANGUAGES } from '../manifest';
import { STOP_WORDS, WAKE_PHRASES, stopWordOf, wakePhraseOf } from '../phrases';

describe('wake phrases', () => {
  it('names one phrase per interface language, each ending on LIA', () => {
    expect(Object.keys(WAKE_PHRASES).sort()).toEqual([...languages].sort());
    for (const phrase of Object.values(WAKE_PHRASES)) expect(phrase).toMatch(/\bLIA$/);
  });

  it('reads the phrase of a regional variant, and none for a language without a shipped model', () => {
    expect(wakePhraseOf('fr')).toBe('Dis LIA');
    expect(wakePhraseOf('fr-BE')).toBe('Dis LIA');
    expect(wakePhraseOf('pt-BR')).toBeNull();
    for (const language of languages) {
      expect(wakePhraseOf(language)).toBe(
        WAKE_SHIPPED_LANGUAGES.includes(language) ? WAKE_PHRASES[language] : null
      );
    }
    expect(wakePhraseOf(undefined)).toBeNull();
  });
});

describe('stop commands', () => {
  it('names one command per interface language: LIA, then the word — never the wake phrase', () => {
    expect(Object.keys(STOP_WORDS).sort()).toEqual([...languages].sort());
    for (const language of languages) {
      expect(STOP_WORDS[language]).toMatch(/^LIA[,，] ?\S/);
      expect(STOP_WORDS[language]).not.toBe(WAKE_PHRASES[language]);
    }
  });

  it('reads the command of a regional variant, and none for a language without a shipped model', () => {
    expect(stopWordOf('fr-CH')).toBe(STOP_WORDS.fr);
    expect(stopWordOf('pt')).toBeNull();
    for (const language of languages) {
      expect(stopWordOf(language)).toBe(
        WAKE_SHIPPED_LANGUAGES.includes(language) ? STOP_WORDS[language] : null
      );
    }
  });
});
