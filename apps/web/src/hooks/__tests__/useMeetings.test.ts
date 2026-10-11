/**
 * `useMeeting` polls only while the server works and re-reads the row after
 * each action; `useMeetingList` treats a 404 as "feature off", never an error.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, renderHook, waitFor } from '@testing-library/react';

import { ApiError } from '@/lib/api-client';
import { MEETING_STATUS_POLL_MS } from '@/lib/constants';
import type { MeetingDetail, MeetingListResponse } from '@/types/meetings';
import { publishApplicationResources } from '@/lib/application-resources';

const auth = vi.hoisted(() => ({ owner: 'one' }));
vi.mock('@/hooks/useAuth', () => ({ useAuth: () => ({ user: { id: auth.owner } }) }));

const api = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  delete: vi.fn(),
  put: vi.fn(),
}));

vi.mock('@/lib/api-client', async importOriginal => {
  const actual = await importOriginal<typeof import('@/lib/api-client')>();
  return { ...actual, apiClient: api };
});

vi.mock('@/lib/logger', () => ({
  logger: { error: vi.fn(), warn: vi.fn(), info: vi.fn(), debug: vi.fn() },
}));

import { isMeetingInFlight, useMeeting, useMeetingList } from '../useMeetings';

import { meetingDetail as detail } from '@/__tests__/fixtures/meeting-detail';

beforeEach(() => {
  auth.owner = 'one';
  // `shouldAdvanceTime`: `waitFor` polls on real time while the hook's own
  // poll timer stays controllable (the telephony hook test's recipe).
  vi.useFakeTimers({ shouldAdvanceTime: true });
  Object.values(api).forEach(fn => fn.mockReset());
});

afterEach(() => {
  vi.useRealTimers();
});

describe('isMeetingInFlight', () => {
  it('is true while stopped/processing or while a ready row carries a stage', () => {
    expect(isMeetingInFlight({ status: 'processing', stage: 'transcribing' })).toBe(true);
    expect(isMeetingInFlight({ status: 'stopped', stage: null })).toBe(true);
    expect(isMeetingInFlight({ status: 'ready', stage: 'synthesizing' })).toBe(true);
    expect(isMeetingInFlight({ status: 'ready', stage: null })).toBe(false);
    expect(isMeetingInFlight({ status: 'failed', stage: null })).toBe(false);
  });
});

describe('useMeeting', () => {
  it('polls while processing and stops once the row is terminal', async () => {
    api.get
      .mockResolvedValueOnce(detail({ status: 'processing', stage: 'transcribing' }))
      .mockResolvedValueOnce(detail({ status: 'processing', stage: 'synthesizing' }))
      .mockResolvedValueOnce(detail({ status: 'ready', stage: null }));
    const { result } = renderHook(() => useMeeting('m1'));
    await waitFor(() => expect(result.current.meeting?.stage).toBe('transcribing'));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(MEETING_STATUS_POLL_MS);
    });
    await waitFor(() => expect(result.current.meeting?.stage).toBe('synthesizing'));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(MEETING_STATUS_POLL_MS);
    });
    await waitFor(() => expect(result.current.meeting?.status).toBe('ready'));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(MEETING_STATUS_POLL_MS * 3);
    });
    expect(api.get).toHaveBeenCalledTimes(3);
  });

  it('applies the row an action returns and flags not-found on 404', async () => {
    api.get.mockResolvedValueOnce(detail());
    api.patch.mockResolvedValueOnce(detail({ report_is_edited: true }));
    const { result } = renderHook(() => useMeeting('m1'));
    await waitFor(() => expect(result.current.meeting).not.toBeNull());
    await act(async () => {
      await result.current.patch({ title: 'Nouveau titre' });
    });
    expect(api.patch).toHaveBeenCalledWith('/meetings/m1', { title: 'Nouveau titre' });
    expect(result.current.meeting?.report_is_edited).toBe(true);

    api.get.mockRejectedValueOnce(new ApiError('nope', 404));
    const gone = renderHook(() => useMeeting('m2'));
    await waitFor(() => expect(gone.result.current.isNotFound).toBe(true));
  });
});

describe('useMeetingList', () => {
  it('returns the page and the exact total', async () => {
    const page: MeetingListResponse = {
      items: [],
      total: 42,
      limit: 20,
      offset: 0,
    };
    api.get.mockResolvedValueOnce(page);
    const { result } = renderHook(() => useMeetingList(20));
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.total).toBe(42);
    expect(api.get).toHaveBeenCalledWith('/meetings', { params: { limit: 20, offset: 0 } });
  });

  it('reads a 404 as the feature being off', async () => {
    api.get.mockRejectedValueOnce(new ApiError('nope', 404));
    const { result } = renderHook(() => useMeetingList(20));
    await waitFor(() => expect(result.current.isUnavailable).toBe(true));
    expect(result.current.error).toBeNull();
  });
});

describe('native meeting changes and account ownership', () => {
  it('refreshes only the addressed account after a native mutation', async () => {
    api.get.mockResolvedValue(detail());
    const { result } = renderHook(() => useMeeting('m1', true));
    await waitFor(() => expect(result.current.meeting?.has_transcript).toBe(true));
    act(() => publishApplicationResources('two', new Set(['meetings'])));
    expect(api.get).toHaveBeenCalledTimes(1);
    api.get.mockResolvedValueOnce(detail({ has_transcript: false }));
    act(() => publishApplicationResources('one', new Set(['meetings'])));
    await waitFor(() => expect(result.current.meeting?.has_transcript).toBe(false));
    expect(api.delete).not.toHaveBeenCalled();
  });

  it('refuses an obsolete mutation callback before sending', async () => {
    api.get.mockResolvedValue(detail());
    const { result, rerender } = renderHook(() => useMeeting('m1'));
    await waitFor(() => expect(result.current.meeting).not.toBeNull());
    const obsolete = result.current.deleteTranscript;
    auth.owner = 'two';
    rerender();
    await waitFor(() => expect(api.get).toHaveBeenCalledTimes(2));
    await act(async () => expect(await obsolete()).toBeNull());
    expect(api.delete).not.toHaveBeenCalled();
  });

  it('hides old account detail immediately and ignores its delayed response', async () => {
    const pending = Promise.withResolvers<MeetingDetail>();
    api.get.mockReturnValueOnce(pending.promise).mockImplementation(() => new Promise(() => {}));
    const { result, rerender } = renderHook(() => useMeeting('m1'));
    await waitFor(() => expect(api.get).toHaveBeenCalledTimes(1));
    auth.owner = 'two';
    rerender();
    await act(async () => pending.resolve(detail()));
    expect(result.current.meeting).toBeNull();
  });

  it('does not apply a late mutation to another account or selected meeting', async () => {
    const pending = Promise.withResolvers<MeetingDetail>();
    api.get.mockResolvedValue(detail());
    api.delete.mockReturnValue(pending.promise);
    const { result, rerender } = renderHook(({ id }) => useMeeting(id), { initialProps: { id: 'm1' } });
    await waitFor(() => expect(result.current.meeting).not.toBeNull());
    let writing: Promise<MeetingDetail | null> | undefined;
    act(() => { writing = result.current.deleteTranscript(); });
    await waitFor(() => expect(api.delete).toHaveBeenCalledTimes(1));
    api.get.mockResolvedValue(detail({ id: 'm2' }));
    rerender({ id: 'm2' });
    await waitFor(() => expect(result.current.meeting?.id).toBe('m2'));
    await act(async () => { pending.resolve(detail({ has_transcript: false })); expect(await writing).toBeNull(); });
    expect(result.current.meeting?.id).toBe('m2');
    expect(result.current.isActing).toBe(false);
  });

  it('keeps polling known processing state through successive network failures', async () => {
    const failure = new Error('offline');
    api.get.mockResolvedValueOnce(detail({ status: 'processing', stage: 'synthesizing' }))
      .mockRejectedValueOnce(failure).mockRejectedValueOnce(failure).mockResolvedValue(detail());
    const { result } = renderHook(() => useMeeting('m1'));
    await waitFor(() => expect(result.current.meeting?.status).toBe('processing'));
    for (let pass = 0; pass < 3; pass += 1) {
      await act(async () => vi.advanceTimersByTime(MEETING_STATUS_POLL_MS));
    }
    await waitFor(() => expect(result.current.meeting?.status).toBe('ready'));
    expect(api.get).toHaveBeenCalledTimes(4);
  });

  it('rereads a native list change without bulk deletion and clears old account totals', async () => {
    api.get.mockResolvedValue({ items: [], total: 42, limit: 20, offset: 0 });
    const { result, rerender } = renderHook(() => useMeetingList(20));
    await waitFor(() => expect(result.current.total).toBe(42));
    api.get.mockResolvedValueOnce({ items: [], total: 41, limit: 20, offset: 0 });
    act(() => publishApplicationResources('one', new Set(['meetings'])));
    await waitFor(() => expect(result.current.total).toBe(41));
    api.get.mockImplementationOnce(() => new Promise(() => {}));
    auth.owner = 'two';
    rerender();
    expect(result.current.meetings).toEqual([]);
    expect(result.current.total).toBe(0);
    expect(api.post).not.toHaveBeenCalled();
  });
});
