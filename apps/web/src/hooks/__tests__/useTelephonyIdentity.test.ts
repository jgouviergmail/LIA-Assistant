/**
 * The person's own phone number — declared, verified by a call (lot 1/2/5).
 *
 * What the hook must guarantee: one read on mount, a 404 that silences it for
 * good (feature off), every action re-reading the identity it returns, and a
 * refusal that reaches the caller as the backend's own translated sentence
 * rather than a generic failure.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, renderHook, waitFor } from '@testing-library/react';

import { ApiError } from '@/lib/api-client';

const { apiClient } = vi.hoisted(() => ({
  apiClient: {
    get: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
  },
}));

vi.mock('@/lib/api-client', async importOriginal => {
  const actual = await importOriginal<typeof import('@/lib/api-client')>();
  return { ...actual, apiClient };
});

import { useTelephonyIdentity } from '../useTelephonyIdentity';

const identity = {
  phone_number: '+33612345678',
  verified: false,
  verified_at: null,
  rich_context_enabled: true,
  verification_pending: false,
};

describe('useTelephonyIdentity', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('reads the identity once on mount', async () => {
    apiClient.get.mockResolvedValueOnce(identity);
    const { result } = renderHook(() => useTelephonyIdentity());
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(apiClient.get).toHaveBeenCalledWith('/telephony/identity');
    expect(result.current.identity?.phone_number).toBe('+33612345678');
    expect(result.current.isUnavailable).toBe(false);
  });

  it('a 404 means the feature is off and stays off', async () => {
    apiClient.get.mockRejectedValueOnce(new ApiError('nope', 404));
    const { result } = renderHook(() => useTelephonyIdentity());
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.isUnavailable).toBe(true);
    expect(result.current.identity).toBeNull();
  });

  it('declaring the number stores what the server normalised', async () => {
    apiClient.get.mockResolvedValueOnce(identity);
    apiClient.put.mockResolvedValueOnce({ ...identity, phone_number: '+33698765432' });
    const { result } = renderHook(() => useTelephonyIdentity());
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await act(async () => {
      await result.current.setNumber('06 98 76 54 32');
    });

    expect(apiClient.put).toHaveBeenCalledWith('/telephony/identity/number', {
      phone_number: '06 98 76 54 32',
    });
    expect(result.current.identity?.phone_number).toBe('+33698765432');
  });

  it('a refusal surfaces the backend sentence and leaves the identity as it was', async () => {
    apiClient.get.mockResolvedValueOnce(identity);
    apiClient.put.mockRejectedValueOnce(
      new ApiError('Ce numéro n’est pas un numéro de téléphone valide.', 400)
    );
    const { result } = renderHook(() => useTelephonyIdentity());
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    let message: string | null = null;
    await act(async () => {
      message = await result.current.setNumber('Marie');
    });

    expect(message).toBe('Ce numéro n’est pas un numéro de téléphone valide.');
    expect(result.current.identity?.phone_number).toBe('+33612345678');
  });

  it('a conflict re-reads the identity so the page reflects what the server holds', async () => {
    // The code expired (or the number changed) while the code form was open:
    // the 409 sentence is shown AND the pending state is re-read, so the form
    // stops asking for a code nobody can type.
    apiClient.get.mockResolvedValueOnce({ ...identity, verification_pending: true });
    apiClient.post.mockRejectedValueOnce(new ApiError('Aucune vérification n’est en cours.', 409));
    apiClient.get.mockResolvedValueOnce({ ...identity, verification_pending: false });
    const { result } = renderHook(() => useTelephonyIdentity());
    await waitFor(() => expect(result.current.identity?.verification_pending).toBe(true));

    let message: string | null = null;
    await act(async () => {
      message = await result.current.confirmCode('4719');
    });

    expect(message).toBe('Aucune vérification n’est en cours.');
    expect(apiClient.get).toHaveBeenCalledTimes(2);
    expect(result.current.identity?.verification_pending).toBe(false);
  });

  it('starting a verification reports the pending state and the code lifetime', async () => {
    apiClient.get
      .mockResolvedValueOnce(identity)
      .mockResolvedValueOnce({ ...identity, verification_pending: true });
    apiClient.post.mockResolvedValueOnce({ call_id: 'c1', expires_in_seconds: 600 });
    const { result } = renderHook(() => useTelephonyIdentity());
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await act(async () => {
      await result.current.startVerification();
    });

    expect(apiClient.post).toHaveBeenCalledWith('/telephony/identity/verify');
    expect(result.current.identity?.verification_pending).toBe(true);
    expect(result.current.codeExpiresInSeconds).toBe(600);
  });

  it('confirming the code marks the number verified', async () => {
    apiClient.get.mockResolvedValueOnce({ ...identity, verification_pending: true });
    apiClient.post.mockResolvedValueOnce({
      ...identity,
      verified: true,
      verified_at: '2026-09-16T10:00:00Z',
    });
    const { result } = renderHook(() => useTelephonyIdentity());
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await act(async () => {
      await result.current.confirmCode('4719');
    });

    expect(apiClient.post).toHaveBeenCalledWith('/telephony/identity/confirm', { code: '4719' });
    expect(result.current.identity?.verified).toBe(true);
  });

  it('the context switch is persisted', async () => {
    apiClient.get.mockResolvedValueOnce(identity);
    apiClient.patch.mockResolvedValueOnce({ ...identity, rich_context_enabled: false });
    const { result } = renderHook(() => useTelephonyIdentity());
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await act(async () => {
      await result.current.setRichContext(false);
    });

    expect(apiClient.patch).toHaveBeenCalledWith('/telephony/identity', {
      rich_context_enabled: false,
    });
    expect(result.current.identity?.rich_context_enabled).toBe(false);
  });

  it('clearing the number re-reads an empty identity', async () => {
    apiClient.get
      .mockResolvedValueOnce(identity)
      .mockResolvedValueOnce({ ...identity, phone_number: null, verified: false });
    apiClient.delete.mockResolvedValueOnce(undefined);
    const { result } = renderHook(() => useTelephonyIdentity());
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await act(async () => {
      await result.current.clearNumber();
    });

    expect(apiClient.delete).toHaveBeenCalledWith('/telephony/identity/number');
    expect(result.current.identity?.phone_number).toBeNull();
  });
});
