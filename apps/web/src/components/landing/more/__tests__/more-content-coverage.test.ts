/**
 * ANTI-REGRESSION GUARDS for the "/more" small-attentions page.
 *
 * 1. Structural contract: exactly 58 unique cards across 6 sections, every
 *    card mapped to one icon and one scene-label list — a card cannot be
 *    added or dropped as a silent side effect of an edit.
 * 2. Level contract: the page presents craft, one level below capabilities —
 *    its card keys must stay disjoint from the 36 major feature cards of the
 *    editorial landing (REQUIRED_FEATURE_KEYS).
 *
 * The i18n content guards (every more.* key present, non-empty, in all 6
 * locales; U+2019-only apostrophes in fr; no digits in card copy) live in
 * this file too — see the "i18n content" describe block.
 */

import { readFileSync } from 'node:fs';
import path from 'node:path';

import { describe, expect, it } from 'vitest';

import { REQUIRED_FEATURE_KEYS } from '../../editorial/chapters-data';
import { CARD_ICONS, MORE_CARD_KEYS, MORE_SECTIONS, SCENE_LABEL_KEYS } from '../more-data';

const LANGS = ['en', 'fr', 'de', 'es', 'it', 'zh'] as const;

function bundle(lang: string): Record<string, unknown> {
  const file = path.join(process.cwd(), 'locales', lang, 'translation.json');
  return JSON.parse(readFileSync(file, 'utf8')) as Record<string, unknown>;
}

function lookup(obj: unknown, dotted: string): unknown {
  return dotted
    .split('.')
    .reduce<unknown>(
      (acc, part) =>
        acc && typeof acc === 'object' ? (acc as Record<string, unknown>)[part] : undefined,
      obj
    );
}

/** Non-card keys the page renders directly (nav, footers, hero, meta, craft). */
const STATIC_KEYS = [
  'landing.nav.more',
  'landing.footer.more',
  'public_footer.more',
  'more.meta.title',
  'more.meta.description',
  'more.hero.title',
  'more.hero.subtitle',
  'more.hero.counter',
  'more.controls.pause_animations',
  'more.craft.title',
  'more.craft.intro',
  'more.craft.tests',
  'more.craft.languages',
  'more.craft.releases',
] as const;

describe('more-data structural contract', () => {
  it('has 58 unique cards across 6 sections', () => {
    expect(MORE_SECTIONS).toHaveLength(6);
    expect(MORE_CARD_KEYS).toHaveLength(58);
    expect(new Set(MORE_CARD_KEYS).size).toBe(58);
    expect(MORE_SECTIONS.map(s => s.cards.length)).toEqual([4, 10, 8, 10, 9, 17]);
  });

  it('presents the air-quality honesty rule among the unseen attentions', () => {
    const unseen = MORE_SECTIONS.find(s => s.id === 'unseen');
    expect(unseen?.cards).toContain('air_quality_honesty');
  });

  it('derives the flat key list from the sections in display order', () => {
    expect(MORE_CARD_KEYS).toEqual(MORE_SECTIONS.flatMap(s => [...s.cards]));
  });

  it('is disjoint from the 36 major feature cards of the editorial landing', () => {
    const majors = new Set<string>(REQUIRED_FEATURE_KEYS);
    expect(MORE_CARD_KEYS.filter(k => majors.has(k))).toEqual([]);
  });

  it('maps every card to exactly one icon and one scene-label list', () => {
    expect(Object.keys(CARD_ICONS).sort()).toEqual([...MORE_CARD_KEYS].sort());
    expect(Object.keys(SCENE_LABEL_KEYS).sort()).toEqual([...MORE_CARD_KEYS].sort());
  });

  it('numbers sections 01..06 with alternating tint starting untinted', () => {
    expect(MORE_SECTIONS.map(s => s.num)).toEqual(['01', '02', '03', '04', '05', '06']);
    expect(MORE_SECTIONS.map(s => s.tinted)).toEqual([false, true, false, true, false, true]);
  });

  it('uses the s1..s6 i18n suffixes in order', () => {
    expect(MORE_SECTIONS.map(s => s.key)).toEqual(['s1', 's2', 's3', 's4', 's5', 's6']);
  });
});

describe('i18n content (all 6 locales)', () => {
  it.each(LANGS)('%s carries every more.* key, non-empty', lang => {
    const b = bundle(lang);
    for (const s of MORE_SECTIONS) {
      for (const suffix of ['title', 'intro'] as const) {
        expect(
          lookup(b, `more.sections.${s.key}.${suffix}`),
          `${lang} ${s.key}.${suffix}`
        ).toBeTruthy();
      }
    }
    for (const key of MORE_CARD_KEYS) {
      for (const suffix of ['title', 'desc'] as const) {
        expect(
          lookup(b, `more.cards.${key}.${suffix}`),
          `${lang} cards.${key}.${suffix}`
        ).toBeTruthy();
      }
      for (const label of SCENE_LABEL_KEYS[key]) {
        expect(
          lookup(b, `more.scenes.${key}.${label}`),
          `${lang} scenes.${key}.${label}`
        ).toBeTruthy();
      }
    }
    for (const k of STATIC_KEYS) {
      expect(lookup(b, k), `${lang} ${k}`).toBeTruthy();
    }
  });

  it('uses only typographic apostrophes (U+2019) in the fr namespace', () => {
    const raw = JSON.stringify(bundle('fr').more);
    expect(raw.includes("'")).toBe(false);
  });

  it('never bakes a digit into card copy (unmanaged-drift rule)', () => {
    for (const lang of LANGS) {
      const b = bundle(lang);
      for (const key of MORE_CARD_KEYS) {
        for (const suffix of ['title', 'desc'] as const) {
          expect(
            String(lookup(b, `more.cards.${key}.${suffix}`)),
            `${lang} cards.${key}.${suffix}`
          ).not.toMatch(/\d/);
        }
      }
    }
  });

  it('interpolates the hero counter with {{total}}, never {{count}} (zh plural trap)', () => {
    for (const lang of LANGS) {
      const counter = String(lookup(bundle(lang), 'more.hero.counter'));
      expect(counter, `${lang} hero.counter`).toContain('{{total}}');
      expect(counter, `${lang} hero.counter`).not.toContain('{{count}}');
    }
  });
});
