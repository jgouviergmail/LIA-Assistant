/**
 * Content contract of the home page's pitch: the positioning, the five
 * arguments and the comparison table.
 *
 * Every key the three sections read is a non-empty string in the six locales,
 * every contender has one of the three published statuses, and the « 60+ » of
 * the thesis is a floor of the living map, never a typed figure.
 */

import { existsSync, readFileSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';

import functional from '@/data/maps/functional.json';

import { brickCountFloor } from '../brick-floor';
import {
  ARGUMENT_IDS,
  COMPARISON_SOURCES,
  COMPETITOR_IDS,
  CONTENDER_IDS,
  CONTENDER_MARKS,
  CONTENDER_SHORT_NAMES,
  CRITERIA,
  cellKeys,
  formatSourcesReadOn,
  type ComparisonStatus,
} from '../comparison-data';

const LANGS = ['en', 'fr', 'de', 'es', 'it', 'zh'] as const;
const STATUSES: readonly ComparisonStatus[] = ['yes', 'mid', 'no'];

/** The interface words the comparison reads, below `landing.comparison`. */
const COMPARISON_UI_KEYS = [
  'title',
  'lede',
  'contenders_label',
  'view_label',
  'caption',
  'criterion_header',
  'status.yes',
  'status.mid',
  'status.no',
  'sources_title',
  'sources_body',
  'sources_note',
  'sources_report',
] as const;

/** Every key the positioning, the arguments and the comparison read. */
function pitchLocaleKeys(): string[] {
  const comparison = 'landing.comparison';
  return [
    ...['title', 'market_agents', 'market_cloud', 'thesis_title', 'thesis_body', 'stat_label'].map(
      key => `landing.positioning.${key}`
    ),
    'landing.arguments.title',
    'landing.arguments.lede',
    ...ARGUMENT_IDS.flatMap(id => [
      `landing.arguments.items.${id}.title`,
      `landing.arguments.items.${id}.body`,
    ]),
    ...COMPARISON_UI_KEYS.map(key => `${comparison}.${key}`),
    ...COMPARISON_SOURCES.map(source => `${comparison}.sources.${source.key}`),
    ...CONTENDER_IDS.flatMap(id =>
      ['role', 'quote', 'meter'].map(field => `${comparison}.contenders.${id}.${field}`)
    ),
    ...CRITERIA.flatMap(criterion => [
      `${comparison}.rows.${criterion.id}.label`,
      ...CONTENDER_IDS.flatMap(contender => {
        const keys = cellKeys(criterion.id, contender);
        return [keys.head, ...keys.bullets, keys.punch];
      }),
    ]),
  ];
}

function translation(lang: string): unknown {
  const file = path.join(process.cwd(), 'locales', lang, 'translation.json');
  return JSON.parse(readFileSync(file, 'utf8'));
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

describe('pitch content contract', () => {
  it('gives every contender one of the three published statuses on every criterion', () => {
    for (const criterion of CRITERIA) {
      expect(Object.keys(criterion.status).sort()).toEqual([...CONTENDER_IDS].sort());
      for (const contender of CONTENDER_IDS) {
        expect(STATUSES).toContain(criterion.status[contender]);
      }
    }
  });

  it('shows each product by its own mark, served from this application', () => {
    for (const id of CONTENDER_IDS) {
      const mark = CONTENDER_MARKS[id];
      expect(mark.startsWith('/'), id).toBe(true);
      const file = path.join(process.cwd(), 'public', ...mark.slice(1).split('/'));
      expect(existsSync(file), `${id} → ${mark}`).toBe(true);
    }
    expect(new Set(Object.values(CONTENDER_MARKS)).size).toBe(CONTENDER_IDS.length);
  });

  it.each([
    ['fr', '16 novembre 2026'],
    ['en', 'November 16, 2026'],
    ['de', '16. November 2026'],
    ['zh', '2026年11月16日'],
  ] as const)('dates the sources as a calendar day, whatever the zone (%s)', (lng, date) => {
    expect(formatSourcesReadOn(lng)).toBe(date);
  });

  it('names every duel button, short enough for one line', () => {
    for (const id of COMPETITOR_IDS) {
      expect(CONTENDER_SHORT_NAMES[id].length).toBeLessThanOrEqual(8);
    }
  });

  it.each(LANGS)('reads every key as a non-empty string in %s', lang => {
    const data = translation(lang);
    const missing = pitchLocaleKeys().filter(key => {
      const value = lookup(data, key);
      return typeof value !== 'string' || value.trim() === '';
    });
    expect(missing).toEqual([]);
  });

  it.each(LANGS)('names the duel in its table caption (%s)', lang => {
    expect(lookup(translation(lang), 'landing.comparison.caption')).toContain('{{name}}');
  });

  it('floors the living map to ten, so « 60+ » stays true without an edit', () => {
    const floor = brickCountFloor();
    expect(floor % 10).toBe(0);
    expect(floor).toBeGreaterThan(0);
    expect(floor).toBeLessThanOrEqual(functional.bricks.length);
    expect(functional.bricks.length - floor).toBeLessThan(10);
  });

  it.each(LANGS)('states the brick floor through {{count}}, never a typed digit (%s)', lang => {
    const thesis = lookup(translation(lang), 'landing.positioning.thesis_body');
    expect(typeof thesis).toBe('string');
    expect(thesis).toContain('{{count}}+');
    expect(String(thesis).replace('{{count}}', '')).not.toMatch(/\d/);
  });
});
