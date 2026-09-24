/**
 * The real data of the maps, in every language of the site.
 *
 * `scripts/audit/doc_maps.py` checks the files themselves (every unit in every
 * language, no stale translation); this test checks what the PAGES do with
 * them: every view builds in every language, and says the same thing about the
 * same structure. And it pins the one import rule of the section — the data of
 * six languages stays on the server.
 */

import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

import { languages } from '@/i18n/settings';

import { mapsData } from '../data';
import { buildBrickMap, buildHistory, buildSummary } from '../model';

const CJK = /[一-鿿]/;

describe('the maps data', () => {
  it('builds every view in every language, over the same structure', () => {
    const reference = buildSummary(mapsData('fr'));
    for (const lng of languages) {
      const data = mapsData(lng);
      const functional = buildBrickMap(data, 'functional');
      const technical = buildBrickMap(data, 'technical');
      const history = buildHistory(data);
      expect(buildSummary(data).functional, lng).toEqual(reference.functional);
      expect(buildSummary(data).history, lng).toEqual(reference.history);
      for (const brick of [...functional.bricks, ...technical.bricks]) {
        expect(brick.name.trim(), `${lng} ${brick.id}`).not.toBe('');
        expect(brick.role.trim(), `${lng} ${brick.id}`).not.toBe('');
      }
      for (const flow of [...functional.flows, ...technical.flows]) {
        expect(
          flow.steps.every(step => step.text.trim()),
          `${lng} ${flow.id}`
        ).toBe(true);
      }
      expect(
        history.decisions.every(d => d.title && d.summary),
        lng
      ).toBe(true);
    }
  });

  it('speaks each language, not the French source', () => {
    const fr = buildHistory(mapsData('fr'));
    for (const lng of languages.filter(l => l !== 'fr')) {
      const view = buildHistory(mapsData(lng));
      const copied = view.decisions.filter((d, i) => d.summary === fr.decisions[i].summary);
      expect(
        copied.map(d => d.adr),
        lng
      ).toEqual([]);
    }
    expect(CJK.test(buildBrickMap(mapsData('zh'), 'functional').lede)).toBe(true);
  });

  it('carries the facts the tree gave it: a version, a date, a file per decision', () => {
    const { facts, history } = mapsData('fr');
    expect(facts.version).toMatch(/^\d+\.\d+\.\d+$/);
    expect(facts.releaseDate).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    const withoutFile = history.entries.filter(e => !facts.adrFiles[String(e.adr)]);
    expect(withoutFile.every(e => Boolean(e.nofile))).toBe(true);
  });

  it('is never imported by a client component', () => {
    const roots = [join(__dirname, '..'), join(__dirname, '../../../components/maps')];
    const offenders: string[] = [];
    for (const root of roots) {
      for (const entry of readdirSync(root, { withFileTypes: true })) {
        if (!entry.isFile() || !/\.tsx?$/.test(entry.name)) continue;
        const source = readFileSync(join(root, entry.name), 'utf8');
        if (source.startsWith("'use client'") && source.includes('@/lib/maps/data')) {
          offenders.push(entry.name);
        }
      }
    }
    expect(offenders).toEqual([]);
  });
});
