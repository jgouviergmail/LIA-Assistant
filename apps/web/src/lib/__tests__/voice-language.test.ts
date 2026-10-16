/**
 * A voice picker narrowed to the reader's language (ADR-345 amendment 2026-10-14):
 * the voices native to it and those that name no language — they speak every one —,
 * and never the voice a form already holds out of its own list.
 */
import { describe, expect, it } from 'vitest';

import { languageNarrows, voicesInLanguage } from '../voice-language';

const voice = (voice_id: string, language: string | null) => ({
  voice_id,
  label: voice_id,
  language,
});

const FISH = [
  voice('emma', 'en'),
  voice('clone', null),
  voice('emilie', 'fr'),
  voice('jun', 'ja'),
  voice('remy', 'fr-FR'),
];

describe('voicesInLanguage', () => {
  it('keeps the voices native to the language and those that name none, in their order', () => {
    expect(voicesInLanguage(FISH, 'fr').map(v => v.voice_id)).toEqual(['clone', 'emilie', 'remy']);
  });

  it('reads both spellings of a language alike — zh and zh-CN are one', () => {
    const voices = [voice('xiaoxiao', 'zh-CN'), voice('aria', 'en')];
    expect(voicesInLanguage(voices, 'zh').map(v => v.voice_id)).toEqual(['xiaoxiao']);
  });

  it('never drops a voice the form already holds', () => {
    expect(voicesInLanguage(FISH, 'fr', ['jun', null]).map(v => v.voice_id)).toEqual([
      'clone',
      'emilie',
      'jun',
      'remy',
    ]);
  });
});

describe('languageNarrows', () => {
  it('is offered when narrowing changes the list and leaves a voice', () => {
    expect(languageNarrows(FISH, 'fr')).toBe(true);
  });

  it('is not offered when every voice speaks every language', () => {
    expect(languageNarrows([voice('alloy', null), voice('nova', null)], 'fr')).toBe(false);
  });

  it('is not offered when it would leave nothing to choose', () => {
    expect(languageNarrows([voice('emma', 'en'), voice('jun', 'ja')], 'fr')).toBe(false);
  });

  it('is not offered on an empty list', () => {
    expect(languageNarrows([], 'fr')).toBe(false);
  });
});
