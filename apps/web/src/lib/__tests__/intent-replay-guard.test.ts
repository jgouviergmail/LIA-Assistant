/**
 * intent-replay-guard — the consumed-intent ledger (ADR-210).
 *
 * A chat `?intent=` URL is a replayable carrier: since ADR-192 made deep links
 * real navigations, the intent URL is a first-class VISIT in the browser's
 * history — omnibox autocomplete, most-visited tiles, session restore and the
 * App Router's own entry bookkeeping can all resurrect it, and `replaceState`
 * only rewrites the session entry, never the visit database. Production
 * 2026-08-05: the same "Prépare une réponse au mail…" executed twice, 27 s
 * apart, each followed by the user cancelling.
 *
 * The ledger makes consumption idempotent AT THE CONSUMER, independent of
 * which mechanism resurrects the URL. Storage failures fail OPEN: a private
 * window degrades to the pre-ledger behavior, never to a lost request.
 */

import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';

import { isIntentConsumed, markIntentConsumed, newIntentId } from '../intent-replay-guard';

beforeEach(() => {
  window.localStorage.clear();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('newIntentId', () => {
  it('is unique per call — one click, one id, two clicks, two executions', () => {
    expect(newIntentId()).not.toBe(newIntentId());
  });
});

describe('consumed-intent ledger', () => {
  it('does not know an id it never saw', () => {
    expect(isIntentConsumed('never-seen')).toBe(false);
  });

  it('knows an id once marked', () => {
    markIntentConsumed('abc');
    expect(isIntentConsumed('abc')).toBe(true);
  });

  it('marking twice stays consumed (StrictMode double-effect)', () => {
    markIntentConsumed('abc');
    markIntentConsumed('abc');
    expect(isIntentConsumed('abc')).toBe(true);
  });

  it('survives across instances — the ledger is shared storage, not memory', () => {
    // Two tabs share localStorage: consuming in one blocks the replay in the
    // other. The unit-level proxy: the read hits storage, not a module cache.
    markIntentConsumed('cross-tab');
    window.localStorage.setItem('lia.chat.consumed-intent-ids', JSON.stringify(['external-write']));
    expect(isIntentConsumed('external-write')).toBe(true);
    expect(isIntentConsumed('cross-tab')).toBe(false); // overwritten by the other tab
  });

  it('evicts the OLDEST id beyond the cap, keeps the newest', () => {
    for (let i = 0; i < 51; i++) markIntentConsumed(`id-${i}`);
    expect(isIntentConsumed('id-0')).toBe(false); // evicted
    expect(isIntentConsumed('id-1')).toBe(true);
    expect(isIntentConsumed('id-50')).toBe(true);
  });

  it('fails OPEN when storage is unavailable', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('denied');
    });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('denied');
    });
    expect(() => markIntentConsumed('abc')).not.toThrow();
    // Fail open = the intent still executes (pre-ledger behavior), because a
    // silently DROPPED request is the worse failure (the hook's own doctrine).
    expect(isIntentConsumed('abc')).toBe(false);
  });

  it('recovers from a corrupted ledger payload', () => {
    window.localStorage.setItem('lia.chat.consumed-intent-ids', '{not json[');
    expect(isIntentConsumed('abc')).toBe(false);
    markIntentConsumed('abc');
    expect(isIntentConsumed('abc')).toBe(true);
  });
});
