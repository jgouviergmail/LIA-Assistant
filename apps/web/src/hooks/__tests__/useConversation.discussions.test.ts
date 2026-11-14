/** Reads of an explicit target cannot become an empty or different discussion. */
import { act, renderHook } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { useConversation } from '../useConversation';

const h = vi.hoisted(() => ({ get: vi.fn(), user: { id: 'owner' } }));
vi.mock('@/lib/api-client', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/api-client')>()), apiClient: { get: h.get },
}));
vi.mock('@/hooks/useAuth', () => ({ useAuth: () => ({ user: h.user }) }));
vi.mock('@/lib/logger', () => ({
  logger: { info: vi.fn(), warn: vi.fn(), error: vi.fn(), debug: vi.fn() },
}));
vi.mock('@/lib/logging-context', () => {
  const withContext = (v?: object) => v ?? {};
  return { useLoggingContext: () => ({ withContext }) };
});

const selection = { conversation_id: 'annex', conversation_revision: 4 };
beforeEach(() => {
  h.get.mockReset();
});

it('sends both coordinates for history and totals', async () => {
  h.get.mockResolvedValue({
    conversation_id: 'annex',
    conversation_revision: 4,
    messages: [],
    has_more: false,
    next_cursor: null,
  });
  const hook = renderHook(() => useConversation(selection));
  await act(async () => {
    await hook.result.current.readNewestPage();
    await hook.result.current.loadConversationTotals();
  });
  for (const [url, config] of h.get.mock.calls.filter(([url]) => String(url).includes('/me/'))) {
    expect(config.params, String(url)).toMatchObject(selection);
  }
});

it('refuses usage returned for a different discussion or revision', async () => {
  h.get.mockResolvedValue({ conversation_id: 'main', conversation_revision: 4, total_tokens_in: 100 });
  const hook = renderHook(() => useConversation(selection));
  await expect(hook.result.current.loadConversationTotals()).rejects.toMatchObject({ status: 409 });
  h.get.mockResolvedValue({ conversation_id: 'annex', conversation_revision: 3, total_tokens_in: 200 });
  await expect(hook.result.current.loadConversationTotals()).rejects.toMatchObject({ status: 409 });
});

it('surfaces an annex 404 instead of treating it as an empty new account', async () => {
  const refusal = Object.assign(new Error('Discussion not found'), { status: 404 });
  h.get.mockRejectedValue(refusal);
  const hook = renderHook(() => useConversation(selection));
  await act(async () => {
    const results = await Promise.allSettled([
      hook.result.current.loadConversationPage(),
      hook.result.current.loadConversationTotals(),
    ]);
    expect(results).toEqual(
      Array.from({ length: 2 }, () => ({ status: 'rejected', reason: refusal }))
    );
  });
});

it('rejects a response arriving after its discussion was retired even if transport ignored abort', async () => {
  const late = Promise.withResolvers<{ messages: []; has_more: false; next_cursor: null }>();
  h.get.mockImplementation((url: string) =>
    url.endsWith('/messages') ? late.promise : Promise.resolve(null)
  );
  const hook = renderHook(() => useConversation(selection));
  const reading = hook.result.current.readNewestPage();
  hook.unmount();
  late.resolve({ messages: [], has_more: false, next_cursor: null });
  await expect(reading).rejects.toMatchObject({ name: 'AbortError' });
});

it('never revives a retired reader when the same discussion is selected again', async () => {
  h.get.mockResolvedValue({ messages: [], has_more: false, next_cursor: null });
  const hook = renderHook(({ target }) => useConversation(target), {
    initialProps: { target: selection },
  });
  const retiredRead = hook.result.current.readNewestPage;
  hook.rerender({ target: { ...selection, conversation_id: 'other' } });
  hook.rerender({ target: selection });
  h.get.mockClear();
  await expect(retiredRead()).rejects.toMatchObject({ name: 'AbortError' });
  // The newly selected view may refresh its metadata; the old page reader may not run.
  expect(h.get.mock.calls.filter(([url]) => String(url).endsWith('/messages'))).toEqual([]);
});
