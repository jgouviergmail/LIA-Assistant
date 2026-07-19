/**
 * SEC-017 — RAG upload proxy route-escape guard (non-regression).
 *
 * `spaceId` is interpolated into the upstream URL. Before the fix, an encoded
 * value (`..%2f..%2fauth%2flogout`) survived WHATWG URL normalization and could
 * retarget a *different* backend POST route while carrying the session cookie.
 *
 * These tests pin the guard: a non-UUID `spaceId` is rejected with 400 BEFORE
 * any upstream request is made (fetch is never called), and a valid UUID is
 * proxied to the exact expected path.
 */

import { NextRequest } from 'next/server';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { POST } from './route';

/** Build a real NextRequest (no contract-bypassing casts). */
function makeRequest(body = 'multipart-body'): NextRequest {
  return new NextRequest('http://localhost/api/rag-upload/x', {
    method: 'POST',
    body,
    headers: { 'content-type': 'multipart/form-data; boundary=x', cookie: 'lia_session=abc' },
  });
}

/** Invoke POST with the given spaceId (params is a Promise in Next 16). */
function callPost(spaceId: string, body?: string) {
  return POST(makeRequest(body), { params: Promise.resolve({ spaceId }) });
}

describe('SEC-017 — rag-upload spaceId route-escape guard', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  const MALICIOUS_IDS = [
    '..',
    '../../auth/logout',
    '..%2f..%2fauth%2flogout',
    '..%252f..%252fauth', // double-encoded
    'a/b',
    'a\\b',
    'valid-looking-but-not-uuid',
    '',
    ' ',
    '00000000-0000-0000-0000-00000000000', // 11 trailing chars: too short
    '00000000-0000-0000-0000-0000000000000', // 13 trailing chars: too long
    'zzzzzzzz-0000-0000-0000-000000000000', // non-hex
    '00000000-0000-0000-0000-000000000000?x=1', // trailing query
  ];

  it.each(MALICIOUS_IDS)('rejects %j with 400 and makes no upstream request', async spaceId => {
    const res = await callPost(spaceId);

    expect(res.status).toBe(400);
    expect(fetch).not.toHaveBeenCalled();
  });

  it('proxies a valid UUID to the exact rag-spaces documents path', async () => {
    const uuid = '3f1e8c9a-1b2c-4d5e-8f90-a1b2c3d4e5f6';
    const upstream = new Response('{"ok":true}', {
      status: 200,
      headers: { 'content-type': 'application/json' },
    });
    vi.mocked(fetch).mockResolvedValue(upstream);

    const res = await callPost(uuid);

    expect(res.status).toBe(200);
    expect(fetch).toHaveBeenCalledTimes(1);
    const calledUrl = vi.mocked(fetch).mock.calls[0][0];
    expect(calledUrl).toBe(
      `${process.env.API_URL_SERVER || 'https://api:8000'}/api/v1/rag-spaces/${uuid}/documents`
    );
    // No traversal survived into the final path.
    expect(String(calledUrl)).not.toContain('..');
  });

  it('accepts a valid UUID case-insensitively', async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response('{}', { status: 200, headers: { 'content-type': 'application/json' } })
    );

    const res = await callPost('3F1E8C9A-1B2C-4D5E-8F90-A1B2C3D4E5F6');

    expect(res.status).toBe(200);
    expect(fetch).toHaveBeenCalledTimes(1);
  });
});
