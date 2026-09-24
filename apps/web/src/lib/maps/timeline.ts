/**
 * The decision history's chronology — pure, so every rule is unit-tested.
 *
 * The page shows the decisions grouped by chapter (era) then by month,
 * interleaved with the milestone releases, filtered by theme, by a searched
 * word or number, or by the brick they shaped, oldest or newest first. The
 * monthly chart above it counts the same decisions by theme.
 */

import { foldForSearch } from './format';
import type { DecisionView, EraView, HistoryView, ReleaseView, ThemeView } from './types';

/** Every month from the first decision to the last, as `YYYY-MM`. */
export function monthRange(decisions: readonly DecisionView[]): string[] {
  if (!decisions.length) return [];
  const dates = decisions.map(d => d.date).sort();
  let [year, month] = dates[0].split('-').map(Number);
  const [lastYear, lastMonth] = dates[dates.length - 1].split('-').map(Number);
  const out: string[] = [];
  while (year < lastYear || (year === lastYear && month <= lastMonth)) {
    out.push(`${year}-${String(month).padStart(2, '0')}`);
    month += 1;
    if (month > 12) {
      month = 1;
      year += 1;
    }
  }
  return out;
}

export interface MonthCount {
  month: string;
  total: number;
  /** Decisions per theme, in theme order (only the themes present). */
  byTheme: Array<{ theme: string; count: number }>;
}

/** The chart's bars: one per month, stacked by theme. */
export function monthlyCounts(
  decisions: readonly DecisionView[],
  themes: readonly ThemeView[]
): MonthCount[] {
  return monthRange(decisions).map(month => {
    const inMonth = decisions.filter(d => d.date.startsWith(month));
    const byTheme = themes
      .map(t => ({ theme: t.id, count: inMonth.filter(d => d.theme === t.id).length }))
      .filter(x => x.count > 0);
    return { month, total: inMonth.length, byTheme };
  });
}

/** A readable axis: a round step giving at most five gridlines, and the top it reaches. */
export function chartScale(maxTotal: number): { step: number; top: number } {
  const step = [5, 10, 20, 25, 50, 100].find(s => maxTotal / s <= 5) ?? 100;
  return { step, top: Math.max(step, Math.ceil(maxTotal / step) * step) };
}

export interface HistoryFilters {
  themes: ReadonlySet<string>;
  query: string;
  /** Show only the decisions that shaped this brick. */
  brick: string | null;
  /** Interleave the milestone releases (only when nothing filters the list). */
  releases: boolean;
  newestFirst: boolean;
}

export const NO_FILTERS: HistoryFilters = {
  themes: new Set(),
  query: '',
  brick: null,
  releases: true,
  newestFirst: false,
};

/** "ADR-042" as the page and the search spell it. */
export const adrLabel = (adr: number): string => `ADR-${String(adr).padStart(3, '0')}`;

/** Whether a decision passes the filters. A search on "42", "adr-42" or "ADR-042" finds ADR-042. */
export function matchDecision(
  decision: DecisionView,
  filters: HistoryFilters,
  themeName: (id: string) => string
): boolean {
  if (filters.themes.size && !filters.themes.has(decision.theme)) return false;
  if (filters.brick && !decision.bricks.includes(filters.brick)) return false;
  const needle = foldForSearch(filters.query.trim());
  if (!needle) return true;
  const number = needle.replace(/^adr-?0*/, '');
  const haystack = foldForSearch(
    `${decision.title} ${decision.summary} ${themeName(decision.theme)} ${adrLabel(decision.adr)}`
  );
  return haystack.includes(needle) || String(decision.adr) === number;
}

/** Whether any filter narrows the list (releases are then left out). */
export function isFiltered(filters: HistoryFilters): boolean {
  return filters.themes.size > 0 || filters.query.trim() !== '' || filters.brick !== null;
}

/** The filters the reader sets by hand — the brick filter comes from the page's hash. */
export type FilterState = Omit<HistoryFilters, 'brick'>;

export const INITIAL_FILTERS: FilterState = {
  themes: new Set(),
  query: '',
  releases: true,
  newestFirst: false,
};

export type FilterAction =
  | { type: 'toggleTheme'; theme: string }
  | { type: 'query'; value: string }
  | { type: 'releases'; value: boolean }
  | { type: 'newestFirst'; value: boolean }
  | { type: 'reset' }
  /** A link points at this decision: if the filters hide it, they give way. */
  | { type: 'reveal'; decision: DecisionView; themeName: (id: string) => string };

export function filtersReducer(state: FilterState, action: FilterAction): FilterState {
  switch (action.type) {
    case 'toggleTheme': {
      const themes = new Set(state.themes);
      if (themes.has(action.theme)) themes.delete(action.theme);
      else themes.add(action.theme);
      return { ...state, themes };
    }
    case 'query':
      return { ...state, query: action.value };
    case 'releases':
      return { ...state, releases: action.value };
    case 'newestFirst':
      return { ...state, newestFirst: action.value };
    case 'reset':
      return { ...state, themes: new Set(), query: '' };
    case 'reveal':
      return matchDecision(action.decision, { ...state, brick: null }, action.themeName)
        ? state
        : { ...state, themes: new Set(), query: '' };
  }
}

/** The decision a hash names (`adr-263`), or null. */
export function decisionOfHash(hash: string): number | null {
  const match = /^adr-(\d+)$/.exec(hash);
  return match ? Number(match[1]) : null;
}

export type TimelineItem =
  | { kind: 'decision'; date: string; decision: DecisionView }
  | { kind: 'release'; date: string; release: ReleaseView };

export interface MonthGroup {
  month: string;
  /** Decisions of the month that pass the filters. */
  count: number;
  items: TimelineItem[];
}

export interface EraGroup {
  era: EraView;
  /** 1-based position of the chapter in the whole history. */
  index: number;
  /** Decisions of the chapter that pass the filters. */
  count: number;
  /** Its four most frequent themes among them. */
  topThemes: Array<{ theme: string; count: number }>;
  months: MonthGroup[];
}

export interface Timeline {
  eras: EraGroup[];
  /** Decisions shown. */
  shown: number;
}

/** The chapter a date falls in. */
export function eraOf(eras: readonly EraView[], date: string): EraView | undefined {
  return eras.find(era => date >= era.from && (era.to === null || date <= era.to));
}

function compareItems(a: TimelineItem, b: TimelineItem, direction: 1 | -1): number {
  if (a.date !== b.date) return (a.date < b.date ? -1 : 1) * direction;
  if (a.kind !== b.kind) return (a.kind === 'release' ? 1 : -1) * direction;
  if (a.kind === 'decision' && b.kind === 'decision') {
    return (a.decision.adr - b.decision.adr) * direction;
  }
  return 0;
}

function topThemes(decisions: readonly DecisionView[]): Array<{ theme: string; count: number }> {
  const counts = new Map<string, number>();
  for (const d of decisions) counts.set(d.theme, (counts.get(d.theme) ?? 0) + 1);
  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .slice(0, 4)
    .map(([theme, count]) => ({ theme, count }));
}

/**
 * The chronology for the current filters: chapters, then months, then the
 * decisions and — when nothing filters the list — the releases of the span.
 */
export function buildTimeline(view: HistoryView, filters: HistoryFilters): Timeline {
  const themeName = new Map(view.themes.map(t => [t.id, t.name]));
  const list = view.decisions.filter(d => matchDecision(d, filters, id => themeName.get(id) ?? ''));
  if (!list.length) return { eras: [], shown: 0 };
  const dates = list.map(d => d.date).sort();
  const [low, high] = [dates[0], dates[dates.length - 1]];
  const releases =
    filters.releases && !isFiltered(filters)
      ? view.releases.filter(r => r.date >= low && r.date <= high)
      : [];
  const direction = filters.newestFirst ? -1 : 1;
  const items: TimelineItem[] = [
    ...list.map(decision => ({ kind: 'decision' as const, date: decision.date, decision })),
    ...releases.map(release => ({ kind: 'release' as const, date: release.date, release })),
  ].sort((a, b) => compareItems(a, b, direction));

  const eras: EraGroup[] = [];
  for (const item of items) {
    const era = eraOf(view.eras, item.date);
    if (!era) continue;
    let group = eras[eras.length - 1];
    if (!group || group.era.id !== era.id) {
      const inEra = list.filter(d => eraOf(view.eras, d.date)?.id === era.id);
      group = {
        era,
        index: view.eras.indexOf(era) + 1,
        count: inEra.length,
        topThemes: topThemes(inEra),
        months: [],
      };
      eras.push(group);
    }
    const month = item.date.slice(0, 7);
    let block = group.months[group.months.length - 1];
    if (!block || block.month !== month) {
      block = { month, count: list.filter(d => d.date.startsWith(month)).length, items: [] };
      group.months.push(block);
    }
    block.items.push(item);
  }
  return { eras, shown: list.length };
}
