// @vitest-environment node
/**
 * Source-level ratchets — two defect classes that must not grow back.
 *
 * Both scan every first-party file, so they live together and share ONE read of
 * the tree, in the **node** environment: they need no DOM, and paying for a
 * jsdom setup/teardown around ~2 s of blocking I/O is what made vitest's
 * watchdog kill the worker under coverage (a killed worker reports nothing,
 * which reads as a failing guard).
 *
 * 1. **The axios error shape.** Both HTTP clients expose the parsed body on
 *    `.data`; `err.response.data` is axios, a dependency this app dropped. That
 *    optional chain never resolved, so every backend message was silently
 *    replaced by a generic fallback. Tests are scanned too — the defect stayed
 *    green for months because a test fabricated a shape production never emits.
 *
 * 2. **Raw `fetch` on a data path.** `apiClient` is where four cross-cutting
 *    behaviours live: the 401 → localized login eject, the 403 step-up
 *    challenge, the request timeout, and the single error contract. A raw
 *    `fetch` opts out of all four, silently. The allowlist is SHRINK-ONLY:
 *    adding an entry means writing down why the client cannot serve that call,
 *    and an entry that no longer applies fails the test until it is removed.
 */

import { describe, it, expect } from 'vitest';

import { filesMatching, isCommentLine } from './source-scan';

// =============================================================================
// 1. The axios error shape
// =============================================================================

/** The historical defect, in both its optional-chained and plain forms. */
const AXIOS_SHAPE = /\.response\s*(\?\.|\.)\s*data\b/;

describe('ratchet — the axios error shape must not come back', () => {
  it('no source file reads an error through `.response.data`', () => {
    // This file is the one exception: it spells the defect out in the oracle.
    const offenders = filesMatching(AXIOS_SHAPE, {
      includeTests: true,
      exclude: ['source-ratchets.guard.test.ts'],
    });

    expect(offenders).toEqual([]);
  });

  it('the detector catches the historical defect', () => {
    expect(AXIOS_SHAPE.test("apiError.response?.data?.detail || t('x')")).toBe(true);
    expect(AXIOS_SHAPE.test('err.response.data.detail')).toBe(true);
    expect(AXIOS_SHAPE.test('getApiErrorDetail(error) ?? fallback')).toBe(false);
  });

  it('the detector still reads code that carries a trailing comment', () => {
    const line = 'const x = err.response?.data?.detail; // legacy';
    expect(isCommentLine(line)).toBe(false);
    expect(AXIOS_SHAPE.test(line)).toBe(true);
  });
});

// =============================================================================
// 2. Raw fetch on a data path
// =============================================================================

/** `fetch(` as a call, not `apiClient.fetch`, `globalThis.fetch = …`, `.fetch(`. */
const RAW_FETCH = /(^|[^.\w])fetch\s*\(/;

/**
 * Files allowed to call `fetch` directly, each with the reason the client
 * cannot serve them. Remove an entry when its call moves to `apiClient` —
 * never add one to make this test pass.
 */
const ALLOWED: Record<string, string> = {
  // --- Genuinely outside the JSON-over-apiClient contract ---
  'lib/api-client.ts': 'the client itself',
  'lib/api-server.ts': 'the Server Action client itself',
  'lib/api/chat.ts': 'SSE: needs the raw ReadableStream body, which apiClient consumes as text',
  'lib/audio/sherpaKws.ts': 'static WASM/model assets from /public, not the API',
  'lib/utils/download-image.ts': 'binary blob download, not a JSON payload',
  'lib/api/mcp-apps.ts': 'widget bridge: called from the sandboxed iframe shell origin',
  'components/settings/ConsumptionExportSection.tsx':
    'file download: reads Content-Disposition and response.blob(), which the client does not expose',
  'hooks/useSkills.ts':
    'FormData upload (the client forces application/json) and a zip blob download',
  'hooks/useAPIHealth.ts':
    'availability probe: a 401 here means "API unreachable", it must not eject the user to /login',
  'lib/product-telemetry.ts':
    'fire-and-forget telemetry (ADR-178): keepalive/sendBeacon on pagehide, anonymous allowed, ' +
    'failures swallowed — apiClient auth-eject and error surfaces must never trigger',
  'components/showroom/LiveDemoInvitation.tsx':
    'credentials: omit — apiClient forces include by BFF contract and refuses an override, but ' +
    'this renders on /demo, whose honesty strip states "no connected account": sending the ' +
    "visitor's session cookie to read a PUBLIC switch would make that displayed claim false. " +
    'Same contract and same reason as the showroom telemetry emitter next to it.',
};

describe('ratchet — data calls go through apiClient', () => {
  it('no unlisted file calls fetch directly', () => {
    const offenders = filesMatching(RAW_FETCH).filter(file => !(file in ALLOWED));

    expect(offenders).toEqual([]);
  });

  it('every allowed entry still calls fetch — otherwise remove it', () => {
    // Shrink-only: a migrated file must lose its exemption, so the list can
    // never quietly outlive the problem it documents.
    const stillRaw = new Set(filesMatching(RAW_FETCH));
    const stale = Object.keys(ALLOWED).filter(file => !stillRaw.has(file));

    expect(stale).toEqual([]);
  });

  it('every exemption carries a written reason', () => {
    const unexplained = Object.entries(ALLOWED)
      .filter(([, reason]) => reason.trim().length < 10)
      .map(([file]) => file);

    expect(unexplained).toEqual([]);
  });

  it('the detector distinguishes a call from a member access', () => {
    expect(RAW_FETCH.test('const r = await fetch(url);')).toBe(true);
    expect(RAW_FETCH.test('  return fetch(`${base}/x`);')).toBe(true);
    expect(RAW_FETCH.test('apiClient.fetch(url)')).toBe(false);
    expect(RAW_FETCH.test('window.fetch(url)')).toBe(false);
    expect(RAW_FETCH.test('const prefetch = (url) => {}')).toBe(false);
  });
});

// =============================================================================
// The scan itself
// =============================================================================

describe('the shared scan', () => {
  it('sees the whole tree — a scan that finds nothing proves nothing', () => {
    // Anti-rot: a path or layout change that silently empties the scan would
    // make both ratchets pass vacuously.
    expect(filesMatching(/./, { includeTests: true }).length).toBeGreaterThan(400);
  });

  it('separates production files from tests', () => {
    const withTests = filesMatching(/./, { includeTests: true }).length;
    const withoutTests = filesMatching(/./).length;

    expect(withoutTests).toBeLessThan(withTests);
    expect(withoutTests).toBeGreaterThan(300);
  });
});
