/**
 * `useMeeting` polls only while the server works and re-reads the row after
 * each action; `useMeetingList` treats a 404 as "feature off", never an error.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, renderHook, waitFor } from '@testing-library/react';

import { ApiError } from '@/lib/api-client';
import { MEETING_STATUS_POLL_MS } from '@/lib/constants';
import type { MeetingDetail, MeetingListResponse } from '@/types/meetings';

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

function detail(over: Partial<MeetingDetail> = {}): MeetingDetail {
  return {
    id: 'm1',
    status: 'ready',
    stage: null,
    started_at: '2026-09-02T10:00:00Z',
    stopped_at: '2026-09-02T11:00:00Z',
    last_segment_at: null,
    client_timezone: 'Europe/Paris',
    audio_format: 'webm_opus',
    segment_count: 120,
    audio_duration_seconds: 3600,
    audio_gaps: 0,
    audio_kept_until: null,
    audio_purged_at: null,
    location_lat: null,
    location_lon: null,
    location_label: null,
    calendar_event_id: null,
    stt_provider: 'elevenlabs',
    stt_model: 'scribe_v2',
    stt_detected_language: 'fr',
    stt_diarized: true,
    stt_cost_eur: 0.2,
    synthesis_model: null,
    synthesis_tokens_in: 0,
    synthesis_tokens_out: 0,
    synthesis_tokens_cache: 0,
    synthesis_cost_eur: null,
    total_cost_eur: 0.2,
    has_transcript: true,
    report: { title: 'Point projet', participants: [], sections: [] },
    report_is_edited: false,
    report_edited_at: null,
    template_snapshot: null,
    index_state: 'indexed',
    indexed_at: null,
    email_sent_at: null,
    last_error_code: null,
    last_error_message: null,
    attempts: 1,
    max_attempts: 3,
    worker_stale: false,
    template_ref: null,
    template_name: null,
    template_selection: null,
    template_selection_reason: null,
    source_meeting_id: null,
    derived_count: 0,
    transcript: null,
    ...over,
  };
}

beforeEach(() => {
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
