/**
 * The shared changelog list and its key builders.
 *
 * `changelog-wiring.test.ts` already pins the list against the locale content
 * (no entry invisible, no dangling key, newest first). What is pinned HERE is
 * the small surface the two rendering surfaces call — the part where an
 * off-by-one silently drops the last bullet of every release, or a malformed
 * count fills the page with empty ones.
 */

import { describe, expect, it } from 'vitest';

import {
  CHANGELOG_VERSION_KEYS,
  LANDING_CHANGELOG_COUNT,
  changelogDateKey,
  changelogItemKeys,
  changelogTitleKey,
  latestChangelogVersions,
} from '../changelog';

describe('latestChangelogVersions', () => {
  it('takes the newest releases, in the list order', () => {
    expect(latestChangelogVersions(3)).toEqual(CHANGELOG_VERSION_KEYS.slice(0, 3));
  });

  it('never invents an entry when asked for more than exist', () => {
    expect(latestChangelogVersions(CHANGELOG_VERSION_KEYS.length + 10)).toHaveLength(
      CHANGELOG_VERSION_KEYS.length
    );
  });

  it('teases a handful, not the whole history', () => {
    expect(LANDING_CHANGELOG_COUNT).toBeGreaterThan(0);
    expect(LANDING_CHANGELOG_COUNT).toBeLessThan(CHANGELOG_VERSION_KEYS.length);
  });
});

describe('key builders', () => {
  it('numbers the items from one, without dropping the last', () => {
    expect(changelogItemKeys('v1_30_9', 3)).toEqual([
      'faq.changelog.versions.v1_30_9.items.i1',
      'faq.changelog.versions.v1_30_9.items.i2',
      'faq.changelog.versions.v1_30_9.items.i3',
    ]);
  });

  it('renders nothing rather than a blank bullet for an unusable count', () => {
    expect(changelogItemKeys('v1_30_9', 0)).toEqual([]);
  });

  it('builds the title and date keys the locales actually carry', () => {
    expect(changelogTitleKey('v1_30_9')).toBe('faq.changelog.versions.v1_30_9.title');
    expect(changelogDateKey('v1_30_9')).toBe('faq.changelog.versions.v1_30_9.date');
  });
});
