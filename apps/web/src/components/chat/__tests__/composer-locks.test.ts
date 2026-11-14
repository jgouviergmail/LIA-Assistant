/**
 * What closes the composer (ADR-299, ADR-384).
 *
 * While LIA answers, the text stays open — words typed meanwhile wait for their
 * turn — but the voice and a card composition, which only a live request can
 * carry, stay closed.
 */
import { describe, expect, it } from 'vitest';

import { composerLocks } from '../ChatWorkspace';

const FREE = {
  apiAvailable: true,
  isTyping: false,
  isUsageBlocked: false,
  liveOpen: false,
  waitingForHistory: false,
};

describe('composerLocks', () => {
  it('opens everything on a free, usable chat', () => {
    expect(composerLocks(FREE)).toMatchObject({ input: false, voice: false, composition: false });
  });

  it('keeps the text open while LIA answers, and closes the voice and a composition', () => {
    expect(composerLocks({ ...FREE, isTyping: true })).toMatchObject({
      input: false,
      voice: true,
      composition: true,
    });
  });

  it.each([
    ['the quota wall', { isUsageBlocked: true }],
    ['a live session', { liveOpen: true }],
    ['a history still loading', { waitingForHistory: true }],
  ])('closes the text behind %s', (_label, flags) => {
    expect(composerLocks({ ...FREE, ...flags })).toMatchObject({ input: true, composition: true });
  });

  it('says why a live session closed it', () => {
    expect(composerLocks({ ...FREE, liveOpen: true }).reasonKey).toBe('live.composer_locked');
  });
});
