/**
 * Every reading the backend accepts is a reading this app can actually open.
 *
 * `RegisterOrigin` was a bare union type until 2026-09-07, so nothing could
 * compare it to the enum the API enforces — the same blind spot that let
 * `EffectSource` gain a fourth value while this side still listed three. It is
 * a runtime list now, and `test_source_vocabulary_crosses_the_stack.py` reads
 * this very file to check the two halves are one list.
 *
 * This guard is the frontend half: the values are the ones the journals and
 * their hooks are actually written for, and none of them is a stray string.
 */

import { describe, expect, it } from 'vitest';

import { REGISTER_ORIGINS, type RegisterOrigin } from '@/types/register-origin';

describe('register origins', () => {
  it('declares exactly the three readings the page offers', () => {
    // `mine` and `initiative` are the two tabs; `all` is the unfiltered
    // default a caller gets when it asks for nothing.
    expect([...REGISTER_ORIGINS].sort()).toEqual(['all', 'initiative', 'mine']);
  });

  it('holds no duplicate', () => {
    expect(new Set(REGISTER_ORIGINS).size).toBe(REGISTER_ORIGINS.length);
  });

  it('derives the type from the list rather than the other way round', () => {
    // If the two ever drift apart, this stops compiling — which is the whole
    // reason the list exists at runtime.
    const everyOne: RegisterOrigin[] = [...REGISTER_ORIGINS];
    expect(everyOne).toHaveLength(REGISTER_ORIGINS.length);
  });

  it('carries values safe to put in a query string verbatim', () => {
    // They travel to the API as `?origin=…`; a value needing encoding would
    // work on one caller and not the next.
    for (const origin of REGISTER_ORIGINS) {
      expect(encodeURIComponent(origin)).toBe(origin);
    }
  });
});
