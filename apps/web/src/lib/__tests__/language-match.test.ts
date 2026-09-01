/**
 * The spellings differ by layer on purpose: Chinese is `zh` in the frontend
 * and `zh-CN` in the backend, which is what a stored diagnosis is stamped
 * with. A raw comparison would tell a Chinese administrator that their Chinese
 * diagnosis is in a foreign language.
 */

import { describe, it, expect } from 'vitest';

import { sameLanguage } from '@/lib/language-match';

describe('sameLanguage', () => {
  it('treats the backend and frontend spellings of Chinese as one language', () => {
    expect(sameLanguage('zh-CN', 'zh')).toBe(true);
    expect(sameLanguage('zh_CN', 'zh')).toBe(true);
  });

  it('ignores region subtags and case', () => {
    expect(sameLanguage('fr-FR', 'fr')).toBe(true);
    expect(sameLanguage('EN', 'en-GB')).toBe(true);
  });

  it('separates genuinely different languages', () => {
    expect(sameLanguage('de', 'fr')).toBe(false);
    expect(sameLanguage('zh-CN', 'ja')).toBe(false);
  });

  it('says nothing when there is nothing to contradict', () => {
    // A row written before the language stamp existed must not be announced
    // as foreign — the honest answer is silence, not a guess.
    expect(sameLanguage(undefined, 'fr')).toBe(true);
    expect(sameLanguage('', 'fr')).toBe(true);
  });
});
