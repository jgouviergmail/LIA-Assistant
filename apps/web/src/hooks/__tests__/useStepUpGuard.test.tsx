/**
 * useStepUpGuard — the replay contract: a step-up 403 parks the action and
 * replays it exactly once after verification; cancellation rejects; other
 * errors pass through untouched.
 */

import { describe, it, expect, vi } from 'vitest';
import { act, renderHook, waitFor } from '@testing-library/react';

import { ApiStepUpError } from '@/lib/api-client';
import { useStepUpGuard } from '../useStepUpGuard';

describe('useStepUpGuard', () => {
  it('passes through a successful action without opening the dialog', async () => {
    const { result } = renderHook(() => useStepUpGuard());
    const action = vi.fn().mockResolvedValue('ok');

    const value = await result.current.guard(action);

    expect(value).toBe('ok');
    expect(action).toHaveBeenCalledTimes(1);
    expect(result.current.stepUpOpen).toBe(false);
  });

  it('parks a step-up 403, then replays once after verification', async () => {
    const { result } = renderHook(() => useStepUpGuard());
    const action = vi
      .fn()
      .mockRejectedValueOnce(new ApiStepUpError())
      .mockResolvedValueOnce('replayed');

    let promise: Promise<string>;
    act(() => {
      promise = result.current.guard(action);
    });

    await waitFor(() => expect(result.current.stepUpOpen).toBe(true));
    act(() => result.current.onVerified());

    await expect(promise!).resolves.toBe('replayed');
    expect(action).toHaveBeenCalledTimes(2);
    expect(result.current.stepUpOpen).toBe(false);
  });

  it('rejects the parked action when the user cancels', async () => {
    const { result } = renderHook(() => useStepUpGuard());
    const action = vi.fn().mockRejectedValue(new ApiStepUpError());

    let promise: Promise<unknown>;
    act(() => {
      promise = result.current.guard(action).catch(e => e);
    });

    await waitFor(() => expect(result.current.stepUpOpen).toBe(true));
    act(() => result.current.onCancel());

    await expect(promise!).resolves.toBeInstanceOf(ApiStepUpError);
    expect(action).toHaveBeenCalledTimes(1);
  });

  it('re-throws non-step-up errors untouched', async () => {
    const { result } = renderHook(() => useStepUpGuard());
    const boom = new Error('500');
    const action = vi.fn().mockRejectedValue(boom);

    await expect(result.current.guard(action)).rejects.toBe(boom);
    expect(result.current.stepUpOpen).toBe(false);
  });
});
