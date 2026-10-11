import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { publishApplicationResources } from '@/lib/application-resources';

const { get, useAuth } = vi.hoisted(() => ({ get: vi.fn(), useAuth: vi.fn() }));
vi.mock('@/lib/api-client', () => ({ default: { get } }));
vi.mock('@/hooks/useAuth', () => ({ useAuth }));
import { useInterestNotificationHistory } from '../useInterestNotificationHistory';

const saved = { total: 1, notifications: [{ id: 'notice', topic: 'Old topic', content: 'Delivered message', source: 'llm', user_feedback: null, created_at: '2026-10-08T12:00:00Z' }] };
beforeEach(() => {
  vi.resetAllMocks();
  useAuth.mockReturnValue({ user: { id: 'one' } });
  get.mockResolvedValue(saved);
});

describe('interest history follows current account management', () => {
  it('refreshes retained notifications after confirmed deletion for their owner', async () => {
    const { result } = renderHook(() => useInterestNotificationHistory());
    await waitFor(() => expect(result.current.notifications?.[0]?.topic).toBe('Old topic'));
    get.mockClear();
    act(() => publishApplicationResources('foreign', new Set(['interests'])));
    expect(get).not.toHaveBeenCalled();
    get.mockResolvedValue({ ...saved, notifications: [{ ...saved.notifications[0], topic: null }] });
    act(() => publishApplicationResources('one', new Set(['interests'])));
    await waitFor(() => expect(result.current.notifications?.[0]?.topic).toBeNull());
    expect(result.current.notifications?.[0]?.content).toBe('Delivered message');
    expect(result.current.total).toBe(1);
  });

  it('hides retired account history and makes retired refresh callbacks inert', async () => {
    const { result, rerender } = renderHook(() => useInterestNotificationHistory());
    await waitFor(() => expect(result.current.total).toBe(1));
    const retired = result.current.refetch;
    get.mockClear();
    get.mockReturnValue(new Promise(() => {}));
    useAuth.mockReturnValue({ user: { id: 'two' } });
    rerender();
    expect(result.current.notifications).toBeUndefined();
    expect(result.current.total).toBe(0);
    await waitFor(() => expect(get).toHaveBeenCalled());
    get.mockClear();
    await act(async () => { await retired(); });
    expect(get).not.toHaveBeenCalled();
  });

  it('does not fetch a closed panel when an interest change is published', () => {
    renderHook(() => useInterestNotificationHistory(false));
    act(() => publishApplicationResources('one', new Set(['interests'])));
    expect(get).not.toHaveBeenCalled();
  });
});
