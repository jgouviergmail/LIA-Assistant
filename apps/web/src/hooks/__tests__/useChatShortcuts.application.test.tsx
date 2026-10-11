import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { publishApplicationResources } from '@/lib/application-resources';

const { get, put, useAuth } = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn(), useAuth: vi.fn() }));
vi.mock('@/hooks/useAuth', () => ({ useAuth }));
vi.mock('@/lib/api-client', async importOriginal => {
  const original = await importOriginal<typeof import('@/lib/api-client')>();
  return { ...original, default: { get, put } };
});
import { useChatShortcuts } from '../useChatShortcuts';

const original = [{ id: 'original', text: 'Original prompt' }];
const proposed = [{ id: 'proposed', text: 'Proposed prompt' }];
const native = [{ id: 'native', text: 'Native prompt' }];

beforeEach(() => {
  vi.resetAllMocks();
  useAuth.mockReturnValue({ user: { id: 'one' } });
});

describe('layout writes and assistant invalidations', () => {
  it('rereads a returning account without reviving its old preview or save callback', async () => {
    get.mockResolvedValueOnce({ shortcuts: original, max_count: 5 })
      .mockResolvedValueOnce({ shortcuts: native, max_count: 5 })
      .mockResolvedValue({ shortcuts: native, max_count: 5 });
    let finishOld: (() => void) | undefined;
    put.mockImplementationOnce(() => new Promise<void>(resolve => { finishOld = resolve; }));
    const { result, rerender } = renderHook(() => useChatShortcuts());
    await waitFor(() => expect(result.current.shortcuts).toEqual(original));
    const oldSave = result.current.save;
    let oldWrite: Promise<boolean> | undefined;
    act(() => { oldWrite = oldSave(proposed); });
    useAuth.mockReturnValue({ user: { id: 'two' } });
    rerender();
    await waitFor(() => expect(result.current.shortcuts).toEqual(native));
    await act(async () => { finishOld?.(); expect(await oldWrite).toBe(true); });

    useAuth.mockReturnValue({ user: { id: 'one' } });
    rerender();
    await waitFor(() => expect(get).toHaveBeenCalledTimes(3));
    await waitFor(() => expect(result.current.shortcuts).toEqual(native));
    await act(async () => { expect(await oldSave(original)).toBe(false); });
    expect(put).toHaveBeenCalledTimes(1);
  });

  it('preserves the new account edit when the previous account write fails late', async () => {
    get.mockResolvedValueOnce({ shortcuts: original, max_count: 5 })
      .mockResolvedValueOnce({ shortcuts: native, max_count: 5 })
      .mockResolvedValue({ shortcuts: proposed, max_count: 5 });
    let failOld: ((error: Error) => void) | undefined;
    let finishNew: (() => void) | undefined;
    put.mockImplementationOnce(() => new Promise<void>((_resolve, reject) => { failOld = reject; }))
      .mockImplementationOnce(() => new Promise<void>(resolve => { finishNew = resolve; }));
    const { result, rerender } = renderHook(() => useChatShortcuts());
    await waitFor(() => expect(result.current.shortcuts).toEqual(original));
    const oldSave = result.current.save;
    let oldWrite: Promise<boolean> | undefined;
    act(() => { oldWrite = oldSave(proposed); });

    useAuth.mockReturnValue({ user: { id: 'two' } });
    rerender();
    await waitFor(() => expect(result.current.shortcuts).toEqual(native));
    let newWrite: Promise<boolean> | undefined;
    act(() => { newWrite = result.current.save(proposed); });
    expect(result.current.shortcuts).toEqual(proposed);

    await act(async () => { failOld?.(new Error('old request failed')); expect(await oldWrite).toBe(false); });
    expect(result.current.shortcuts).toEqual(proposed);
    await act(async () => { expect(await oldSave(original)).toBe(false); });
    expect(put).toHaveBeenCalledTimes(2);

    await act(async () => { finishNew?.(); expect(await newWrite).toBe(true); });
    await waitFor(() => expect(get).toHaveBeenCalledTimes(3));
    expect(result.current.shortcuts).toEqual(proposed);
  });

  it('keeps the pending UI edit through an invalidation, then rereads after its commit', async () => {
    get.mockResolvedValueOnce({ shortcuts: original, max_count: 5 })
      .mockResolvedValueOnce({ shortcuts: native, max_count: 5 })
      .mockResolvedValue({ shortcuts: proposed, max_count: 5 });
    let complete: (() => void) | undefined;
    put.mockImplementationOnce(() => new Promise<void>(done => { complete = done; }));
    const { result } = renderHook(() => useChatShortcuts());
    await waitFor(() => expect(result.current.shortcuts).toEqual(original));
    let saved: Promise<boolean> | undefined;
    act(() => { saved = result.current.save(proposed); });
    expect(result.current.shortcuts).toEqual(proposed);
    act(() => { publishApplicationResources('one', new Set(['chat_shortcuts'])); });
    await waitFor(() => expect(get).toHaveBeenCalledTimes(2));
    await act(async () => {});
    expect(result.current.shortcuts).toEqual(proposed);
    await act(async () => { complete?.(); expect(await saved).toBe(true); });
    await waitFor(() => expect(get).toHaveBeenCalledTimes(3));
    expect(result.current.shortcuts).toEqual(proposed);
  });
});
