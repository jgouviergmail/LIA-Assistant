import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { UseMeetingReturn } from '@/hooks/useMeetings';
import { useMeetingActions } from '../useMeetingActions';

const { auth, success, error } = vi.hoisted(() => ({ auth: { owner: 'one' }, success: vi.fn(), error: vi.fn() }));
vi.mock('@/hooks/useAuth', () => ({ useAuth: () => ({ user: { id: auth.owner } }) }));
vi.mock('sonner', () => ({ toast: { success, error } }));
function state(): UseMeetingReturn {
  return { meeting: null, isLoading: false, isNotFound: false, isActing: false, error: null, refetch: vi.fn(), patch: vi.fn(), resetReport: vi.fn(), regenerate: vi.fn(), reformat: vi.fn(), retry: vi.fn(), email: vi.fn(), deleteTranscript: vi.fn(), remove: vi.fn() };
}
function deps() { return { t: (key: string) => key, confirm: vi.fn().mockResolvedValue(true), navigateToList: vi.fn(), navigateToMeeting: vi.fn(), setDraft: vi.fn(), setShowTranscript: vi.fn() }; }
beforeEach(() => { vi.clearAllMocks(); auth.owner = 'one'; });

describe('meeting action feedback ownership', () => {
  it('does not announce a successful email when the write was refused locally', async () => {
    const source = state();
    vi.mocked(source.email).mockResolvedValue(null);
    const { result } = renderHook(() => useMeetingActions(source, deps()));
    await act(async () => result.current.email());
    expect(success).not.toHaveBeenCalled();
  });

  it('suppresses a late failure after changing account', async () => {
    const pending = Promise.withResolvers<never>();
    const source = state();
    vi.mocked(source.retry).mockReturnValue(pending.promise);
    const options = deps();
    const { result, rerender } = renderHook(() => useMeetingActions(source, options));
    let running: Promise<void> | undefined;
    act(() => { running = result.current.retry(); });
    auth.owner = 'two'; rerender();
    await act(async () => { pending.reject(new Error('old private failure')); await running; });
    expect(error).not.toHaveBeenCalled();
  });

  it('refuses confirmation resumed after its account has left', async () => {
    const pending = Promise.withResolvers<boolean>();
    const source = state();
    const options = deps(); options.confirm.mockReturnValue(pending.promise);
    const { result, rerender } = renderHook(() => useMeetingActions(source, options));
    let running: Promise<void> | undefined;
    act(() => { running = result.current.deleteTranscript(); });
    auth.owner = 'two'; rerender();
    await act(async () => { pending.resolve(true); await running; });
    expect(source.deleteTranscript).not.toHaveBeenCalled();
    expect(options.setShowTranscript).not.toHaveBeenCalled();
  });
});
