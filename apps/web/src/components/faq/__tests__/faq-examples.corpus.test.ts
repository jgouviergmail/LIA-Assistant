/**
 * Clickable FAQ examples (W1) — the splitter against the REAL corpus.
 *
 * Unit tests on synthetic strings prove the rule; only the corpus proves the
 * rule survives 222 questions authored by hand across six languages, with their
 * emoji headings, nested bullet lists, HTML entities and locale-specific
 * quotation marks.
 *
 * The two invariants that matter:
 *  - LOSSLESS: nothing authored may disappear in the split. A dropped sentence
 *    would be invisible in review and obvious to a user.
 *  - NO NONSENSE: every extracted phrase must be a plausible instruction, not
 *    a fragment of prose that happened to sit near a bullet.
 */

import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { describe, it, expect } from 'vitest';

import { splitFaqAnswer } from '../faq-examples';

const LOCALES = ['en', 'fr', 'de', 'es', 'it', 'zh'] as const;

/** Every authored answer of a locale, flattened. */
function answersOf(locale: string): Array<{ path: string; answer: string }> {
  const raw = readFileSync(join(process.cwd(), 'locales', locale, 'translation.json'), 'utf8');
  const dictionary = JSON.parse(raw) as {
    faq: { sections: Record<string, { questions?: Record<string, { answer?: string }> }> };
  };
  const out: Array<{ path: string; answer: string }> = [];
  for (const [section, body] of Object.entries(dictionary.faq.sections)) {
    for (const [key, question] of Object.entries(body.questions ?? {})) {
      if (question.answer) out.push({ path: `${section}.${key}`, answer: question.answer });
    }
  }
  return out;
}

describe.each(LOCALES)('FAQ corpus — %s', locale => {
  const answers = answersOf(locale);

  it('has answers to split', () => {
    expect(answers.length).toBeGreaterThan(20);
  });

  it('never loses authored content', () => {
    // Rebuild each answer from its segments and compare byte for byte. The
    // `<em>` wrapper is re-added around every extracted phrase; anything else
    // differing means content vanished or was duplicated.
    for (const { path, answer } of answers) {
      const rebuilt = splitFaqAnswer(answer)
        .map(segment => (segment.kind === 'html' ? segment.html : `<em>${segment.text}</em>`))
        .join('');
      // Entity decoding is one-way, so compare on the decoded form.
      const normalise = (value: string) =>
        value
          .replace(/&quot;/g, '"')
          .replace(/&#39;|&apos;/g, "'")
          .replace(/&laquo;/g, '«')
          .replace(/&raquo;/g, '»')
          .replace(/&nbsp;/g, ' ')
          .replace(/&amp;/g, '&')
          // The splitter trims the phrase it lifts; ignore that difference.
          .replace(/<em>\s+/g, '<em>')
          .replace(/\s+<\/em>/g, '</em>');
      expect(normalise(rebuilt), `${locale}/${path} lost or duplicated content`).toBe(
        normalise(answer)
      );
    }
  });

  it('extracts only plausible instructions', () => {
    for (const { path, answer } of answers) {
      for (const segment of splitFaqAnswer(answer)) {
        if (segment.kind !== 'example') continue;
        expect(segment.text.length, `${locale}/${path}: empty command`).toBeGreaterThan(1);
        expect(segment.text, `${locale}/${path}: markup leaked into a command`).not.toMatch(/[<>]/);
        expect(segment.text, `${locale}/${path}: undecoded entity`).not.toMatch(/&[a-z]+;/i);
        expect(segment.text, `${locale}/${path}: untrimmed command`).toBe(segment.text.trim());
      }
    }
  });

  it('fits what the composer accepts', () => {
    // The backend caps a message at 10 000 characters and the composer mirrors
    // that; an example longer than the cap would prefill something unsendable.
    for (const { path, answer } of answers) {
      for (const segment of splitFaqAnswer(answer)) {
        if (segment.kind !== 'example') continue;
        expect(segment.text.length, `${locale}/${path} is too long to send`).toBeLessThan(10_000);
      }
    }
  });
});

describe('FAQ corpus — coverage across locales', () => {
  /** Commands found per locale, for the counts asserted below. */
  const counts = Object.fromEntries(
    LOCALES.map(locale => [
      locale,
      answersOf(locale).reduce(
        (total, { answer }) =>
          total + splitFaqAnswer(answer).filter(s => s.kind === 'example').length,
        0
      ),
    ])
  ) as Record<(typeof LOCALES)[number], number>;

  it('turns hundreds of written phrases into a rail to the chat', () => {
    // Measured 2026-07-26. A large drop would mean the discriminator stopped
    // matching the authored style — the failure mode of a silent scanner.
    expect(counts.fr).toBeGreaterThanOrEqual(350);
    expect(counts.en).toBeGreaterThanOrEqual(350);
  });

  it('covers every locale, not just the reference ones', () => {
    for (const locale of LOCALES) {
      expect(counts[locale], `${locale} has almost no clickable example`).toBeGreaterThanOrEqual(
        300
      );
    }
  });

  it('documents the known content drift between locales', () => {
    // The FAQ answers are authored, not machine-translated: German and Chinese
    // legitimately carry fewer examples than French. The i18n parity guard
    // checks KEYS, never HTML content, so nothing else would report this.
    // Pinned as a fact rather than left as a surprise.
    const spread = Math.max(...Object.values(counts)) - Math.min(...Object.values(counts));
    expect(spread, `unexpected spread across locales: ${JSON.stringify(counts)}`).toBeLessThan(80);
  });
});
