/**
 * FAQ answer grouping — content-preservation tests.
 *
 * The public FAQ renders the huge "What can I ask LIA?" answer (~10k chars of
 * `<br>`-separated bullets under `<strong>` emoji headings) as collapsible
 * per-domain groups. The transformation is presentation-only: these tests run
 * against the REAL translation files of all 6 locales and prove that every
 * word of the source answer survives the split (nothing lost, nothing added,
 * order preserved), and that non-matching answers (zh's q4 has a completely
 * different structure) fall back to untouched rendering.
 */

import { describe, it, expect } from 'vitest';

import { splitAnswerGroups } from '../faq-answer-groups';

import en from '../../../locales/en/translation.json';
import fr from '../../../locales/fr/translation.json';
import de from '../../../locales/de/translation.json';
import es from '../../../locales/es/translation.json';
import it_ from '../../../locales/it/translation.json';
import zh from '../../../locales/zh/translation.json';

const LOCALES = { en, fr, de, es, it: it_, zh } as const;
const GROUPED_LOCALES = ['en', 'fr', 'de', 'es', 'it'] as const;

function q4Answer(locale: keyof typeof LOCALES): string {
  return LOCALES[locale].faq.sections.getting_started.questions.q4.answer;
}

/** Text an end user reads: tags stripped, bullets dropped, spaces collapsed. */
function readableText(html: string): string {
  return html
    .replace(/<br\s*\/?>/gi, ' ')
    .replace(/<[^>]*>/g, '')
    .replace(/•/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

describe('splitAnswerGroups', () => {
  it.each(GROUPED_LOCALES)('groups the %s q4 answer into its 12 domains', locale => {
    const groups = splitAnswerGroups(q4Answer(locale));
    expect(groups).not.toBeNull();
    expect(groups!.groups).toHaveLength(12);
    // Every group carries a heading and at least one bullet item.
    for (const group of groups!.groups) {
      expect(group.heading.length).toBeGreaterThan(0);
      expect(group.items.length).toBeGreaterThan(0);
    }
  });

  it.each(GROUPED_LOCALES)('preserves every word of the %s q4 answer', locale => {
    const source = q4Answer(locale);
    const parsed = splitAnswerGroups(source)!;
    const reassembled = [
      parsed.intro,
      ...parsed.groups.flatMap(g => [g.heading, ...g.items]),
    ].join(' ');
    expect(readableText(reassembled)).toBe(readableText(source));
  });

  it('returns null for the zh q4 answer (different structure, no groups)', () => {
    expect(splitAnswerGroups(q4Answer('zh'))).toBeNull();
  });

  it('returns null for short answers without grouped headings', () => {
    expect(splitAnswerGroups('A plain <strong>bold</strong> answer.')).toBeNull();
    expect(
      splitAnswerGroups('Line<br><br><strong>Only one heading</strong><br>• "item"')
    ).toBeNull();
  });

  it('keeps inline markup (em, strong, a) inside bullet items verbatim', () => {
    const html =
      'Intro:' +
      '<br><br><strong>🅰️ A</strong><br>• "<em>first <strong>bold</strong></em>"<br>• "<a href="/x">link</a>"' +
      '<br><br><strong>🅱️ B</strong><br>• "<em>second</em>"' +
      '<br><br><strong>🅲 C</strong><br>• "<em>third</em>"';
    const parsed = splitAnswerGroups(html)!;
    expect(parsed.intro).toBe('Intro:');
    expect(parsed.groups[0].items[0]).toBe('"<em>first <strong>bold</strong></em>"');
    expect(parsed.groups[0].items[1]).toBe('"<a href="/x">link</a>"');
    expect(parsed.groups[1].items[0]).toBe('"<em>second</em>"');
  });
});
