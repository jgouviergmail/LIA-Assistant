/**
 * What the board is narrowed to — the predicate, the count and the sentence.
 *
 * Three questions, one place. `hasFilters` used to live inside the page as a
 * private helper; the filter block now FOLDS on a phone, and a folded block is
 * an index entry: what it holds has to be readable before opening it, or the
 * reader opens it to find out — exactly the scanning the fold exists to spare
 * them (`components/ui/disclosure.tsx`).
 *
 * Two rules the shapes obey:
 *
 * - **The sort is not a narrowing.** It changes the ORDER, never the set;
 *   counting it would announce « no match » to somebody who merely sorted by
 *   due date, and would light the badge on an untouched board.
 * - **A control is counted once, whatever its cardinality.** The badge answers
 *   "how many controls are set", not "how many values were picked" — two
 *   priorities are one narrowing, and the sentence lists both.
 */

import type { BoardFilters } from '@/types/workboard';

/** Between two narrowings; the same mark the cards use between two facts. */
const JOIN = ' · ';

/** Resolver of an i18n key — the caller's own `t`, never a hook here. */
type Translate = (key: string) => string;

/**
 * Whether the reader narrowed the board.
 *
 * « Nothing yet » is not « no match »: the empty state says one or the other
 * on the strength of this predicate.
 *
 * @param filters - What the board is showing.
 * @returns True when at least one control is set.
 */
export function hasFilters(filters: BoardFilters): boolean {
  return activeFilterCount(filters) > 0;
}

/**
 * How many controls narrow the board right now.
 *
 * @param filters - What the board is showing.
 * @returns The exact count (ADR-185), zero on an untouched board.
 */
export function activeFilterCount(filters: BoardFilters): number {
  let count = 0;
  if (filters.q?.trim()) count += 1;
  if (filters.assignee && filters.assignee !== 'all') count += 1;
  if (filters.priority?.length) count += 1;
  if (filters.status?.length) count += 1;
  if (filters.overdue) count += 1;
  return count;
}

/**
 * The narrowings, in the words their own controls carry.
 *
 * Read in control order — search, holder, priority, column, overdue — so the
 * folded line and the open block name things in the same sequence.
 *
 * @param filters - What the board is showing.
 * @param t - The caller's translator.
 * @returns One line, or `''` when nothing narrows the board.
 */
export function describeFilters(filters: BoardFilters, t: Translate): string {
  const parts: string[] = [];
  const needle = filters.q?.trim();
  // The needle IS the information: « Search » would name the field and say
  // nothing about what the reader is looking at.
  if (needle) parts.push(`« ${needle} »`);
  if (filters.assignee && filters.assignee !== 'all') {
    parts.push(t(`workboard.filters.side_${filters.assignee}`));
  }
  if (filters.priority?.length) {
    parts.push(filters.priority.map(value => t(`workboard.priority.${value}`)).join(', '));
  }
  if (filters.status?.length) {
    parts.push(filters.status.map(value => t(`workboard.columns.${value}`)).join(', '));
  }
  if (filters.overdue) parts.push(t('workboard.filters.overdue'));
  return parts.join(JOIN);
}
