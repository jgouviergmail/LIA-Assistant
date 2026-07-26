/**
 * Contract: NEXT_PUBLIC_API_URL="" (explicit empty string) means SAME-ORIGIN
 * relative `/api/v1/...` URLs through the BFF proxy — it must NEVER be
 * rewritten to the dev fallback.
 *
 * Hermetic E2E/CI builds set NEXT_PUBLIC_API_URL="" so every browser call is
 * relative and interceptable. Five call sites used `||`, which swallowed the
 * empty string into `http://localhost:8000`: browser traffic went cross-origin
 * and the authenticated scenarios lost their user (mocked responses blocked by
 * the browser). These tests pin the `??` semantics on the module-level readers
 * and on the real request paths; only a truly ABSENT variable may fall back.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const ENV_KEY = 'NEXT_PUBLIC_API_URL';
const originalValue = process.env[ENV_KEY];

function setEnv(value: string | undefined): void {
  if (value === undefined) {
    delete process.env[ENV_KEY];
  } else {
    process.env[ENV_KEY] = value;
  }
}

beforeEach(() => {
  vi.resetModules();
  // A real Response: `apiClient` reads `status` and `headers` before the body,
  // so a `{ok, json}` duck would only exercise the raw-fetch call sites.
  vi.stubGlobal(
    'fetch',
    vi
      .fn()
      .mockImplementation(
        async () =>
          new Response('{}', { status: 200, headers: { 'content-type': 'application/json' } })
      )
  );
});

afterEach(() => {
  setEnv(originalValue);
  vi.unstubAllGlobals();
});

describe('NEXT_PUBLIC_API_URL="" (explicit empty string → same-origin)', () => {
  beforeEach(() => setEnv(''));

  it('api-config keeps the empty base URL', async () => {
    const { API_BASE_URL } = await import('@/lib/api-config');
    expect(API_BASE_URL).toBe('');
  });

  it('personality API calls a RELATIVE /api/v1 URL', async () => {
    const { fetchPersonalities } = await import('@/lib/api/personality');
    await fetchPersonalities();
    expect(vi.mocked(fetch).mock.calls[0][0]).toBe('/api/v1/personalities');
  });

  it('chat API calls a RELATIVE /api/v1 URL', async () => {
    const { fetchActiveRun } = await import('@/lib/api/chat');
    await fetchActiveRun();
    expect(vi.mocked(fetch).mock.calls[0][0]).toBe('/api/v1/agents/runs/active');
  });
});

describe('NEXT_PUBLIC_API_URL absent (unset → dev fallback preserved)', () => {
  beforeEach(() => setEnv(undefined));

  it('api-config falls back to the dev API origin', async () => {
    const { API_BASE_URL } = await import('@/lib/api-config');
    expect(API_BASE_URL).toBe('http://localhost:8000');
  });

  it('apiClient stays relative and lets the Next.js rewrite proxy the call', async () => {
    // `api-config` (a module-level constant) and `apiClient` (the request path)
    // answer an ABSENT variable differently, on purpose: the client documents
    // relative URLs as the development contract, because the Next.js rewrite
    // proxies `/api/*` and that is what keeps the session cookie same-site.
    // Every data call in the app goes through the client, so this is the
    // behaviour that matters at runtime.
    const { default: apiClient } = await import('@/lib/api-client');
    await apiClient.get('/personalities');
    expect(vi.mocked(fetch).mock.calls[0][0]).toBe('/api/v1/personalities');
  });

  it('the personality API follows the client, not its own resolver', async () => {
    // It used to carry `process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'`
    // of its own, so an unset variable sent personality traffic cross-origin
    // while every other call stayed relative. Migrating it onto `apiClient`
    // (ADR-less cleanup: session handling, timeout, one error contract) removed
    // that divergence.
    const { fetchPersonalities } = await import('@/lib/api/personality');
    await fetchPersonalities();
    expect(vi.mocked(fetch).mock.calls[0][0]).toBe('/api/v1/personalities');
  });
});
