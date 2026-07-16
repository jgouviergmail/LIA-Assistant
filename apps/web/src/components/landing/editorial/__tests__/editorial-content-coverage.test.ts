/**
 * ANTI-REGRESSION GUARDS for the editorial landing.
 *
 * 1. Content coverage (the "zero information loss" contract): the chapter
 *    catalogs + the basics catalog must form an exact partition of
 *    REQUIRED_FEATURE_KEYS — the canonical inventory of the detailed feature
 *    cards inherited from the former features wall. Dropping a card from the
 *    landing now requires editing the contract deliberately; it can no longer
 *    happen as a silent side effect of a redesign.
 * 2. i18n contract: every key referenced by the editorial components exists,
 *    non-empty, in all 6 locales; keys orphaned by the removed sections are
 *    purged everywhere (parity cannot rot silently).
 */

import { readFileSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';

import {
  BASICS_CATALOG,
  BASICS_CHIPS,
  CHAPTERS,
  FEATURE_ICONS,
  REQUIRED_FEATURE_KEYS,
} from '../chapters-data';

const LANGS = ['en', 'fr', 'de', 'es', 'it', 'zh'] as const;

type Landing = Record<string, unknown>;

function landingBlock(lang: string): Landing {
  const file = path.join(process.cwd(), 'locales', lang, 'translation.json');
  return JSON.parse(readFileSync(file, 'utf8')).landing as Landing;
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

describe('editorial content coverage (zero information loss)', () => {
  const covered = [...CHAPTERS.flatMap(c => [...c.catalog]), ...BASICS_CATALOG];

  it('covers every canonical feature card exactly once', () => {
    expect([...covered].sort()).toEqual([...REQUIRED_FEATURE_KEYS].sort());
    expect(new Set(covered).size).toBe(covered.length);
  });

  it('has an icon for every covered feature card', () => {
    for (const key of covered) {
      expect(FEATURE_ICONS[key], `icon for ${key}`).toBeDefined();
    }
  });

  it('keeps the reused copy of every card in all 6 locales', () => {
    for (const lang of LANGS) {
      const landing = landingBlock(lang);
      for (const key of REQUIRED_FEATURE_KEYS) {
        expect(lookup(landing, `features.${key}.title`), `${lang}:${key}.title`).toBeTruthy();
        expect(
          lookup(landing, `features.${key}.description`),
          `${lang}:${key}.description`
        ).toBeTruthy();
      }
    }
  });
});

describe('editorial i18n contract', () => {
  /** Keys referenced by the editorial components (suffixes under landing.). */
  const REFERENCED: string[] = [
    'chapters.eyebrow',
    'chapters.backstage_label',
    'chapters.catalog_label',
    'chapters.how_prefix',
    ...CHAPTERS.flatMap(c => {
      const base = `chapters.${c.key}`;
      const benefits = Array.from({ length: c.benefits }, (_, i) => [
        `${base}.b${i + 1}_t`,
        `${base}.b${i + 1}_d`,
      ]).flat();
      return [`${base}.bubble`, `${base}.title`, `${base}.sub`, `${base}.how`, `${base}.catalog_hint`, ...benefits];
    }),
    // vignette / scene strings
    ...['v_query', 'v_t1', 'v_t1_sub', 'v_t2', 'v_t2_sub', 'v_t3', 'v_t3_sub', 'v_series', 'v_series_sub'].map(s => `chapters.c1.${s}`),
    ...['s_chip', 's_greet', 's_weather', 's_weather_b1', 's_weather_b2', 's_day', 's_day_b1', 's_day_b2', 's_day_b3'].map(s => `chapters.c2.${s}`),
    ...['v_intro', 'v_left', 'v_left_sub', 'v_right', 'v_right_sub', 'v_note'].map(s => `chapters.c3.${s}`),
    ...['s_chip', 's_hitl', 's_subject', 's_quote', 's_user', 's_reply'].map(s => `chapters.c4.${s}`),
    ...['v_forge', 'v_forge_sub', 'v_docs'].map(s => `chapters.c5.${s}`),
    'basics.title',
    'basics.sub',
    'basics.detail_label',
    'basics.detail_hint',
    ...BASICS_CHIPS.map(c => `basics.${c.key}`),
    ...['title', 'sub', 'cost_prefix', 'cost_note', 'p1_t', 'p1_d', 'p2_t', 'p2_d', 'p2_link', 'p3_t', 'p3_d', 'p3_link', 'p4_t', 'p4_d', 'p4_link', 'honest', 'cta'].map(s => `transparency.${s}`),
    'day.title',
    'day.tabs_label',
    ...['freelance', 'family', 'dev', 'admin'].flatMap(p => [
      `day.tab_${p}`,
      ...['s1', 's2', 's3', 's4'].flatMap(s => [`day.${p}.${s}_time`, `day.${p}.${s}_text`]),
    ]),
    ...['title', 'sub', 'tabs_label', 'tab_screens', 'tab_slides'].map(s => `gallery.${s}`),
    'rail.aria',
    ...['bubble', 'title', 'subtitle', 'button', 'note_beta', 'philosophy_link'].map(s => `cta.${s}`),
    'use_cases.example6.query',
    'use_cases.example6.description',
    // security block reused by chapter 04's catalog extra
    'security.title',
    'security.intro',
    'security.privacy_link',
    ...['data_control', 'bff', 'encryption', 'gdpr'].flatMap(k => [
      `security.${k}.title`,
      `security.${k}.description`,
    ]),
    // engineering stats strip (TechSection) reuses the proof labels
    ...['agents', 'tools', 'providers', 'voice_languages', 'tests', 'adrs', 'releases'].map(s => `proof.items.${s}`),
  ];

  /** Keys orphaned by the removed sections — must stay purged everywhere. */
  const PURGED = [
    'audience',
    'rex',
    'features.title',
    'features.subtitle',
    'features.subtitle_responsible',
    'features.responsible_desc',
    'features.group_conversation',
    'features.group_personality',
    'features.group_automation',
    'features.group_creation',
    'features.group_power',
    'proof.title',
    'proof.audit_value',
    'proof.audit_link_aria',
    'proof.rex_teaser',
    'proof.rex_link',
  ];

  it.each(LANGS)('%s carries every referenced editorial key, non-empty', lang => {
    const landing = landingBlock(lang);
    for (const key of REFERENCED) {
      expect(lookup(landing, key), `${lang}:landing.${key}`).toBeTruthy();
    }
  });

  it.each(LANGS)('%s keeps the orphaned keys purged', lang => {
    const landing = landingBlock(lang);
    for (const key of PURGED) {
      expect(lookup(landing, key), `${lang}:landing.${key}`).toBeUndefined();
    }
  });

  it.each(LANGS)('%s keeps how_it_works alive for the HowTo JsonLd', lang => {
    const landing = landingBlock(lang);
    for (const step of ['step1', 'step2', 'step3', 'step4']) {
      expect(lookup(landing, `how_it_works.${step}.title`)).toBeTruthy();
      expect(lookup(landing, `how_it_works.${step}.description`)).toBeTruthy();
    }
  });
});
