/**
 * What can be seen of a document (ADR-369, lot 14). A read that starts costs a transfer the
 * server cannot take back, even once the page dropped it: measured 2026-11-05, Strict Mode's
 * first effect held the account's claim and refused the second, 35 reads of 66 failing. So a
 * read starts once the page has settled on a document; what is not there tells a failure, which
 * can be tried again, from a document with nothing to show.
 */
import { act, renderHook } from '@testing-library/react';
import { StrictMode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from '@/lib/api-client';
import type { QueryParamValue } from '@/lib/api-client';
import type { Shown } from '@/lib/workbench/shown';

const { shownOf } = vi.hoisted(() => ({ shownOf: vi.fn() }));
vi.mock('@/lib/workbench/shown', () => ({ shownOf }));

import { useShownDocument } from '../useShownDocument';

const HELLO: Shown = { kind: 'text', text: 'hello', cut: false };
const PATH = '/workbench/files/preview';

type Props = { id: string };

function read(wrapper?: typeof StrictMode) {
  return renderHook(
    ({ id }: Props) => useShownDocument(PATH, { id } as Record<string, QueryParamValue>),
    { initialProps: { id: 'f1' }, wrapper }
  );
}

async function settle(): Promise<void> {
  await act(async () => {
    await vi.runAllTimersAsync();
  });
}

describe('useShownDocument', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    shownOf.mockReset();
    shownOf.mockResolvedValue(HELLO);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('reads a document once, whatever Strict Mode does to its effects', async () => {
    const { result } = read(StrictMode);

    expect(result.current.state).toEqual({ kind: 'loading' });
    await settle();

    expect(shownOf).toHaveBeenCalledTimes(1);
    expect(result.current.state).toEqual(HELLO);
  });

  it('reads nothing of a document it only passed over', async () => {
    const { rerender } = read();

    rerender({ id: 'f2' });
    rerender({ id: 'f3' });
    await settle();

    expect(shownOf).toHaveBeenCalledTimes(1);
    expect(shownOf.mock.calls[0]?.[1]).toEqual({ id: 'f3' });
  });

  it('drops the read under way when another document takes its place', async () => {
    let answer: (shown: Shown) => void = () => undefined;
    shownOf.mockReturnValueOnce(new Promise<Shown>(resolve => (answer = resolve)));
    const { result, rerender } = read();
    await settle();
    const signal: AbortSignal = shownOf.mock.calls[0]?.[2];

    rerender({ id: 'f2' });

    expect(signal.aborted).toBe(true);
    expect(result.current.state).toEqual({ kind: 'loading' });
    await act(async () => answer({ kind: 'text', text: 'late', cut: false }));
    await settle();
    expect(result.current.state).toEqual(HELLO);
  });

  it('lets no read it left speak over the one it stayed on', async () => {
    let refuse: (reason: Error) => void = () => undefined;
    shownOf.mockReturnValueOnce(new Promise<Shown>((_, reject) => (refuse = reject)));
    const { result, rerender } = read();
    await settle();
    rerender({ id: 'f2' });
    await settle();
    expect(result.current.state).toEqual(HELLO);

    await act(async () => refuse(new Error('aborted')));

    expect(result.current.state).toEqual(HELLO);
  });

  it('reads nothing without a path', async () => {
    const { result } = renderHook(() => useShownDocument(null, { id: 'f1' }));

    await settle();

    expect(shownOf).not.toHaveBeenCalled();
    expect(result.current.state).toEqual({ kind: 'loading' });
  });

  it('says a document has nothing to show', async () => {
    shownOf.mockRejectedValue(
      new ApiError('no', 422, { detail: { code: 'not_supported_by_provider' } })
    );
    const { result } = read();

    await settle();

    expect(result.current.state).toEqual({ kind: 'none' });
  });

  it('tells a failure apart, with what the API said', async () => {
    shownOf.mockRejectedValue(
      new ApiError('no', 413, { detail: { code: 'too_large', max_bytes: 1024 * 1024 } })
    );
    const { result } = read();

    await settle();

    expect(result.current.state).toEqual({
      kind: 'failed',
      refusal: { key: 'workbench.errors.too_large_bounded', values: { megabytes: 1 } },
    });
  });

  it('calls a failure nobody explained a failure', async () => {
    shownOf.mockRejectedValue(new Error('network'));
    const { result } = read();

    await settle();

    expect(result.current.state).toEqual({ kind: 'failed', refusal: null });
  });

  it('reads again when asked, and shows it is reading', async () => {
    shownOf.mockRejectedValueOnce(new Error('network'));
    const { result } = read();
    await settle();

    act(() => result.current.retry());

    expect(result.current.state).toEqual({ kind: 'loading' });
    await settle();
    expect(shownOf).toHaveBeenCalledTimes(2);
    expect(result.current.state).toEqual(HELLO);
  });

  it('lets an image go with the page that drew it', async () => {
    const revoke = vi.fn();
    vi.stubGlobal('URL', Object.assign(URL, { revokeObjectURL: revoke }));
    shownOf.mockResolvedValue({ kind: 'image', url: 'blob:one' });
    const { unmount } = read();
    await settle();

    unmount();

    expect(revoke).toHaveBeenCalledWith('blob:one');
    vi.unstubAllGlobals();
  });
});
