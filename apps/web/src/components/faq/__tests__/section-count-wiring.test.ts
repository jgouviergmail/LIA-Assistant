/**
 * A FAQ section renders `q1..qN` where N comes from a SEPARATE string,
 * `faq.sections.<section>.count` (FAQContent.tsx: `parseInt(t(...count))`).
 * Adding a question therefore takes TWO edits, and forgetting the second one
 * fails silently in the worst way: i18n parity passes (the key exists in all 6
 * locales), no test breaks, no console warning — the answer simply never
 * appears on the page.
 *
 * The mirror defect is just as quiet: a count larger than the questions written
 * makes the section render `faq.sections.x.questions.q8.question` as literal
 * text to the user.
 *
 * Checked on every locale, not just the reference one: the count is a string
 * per locale, so one language can drift on its own.
 */

import { describe, it, expect } from 'vitest';

// Suffixed on purpose: the Italian locale is `it`, which would shadow
// vitest's `it` and turn the whole file into a parse error.
import deLocale from '../../../../locales/de/translation.json';
import enLocale from '../../../../locales/en/translation.json';
import esLocale from '../../../../locales/es/translation.json';
import frLocale from '../../../../locales/fr/translation.json';
import itLocale from '../../../../locales/it/translation.json';
import zhLocale from '../../../../locales/zh/translation.json';

interface FaqSection {
  count: string;
  questions: Record<string, { question: string; answer: string }>;
}

const LOCALES: Record<string, Record<string, FaqSection>> = {
  en: enLocale.faq.sections as unknown as Record<string, FaqSection>,
  fr: frLocale.faq.sections as unknown as Record<string, FaqSection>,
  de: deLocale.faq.sections as unknown as Record<string, FaqSection>,
  es: esLocale.faq.sections as unknown as Record<string, FaqSection>,
  it: itLocale.faq.sections as unknown as Record<string, FaqSection>,
  zh: zhLocale.faq.sections as unknown as Record<string, FaqSection>,
};

const entries = Object.entries(LOCALES);

describe('FAQ section count wiring', () => {
  it.each(entries)('%s declares a count matching the questions written', (_lng, sections) => {
    const mismatched = Object.entries(sections)
      .filter(([, section]) => Number(section.count) !== Object.keys(section.questions).length)
      .map(
        ([name, section]) =>
          `${name}: count=${section.count} but ${Object.keys(section.questions).length} questions`
      );

    expect(
      mismatched,
      'a count below the questions written hides the extra answers; a count above ' +
        `renders raw i18n keys to the user: ${mismatched.join(' | ')}`
    ).toEqual([]);
  });

  it.each(entries)('%s numbers its questions q1..qN without a gap', (_lng, sections) => {
    const broken = Object.entries(sections)
      .filter(([, section]) => {
        const keys = Object.keys(section.questions);
        const expected = keys.map((_, i) => `q${i + 1}`);
        return [...keys].sort().join() !== [...expected].sort().join();
      })
      .map(([name, section]) => `${name}: ${Object.keys(section.questions).join(',')}`);

    expect(
      broken,
      `the render loop is index-based, so a gap silently truncates: ${broken.join(' | ')}`
    ).toEqual([]);
  });

  it('keeps every locale on the same number of questions per section', () => {
    const [, reference] = entries[0];
    const drifted: string[] = [];

    for (const [name, section] of Object.entries(reference)) {
      const expected = Object.keys(section.questions).length;
      for (const [lng, sections] of entries.slice(1)) {
        const local = sections[name];
        if (!local) {
          drifted.push(`${lng}: section '${name}' missing`);
        } else if (Object.keys(local.questions).length !== expected) {
          drifted.push(
            `${lng}.${name}: ${Object.keys(local.questions).length} questions vs ${expected}`
          );
        }
      }
    }

    expect(drifted, `sections must stay aligned across locales: ${drifted.join(' | ')}`).toEqual(
      []
    );
  });
});
