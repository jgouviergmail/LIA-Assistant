/**
 * useWorkbenchTasks — the tasks screen's reads and acts (ADR-369, Task 6.2).
 *
 * A completion shows at once and is rolled back when the provider refuses it;
 * a new task carries the key of its submission and the list is re-read in
 * place; a removed task leaves the list — one already gone too. A second
 * submission of one key re-reads what the first made; a real refusal leaves
 * everything where it was.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

import { act, renderHook, waitFor } from '@/__tests__/test-utils';
import { ApiError } from '@/lib/api-client';
import type { WorkbenchTask } from '@/lib/workbench/types';

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

import { useWorkbenchTasks } from '../useWorkbenchTasks';

function task(id: string, overrides: Partial<WorkbenchTask> = {}): WorkbenchTask {
  return {
    id,
    title: id,
    notes: null,
    completed: false,
    due: null,
    parent: null,
    position: null,
    ...overrides,
  };
}

const LISTS = { items: [{ id: 'l1', title: 'Home' }], next_page_token: null };

beforeEach(() => {
  vi.clearAllMocks();
  api.get.mockImplementation((path: string) =>
    Promise.resolve(
      path.endsWith('/lists') ? LISTS : { items: [task('t1')], next_page_token: null }
    )
  );
});

async function rendered() {
  const hook = renderHook(() => useWorkbenchTasks('l1', false));
  await waitFor(() => expect(hook.result.current.tasks.items).toHaveLength(1));
  return hook;
}

describe('useWorkbenchTasks', () => {
  it('reads the lists, and the tasks of the list asked for', async () => {
    const { result } = await rendered();

    expect(result.current.lists.items).toEqual(LISTS.items);
    expect(api.get).toHaveBeenCalledWith('/workbench/tasks', {
      params: { list_id: 'l1', show_completed: false },
      signal: expect.any(AbortSignal),
    });
  });

  it('opens the first list when none is asked for', async () => {
    const { result } = renderHook(() => useWorkbenchTasks(null, false));

    await waitFor(() => expect(result.current.listId).toBe('l1'));
    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith('/workbench/tasks', {
        params: { list_id: 'l1', show_completed: false },
        signal: expect.any(AbortSignal),
      })
    );
  });

  it('reads no task while the account has no list', async () => {
    api.get.mockImplementation((path: string) =>
      Promise.resolve(path.endsWith('/lists') ? { items: [], next_page_token: null } : LISTS)
    );
    const { result } = renderHook(() => useWorkbenchTasks(null, false));

    await waitFor(() => expect(result.current.lists.loading).toBe(false));
    expect(result.current.listId).toBeNull();
    expect(api.get).not.toHaveBeenCalledWith('/workbench/tasks', expect.anything());
  });

  it('marks a task done at once, and keeps what the provider answers', async () => {
    const { result } = await rendered();
    let answer!: (value: WorkbenchTask) => void;
    api.patch.mockReturnValueOnce(new Promise(resolve => (answer = resolve)));

    let done: Promise<void> = Promise.resolve();
    act(() => {
      done = result.current.setCompleted(task('t1'), true);
    });
    expect(result.current.tasks.items[0]?.completed).toBe(true);

    await act(async () => {
      answer(task('t1', { completed: true, title: 'as stored' }));
      await done;
    });
    expect(result.current.tasks.items[0]?.title).toBe('as stored');
    expect(api.patch).toHaveBeenCalledWith(
      '/workbench/tasks',
      { list_id: 'l1', task_id: 't1', completed: true },
      undefined
    );
  });

  it('rolls a completion back when the provider refuses it, and says why', async () => {
    const { result } = await rendered();
    const refused = new ApiError('refused', 502, { detail: { code: 'provider_unavailable' } });
    api.patch.mockRejectedValueOnce(refused);

    await act(async () => {
      await expect(result.current.setCompleted(task('t1'), true)).rejects.toBe(refused);
    });

    expect(result.current.tasks.items[0]?.completed).toBe(false);
  });

  it('takes no second completion while the first is on its way', async () => {
    const { result } = await rendered();
    let answer!: (value: WorkbenchTask) => void;
    api.patch.mockReturnValueOnce(new Promise(resolve => (answer = resolve)));

    let first: Promise<void> = Promise.resolve();
    act(() => {
      first = result.current.setCompleted(task('t1'), true);
      void result.current.setCompleted(task('t1', { completed: true }), false);
    });
    expect(result.current.pending.has('t1')).toBe(true);

    await act(async () => {
      answer(task('t1', { completed: true }));
      await first;
    });
    expect(api.patch).toHaveBeenCalledTimes(1);
    expect(result.current.pending.has('t1')).toBe(false);
  });

  it('adds a task under its submission key, then re-reads the list in place', async () => {
    const { result } = await rendered();
    api.post.mockResolvedValueOnce(task('t2'));
    api.get.mockResolvedValueOnce({ items: [task('t2'), task('t1')], next_page_token: null });

    await act(async () => {
      await result.current.addTask({ title: 't2', idempotency_key: 'key-1' });
    });

    expect(api.post).toHaveBeenCalledWith(
      '/workbench/tasks',
      { list_id: 'l1', title: 't2', idempotency_key: 'key-1' },
      undefined
    );
    await waitFor(() =>
      expect(result.current.tasks.items.map(item => item.id)).toEqual(['t2', 't1'])
    );
  });

  it('re-reads the list after removing a task that had subtasks on screen', async () => {
    api.get.mockImplementation((path: string) =>
      Promise.resolve(
        path.endsWith('/lists')
          ? LISTS
          : { items: [task('t1'), task('t1a', { parent: 't1' })], next_page_token: null }
      )
    );
    const hook = renderHook(() => useWorkbenchTasks('l1', false));
    await waitFor(() => expect(hook.result.current.tasks.items).toHaveLength(2));
    api.delete.mockResolvedValueOnce(undefined);
    api.get.mockResolvedValueOnce({ items: [], next_page_token: null });

    await act(async () => {
      await hook.result.current.removeTask(task('t1'));
    });

    await waitFor(() => expect(hook.result.current.tasks.items).toEqual([]));
  });

  it('takes a removed task off the list — one already gone too', async () => {
    const { result } = await rendered();
    api.delete.mockRejectedValueOnce(new ApiError('gone', 404, { detail: { code: 'item_gone' } }));

    await act(async () => {
      await result.current.removeTask(task('t1'));
    });

    expect(result.current.tasks.items).toEqual([]);
    expect(api.delete).toHaveBeenCalledWith('/workbench/tasks', {
      params: { list_id: 'l1', task_id: 't1' },
      body: undefined,
    });
  });
});

const REPLAY = new ApiError('replay', 409, {
  detail: { code: 'already_submitted', outcome: 'done' },
});
const REFUSED = new ApiError('down', 502, { detail: { code: 'provider_unavailable' } });

describe('useWorkbenchTasks — saving, replays and refusals', () => {
  it('saves a change and keeps what the provider answers', async () => {
    const { result } = await rendered();
    api.patch.mockResolvedValueOnce(task('t1', { title: 'Buy oat milk', due: '2026-11-03' }));

    await act(async () => {
      await result.current.saveTask(task('t1'), { title: 'Buy oat milk' });
    });

    expect(api.patch).toHaveBeenCalledWith(
      '/workbench/tasks',
      { list_id: 'l1', task_id: 't1', title: 'Buy oat milk' },
      undefined
    );
    expect(result.current.tasks.items[0]).toMatchObject({
      title: 'Buy oat milk',
      due: '2026-11-03',
    });
  });

  it('re-reads the list when a task was already made by the same submission, and says so', async () => {
    const { result } = await rendered();
    api.post.mockRejectedValueOnce(REPLAY);
    api.get.mockResolvedValueOnce({ items: [task('t2'), task('t1')], next_page_token: null });

    await act(async () => {
      await expect(result.current.addTask({ title: 't2', idempotency_key: 'key-1' })).rejects.toBe(
        REPLAY
      );
    });

    await waitFor(() =>
      expect(result.current.tasks.items.map(item => item.id)).toEqual(['t2', 't1'])
    );
  });

  it('re-reads nothing after a real refusal, and keeps a task whose removal was refused', async () => {
    const { result } = await rendered();
    const reads = api.get.mock.calls.length;
    api.post.mockRejectedValueOnce(REFUSED);
    api.delete.mockRejectedValueOnce(REFUSED);

    await act(async () => {
      await expect(result.current.addTask({ title: 't2', idempotency_key: 'key-1' })).rejects.toBe(
        REFUSED
      );
      await expect(result.current.removeTask(task('t1'))).rejects.toBe(REFUSED);
    });

    expect(api.get).toHaveBeenCalledTimes(reads);
    expect(result.current.tasks.items.map(item => item.id)).toEqual(['t1']);
  });
});

describe('useWorkbenchTasks — the lists', () => {
  it('creates a list once per key and re-reads the lists, a replay too', async () => {
    const { result } = await rendered();
    const created = { id: 'l2', title: 'Work' };
    api.post.mockResolvedValueOnce(created).mockRejectedValueOnce(REPLAY);
    const lists = () => api.get.mock.calls.filter(([path]) => String(path).endsWith('/lists'));
    const before = lists().length;

    let made: unknown;
    await act(async () => {
      made = await result.current.addList('Work', 'key-2');
    });
    expect(made).toEqual(created);
    expect(api.post).toHaveBeenLastCalledWith(
      '/workbench/tasks/lists',
      { title: 'Work', idempotency_key: 'key-2' },
      undefined
    );
    await waitFor(() => expect(lists().length).toBe(before + 1));

    await act(async () => {
      await expect(result.current.addList('Work', 'key-2')).rejects.toBe(REPLAY);
    });
    await waitFor(() => expect(lists().length).toBe(before + 2));
  });

  it('takes a removed list away — one already gone too — and keeps one whose removal was refused', async () => {
    const { result } = await rendered();
    const home = { id: 'l1', title: 'Home' };
    api.delete
      .mockRejectedValueOnce(REFUSED)
      .mockRejectedValueOnce(new ApiError('gone', 404, { detail: { code: 'item_gone' } }));

    await act(async () => {
      await expect(result.current.removeList(home)).rejects.toBe(REFUSED);
    });
    expect(result.current.lists.items.map(list => list.id)).toEqual(['l1']);

    await act(async () => {
      await result.current.removeList(home);
    });
    expect(result.current.lists.items).toEqual([]);
    expect(api.delete).toHaveBeenLastCalledWith('/workbench/tasks/lists', {
      params: { list_id: 'l1' },
      body: undefined,
    });
  });
});
