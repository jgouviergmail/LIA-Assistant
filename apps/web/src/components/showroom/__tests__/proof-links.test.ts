/**
 * Immutable proof links (P0 Task 5).
 *
 * What must hold:
 * - only a full lowercase 40-hex commit SHA yields immutable links; tags,
 *   branches, abbreviated SHAs, URLs and everything else fall back to
 *   repository-root links with isImmutable false;
 * - accepted SHAs build fixed blob URLs under the canonical repository;
 * - the registry is code-owned: callers cannot inject a URL or path, and it
 *   covers routing, planner/orchestrator, HITL, trace capture, and the
 *   public fixture/test, each labeled product-core or p0-fixture.
 */

import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  getConfiguredProofSha,
  getShowroomProofLinks,
} from '@/components/showroom/proof-links';

const SHA = 'a'.repeat(40);
const REPO = 'https://github.com/jgouviergmail/LIA-Assistant';

describe('showroom proof-links', () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it('accepts only a full lowercase 40-hex SHA', () => {
    for (const bad of [
      undefined,
      '',
      'main',
      'v1.28.0',
      SHA.slice(0, 12),
      SHA.toUpperCase(),
      `${SHA}\n`,
      `https://github.com/x/y/commit/${SHA}`,
      'g'.repeat(40),
    ]) {
      const result = getShowroomProofLinks(bad);
      expect(result.isImmutable).toBe(false);
      for (const link of result.links) {
        expect(link.url).toBe(REPO);
      }
    }
  });

  it('builds fixed immutable blob URLs from an accepted SHA', () => {
    const result = getShowroomProofLinks(SHA);
    expect(result.isImmutable).toBe(true);
    expect(result.links.length).toBeGreaterThanOrEqual(6);
    for (const link of result.links) {
      expect(link.url.startsWith(`${REPO}/blob/${SHA}/`)).toBe(true);
      expect(['product-core', 'p0-fixture']).toContain(link.kind);
    }
  });

  it('covers the promised capability areas with stable ids', () => {
    const ids = getShowroomProofLinks(SHA).links.map((l) => l.id);
    for (const expected of [
      'routing',
      'planner',
      'orchestrator',
      'hitl',
      'trace',
      'fixture',
    ]) {
      expect(ids).toContain(expected);
    }
    // Both evidence kinds are present.
    const kinds = new Set(getShowroomProofLinks(SHA).links.map((l) => l.kind));
    expect(kinds).toEqual(new Set(['product-core', 'p0-fixture']));
  });

  it('reads the build-time SHA through the helper only', () => {
    vi.stubEnv('NEXT_PUBLIC_SHOWROOM_PROOF_SHA', SHA);
    expect(getConfiguredProofSha()).toBe(SHA);
  });

  it('treats an unset build-time SHA as absent', () => {
    // Explicitly unset: `task test:frontend` loads the repository `.env`, so
    // relying on ambient absence made this test pass only by accident.
    vi.stubEnv('NEXT_PUBLIC_SHOWROOM_PROOF_SHA', undefined);
    expect(getConfiguredProofSha()).toBeUndefined();
  });
});
