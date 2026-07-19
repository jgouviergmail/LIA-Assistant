/**
 * The FAQ changelog is wired by TWO independent things: the locale content
 * (`faq.changelog.versions.vX_Y_Z`) and the hardcoded `changelogVersionKeys`
 * array that decides what the accordion renders. Either half can drift silently:
 *
 *  - a key missing from the array = an entry that exists in all 6 locales,
 *    passes i18n parity, and never displays (`v1_21_8` and `v1_21_9` shipped
 *    invisible until repaired at v1.25.10 — the bug this file exists to prevent);
 *  - a key in the array with no locale entry = an accordion row whose title and
 *    body render as raw i18n keys.
 *
 * i18n parity across the 6 locales is enforced elsewhere (the pre-commit hook and
 * the `code-hygiene` CI job run `scripts/i18n/validate_translations.py`), so
 * checking the reference locale here is enough to catch the wiring drift.
 */

import { describe, it, expect } from 'vitest';

import en from '../../../../locales/en/translation.json';
import { changelogVersionKeys } from '../FAQContent';

const versions = en.faq.changelog.versions as Record<
  string,
  { title: string; date: string; count: string; items: Record<string, string> }
>;

describe('FAQ changelog wiring', () => {
  it('renders every version that has locale content', () => {
    const orphaned = Object.keys(versions).filter(
      key => !(changelogVersionKeys as readonly string[]).includes(key)
    );

    expect(
      orphaned,
      `these versions exist in the locales but are absent from changelogVersionKeys, ` +
        `so they never render: ${orphaned.join(', ')}`
    ).toEqual([]);
  });

  it('has locale content for every version it renders', () => {
    const dangling = changelogVersionKeys.filter(key => !(key in versions));

    expect(
      dangling,
      `these keys are rendered but have no locale entry, so the accordion would ` +
        `show raw i18n keys: ${dangling.join(', ')}`
    ).toEqual([]);
  });

  it('declares an item count matching the items actually written', () => {
    // The accordion loops i1..iN bounded by `count`: a mismatch silently hides
    // the extra items (count too low) or renders raw keys (count too high).
    const mismatched = Object.entries(versions)
      .filter(([, v]) => Number(v.count) !== Object.keys(v.items).length)
      .map(([key, v]) => `${key} (count=${v.count}, items=${Object.keys(v.items).length})`);

    expect(mismatched).toEqual([]);
  });

  it('lists the newest version first', () => {
    // The accordion renders in array order; a version appended at the end would
    // bury the latest release under the history.
    const toNumbers = (key: string) => key.replace(/^v/, '').split('_').map(Number);
    const [first, second] = [changelogVersionKeys[0], changelogVersionKeys[1]].map(toNumbers);

    expect(first.length).toBe(3);
    // Compare as a version tuple, not lexicographically (v1_25_9 > v1_25_10 as strings).
    expect(first.some((part, i) => part > second[i])).toBe(true);
  });
});
