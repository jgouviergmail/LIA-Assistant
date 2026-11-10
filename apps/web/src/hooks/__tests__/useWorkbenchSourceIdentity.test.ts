/** Source identity is part of a Tool's reactive read key, including same-id history visits. */
import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useWorkbenchItem } from '../useWorkbenchItem';
import { useWorkbenchPage } from '../useWorkbenchPage';

const route = vi.hoisted(() => ({ search: '', pathname: '/en/dashboard/tools/mail' }));
const api = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('next/navigation', () => ({
  usePathname: () => route.pathname,
  useSearchParams: () => new URLSearchParams(route.search),
}));
vi.mock('@/hooks/useAuth', () => ({ useAuth: () => ({ user: { id: 'account' } }) }));
vi.mock('@/lib/api-client', async original => ({
  ...(await original<typeof import('@/lib/api-client')>()),
  default: api,
}));

interface Item {
  id: string;
  title: string;
}
interface Page {
  items: Item[];
  next_page_token: null;
}
interface SourceRead {
  items: Item[];
  loading: boolean;
  error: unknown;
}
const item = (title: string): Item => ({ id: 'same-id', title });
function useItemRead(): SourceRead {
  const read = useWorkbenchItem<Item>('/workbench/mail/message', { id: 'same-id' });
  return { ...read, items: read.item ? [read.item] : [] };
}
function usePageRead(): SourceRead {
  return useWorkbenchPage<Item>('/workbench/mail/messages', { folder: 'same-folder' });
}
const readers = [
  { name: 'item', hook: useItemRead, answer: (title: string): Item | Page => item(title) },
  {
    name: 'page',
    hook: usePageRead,
    answer: (title: string): Item | Page => ({ items: [item(title)], next_page_token: null }),
  },
];
beforeEach(() => {
  route.search = '';
  route.pathname = '/en/dashboard/tools/mail';
  api.get.mockReset();
});

describe.each(readers)('$name source-aware identity', reader => {
  it.each(['', 'card_source=unchanged'])('does not refetch when proof stays %s', async search => {
    route.search = search;
    api.get.mockResolvedValue(reader.answer('current'));
    const view = renderHook(reader.hook);
    await waitFor(() => expect(view.result.current.items[0]?.title).toBe('current'));
    view.rerender();
    expect(api.get).toHaveBeenCalledOnce();
  });

  it('withdraws the previous source synchronously and shows a source refusal', async () => {
    route.search = 'card_source=old';
    api.get.mockResolvedValueOnce(reader.answer('previous source'));
    const view = renderHook(reader.hook);
    await waitFor(() => expect(view.result.current.items).toHaveLength(1));
    const pending = Promise.withResolvers<Item | Page>();
    api.get.mockReturnValueOnce(pending.promise);
    route.search = 'card_source=new';
    view.rerender();
    expect(view.result.current.items).toEqual([]);
    expect(view.result.current.loading).toBe(true);
    await act(async () => pending.reject(new Error('source_changed')));
    expect(view.result.current.items).toEqual([]);
    expect(view.result.current.error).toBeInstanceOf(Error);
  });

  it('drops a late response from the former source on the same id', async () => {
    route.search = 'card_source=old';
    const pending = Promise.withResolvers<Item | Page>();
    api.get
      .mockReturnValueOnce(pending.promise)
      .mockResolvedValueOnce(reader.answer('current source'));
    const view = renderHook(reader.hook);
    route.search = 'card_source=new';
    view.rerender();
    await waitFor(() => expect(view.result.current.items[0]?.title).toBe('current source'));
    await act(async () => pending.resolve(reader.answer('previous source')));
    expect(view.result.current.items[0]?.title).toBe('current source');
  });

  it('does not invalidate an unrelated family for a card proof', async () => {
    route.pathname = '/en/dashboard/tools/contacts';
    api.get.mockResolvedValue(reader.answer('current'));
    const view = renderHook(reader.hook);
    await waitFor(() => expect(view.result.current.items).toHaveLength(1));
    route.search = 'card_source=contact-proof';
    view.rerender();
    expect(api.get).toHaveBeenCalledOnce();
  });
});
