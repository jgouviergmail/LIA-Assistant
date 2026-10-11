import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { LivePreferences } from '@/lib/live/types';
import { publishApplicationResources } from '@/lib/application-resources';

const { get, put, useAuth } = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn(), useAuth: vi.fn() }));
vi.mock('@/hooks/useAuth', () => ({ useAuth }));
vi.mock('@/lib/api-client', async importOriginal => {
  const original = await importOriginal<typeof import('@/lib/api-client')>();
  return { ...original, default: { get, put } };
});
import { useLivePreferences } from '../useLivePreferences';

const saved: LivePreferences = {
  interruptions: true, end_of_speech: 'normal', result_delivery: 'when_idle',
};
beforeEach(() => {
  vi.resetAllMocks();
  useAuth.mockReturnValue({ user: { id: 'one' } });
  get.mockResolvedValue(saved);
});

describe('live reflex account lifetime and full replacement writes', () => {
  it('serializes rapid writes and includes both changes in the second replacement', async () => {
    let complete: ((value: LivePreferences) => void) | undefined;
    put.mockImplementationOnce(() => new Promise<LivePreferences>(done => { complete = done; }))
      .mockImplementationOnce(async (_path: string, values: LivePreferences) => values);
    const { result } = renderHook(() => useLivePreferences());
    await waitFor(() => expect(result.current.preferences).toEqual(saved));
    let first: Promise<boolean> | undefined;
    let second: Promise<boolean> | undefined;
    act(() => {
      first = result.current.save({ interruptions: false });
      second = result.current.save({ end_of_speech: 'calm' });
    });
    await waitFor(() => expect(put).toHaveBeenCalledTimes(1));
    expect(result.current.preferences).toEqual({ ...saved, interruptions: false, end_of_speech: 'calm' });
    get.mockResolvedValue({ ...saved, interruptions: false, end_of_speech: 'calm' });
    await act(async () => { complete?.({ ...saved, interruptions: false }); await first; await second; });
    expect(put.mock.calls[1][1]).toEqual({ ...saved, interruptions: false, end_of_speech: 'calm' });
    expect(result.current.preferences).toEqual({ ...saved, interruptions: false, end_of_speech: 'calm' });
  });

  it('refuses an obsolete callback before sending a write after A-to-B-to-A', async () => {
    const { result, rerender } = renderHook(() => useLivePreferences());
    await waitFor(() => expect(result.current.preferences).toEqual(saved));
    const obsolete = result.current.save;
    useAuth.mockReturnValue({ user: { id: 'two' } });
    rerender();
    await waitFor(() => expect(result.current.preferences).toEqual(saved));
    useAuth.mockReturnValue({ user: { id: 'one' } });
    rerender();
    await waitFor(() => expect(result.current.preferences).toEqual(saved));
    await act(async () => { expect(await obsolete({ interruptions: false })).toBe(false); });
    expect(put).not.toHaveBeenCalled();
  });

  it('rereads an addressed native change without writing or affecting another account', async () => {
    const { result } = renderHook(() => useLivePreferences());
    await waitFor(() => expect(result.current.preferences).toEqual(saved));
    act(() => publishApplicationResources('two', new Set(['live_preferences'])));
    expect(get).toHaveBeenCalledTimes(1);
    get.mockResolvedValueOnce({ ...saved, result_delivery: 'interrupt' });
    act(() => publishApplicationResources('one', new Set(['live_preferences'])));
    await waitFor(() => expect(result.current.preferences?.result_delivery).toBe('interrupt'));
    expect(put).not.toHaveBeenCalled();
  });

  it('keeps the last known settings on a failed native reread', async () => {
    const { result } = renderHook(() => useLivePreferences());
    await waitFor(() => expect(result.current.preferences).toEqual(saved));
    get.mockRejectedValueOnce(new Error('offline'));
    act(() => publishApplicationResources('one', new Set(['live_preferences'])));
    await waitFor(() => expect(result.current.loadError).toBe(true));
    expect(result.current.preferences).toEqual(saved);
  });

  it('does not publish a late successful write into a new account', async () => {
    let complete: ((value: LivePreferences) => void) | undefined;
    put.mockImplementationOnce(() => new Promise<LivePreferences>(done => { complete = done; }));
    const { result, rerender } = renderHook(() => useLivePreferences());
    await waitFor(() => expect(result.current.preferences).toEqual(saved));
    let writing: Promise<boolean> | undefined;
    act(() => { writing = result.current.save({ interruptions: false }); });
    await waitFor(() => expect(put).toHaveBeenCalledTimes(1));
    useAuth.mockReturnValue({ user: { id: 'two' } });
    get.mockResolvedValueOnce({ ...saved, end_of_speech: 'lively' });
    rerender();
    await waitFor(() => expect(result.current.preferences?.end_of_speech).toBe('lively'));
    await act(async () => { complete?.({ ...saved, interruptions: false }); expect(await writing).toBe(false); });
    expect(result.current.preferences).toEqual({ ...saved, end_of_speech: 'lively' });
    expect(get).toHaveBeenCalledTimes(2);
  });

  it('settles a refused optimistic save back to the canonical server values', async () => {
    put.mockRejectedValueOnce(new Error('refused'));
    const { result } = renderHook(() => useLivePreferences());
    await waitFor(() => expect(result.current.preferences).toEqual(saved));
    await act(async () => { expect(await result.current.save({ interruptions: false })).toBe(false); });
    await waitFor(() => expect(result.current.preferences).toEqual(saved));
    expect(result.current.saving).toBe(false);
  });

  it('never retains an unsaved optimistic value when both write and reread fail', async () => {
    const { result } = renderHook(() => useLivePreferences());
    await waitFor(() => expect(result.current.preferences).toEqual(saved));
    put.mockRejectedValueOnce(new Error('offline'));
    get.mockRejectedValueOnce(new Error('still offline'));
    await act(async () => { expect(await result.current.save({ interruptions: false })).toBe(false); });
    await waitFor(() => expect(result.current.loadError).toBe(true));
    expect(result.current.preferences).toEqual(saved);
  });
});
