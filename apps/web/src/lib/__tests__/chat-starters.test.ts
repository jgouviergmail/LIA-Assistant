/**
 * The rail the empty chat offers.
 *
 * Generic examples proved nothing; grounded ones prove LIA already knows the
 * day. What must hold is the arithmetic between the two: always three entries,
 * grounded first, and the generic fallback intact when the server has no
 * evidence (a cold cache, or an account with no connector at all).
 */

import { describe, it, expect } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';

import {
  CHAT_STARTER_IDS,
  KNOWN_SUGGESTION_IDS,
  composeStarterRail,
  starterTextKey,
} from '../chat-starters';

/** Echoes the key and its params, so the composition is observable. */
const t = (key: string, options?: Record<string, unknown>) =>
  options ? `${key}(${Object.values(options).join(',')})` : key;

describe('composeStarterRail', () => {
  it('falls back to the generic starters when nothing is grounded', () => {
    const rail = composeStarterRail([], t);

    expect(rail.map(e => e.text)).toEqual(CHAT_STARTER_IDS.map(id => starterTextKey(id)));
    expect(rail.every(e => !e.grounded)).toBe(true);
  });

  it('puts grounded suggestions first and fills up with generics', () => {
    const rail = composeStarterRail([{ id: 'next_event', params: { subject: 'Revue produit' } }], t);

    expect(rail).toHaveLength(CHAT_STARTER_IDS.length);
    expect(rail[0]).toMatchObject({ grounded: true });
    expect(rail[0].text).toBe('chat.suggestions.next_event(Revue produit)');
    expect(rail.slice(1).every(e => !e.grounded)).toBe(true);
  });

  it('never grows the rail beyond three, whatever the server sends', () => {
    const rail = composeStarterRail(
      [{ id: 'a' }, { id: 'b' }, { id: 'c' }, { id: 'd' }, { id: 'e' }],
      t
    );

    expect(rail).toHaveLength(CHAT_STARTER_IDS.length);
  });

  it('drops the generics entirely once three are grounded', () => {
    // The REAL three the backend produces: placeholder ids would now be
    // filtered as unwordable, and the test would pass by rejecting them.
    const rail = composeStarterRail(
      [{ id: 'next_event' }, { id: 'important_mails' }, { id: 'close_loop' }],
      t
    );

    expect(rail.every(e => e.grounded)).toBe(true);
  });

  it('gives every entry a distinct, stable key', () => {
    const rail = composeStarterRail([{ id: 'next_event' }], t);

    expect(new Set(rail.map(e => e.key)).size).toBe(rail.length);
    // Namespaced so a grounded id can never collide with a starter id.
    expect(rail[0].key.startsWith('grounded:')).toBe(true);
    expect(rail[1].key.startsWith('starter:')).toBe(true);
  });

  it('passes the parameters through so the wording names the real thing', () => {
    const rail = composeStarterRail([{ id: 'close_loop', params: { subject: 'devis de Marie' } }], t);

    expect(rail[0].text).toContain('devis de Marie');
  });
});

describe('a grounded suggestion the frontend has no wording for', () => {
  // The backend contract is `id: string`, so a new suggestion kind can ship
  // server-first. `t()` answers an unknown key with the key itself — and this
  // rail does not merely DISPLAY its text, it drops it into the composer. The
  // reader would send "chat.suggestions.new_thing" to the assistant.
  const echo = (key: string) => key;

  it('is dropped rather than shown as its own i18n key', () => {
    const rail = composeStarterRail([{ id: 'not_a_known_kind' }], echo);

    expect(rail.every(entry => !entry.text.startsWith('chat.suggestions.'))).toBe(true);
  });

  it('gives its place back to a generic starter', () => {
    // Refusing it must not leave a hole: the rail keeps its three entries.
    const rail = composeStarterRail([{ id: 'not_a_known_kind' }], echo);

    expect(rail).toHaveLength(CHAT_STARTER_IDS.length);
    expect(rail.every(entry => !entry.grounded)).toBe(true);
  });

  it('keeps the known ones alongside', () => {
    const rail = composeStarterRail(
      [{ id: 'not_a_known_kind' }, { id: 'next_event', params: { subject: 'Dentiste' } }],
      echo
    );

    expect(rail.filter(entry => entry.grounded)).toHaveLength(1);
    expect(rail[0].key).toBe('grounded:next_event');
  });
});

describe('the known-suggestion list against the backend that produces them', () => {
  // `KNOWN_SUGGESTION_IDS` is a hand-maintained copy of a vocabulary the
  // BACKEND owns. Dropping an id we cannot word is the safe failure, but a
  // silent one: a suggestion kind added server-side would simply never appear,
  // and nothing would say so. Same doctrine as the SSE contract-symmetry test,
  // same mechanism — re-parse the source when the checkout exposes it.
  //
  // Skipped inside the web dev container, which mounts only apps/web; enforced
  // on host checkouts and in CI.
  const backendPath = path.resolve(process.cwd(), '../api/src/domains/chat/suggestions.py');

  it.skipIf(!fs.existsSync(backendPath))(
    'words every suggestion the backend can emit',
    () => {
      const source = fs.readFileSync(backendPath, 'utf-8');
      const emitted = [...source.matchAll(/ChatSuggestion\(id="([a-z_]+)"/g)].map(m => m[1]);

      expect(emitted.length).toBeGreaterThan(0);
      for (const id of emitted) {
        expect(KNOWN_SUGGESTION_IDS.has(id), `backend emits "${id}" — no wording here`).toBe(true);
      }
    }
  );

  it.skipIf(!fs.existsSync(backendPath))(
    'declares nothing the backend never emits',
    () => {
      // The other direction: a stale entry here is dead vocabulary that looks
      // supported, and would hide the day it stops being produced.
      const source = fs.readFileSync(backendPath, 'utf-8');
      const emitted = new Set(
        [...source.matchAll(/ChatSuggestion\(id="([a-z_]+)"/g)].map(m => m[1])
      );

      expect([...KNOWN_SUGGESTION_IDS].sort()).toEqual([...emitted].sort());
    }
  );
});
