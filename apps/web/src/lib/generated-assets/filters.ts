/**
 * What a gallery is narrowed to, counted and said (ADR-279).
 *
 * The filter block folds on a phone, and a folded block is an index entry:
 * what it holds has to be readable before opening it, or the reader opens it to
 * find out — the scanning the fold exists to spare them. Same two answers as
 * the workboard's: how MANY narrowings are active (an exact count, ADR-185) and
 * WHICH ones, in the words their own controls carry.
 *
 * The SORT is not a narrowing. It changes the order, never the set, so counting
 * it would light the badge on an untouched gallery and make an empty result
 * read as « no match » to somebody who merely reordered.
 */

import type { GeneratedAssetFilters } from '@/types/generated-assets';

/** Between two narrowings — the mark the cards use between two facts. */
const JOIN = ' · ';

/** Resolver of an i18n key — the caller's own `t`, never a hook here. */
type Translate = (key: string, options?: Record<string, unknown>) => string;

/**
 * How many controls narrow this gallery right now.
 *
 * @param filters - What it is showing.
 * @returns The exact count, zero on an untouched gallery.
 */
export function activeAssetFilterCount(filters: GeneratedAssetFilters): number {
  let count = 0;
  if (filters.q?.trim()) count += 1;
  if (filters.createdAfter || filters.createdBefore) count += 1;
  if (filters.expiresBefore) count += 1;
  return count;
}

/**
 * Whether the reader narrowed the gallery.
 *
 * @param filters - What it is showing.
 * @returns True when at least one control is set — « nothing yet » is not
 *   « no match ».
 */
export function hasAssetFilters(filters: GeneratedAssetFilters): boolean {
  return activeAssetFilterCount(filters) > 0;
}

/**
 * The narrowings, in the words their own controls carry.
 *
 * @param filters - What the gallery is showing.
 * @param t - The caller's translator.
 * @returns One line, or `''` when nothing narrows it.
 */
export function describeAssetFilters(filters: GeneratedAssetFilters, t: Translate): string {
  const parts: string[] = [];
  const needle = filters.q?.trim();
  // The needle IS the information: naming the field would say nothing about
  // what the reader is looking at.
  if (needle) parts.push(`« ${needle} »`);
  if (filters.createdAfter || filters.createdBefore) {
    parts.push(t('settings.generated_assets.filters.created_active'));
  }
  if (filters.expiresBefore) {
    parts.push(t('settings.generated_assets.filters.expiring_active'));
  }
  return parts.join(JOIN);
}
