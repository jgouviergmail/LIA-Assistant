/**
 * useRoutineWebhookSecret — the one door that draws a routine's new secret
 * (ADR-386): its own route, its answer handed to the caller, nothing kept.
 */

import { describe, expect, it, vi } from 'vitest';

import { mutateSpy, mutationResult } from '@/__tests__/api-mocks';
import { act, renderHook } from '@/__tests__/test-utils';

const { useApiMutation } = vi.hoisted(() => ({ useApiMutation: vi.fn() }));
vi.mock('@/hooks/useApiMutation', () => ({ useApiMutation }));

import { useRoutineWebhookSecret } from '../useRoutineWebhookSecret';

describe('useRoutineWebhookSecret', () => {
  it('draws a new secret through its own route and hands the answer back', async () => {
    const mutate = mutateSpy();
    mutate.mockResolvedValue({ webhook_url: 'https://x/k', webhook_secret: 'n3w' });
    useApiMutation.mockReturnValue(mutationResult({ mutate }));
    const { result } = renderHook(() => useRoutineWebhookSecret());

    let drawn: unknown;
    await act(async () => {
      drawn = await result.current.drawWebhookSecret('a1');
    });

    expect(useApiMutation).toHaveBeenCalledWith(expect.objectContaining({ method: 'POST' }));
    expect(mutate).toHaveBeenCalledWith('/scheduled-actions/a1/webhook-secret');
    expect(drawn).toEqual({ webhook_url: 'https://x/k', webhook_secret: 'n3w' });
  });

  it('says when a secret is being drawn', () => {
    useApiMutation.mockReturnValue(mutationResult({ mutate: mutateSpy(), loading: true }));
    const { result } = renderHook(() => useRoutineWebhookSecret());

    expect(result.current.drawingSecret).toBe(true);
  });
});
