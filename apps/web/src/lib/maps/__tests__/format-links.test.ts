/**
 * Dates and numbers in the reader's language, and the addresses the maps share.
 */

import { describe, expect, it } from 'vitest';

import { civilDate, foldForSearch, mapsFormat } from '../format';
import {
  brickDecisionsHref,
  brickHref,
  decisionFileUrl,
  decisionHref,
  domainUrl,
  mapPageHref,
  releaseUrl,
  repoUrl,
} from '../links';

describe('mapsFormat', () => {
  it('reads a civil date in UTC, so no timezone moves a decision to the day before', () => {
    expect(civilDate('2026-01-01').toISOString()).toBe('2026-01-01T00:00:00.000Z');
    expect(civilDate('2026-02').toISOString()).toBe('2026-02-01T00:00:00.000Z');
  });

  it('formats dates, months and numbers in each language', () => {
    const fr = mapsFormat('fr');
    expect(fr.day('2026-09-24')).toBe('24 septembre 2026');
    expect(fr.month('2026-09')).toBe('septembre 2026');
    expect(fr.number(1069)).toMatch(/^1\s069$/u);
    const en = mapsFormat('en');
    expect(en.day('2026-09-24')).toBe('September 24, 2026');
    expect(en.number(1069)).toBe('1,069');
    expect(mapsFormat('de').number(1069)).toBe('1.069');
    expect(mapsFormat('zh').day('2026-09-24')).toBe('2026年9月24日');
    expect(en.dayShort('2026-09-24')).toContain('2026');
    expect(en.monthAxis('2026-09')).toContain('26');
  });

  it('folds accents and case for search', () => {
    expect(foldForSearch('Mémoire ÉLÈVE')).toBe('memoire eleve');
    expect(foldForSearch('记忆')).toBe('记忆');
  });
});

describe('links', () => {
  it('builds the localized path of each page, French without a prefix', () => {
    expect(mapPageHref('history', 'fr')).toBe('/maps/history');
    expect(mapPageHref('functional', 'en')).toBe('/en/maps/functional');
  });

  it('keeps a brick of the current map a bare hash, and crosses to the other map', () => {
    expect(brickHref('f.chat', 'functional', 'functional', 'fr')).toBe('#f.chat');
    expect(brickHref('t.redis', 'technical', 'functional', 'de')).toBe(
      '/de/maps/technical#t.redis'
    );
    expect(brickHref('f.chat', 'functional', 'history', 'fr')).toBe('/maps/functional#f.chat');
  });

  it('points at a decision on the history page, and at a brick filter of it', () => {
    expect(decisionHref(263, 'history', 'fr')).toBe('#adr-263');
    expect(decisionHref(263, 'technical', 'it')).toBe('/it/maps/history#adr-263');
    expect(brickDecisionsHref('f.chat', 'zh')).toBe('/zh/maps/history#f.chat');
  });

  it('points at the repository: a decision file, or the index when it has none', () => {
    const repo = 'https://github.com/x/y/blob/main/';
    expect(decisionFileUrl(repo, 1, 'ADR-001-A.md')).toBe(`${repo}docs/architecture/ADR-001-A.md`);
    expect(decisionFileUrl(repo, 8, null)).toBe(`${repo}docs/architecture/ADR_INDEX.md#adr-008`);
    expect(repoUrl(repo, 'apps/web')).toBe(`${repo}apps/web`);
    expect(domainUrl(repo, 'chat')).toBe(`${repo}apps/api/src/domains/chat`);
    expect(releaseUrl(repo, '1.47.2', '2026-09-24')).toBe(`${repo}CHANGELOG.md#1472---2026-09-24`);
  });
});
