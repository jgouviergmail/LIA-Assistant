import { act, renderHook } from '@/__tests__/test-utils';
import { beforeEach, afterEach, describe, it, expect, vi } from 'vitest';
import { handOff, handoffStore, setHandoffOwner } from '@/lib/workbench/handoff';
import { useHandoff, useHandoffNavigation, useHandoffOwner } from '../useHandoff';
const { account, push, info } = vi.hoisted(() => ({
  account: { id: 'owner' },
  push: vi.fn(),
  info: vi.fn(),
}));
vi.mock('@/hooks/useAuth', () => ({ useAuth: () => ({ user: { id: account.id } }) }));
vi.mock('next/navigation', () => ({ useRouter: () => ({ push }) }));
vi.mock('sonner', () => ({ toast: { info } }));
beforeEach(() => {
  account.id = 'owner';
  setHandoffOwner('owner');
  vi.clearAllMocks();
});
afterEach(() => setHandoffOwner(null));

describe('native form handover', () => {
  it('routes reminder and ticket proposals without putting their content in a URL', () => {
    const { result } = renderHook(() => useHandoffNavigation('fr'));
    act(() =>
      result.current({
        kind: 'reminder',
        reminder: { content: 'Private reminder', recurrence: null },
      })
    );
    expect(push).toHaveBeenLastCalledWith('/fr/dashboard/settings?section=reminders');
    act(() =>
      result.current({ kind: 'ticket', ticket: { title: 'Private ticket', description: 'Source' } })
    );
    expect(push).toHaveBeenLastCalledWith('/dashboard/workboard');
    expect(push.mock.calls.flat().join('')).not.toContain('Private');
  });
  it('receives successive proposals on an already mounted page once each', () => {
    const receive = vi.fn();
    const { rerender } = renderHook(() => useHandoff('task', true, receive));
    act(() => {
      handOff('owner', { kind: 'task', title: 'First', notes: '' });
    });
    rerender();
    expect(receive).toHaveBeenCalledTimes(1);
    act(() => {
      handOff('owner', { kind: 'task', title: 'Second', notes: '' });
    });
    expect(receive).toHaveBeenCalledTimes(2);
    expect(receive.mock.calls[1][0].title).toBe('Second');
  });
  it('waits for availability and protects a form until it closes', () => {
    const receive = vi.fn();
    const { rerender } = renderHook(({ ready, busy }) => useHandoff('task', ready, receive, busy), {
      initialProps: { ready: false, busy: false },
    });
    act(() => {
      handOff('owner', { kind: 'task', title: 'Waiting', notes: '' });
    });
    expect(receive).not.toHaveBeenCalled();
    rerender({ ready: true, busy: true });
    expect(receive).not.toHaveBeenCalled();
    expect(info).toHaveBeenCalledOnce();
    expect(handoffStore.getSnapshot()).not.toBeNull();
    rerender({ ready: true, busy: false });
    expect(receive).toHaveBeenCalledOnce();
    expect(handoffStore.getSnapshot()).toBeNull();
  });
  it('purges at auth transition, and old A-B-A navigation callbacks cannot publish', () => {
    const { result, rerender } = renderHook(() => {
      useHandoffOwner(account.id);
      return useHandoffNavigation('fr');
    });
    const old = result.current;
    act(() => old({ kind: 'memory', memory: { content: 'Private words', category: 'personal' } }));
    expect(push).toHaveBeenCalledWith('/fr/dashboard/settings?section=memories');
    expect(push.mock.calls.flat().join('')).not.toContain('Private');
    account.id = 'other';
    rerender();
    expect(handoffStore.getSnapshot()).toBeNull();
    account.id = 'owner';
    rerender();
    act(() => old({ kind: 'task', title: 'Late private result', notes: '' }));
    expect(push).toHaveBeenCalledOnce();
    expect(handoffStore.getSnapshot()).toBeNull();
  });
});
