import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { publishApplicationResources } from '@/lib/application-resources';

const { get, post, patch, remove, useAuth } = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  remove: vi.fn(),
  useAuth: vi.fn(),
}));
vi.mock('@/hooks/useAuth', () => ({ useAuth }));
vi.mock('@/lib/api-client', async importOriginal => {
  const original = await importOriginal<typeof import('@/lib/api-client')>();
  return { ...original, default: { get, post, patch, delete: remove } };
});
import { useReminders } from '../useReminders';

const saved = { reminders: [{ id: 'reminder', content: 'Saved reminder' }], total: 1 };
beforeEach(() => {
  vi.resetAllMocks();
  useAuth.mockReturnValue({ user: { id: 'one' } });
  get.mockResolvedValue(saved);
});

describe('reminder data and callbacks belong to the current account', () => {
  it('rereads a committed assistant change only for its owner', async () => {
    const { result } = renderHook(() => useReminders());
    await waitFor(() => expect(result.current.reminders).toHaveLength(1));
    get.mockClear();
    act(() => publishApplicationResources('foreign', new Set(['reminders'])));
    expect(get).not.toHaveBeenCalled();
    get.mockResolvedValue({ reminders: [], total: 0 });
    act(() => publishApplicationResources('one', new Set(['reminders'])));
    await waitFor(() => expect(result.current.reminders).toEqual([]));
    expect(get.mock.calls.map(call => call[0])).toEqual(['/reminders/detail?limit=100']);
  });

  it('hides old data and rejects retired mutation callbacks after an account change', async () => {
    const { result, rerender } = renderHook(() => useReminders());
    await waitFor(() => expect(result.current.reminders).toHaveLength(1));
    const retired = {
      create: result.current.createReminder,
      update: result.current.updateReminder,
      remove: result.current.deleteReminder,
    };
    get.mockReturnValue(new Promise(() => {}));
    useAuth.mockReturnValue({ user: { id: 'two' } });
    rerender();
    expect(result.current.reminders).toEqual([]);
    await act(async () => {
      await retired.create({
        content: 'Old',
        original_message: 'Old',
        trigger_at: '2099-01-01T09:00:00Z',
      });
      await retired.update('reminder', { content: 'Old' });
      await retired.remove('reminder');
    });
    expect(post).not.toHaveBeenCalled();
    expect(patch).not.toHaveBeenCalled();
    expect(remove).not.toHaveBeenCalled();
  });
});
