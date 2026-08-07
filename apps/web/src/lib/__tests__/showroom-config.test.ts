/**
 * Public showroom rollout setting (P0 — public-web-showroom program).
 *
 * What must hold:
 * - the variant is a bounded union: absent, invalid, or 'legacy' → 'legacy';
 * - 'guided' opts the /demo page into the interactive mission;
 * - the parser never throws, whatever the raw input;
 * - the env reader uses the statically inlined NEXT_PUBLIC_ value.
 */

import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  getPublicShowroomVariant,
  parsePublicShowroomVariant,
} from '@/lib/showroom-config';

describe('showroom-config', () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it.each([
    [undefined, 'legacy'],
    ['', 'legacy'],
    ['legacy', 'legacy'],
    ['guided', 'guided'],
  ] as const)('parses %j as %s', (raw, expected) => {
    expect(parsePublicShowroomVariant(raw)).toBe(expected);
  });

  it.each(['GUIDED', 'Guided', 'live', 'demo', '1', 'true', ' guided '])(
    'falls back to legacy on unknown or unnormalized value %j',
    (raw) => {
      expect(parsePublicShowroomVariant(raw)).toBe('legacy');
    }
  );

  it('never throws on hostile input', () => {
    expect(() =>
      parsePublicShowroomVariant('x'.repeat(10_000))
    ).not.toThrow();
  });

  it('reads the build-time env variable', () => {
    vi.stubEnv('NEXT_PUBLIC_PUBLIC_SHOWROOM_VARIANT', 'guided');
    expect(getPublicShowroomVariant()).toBe('guided');
  });

  it('defaults to legacy when the env variable is unset', () => {
    // Stub it AWAY explicitly: the oracle is "the code defaults", not "the
    // ambient environment happens to be empty". `task test:frontend` loads
    // the repository `.env`, where this variable is legitimately set once
    // the guided showroom is deployed — the test must survive that.
    vi.stubEnv('NEXT_PUBLIC_PUBLIC_SHOWROOM_VARIANT', undefined);
    expect(getPublicShowroomVariant()).toBe('legacy');
  });
});
