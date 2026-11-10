/** Multipart uploads use the ordinary session, cancellation and refusal boundary intact. */
import { act, renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { useApiMutation } from '@/hooks/useApiMutation';
import apiClient, { ApiError } from '@/lib/api-client';

afterEach(() => vi.restoreAllMocks());

function cardForm() {
  const file = new File(['photographed card'], 'card.jpg', { type: 'image/jpeg' });
  const form = new FormData();
  form.append('file', file);
  form.append('id', 'people/card');
  return { file, form };
}

describe('multipart mutations', () => {
  it.each(['POST', 'PUT', 'PATCH'] as const)(
    '%s sends the file unchanged through the real mutation hook and HTTP client',
    async method => {
      const { file, form } = cardForm();
      const fetched = vi
        .spyOn(globalThis, 'fetch')
        .mockResolvedValue(Response.json({ done: true }));
      const controller = new AbortController();
      const { result } = renderHook(() =>
        useApiMutation<FormData, { done: boolean }>({ method, componentName: 'MultipartTest' })
      );

      await act(() =>
        result.current.mutate('/tool-assists/contacts/from-card', form, {
          signal: controller.signal,
          headers: {
            'Content-Type': 'application/json',
            'content-type': 'multipart/form-data',
            Accept: 'application/json',
          },
        })
      );

      const sent = fetched.mock.calls[0][1];
      expect(sent?.body).toBe(form);
      expect(form.get('file')).toBe(file);
      expect(form.get('id')).toBe('people/card');
      expect(sent).toMatchObject({ method, credentials: 'include' });
      const headers = new Headers(sent?.headers);
      expect(headers.has('Content-Type')).toBe(false);
      expect(headers.get('Accept')).toBe('application/json');
      expect(result.current.data).toEqual({ done: true });
      controller.abort();
      expect(sent?.signal?.aborted).toBe(true);
    }
  );

  it('keeps a multipart streamed response unread', async () => {
    const { form } = cardForm();
    const fetched = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('proposal'));
    const response = await apiClient.postResponse('/tool-assists/contacts/from-card', form);
    expect(fetched.mock.calls[0][1]?.body).toBe(form);
    expect(new Headers(fetched.mock.calls[0][1]?.headers).has('Content-Type')).toBe(false);
    expect(response.bodyUsed).toBe(false);
    expect(await response.text()).toBe('proposal');
  });

  it('preserves the typed API refusal after an upload', async () => {
    const { form } = cardForm();
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      Response.json({ detail: { code: 'assist_unreadable' } }, { status: 422 })
    );
    const pending = apiClient.post('/tool-assists/contacts/from-card', form);
    await expect(pending).rejects.toBeInstanceOf(ApiError);
    await expect(pending).rejects.toMatchObject({
      status: 422,
      data: { detail: { code: 'assist_unreadable' } },
    });
  });
});
