/**
 * useWorkbenchMail — the mail screen's reads and acts on messages (ADR-369, Task 4.7).
 *
 * A read state shows AT ONCE and every message the provider did not do is
 * rolled back (a refusal of the whole act rolls back every one); the trash
 * removes exactly the messages it moved; a label applied shows on its rows,
 * and a row whose label is removed leaves that label's listing.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

import { act, renderHook, waitFor } from '@/__tests__/test-utils';
import { ApiError } from '@/lib/api-client';
import type { MailSummary } from '@/lib/workbench/types';

const { api } = vi.hoisted(() => ({
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));
vi.mock('@/hooks/useAuth', () => ({ useAuth: () => ({ user: { id: 'owner' } }) }));
vi.mock('@/lib/api-client', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/api-client')>()),
  default: api,
}));
vi.mock('@/lib/logger', () => ({
  logger: { debug: vi.fn(), error: vi.fn(), warn: vi.fn(), info: vi.fn() },
}));

import { useWorkbenchMail } from '../useWorkbenchMail';

function row(id: string, overrides: Partial<MailSummary> = {}): MailSummary {
  return {
    id,
    thread_id: id,
    sender: { name: 'Ana', address: 'ana@example.org' },
    subject: id,
    snippet: '',
    received_at: null,
    is_read: false,
    is_starred: false,
    label_ids: [],
    ...overrides,
  };
}

const FOLDERS = {
  folders: [
    { id: 'system:inbox', kind: 'system', role: 'inbox', name: null },
    { id: 'Label_7', kind: 'user', role: null, name: 'Work' },
  ],
};

let page: { items: MailSummary[]; next_page_token: string | null; skipped: number };

beforeEach(() => {
  vi.clearAllMocks();
  page = { items: [row('m1'), row('m2'), row('m3')], next_page_token: null, skipped: 0 };
  api.get.mockImplementation((path: string) =>
    Promise.resolve(path === '/workbench/mail/folders' ? FOLDERS : page)
  );
});

async function rendered(folder = 'system:inbox') {
  const hook = renderHook(() => useWorkbenchMail(true, folder, { folder }));
  await waitFor(() => expect(hook.result.current.messages.items).toHaveLength(3));
  return hook;
}

/** The body last posted to a path (the mutation's plumbing is not the contract). */
function posted(path: string): unknown {
  return api.post.mock.calls.filter(([called]) => called === path).at(-1)?.[1];
}

function readStates(items: readonly MailSummary[]): boolean[] {
  return items.map(item => item.is_read);
}

describe('useWorkbenchMail', () => {
  it('reads the folder pane and the folder asked for', async () => {
    const { result } = await rendered();

    await waitFor(() => expect(result.current.folders).toEqual(FOLDERS.folders));
    expect(api.get).toHaveBeenCalledWith('/workbench/mail/messages', {
      params: { folder: 'system:inbox' },
      signal: expect.any(AbortSignal),
    });
  });

  it('shows a read state at once and rolls back the messages the provider did not do', async () => {
    let answer!: (value: unknown) => void;
    api.post.mockReturnValueOnce(new Promise(resolve => (answer = resolve)));
    const { result } = await rendered();
    const [first, second] = result.current.messages.items;

    let acted!: Promise<unknown>;
    act(() => {
      acted = result.current.setRead([first, second], true);
    });
    expect(readStates(result.current.messages.items)).toEqual([true, true, false]);
    expect(result.current.pending.has('m1')).toBe(true);

    await act(async () => {
      answer({ done: ['m1'], failed: [{ id: 'm2', status: 'failed' }] });
      await acted;
    });
    expect(readStates(result.current.messages.items)).toEqual([true, false, false]);
    expect(result.current.pending.size).toBe(0);
    expect(posted('/workbench/mail/read-state')).toEqual({ message_ids: ['m1', 'm2'], read: true });
  });

  it('rolls every message back when the act is refused whole, and says why', async () => {
    api.post.mockRejectedValueOnce(
      new ApiError('refused', 502, { detail: { code: 'provider_unavailable' } })
    );
    const { result } = await rendered();

    await act(async () => {
      await expect(result.current.setRead(result.current.messages.items, true)).rejects.toThrow();
    });

    expect(readStates(result.current.messages.items)).toEqual([false, false, false]);
  });

  it('removes exactly the messages the trash took', async () => {
    api.post.mockResolvedValueOnce({
      done: ['m1', 'm3'],
      failed: [{ id: 'm2', status: 'failed' }],
    });
    const { result } = await rendered();

    let outcome: unknown;
    await act(async () => {
      outcome = await result.current.trash(['m1', 'm2', 'm3']);
    });

    expect(result.current.messages.items.map(item => item.id)).toEqual(['m2']);
    expect(outcome).toEqual({ done: ['m1', 'm3'], failed: [{ id: 'm2', status: 'failed' }] });
  });

  it('draws a label applied on its rows', async () => {
    api.post.mockResolvedValueOnce(undefined);
    const { result } = await rendered();
    const [first] = result.current.messages.items;

    await act(() => result.current.applyLabels([first], ['Label_7'], []));

    expect(result.current.messages.items[0].label_ids).toEqual(['Label_7']);
    expect(posted('/workbench/mail/labels/apply')).toEqual({
      message_ids: ['m1'],
      add: ['Label_7'],
      remove: [],
    });
  });

  it('takes a message out of a label’s listing when that label is removed from it', async () => {
    page = {
      items: [row('m1', { label_ids: ['Label_7'] }), row('m2'), row('m3')],
      next_page_token: null,
      skipped: 0,
    };
    api.post.mockResolvedValueOnce(undefined);
    const { result } = await rendered('Label_7');

    await act(() =>
      result.current.applyLabels([result.current.messages.items[0]], [], ['Label_7'])
    );

    expect(result.current.messages.items.map(item => item.id)).toEqual(['m2', 'm3']);
  });

  it('re-reads the pane after a label is created', async () => {
    api.post.mockResolvedValueOnce({ id: 'Label_9', kind: 'user', role: null, name: 'Trips' });
    const { result } = await rendered();
    await waitFor(() => expect(result.current.folders).toBeDefined());
    const reads = api.get.mock.calls.filter(([path]) => path === '/workbench/mail/folders').length;

    await act(async () => {
      await result.current.createLabel('Trips');
    });

    expect(posted('/workbench/mail/labels')).toEqual({ name: 'Trips' });
    await waitFor(() =>
      expect(api.get.mock.calls.filter(([path]) => path === '/workbench/mail/folders').length).toBe(
        reads + 1
      )
    );
  });

  it('reads nothing while the tool is not ready', async () => {
    renderHook(() => useWorkbenchMail(false, 'system:inbox', { folder: 'system:inbox' }));

    await act(async () => {
      await Promise.resolve();
    });
    expect(api.get).not.toHaveBeenCalled();
  });
});
