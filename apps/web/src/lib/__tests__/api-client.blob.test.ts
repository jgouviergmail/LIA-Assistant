/**
 * A binary body through the same client: the cookie, the error contract and
 * the caller's cancellation are the JSON calls' own.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import apiClient, { ApiError } from '@/lib/api-client';

beforeEach(() => {
  vi.restoreAllMocks();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('getBlob', () => {
  it('returns the body as a blob and carries the session cookie', async () => {
    const fetched = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(
        new Response(new Uint8Array([1, 2, 3]), { headers: { 'content-type': 'audio/mpeg' } })
      );

    const blob = await apiClient.getBlob('/radio/sessions/s1/segments/1/audio');

    expect(blob.size).toBe(3);
    expect(fetched.mock.calls[0][1]?.credentials).toBe('include');
  });

  it('raises the server error like any other call', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ detail: 'segment_gone' }), {
        status: 410,
        headers: { 'content-type': 'application/json' },
      })
    );

    await expect(apiClient.getBlob('/radio/sessions/s1/segments/9/audio')).rejects.toMatchObject({
      name: ApiError.name,
      status: 410,
      message: 'segment_gone',
    });
  });

  it("lets the caller's signal cancel the download", async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(
      (_url, init) =>
        new Promise((_resolve, reject) => {
          init?.signal?.addEventListener('abort', () =>
            reject(new DOMException('aborted', 'AbortError'))
          );
        })
    );
    const controller = new AbortController();

    const pending = apiClient.getBlob('/radio/sessions/s1/segments/2/audio', {
      signal: controller.signal,
    });
    controller.abort();

    await expect(pending).rejects.toMatchObject({ name: 'AbortError' });
  });
});
