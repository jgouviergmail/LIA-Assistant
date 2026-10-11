import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { useAuth, get, patch, post } = vi.hoisted(() => ({
  useAuth: vi.fn(),
  get: vi.fn(),
  patch: vi.fn(),
  post: vi.fn(),
}));
vi.mock('@/hooks/useAuth', () => ({ useAuth }));
vi.mock('@/lib/api-client', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/api-client')>()),
  default: { get, patch, post },
}));
import { publishApplicationResources } from '@/lib/application-resources';
import { useOpenLoops } from '../useOpenLoops';

const row = {
  id: 'one',
  subject: 'Original promise',
  counterparty: null,
  direction: 'user_owes',
  due_hint: null,
  created_at: '2026-10-08T08:00:00Z',
};
beforeEach(() => {
  vi.clearAllMocks();
  get.mockReset();
  patch.mockReset();
  post.mockReset();
  useAuth.mockReturnValue({ user: { id: 'account-one' } });
  get.mockResolvedValue({ items: [row], total: 1 });
});

describe('owned commitment management synchronization', () => {
  it('rereads a native change and releases earlier manual edits', async () => {
    patch.mockResolvedValue({ ...row, subject: 'Manual edit' });
    const { result } = renderHook(() => useOpenLoops());
    await waitFor(() => expect(result.current.loops).toHaveLength(1));
    await act(async () => {
      await result.current.update('one', { subject: 'Manual edit' });
    });
    expect(result.current.loops[0].subject).toBe('Manual edit');
    get.mockResolvedValue({ items: [{ ...row, subject: 'Confirmed native edit' }], total: 1 });
    act(() => publishApplicationResources('account-one', new Set(['open_loops'])));
    await waitFor(() => expect(result.current.loops[0].subject).toBe('Confirmed native edit'));
  });

  it('hides private rows on an account switch and refuses obsolete action callbacks', async () => {
    const { result, rerender } = renderHook(() => useOpenLoops());
    await waitFor(() => expect(result.current.loops).toHaveLength(1));
    const obsolete = result.current.close;
    get.mockImplementationOnce(() => new Promise(() => {}));
    useAuth.mockReturnValue({ user: { id: 'account-two' } });
    rerender();
    expect(result.current.loops).toEqual([]);
    await act(async () => {
      expect(await obsolete('one', 'done')).toBe(false);
    });
    expect(post).not.toHaveBeenCalled();
  });

  it('does not restore an old account optimistic response into the current account', async () => {
    let resolve: ((value: unknown) => void) | undefined;
    patch.mockImplementationOnce(
      () =>
        new Promise(done => {
          resolve = done;
        })
    );
    const { result, rerender } = renderHook(() => useOpenLoops());
    await waitFor(() => expect(result.current.loops).toHaveLength(1));
    let pending: Promise<boolean>;
    act(() => {
      pending = result.current.update('one', { subject: 'Private edit' });
    });
    useAuth.mockReturnValue({ user: { id: 'account-two' } });
    get.mockResolvedValue({ items: [{ ...row, subject: 'Other account promise' }], total: 1 });
    rerender();
    await waitFor(() => expect(result.current.loops[0]?.subject).toBe('Other account promise'));
    await act(async () => {
      resolve?.({ ...row, subject: 'Private edit' });
      await pending;
    });
    expect(result.current.loops[0].subject).toBe('Other account promise');
  });

  it('a late failed manual request cannot restore an override removed by a native reread', async () => {
    patch.mockResolvedValueOnce({ ...row, subject: 'Earlier manual edit' });
    const { result } = renderHook(() => useOpenLoops());
    await waitFor(() => expect(result.current.loops).toHaveLength(1));
    await act(async () => {
      await result.current.update('one', { subject: 'Earlier manual edit' });
    });
    let reject: ((reason: Error) => void) | undefined;
    patch.mockImplementationOnce(
      () =>
        new Promise((_resolve, fail) => {
          reject = fail;
        })
    );
    let pending: Promise<boolean>;
    act(() => {
      pending = result.current.update('one', { subject: 'Pending correction' });
    });
    get.mockResolvedValue({
      items: [{ ...row, subject: 'Confirmed native correction' }],
      total: 1,
    });
    act(() => publishApplicationResources('account-one', new Set(['open_loops'])));
    await waitFor(() =>
      expect(result.current.loops[0].subject).toBe('Confirmed native correction')
    );
    await act(async () => {
      reject?.(new Error('stale request'));
      await pending;
    });
    expect(result.current.loops[0].subject).toBe('Confirmed native correction');
  });
});
