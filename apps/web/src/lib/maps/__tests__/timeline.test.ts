/**
 * The decision history's chronology: chapters, months, releases, filters.
 */

import { describe, expect, it } from 'vitest';

import { buildHistory } from '../model';
import {
  INITIAL_FILTERS,
  NO_FILTERS,
  adrLabel,
  buildTimeline,
  chartScale,
  decisionOfHash,
  eraOf,
  filtersReducer,
  isFiltered,
  matchDecision,
  monthRange,
  monthlyCounts,
  type HistoryFilters,
} from '../timeline';
import { mapsDataFixture } from './fixtures';

const view = buildHistory(mapsDataFixture());
const themeName = (id: string) => view.themes.find(t => t.id === id)?.name ?? '';

describe('monthRange and monthlyCounts', () => {
  it('spans every month from the first decision to the last, across a new year', () => {
    expect(monthRange(view.decisions)).toEqual(['2025-10', '2025-11', '2025-12', '2026-01']);
    expect(monthRange([])).toEqual([]);
  });

  it('counts each month by theme, empty months included', () => {
    const counts = monthlyCounts(view.decisions, view.themes);
    expect(counts.map(c => c.total)).toEqual([1, 1, 0, 1]);
    expect(counts[1].byTheme).toEqual([{ theme: 'voice', count: 1 }]);
    expect(counts[2].byTheme).toEqual([]);
  });

  it('picks a round axis step giving at most five gridlines', () => {
    expect(chartScale(3)).toEqual({ step: 5, top: 5 });
    expect(chartScale(42)).toEqual({ step: 10, top: 50 });
    expect(chartScale(96)).toEqual({ step: 20, top: 100 });
    expect(chartScale(1000)).toEqual({ step: 100, top: 1000 });
  });
});

describe('matchDecision', () => {
  const only = (over: Partial<HistoryFilters>) => ({ ...NO_FILTERS, ...over });

  it('finds a decision by its number however it is typed', () => {
    const second = view.decisions[1];
    for (const query of ['2', 'adr-2', 'ADR-002', 'adr2']) {
      expect(matchDecision(second, only({ query }), themeName)).toBe(true);
    }
    expect(matchDecision(second, only({ query: '3' }), themeName)).toBe(false);
  });

  it('searches the words, the theme and the label, accents folded', () => {
    expect(matchDecision(view.decisions[1], only({ query: 'LIA PARLE' }), themeName)).toBe(true);
    expect(matchDecision(view.decisions[1], only({ query: 'voix' }), themeName)).toBe(true);
  });

  it('filters by theme and by the brick a decision shaped', () => {
    const [first, second] = view.decisions;
    expect(matchDecision(first, only({ themes: new Set(['voice']) }), themeName)).toBe(false);
    expect(matchDecision(second, only({ themes: new Set(['voice']) }), themeName)).toBe(true);
    expect(matchDecision(first, only({ brick: 'f.two' }), themeName)).toBe(false);
    expect(matchDecision(second, only({ brick: 'f.two' }), themeName)).toBe(true);
  });

  it('says when the list is narrowed', () => {
    expect(isFiltered(NO_FILTERS)).toBe(false);
    expect(isFiltered(only({ query: '  ' }))).toBe(false);
    expect(isFiltered(only({ brick: 't.one' }))).toBe(true);
  });
});

describe('buildTimeline', () => {
  it('groups by chapter then month, interleaving the releases of the span', () => {
    const timeline = buildTimeline(view, NO_FILTERS);
    expect(timeline.shown).toBe(3);
    expect(timeline.eras.map(g => [g.era.id, g.index, g.count])).toEqual([
      ['first', 1, 2],
      ['second', 2, 1],
    ]);
    const [october, november] = timeline.eras[0].months;
    expect(october.items.map(i => i.kind)).toEqual(['decision']);
    // The release of 2025-11-01 falls inside the span: it joins November.
    expect(
      november.items.map(i => (i.kind === 'release' ? i.release.version : i.decision.adr))
    ).toEqual(['1.0.0', 2]);
    expect(timeline.eras[0].topThemes).toEqual([
      { theme: 'platform', count: 1 },
      { theme: 'voice', count: 1 },
    ]);
  });

  it('leaves the releases out when a filter narrows the list, or on request', () => {
    const filtered = buildTimeline(view, { ...NO_FILTERS, themes: new Set(['platform']) });
    expect(filtered.shown).toBe(2);
    const kinds = filtered.eras.flatMap(e => e.months.flatMap(m => m.items.map(i => i.kind)));
    expect(kinds).not.toContain('release');
    const hidden = buildTimeline(view, { ...NO_FILTERS, releases: false });
    expect(hidden.eras.flatMap(e => e.months.flatMap(m => m.items)).length).toBe(3);
  });

  it('reads newest first on request', () => {
    const timeline = buildTimeline(view, { ...NO_FILTERS, newestFirst: true });
    expect(timeline.eras.map(g => g.era.id)).toEqual(['second', 'first']);
    const order = timeline.eras.flatMap(e =>
      e.months.flatMap(m =>
        m.items.map(i => (i.kind === 'release' ? i.release.version : i.decision.adr))
      )
    );
    expect(order).toEqual([3, 2, '1.0.0', 1]);
  });

  it('is empty when nothing matches', () => {
    expect(buildTimeline(view, { ...NO_FILTERS, query: 'introuvable' })).toEqual({
      eras: [],
      shown: 0,
    });
  });

  it('places a date in its chapter, the last one open-ended', () => {
    expect(eraOf(view.eras, '2025-12-31')?.id).toBe('first');
    expect(eraOf(view.eras, '2031-01-01')?.id).toBe('second');
    expect(eraOf(view.eras, '2024-01-01')).toBeUndefined();
  });
});

describe('filtersReducer', () => {
  it('toggles themes, sets the search and the two switches, resets the narrowing', () => {
    let state = filtersReducer(INITIAL_FILTERS, { type: 'toggleTheme', theme: 'voice' });
    expect([...state.themes]).toEqual(['voice']);
    state = filtersReducer(state, { type: 'toggleTheme', theme: 'voice' });
    expect(state.themes.size).toBe(0);
    state = filtersReducer(state, { type: 'query', value: 'cache' });
    state = filtersReducer(state, { type: 'releases', value: false });
    state = filtersReducer(state, { type: 'newestFirst', value: true });
    state = filtersReducer(state, { type: 'toggleTheme', theme: 'platform' });
    const reset = filtersReducer(state, { type: 'reset' });
    expect(reset).toEqual({ themes: new Set(), query: '', releases: false, newestFirst: true });
  });

  it('gives way to a decision a link points at, only when the filters hide it', () => {
    const narrowed = filtersReducer(INITIAL_FILTERS, { type: 'toggleTheme', theme: 'voice' });
    const second = view.decisions[1];
    expect(filtersReducer(narrowed, { type: 'reveal', decision: second, themeName })).toBe(
      narrowed
    );
    const revealed = filtersReducer(narrowed, {
      type: 'reveal',
      decision: view.decisions[0],
      themeName,
    });
    expect(revealed.themes.size).toBe(0);
  });

  it('reads the decision a hash names', () => {
    expect(decisionOfHash('adr-263')).toBe(263);
    expect(decisionOfHash('f.chat')).toBeNull();
    expect(adrLabel(8)).toBe('ADR-008');
  });
});
