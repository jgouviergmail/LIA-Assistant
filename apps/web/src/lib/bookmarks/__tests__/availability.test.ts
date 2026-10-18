import { describe, expect, it } from 'vitest';

import { bookmarkKeepingAvailable, bookmarksReadable } from '../availability';

describe('bookmarkKeepingAvailable', () => {
  it('follows the operator switch, not the deployment ceiling', () => {
    // The bubbles used to read the ceiling alone: the bookmark stayed on every
    // answer with the capability switched off, and each click was refused.
    expect(
      bookmarkKeepingAvailable({
        features: { bookmarks_enabled: true },
        capabilities: { bookmarks: { enabled: false, family: 'knowledge' } },
      })
    ).toBe(false);
  });

  it('offers keeping when the effective state is on', () => {
    expect(
      bookmarkKeepingAvailable({
        features: { bookmarks_enabled: true },
        capabilities: { bookmarks: { enabled: true, family: 'knowledge' } },
      })
    ).toBe(true);
  });

  it('falls back to the ceiling when the API publishes no capability map', () => {
    expect(bookmarkKeepingAvailable({ features: { bookmarks_enabled: true } })).toBe(true);
    expect(bookmarkKeepingAvailable({ features: { bookmarks_enabled: false } })).toBe(false);
  });

  it('offers nothing while the configuration loads', () => {
    expect(bookmarkKeepingAvailable(null)).toBe(false);
  });
});

describe('bookmarksReadable', () => {
  it('follows the deployment ceiling alone, whatever the operator switch', () => {
    // What was kept stays readable and deletable with keeping switched off.
    expect(
      bookmarksReadable({
        features: { bookmarks_enabled: true },
        capabilities: { bookmarks: { enabled: false, family: 'knowledge' } },
      })
    ).toBe(true);
    expect(bookmarksReadable({ features: { bookmarks_enabled: false } })).toBe(false);
  });

  it('reads nothing while the configuration loads', () => {
    expect(bookmarksReadable(null)).toBe(false);
  });
});
