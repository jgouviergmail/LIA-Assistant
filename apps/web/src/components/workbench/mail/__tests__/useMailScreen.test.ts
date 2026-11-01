/**
 * The look that marks a message read (ADR-369, Task 4.7): once per opening,
 * after `MAIL_READ_DWELL_MS`, never at a glance — and never again over the
 * person's own « Mark as unread ».
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { act, renderHook } from '@/__tests__/test-utils';
import type { WorkbenchItemState } from '@/hooks/useWorkbenchItem';
import { MAIL_READ_DWELL_MS } from '@/lib/workbench/mail';
import type { MailMessage } from '@/lib/workbench/types';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

import { useReadAfterLook } from '../useMailScreen';

function shown(id: string, isRead: boolean): WorkbenchItemState<MailMessage> {
  return {
    item: {
      id,
      thread_id: id,
      sender: null,
      reply_to: [],
      to: [],
      cc: [],
      subject: '',
      received_at: null,
      is_read: isRead,
      is_starred: false,
      label_ids: [],
      body: '',
      attachments: [],
    },
    loading: false,
    error: null,
    refresh: vi.fn(),
    setItem: vi.fn(),
  };
}

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

describe('useReadAfterLook', () => {
  it('marks an unread message read after a look, not at a glance', () => {
    const mark = vi.fn().mockResolvedValue(undefined);
    renderHook(() => useReadAfterLook(shown('m1', false), mark));

    act(() => vi.advanceTimersByTime(MAIL_READ_DWELL_MS - 1));
    expect(mark).not.toHaveBeenCalled();
    act(() => vi.advanceTimersByTime(1));
    expect(mark).toHaveBeenCalledTimes(1);
  });

  it('never marks again over the person’s own « Mark as unread »', () => {
    const mark = vi.fn().mockResolvedValue(undefined);
    const { rerender } = renderHook(({ state }) => useReadAfterLook(state, mark), {
      initialProps: { state: shown('m1', false) },
    });
    act(() => vi.advanceTimersByTime(MAIL_READ_DWELL_MS));
    rerender({ state: shown('m1', true) });

    rerender({ state: shown('m1', false) });
    act(() => vi.advanceTimersByTime(MAIL_READ_DWELL_MS * 3));

    expect(mark).toHaveBeenCalledTimes(1);
  });

  it('looks again when the same message is opened again after a glance', () => {
    const mark = vi.fn().mockResolvedValue(undefined);
    const closed: WorkbenchItemState<MailMessage> = { ...shown('m1', false), item: undefined };
    const { rerender } = renderHook(({ state }) => useReadAfterLook(state, mark), {
      initialProps: { state: shown('m1', false) },
    });
    act(() => vi.advanceTimersByTime(MAIL_READ_DWELL_MS / 2));
    rerender({ state: closed });

    rerender({ state: shown('m1', false) });
    act(() => vi.advanceTimersByTime(MAIL_READ_DWELL_MS));

    expect(mark).toHaveBeenCalledTimes(1);
  });

  it('looks again at another message', () => {
    const mark = vi.fn().mockResolvedValue(undefined);
    const { rerender } = renderHook(({ state }) => useReadAfterLook(state, mark), {
      initialProps: { state: shown('m1', false) },
    });
    act(() => vi.advanceTimersByTime(MAIL_READ_DWELL_MS));

    rerender({ state: shown('m2', false) });
    act(() => vi.advanceTimersByTime(MAIL_READ_DWELL_MS));

    expect(mark).toHaveBeenCalledTimes(2);
  });
});
