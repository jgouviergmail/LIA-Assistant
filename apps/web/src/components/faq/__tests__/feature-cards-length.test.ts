/**
 * The "How LIA works" cards are a synthesis, not a specification.
 *
 * Owner directive, 2026-08-29: "les paragraphes sont bien mais trop longs, il
 * faut synthétiser et expliquer l'essentiel et le plus intéressant". Measured
 * before the pass: 68 cards, 50 380 characters in English, a median of 710 and
 * a longest card at 1 533 — a wall of prose nobody reads in a FAQ intro. After:
 * 31 025 characters, median 458, longest 640.
 *
 * The drift is silent by nature. Every release adds one sentence to the card
 * whose feature it touched, each addition is individually justified, and three
 * releases later the section is back where it was. That is exactly what
 * happened: `security` reached 1 533 characters one clause at a time.
 *
 * SHRINK-ONLY, like every other ratchet in this repository. Lower the cap after
 * a shortening pass; never raise it to admit a card that grew. If a card needs
 * more than this to be understood, the detail belongs in the FAQ answers below,
 * in a guide, or in `docs/` — not in the card that is supposed to make someone
 * want to read them.
 */

import { describe, it, expect } from 'vitest';

import de from '../../../../locales/de/translation.json';
import en from '../../../../locales/en/translation.json';
import es from '../../../../locales/es/translation.json';
import fr from '../../../../locales/fr/translation.json';
import itLocale from '../../../../locales/it/translation.json';
import zh from '../../../../locales/zh/translation.json';

type Card = { title: string; description: string };

const BUNDLES: Record<string, { faq: { intro: { features: Record<string, Card> } } }> = {
  de,
  en,
  es,
  fr,
  it: itLocale,
  zh,
};

/**
 * Longest admissible description, in characters, per locale.
 *
 * Measured 2026-08-29 after the shortening pass; the value is the real maximum
 * rounded up to leave a card room to be rephrased, not to grow. German and
 * Spanish run longest because their compounds and articles are; Chinese is
 * dense and sits far below its cap, which is deliberately not tightened to its
 * measurement — a translation may legitimately need a clause the English does
 * not.
 */
const MAX_DESCRIPTION: Record<string, number> = {
  en: 700,
  fr: 800,
  de: 800,
  es: 800,
  it: 800,
  zh: 400,
};

/** Longest admissible aggregate, in characters: the section as a whole. */
const MAX_TOTAL: Record<string, number> = {
  en: 33_000,
  fr: 36_500,
  de: 36_500,
  es: 36_000,
  it: 36_000,
  zh: 12_000,
};

describe('FAQ intro cards stay a synthesis', () => {
  for (const [locale, bundle] of Object.entries(BUNDLES)) {
    const features = bundle.faq.intro.features;

    it(`${locale}: no card exceeds its cap`, () => {
      const tooLong = Object.entries(features)
        .filter(([, card]) => card.description.length > MAX_DESCRIPTION[locale])
        .map(([key, card]) => `${key} (${card.description.length})`);

      expect(tooLong).toEqual([]);
    });

    it(`${locale}: the section as a whole stays under its cap`, () => {
      const total = Object.values(features).reduce((sum, card) => sum + card.description.length, 0);

      expect(total).toBeLessThanOrEqual(MAX_TOTAL[locale]);
    });

    it(`${locale}: every card still says something`, () => {
      const tooShort = Object.entries(features)
        .filter(([, card]) => card.description.trim().length < 40)
        .map(([key]) => key);

      expect(tooShort).toEqual([]);
    });
  }
});
