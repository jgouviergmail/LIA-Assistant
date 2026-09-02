/**
 * The release history, as ONE list.
 *
 * The FAQ has rendered a changelog for a long time; the landing page now shows
 * the most recent entries too, so a visitor sees the product moving before
 * they sign up. Two lists would drift the moment a release was added to one of
 * them — which has happened here before, in the other direction: entries
 * existed in all six locales and shipped invisible for two releases because
 * this list did not name them (`__tests__/changelog-wiring.test.ts` fails on
 * either kind of drift now).
 *
 * The list is the ONLY thing that makes an entry visible: a
 * `faq.changelog.versions.vX_Y_Z` block can exist everywhere, pass i18n
 * parity, and still never render if its key is missing here. Newest first.
 */

/** Versions rendered by any changelog surface, newest first. */
export const CHANGELOG_VERSION_KEYS = [
  'v1_38_6',
  'v1_38_5',
  'v1_38_4',
  'v1_38_3',
  'v1_38_2',
  'v1_38_1',
  'v1_38_0',
  'v1_37_0',
  'v1_36_0',
  'v1_35_0',
  'v1_34_1',
  'v1_34_0',
  'v1_33_2',
  'v1_33_1',
  'v1_33_0',
  'v1_32_0',
  'v1_31_3',
  'v1_31_2',
  'v1_31_1',
  'v1_31_0',
  'v1_30_16',
  'v1_30_15',
  'v1_30_14',
  'v1_30_13',
  'v1_30_12',
  'v1_30_11',
  'v1_30_10',
  'v1_30_9',
  'v1_30_8',
  'v1_30_7',
  'v1_30_6',
  'v1_30_5',
  'v1_30_4',
  'v1_30_3',
  'v1_30_2',
  'v1_30_1',
  'v1_30_0',
  'v1_29_0',
  'v1_28_0',
  'v1_27_14',
  'v1_27_13',
  'v1_27_12',
  'v1_27_11',
  'v1_27_10',
  'v1_27_9',
  'v1_27_8',
  'v1_27_7',
  'v1_27_6',
  'v1_27_5',
  'v1_27_4',
  'v1_27_3',
  'v1_27_2',
  'v1_27_1',
  'v1_27_0',
  'v1_26_4',
  'v1_26_3',
  'v1_26_2',
  'v1_26_1',
  'v1_26_0',
  'v1_25_33',
  'v1_25_32',
  'v1_25_31',
  'v1_25_30',
  'v1_25_29',
  'v1_25_28',
  'v1_25_27',
  'v1_25_26',
  'v1_25_25',
  'v1_25_24',
  'v1_25_23',
  'v1_25_22',
  'v1_25_21',
  'v1_25_20',
  'v1_25_19',
  'v1_25_18',
  'v1_25_17',
  'v1_25_16',
  'v1_25_15',
  'v1_25_14',
  'v1_25_13',
  'v1_25_12',
  'v1_25_11',
  'v1_25_10',
  'v1_25_9',
  'v1_25_8',
  'v1_25_7',
  'v1_25_6',
  'v1_25_5',
  'v1_25_4',
  'v1_25_3',
  'v1_25_2',
  'v1_25_1',
  'v1_25_0',
  'v1_24_0',
  'v1_23_13',
  'v1_23_12',
  'v1_23_11',
  'v1_23_10',
  'v1_23_9',
  'v1_23_8',
  'v1_23_7',
  'v1_23_6',
  'v1_23_5',
  'v1_23_4',
  'v1_23_3',
  'v1_23_2',
  'v1_23_1',
  'v1_23_0',
  'v1_22_0',
  'v1_21_26',
  'v1_21_25',
  'v1_21_24',
  'v1_21_23',
  'v1_21_22',
  'v1_21_21',
  'v1_21_20',
  'v1_21_19',
  'v1_21_18',
  'v1_21_17',
  'v1_21_16',
  'v1_21_15',
  'v1_21_14',
  'v1_21_13',
  'v1_21_12',
  'v1_21_11',
  'v1_21_10',
  'v1_21_9',
  'v1_21_8',
  'v1_21_7',
  'v1_21_6',
  'v1_21_5',
  'v1_21_4',
  'v1_21_3',
  'v1_21_2',
  'v1_21_1',
  'v1_21_0',
  // v1_20_17..22 shipped complete in the 6 locales but were never listed
  // here, so six releases of history stayed invisible. Found by
  // changelog-wiring.test.ts.
  'v1_20_22',
  'v1_20_21',
  'v1_20_20',
  'v1_20_19',
  'v1_20_18',
  'v1_20_17',
  'v1_20_16',
  'v1_20_15',
  'v1_20_14',
  'v1_20_13',
  'v1_20_12',
  'v1_20_11',
  'v1_20_10',
  'v1_20_9',
  'v1_20_8',
  'v1_20_7',
  'v1_20_6',
  'v1_20_5',
  'v1_20_4',
  'v1_20_3',
  'v1_20_2',
  'v1_20_1',
  'v1_20_0',
  'v1_18_1',
  'v1_18_0',
  'v1_17_2',
  'v1_17_1',
  'v1_17_0',
  'v1_16_10',
  'v1_16_9',
  'v1_16_8',
  'v1_16_7',
  'v1_16_6',
  'v1_16_5',
  'v1_16_4',
  'v1_16_3',
  'v1_16_2',
  'v1_16_1',
  'v1_16_0',
  'v1_15_3',
  'v1_15_2',
  'v1_15_1',
  'v1_15',
  'v1_14',
  'v1_13',
  'v1_12',
  'v1_11',
  'v1_10',
  'v1_9',
  'v1_8',
  'v1_7',
  'v1_6',
  'v1_5',
  'v1_4',
  'v1_3',
  'v1_1',
] as const;

export type ChangelogVersionKey = (typeof CHANGELOG_VERSION_KEYS)[number];

/**
 * How many releases the landing page teases.
 *
 * Three: enough to show a rhythm, few enough that the section stays a taste
 * of the product rather than a second FAQ. The full history stays one click
 * away, where it has always been.
 */
export const LANDING_CHANGELOG_COUNT = 3;

/**
 * The most recent releases.
 *
 * @param count - How many to take, newest first.
 * @returns That many version keys (fewer only if the history is shorter).
 */
export function latestChangelogVersions(count: number): ChangelogVersionKey[] {
  return CHANGELOG_VERSION_KEYS.slice(0, count);
}

/** i18n key of one release's title. */
export function changelogTitleKey(version: string): string {
  return `faq.changelog.versions.${version}.title`;
}

/** i18n key of one release's date line. */
export function changelogDateKey(version: string): string {
  return `faq.changelog.versions.${version}.date`;
}

/**
 * i18n keys of one release's items, in order.
 *
 * Items are numbered `i1…iN` and the count lives beside them, so a release
 * that gained an item never renders a blank bullet or drops the last one.
 *
 * @param version - A version key.
 * @param count - The release's declared item count.
 * @returns One key per item.
 */
export function changelogItemKeys(version: string, count: number): string[] {
  return Array.from(
    { length: count },
    (_, index) => `faq.changelog.versions.${version}.items.i${index + 1}`
  );
}

/**
 * One minor series of releases — `v1.30` and every patch it shipped.
 *
 * 166 releases in one flat column is a wall, not a history: the series is the
 * unit a reader actually navigates by ("what changed in 1.27?"), so the public
 * page renders one landmark per series and an anchor rail over them.
 */
export interface ChangelogSeries {
  /** Display label, e.g. `v1.30`. */
  label: string;
  /** DOM id and anchor fragment, e.g. `release-1-30`. */
  id: string;
  /** Its versions, in the shared list's own order (newest first). */
  versions: string[];
}

/**
 * Group release keys by minor series, preserving the list's order.
 *
 * The shared list is the ONLY authority on order; this function never sorts,
 * it only folds runs of the same series together. The oldest releases are
 * keyed on two segments (`v1_15`) and their patches on three (`v1_15_1`) —
 * both belong to `v1.15`, so the series is read from the first two segments
 * whatever the key's length.
 *
 * @param versions - Release keys, newest first.
 * @returns One entry per series, in first-encounter order.
 */
export function groupChangelogBySeries(versions: readonly string[]): ChangelogSeries[] {
  const groups: ChangelogSeries[] = [];

  for (const version of versions) {
    const label = `v${version.replace(/^v/, '').split('_').slice(0, 2).join('.')}`;
    const current = groups[groups.length - 1];

    if (current?.label === label) {
      current.versions.push(version);
    } else {
      groups.push({
        label,
        id: `release-${label.slice(1).replace(/\./g, '-')}`,
        versions: [version],
      });
    }
  }

  return groups;
}

/**
 * How many bullets a release declares.
 *
 * The count lives in its own i18n string beside the items, so a malformed or
 * missing one must render NO bullet rather than a list of empty ones. Shared
 * by every surface: nothing is honest, an empty bullet is not.
 *
 * @param raw - The release's declared count, as the locale carries it.
 * @returns A usable item count, or 0.
 */
export function changelogItemCount(raw: string): number {
  const parsed = Number.parseInt(raw, 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 0;
}

/** i18n key of one release's declared item count. */
export function changelogCountKey(version: string): string {
  return `faq.changelog.versions.${version}.count`;
}
