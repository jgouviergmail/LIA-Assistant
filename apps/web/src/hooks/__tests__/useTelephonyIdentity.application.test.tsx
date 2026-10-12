import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { publishApplicationResources } from '@/lib/application-resources';
import type { TelephonyIdentity } from '@/types/telephony';

const { get, patch, post, put, useAuth } = vi.hoisted(() => ({
  get: vi.fn(),
  patch: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  useAuth: vi.fn(),
}));
vi.mock('@/hooks/useAuth', () => ({ useAuth }));
vi.mock('@/lib/api-client', async importOriginal => {
  const original = await importOriginal<typeof import('@/lib/api-client')>();
  const client = { get, patch, post, put };
  return { ...original, apiClient: client, default: client };
});
import { useTelephonyIdentity } from '../useTelephonyIdentity';

const saved: TelephonyIdentity = {
  phone_number: '+33612345678',
  verified: false,
  verified_at: null,
  rich_context_enabled: true,
  verification_pending: false,
  disabled_domains: ['email'],
  available_domains: ['email', 'event'],
  call_mode: 'delegated',
  call_mode_effective: 'direct',
  live_available: false,
  live_unavailable_reason: 'callback_not_public',
};
beforeEach(() => {
  vi.resetAllMocks();
  useAuth.mockReturnValue({ user: { id: 'one' } });
  get.mockResolvedValue(saved);
});

describe('phone identity synchronization and account lifetime', () => {
  it('orders a confirmed number reread after an in-flight manual number save', async () => {
    let complete: ((value: TelephonyIdentity) => void) | undefined;
    put.mockImplementationOnce(
      () =>
        new Promise<TelephonyIdentity>(done => {
          complete = done;
        })
    );
    const { result } = renderHook(() => useTelephonyIdentity());
    await waitFor(() => expect(result.current.identity).toEqual(saved));
    let saving: Promise<string | null>;
    act(() => {
      saving = result.current.setNumber('+33698765432');
    });
    await waitFor(() => expect(put).toHaveBeenCalledTimes(1));
    get.mockResolvedValueOnce({ ...saved, phone_number: null, verification_pending: false });
    act(() => publishApplicationResources('one', new Set(['phone_identity'])));
    expect(get).toHaveBeenCalledTimes(1);
    await act(async () => {
      complete?.({ ...saved, phone_number: '+33698765432' });
      await saving;
    });
    await waitFor(() => expect(result.current.identity?.phone_number).toBeNull());
    expect(result.current.isBusy).toBe(false);
  });

  it('refuses an old number-setting callback after returning to the same account', async () => {
    const { result, rerender } = renderHook(() => useTelephonyIdentity());
    await waitFor(() => expect(result.current.identity).toEqual(saved));
    const old = result.current.setNumber;
    useAuth.mockReturnValue({ user: { id: 'two' } });
    rerender();
    await waitFor(() => expect(get).toHaveBeenCalledTimes(2));
    useAuth.mockReturnValue({ user: { id: 'one' } });
    rerender();
    await waitFor(() => expect(get).toHaveBeenCalledTimes(3));
    await act(async () => {
      await old('+33698765432');
    });
    expect(put).not.toHaveBeenCalled();
  });

  it('rereads an addressed confirmed change without calling or mutating', async () => {
    const { result } = renderHook(() => useTelephonyIdentity());
    await waitFor(() => expect(result.current.identity).toEqual(saved));
    act(() => publishApplicationResources('two', new Set(['phone_identity'])));
    expect(get).toHaveBeenCalledTimes(1);
    get.mockResolvedValueOnce({ ...saved, rich_context_enabled: false });
    act(() => publishApplicationResources('one', new Set(['phone_identity'])));
    await waitFor(() => expect(result.current.identity?.rich_context_enabled).toBe(false));
    expect(patch).not.toHaveBeenCalled();
    expect(post).not.toHaveBeenCalled();
  });

  it('hides previous-account identity until a fresh response returns', async () => {
    const { result, rerender } = renderHook(() => useTelephonyIdentity());
    await waitFor(() => expect(result.current.identity).toEqual(saved));
    get.mockImplementationOnce(() => new Promise(() => {}));
    useAuth.mockReturnValue({ user: { id: 'two' } });
    rerender();
    expect(result.current.identity).toBeNull();
    await waitFor(() => expect(get).toHaveBeenCalledTimes(2));
  });

  it('refuses an obsolete action after A-to-B-to-A before HTTP', async () => {
    const { result, rerender } = renderHook(() => useTelephonyIdentity());
    await waitFor(() => expect(result.current.identity).toEqual(saved));
    const obsolete = result.current.setRichContext;
    useAuth.mockReturnValue({ user: { id: 'two' } });
    rerender();
    await waitFor(() => expect(get).toHaveBeenCalledTimes(2));
    useAuth.mockReturnValue({ user: { id: 'one' } });
    rerender();
    await waitFor(() => expect(get).toHaveBeenCalledTimes(3));
    await act(async () => {
      await obsolete(false);
    });
    expect(patch).not.toHaveBeenCalled();
  });

  it('does not apply a previous-account verification expiry after a late response', async () => {
    let complete: ((value: { expires_in_seconds: number }) => void) | undefined;
    post.mockImplementationOnce(
      () =>
        new Promise(done => {
          complete = done;
        })
    );
    const { result, rerender } = renderHook(() => useTelephonyIdentity());
    await waitFor(() => expect(result.current.identity).toEqual(saved));
    let writing: Promise<string | null> | undefined;
    act(() => {
      writing = result.current.startVerification();
    });
    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    useAuth.mockReturnValue({ user: { id: 'two' } });
    rerender();
    await waitFor(() => expect(get).toHaveBeenCalledTimes(2));
    await act(async () => {
      complete?.({ expires_in_seconds: 600 });
      await writing;
    });
    expect(result.current.codeExpiresInSeconds).toBeNull();
    expect(result.current.isBusy).toBe(false);
    expect(result.current.identity).toEqual(saved);
  });

  it('preserves the last verified identity on an unsuccessful native reread', async () => {
    const { result } = renderHook(() => useTelephonyIdentity());
    await waitFor(() => expect(result.current.identity).toEqual(saved));
    get.mockRejectedValueOnce(new Error('offline'));
    act(() => publishApplicationResources('one', new Set(['phone_identity'])));
    await waitFor(() => expect(get).toHaveBeenCalledTimes(2));
    expect(result.current.identity).toEqual(saved);
  });

  it('keeps the mounted form visible throughout a native reread', async () => {
    const { result } = renderHook(() => useTelephonyIdentity());
    await waitFor(() => expect(result.current.identity).toEqual(saved));
    get.mockImplementationOnce(() => new Promise(() => {}));
    act(() => publishApplicationResources('one', new Set(['phone_identity'])));
    await waitFor(() => expect(get).toHaveBeenCalledTimes(2));
    expect(result.current.isLoading).toBe(false);
    expect(result.current.identity).toEqual(saved);
  });

  it('orders a manual write after an already running native reread', async () => {
    let finishRead: ((value: TelephonyIdentity) => void) | undefined;
    get
      .mockImplementationOnce(async () => saved)
      .mockImplementationOnce(
        () =>
          new Promise<TelephonyIdentity>(done => {
            finishRead = done;
          })
      );
    patch.mockResolvedValue({ ...saved, rich_context_enabled: false });
    const { result } = renderHook(() => useTelephonyIdentity());
    await waitFor(() => expect(result.current.identity).toEqual(saved));
    act(() => publishApplicationResources('one', new Set(['phone_identity'])));
    await waitFor(() => expect(get).toHaveBeenCalledTimes(2));
    let writing: Promise<string | null> | undefined;
    act(() => {
      writing = result.current.setRichContext(false);
    });
    await act(async () => {
      await Promise.resolve();
    });
    expect(patch).not.toHaveBeenCalled();
    await act(async () => {
      finishRead?.(saved);
      await writing;
    });
    expect(result.current.identity?.rich_context_enabled).toBe(false);
    expect(result.current.isBusy).toBe(false);
  });

  it('waits for a pending manual action before native reconciliation', async () => {
    let finishWrite: ((value: TelephonyIdentity) => void) | undefined;
    patch.mockImplementationOnce(
      () =>
        new Promise<TelephonyIdentity>(done => {
          finishWrite = done;
        })
    );
    const { result } = renderHook(() => useTelephonyIdentity());
    await waitFor(() => expect(result.current.identity).toEqual(saved));
    let writing: Promise<string | null> | undefined;
    act(() => {
      writing = result.current.setRichContext(false);
    });
    await waitFor(() => expect(patch).toHaveBeenCalledTimes(1));
    act(() => publishApplicationResources('one', new Set(['phone_identity'])));
    await act(async () => {
      await Promise.resolve();
    });
    expect(get).toHaveBeenCalledTimes(1);
    get.mockResolvedValue({ ...saved, rich_context_enabled: false });
    await act(async () => {
      finishWrite?.({ ...saved, rich_context_enabled: false });
      await writing;
    });
    await waitFor(() => expect(result.current.identity?.rich_context_enabled).toBe(false));
    await waitFor(() => expect(result.current.isBusy).toBe(false));
    expect(get).toHaveBeenCalledTimes(2);
  });
});
