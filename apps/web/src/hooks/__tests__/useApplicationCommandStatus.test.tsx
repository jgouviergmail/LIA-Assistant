import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '@/lib/api-client';

const { get, useAuth } = vi.hoisted(() => ({ get: vi.fn(), useAuth: vi.fn() }));
vi.mock('@/hooks/useAuth', () => ({ useAuth }));
vi.mock('@/lib/api-client', async importOriginal => {
  const actual = await importOriginal<typeof import('@/lib/api-client')>();
  const client = { get };
  return { ...actual, apiClient: client, default: client };
});
import { useApplicationCommandStatus } from '../useApplicationCommandStatus';

const first = '00000000-0000-4000-8000-000000000001';
const second = '00000000-0000-4000-8000-000000000002';
const status = {
  schema_version: 1,
  command_id: first,
  operation_id: 'preferences.update',
  phase: 'waiting',
  expires_at: '2026-12-01T10:00:00Z',
  interaction: { interaction_id: first, kind: 'secure', expires_at: '2026-12-01T10:00:00Z' },
  outcome: {
    success: false,
    phase: 'waiting',
    committed: false,
    no_op: false,
    values: {},
    error_code: null,
    interaction: { interaction_id: first, kind: 'secure', expires_at: '2026-12-01T10:00:00Z' },
  },
};
beforeEach(() => {
  vi.resetAllMocks();
  useAuth.mockReturnValue({ user: { id: 'owner' } });
  get.mockResolvedValue(status);
});

describe('transport-bound command observation', () => {
  it('never sends a malformed command path to the server', async () => {
    const { result } = renderHook(() => useApplicationCommandStatus('../auth/step-up/password'));
    await act(async () => {});
    expect(get).not.toHaveBeenCalled();
    expect(result.current.status).toBeNull();
  });

  it('refuses a response identifying another command and preserves the accepted one', async () => {
    const { result } = renderHook(() => useApplicationCommandStatus(first));
    await waitFor(() => expect(result.current.status?.command_id).toBe(first));
    get.mockResolvedValueOnce({ ...status, command_id: second });
    await act(async () => {
      await result.current.refresh();
    });
    expect(result.current.status?.command_id).toBe(first);
    expect(result.current.error).toBeTruthy();
  });

  it('reads a validated status without sending credentials or an actor selector', async () => {
    const { result } = renderHook(() => useApplicationCommandStatus(first));
    await waitFor(() => expect(result.current.status?.command_id).toBe(first));
    expect(get).toHaveBeenCalledWith(`/application-commands/${first}`, expect.any(Object));
    expect(JSON.stringify(get.mock.calls)).not.toContain('owner');
  });

  it('retains the current card on a transient failure or malformed response', async () => {
    const { result } = renderHook(() => useApplicationCommandStatus(first));
    await waitFor(() => expect(result.current.status?.command_id).toBe(first));
    get.mockRejectedValueOnce(new ApiError('unavailable', 503));
    await act(async () => {
      await result.current.refresh();
    });
    expect(result.current.status).toEqual(status);
    get.mockResolvedValueOnce({ ...status, outcome: { ...status.outcome, committed: true } });
    await act(async () => {
      await result.current.refresh();
    });
    expect(result.current.status).toEqual(status);
    expect(result.current.error).toBeTruthy();
  });

  it('withdraws cached data on authoritative denial and keeps it hidden during retry', async () => {
    const { result } = renderHook(() => useApplicationCommandStatus(first));
    await waitFor(() => expect(result.current.status?.command_id).toBe(first));
    get.mockRejectedValueOnce(new ApiError('forbidden', 403));
    await act(async () => {
      await result.current.refresh();
    });
    expect(result.current.status).toBeNull();
    get.mockImplementationOnce(() => new Promise(() => {}));
    act(() => {
      void result.current.refresh();
    });
    await waitFor(() => expect(get).toHaveBeenCalledTimes(3));
    expect(result.current.status).toBeNull();
  });

  it('hides previous command state and refuses obsolete refresh after A-B-A', async () => {
    const { result, rerender } = renderHook(({ id }) => useApplicationCommandStatus(id), {
      initialProps: { id: first },
    });
    await waitFor(() => expect(result.current.status?.command_id).toBe(first));
    const old = result.current.refresh;
    get.mockResolvedValueOnce({
      ...status,
      command_id: second,
      phase: 'pending',
      interaction: null,
      outcome: null,
    });
    rerender({ id: second });
    expect(result.current.status).toBeNull();
    await waitFor(() => expect(result.current.status?.command_id).toBe(second));
    rerender({ id: first });
    await waitFor(() => expect(result.current.status?.command_id).toBe(first));
    await act(async () => {
      await old();
    });
    expect(get).toHaveBeenCalledTimes(3);
  });

  it('cannot revive a previous-account response after account return', async () => {
    let finish: ((value: unknown) => void) | undefined;
    get.mockImplementationOnce(
      () =>
        new Promise(done => {
          finish = done;
        })
    );
    const { result, rerender } = renderHook(() => useApplicationCommandStatus(first));
    await waitFor(() => expect(get).toHaveBeenCalledTimes(1));
    useAuth.mockReturnValue({ user: { id: 'other' } });
    rerender();
    await waitFor(() => expect(get).toHaveBeenCalledTimes(2));
    useAuth.mockReturnValue({ user: { id: 'owner' } });
    rerender();
    await waitFor(() => expect(get).toHaveBeenCalledTimes(3));
    await act(async () => {
      finish?.({ ...status, phase: 'cancelled', outcome: null, interaction: null });
    });
    expect(result.current.status?.phase).toBe('waiting');
  });
});
