/**
 * Every FAQ section that exists in the locale files is rendered, and every
 * rendered section exists.
 *
 * A section is written and translated in six languages under
 * `faq.sections.<key>`, but the page renders only the keys listed in
 * `FAQ_SECTIONS`: a section missing from that list passes i18n parity, breaks
 * no other test and simply never appears — the never-wired class this file
 * closes, after features had stayed absent from the FAQ altogether (owner
 * rule, 2026-10-17: every feature available to users is in the FAQ).
 */

import { describe, expect, it } from 'vitest';

import de from '../../../../locales/de/translation.json';
import en from '../../../../locales/en/translation.json';
import es from '../../../../locales/es/translation.json';
import fr from '../../../../locales/fr/translation.json';
import itLocale from '../../../../locales/it/translation.json';
import zh from '../../../../locales/zh/translation.json';
import { FAQ_SECTIONS, FAQ_SECTION_ICONS, PUBLIC_FAQ_SECTIONS } from '../faq-sections';

const LOCALES: Record<string, { faq: { sections: Record<string, unknown> } }> = {
  de,
  en,
  es,
  fr,
  it: itLocale,
  zh,
};

const listed = [...FAQ_SECTIONS].sort();

describe('FAQ section registry', () => {
  it.each(Object.entries(LOCALES))(
    '%s renders exactly the sections it translates',
    (_lng, bundle) => {
      expect(Object.keys(bundle.faq.sections).sort()).toEqual(listed);
    }
  );

  it('lists each section once', () => {
    expect(new Set(FAQ_SECTIONS).size).toBe(FAQ_SECTIONS.length);
  });

  it('gives every listed section an icon, and no icon to an unlisted one', () => {
    expect(Object.keys(FAQ_SECTION_ICONS).sort()).toEqual(listed);
  });

  it('exposes to visitors only sections that exist', () => {
    const known = new Set<string>(FAQ_SECTIONS);
    expect(PUBLIC_FAQ_SECTIONS.filter(section => !known.has(section))).toEqual([]);
  });
});
