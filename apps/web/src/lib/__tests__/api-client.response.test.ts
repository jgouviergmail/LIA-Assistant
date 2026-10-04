import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { isNativeShell } = vi.hoisted(() => ({ isNativeShell: vi.fn(() => false) }));
vi.mock('@/lib/native/shell', () => ({ isNativeShell }));

import { apiClient } from '@/lib/api-client';

beforeEach(() => isNativeShell.mockReturnValue(false));
afterEach(() => vi.restoreAllMocks());

describe('streamed API response', () => {
  it('keeps the body unread and its headers available, with session and native marker', async () => {
    isNativeShell.mockReturnValue(true);
    const source = new Response('source excerpt', { headers: { 'X-Preview-Truncated': 'true' } });
    const fetched = vi.spyOn(globalThis, 'fetch').mockResolvedValue(source);

    const response = await apiClient.getResponse('/attachments/id/preview');

    expect(response.bodyUsed).toBe(false);
    expect(response.headers.get('X-Preview-Truncated')).toBe('true');
    expect(await response.text()).toBe('source excerpt');
    expect(fetched.mock.calls[0][1]).toMatchObject({
      credentials: 'include',
      headers: { 'X-LIA-Native': '1' },
    });
  });

  it('retains the shared typed HTTP error contract before returning a body', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ detail: 'preview_gone' }), {
        status: 410,
        headers: { 'Content-Type': 'application/json' },
      })
    );
    await expect(apiClient.getResponse('/attachments/id/preview')).rejects.toMatchObject({
      name: 'ApiError',
      status: 410,
      message: 'preview_gone',
    });
  });

  it('keeps caller cancellation combined with the client timeout', async () => {
    const fetched = vi.spyOn(globalThis, 'fetch').mockImplementation(
      (_url, init) =>
        new Promise((_resolve, reject) => {
          init?.signal?.addEventListener('abort', () =>
            reject(new DOMException('aborted', 'AbortError'))
          );
        })
    );
    const controller = new AbortController();
    const pending = apiClient.getResponse('/attachments/id/preview', { signal: controller.signal });
    const effectiveSignal = fetched.mock.calls[0][1]?.signal;
    expect(effectiveSignal).not.toBe(controller.signal);
    controller.abort();
    expect(effectiveSignal?.aborted).toBe(true);
    await expect(pending).rejects.toMatchObject({ name: 'AbortError' });
  });
});
