/**
 * The format picker in the banner (ADR-259): while the recording is live the
 * user can choose the minutes format ahead of processing; the choice is saved
 * on the meeting, remembered in the recorder store (a reload keeps it), and a
 * refusal is named and leaves the previous choice in place.
 */

import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';
import type { UseMeetingRecorderReturn } from '@/hooks/useMeetingRecorder';
import { useMeetingRecorderStore, type PersistedRecording } from '@/stores/meetingRecorderStore';
import type { MeetingTemplateSummary } from '@/types/meetings';

const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock('sonner', () => ({ toast }));

const api = vi.hoisted(() => ({ patch: vi.fn() }));
vi.mock('@/lib/meetings/api', async importOriginal => {
  const actual = await importOriginal<typeof import('@/lib/meetings/api')>();
  return { ...actual, meetingsApi: { ...actual.meetingsApi, patch: api.patch } };
});

const TEMPLATES: MeetingTemplateSummary[] = [
  {
    ref: 'builtin:daily_standup',
    name: 'Daily standup',
    description: null,
    category: 'meeting',
    builtin: true,
    sections_count: 4,
    auto_selectable: true,
  },
];
vi.mock('@/hooks/useMeetingTemplates', () => ({
  useMeetingTemplates: () => ({
    templates: TEMPLATES,
    maxUserTemplates: 50,
    isLoading: false,
    isSaving: false,
    error: null,
    refetch: vi.fn(),
    load: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    remove: vi.fn(),
  }),
}));

import { MeetingRecordingBanner } from '../MeetingRecordingBanner';

const RECORDING: PersistedRecording = {
  meetingId: 'm1',
  startedAt: '2026-09-02T10:00:00Z',
  audioFormat: 'webm_opus',
  mimeType: 'audio/webm;codecs=opus',
  segmentSeconds: 30,
  nextSequence: 2,
};

function recorder(over: Partial<UseMeetingRecorderReturn> = {}): UseMeetingRecorderReturn {
  return {
    phase: 'recording',
    recording: RECORDING,
    engine: null,
    limits: null,
    elapsedSeconds: 10,
    level: 0,
    uploadedSegments: 0,
    pendingSegments: 0,
    silencePrompt: false,
    errorCode: null,
    missingSegments: null,
    isSupported: true,
    isCapturing: true,
    isLive: true,
    start: vi.fn(async () => undefined),
    stop: vi.fn(async () => 'processing' as const),
    finalizeWithGaps: vi.fn(async () => 'processing' as const),
    resume: vi.fn(async () => undefined),
    discard: vi.fn(async () => undefined),
    dismiss: vi.fn(),
    continueAfterSilence: vi.fn(),
    ...over,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  useMeetingRecorderStore.getState().begin(RECORDING, null, null);
  api.patch.mockResolvedValue({});
});

afterEach(() => {
  useMeetingRecorderStore.getState().reset();
});

describe('MeetingRecordingBanner — format (ADR-259)', () => {
  it('offers the format while live, saves the choice and remembers it', async () => {
    const { user } = renderWithProviders(<MeetingRecordingBanner lng="en" recorder={recorder()} />);
    const picker = screen.getByRole('combobox', { name: 'meetings.banner.format_label' });
    expect(picker).toHaveTextContent('meetings.banner.format_auto');
    await user.click(picker);
    await user.click(await screen.findByRole('option', { name: 'Daily standup' }));
    await waitFor(() =>
      expect(api.patch).toHaveBeenCalledWith('m1', { template_ref: 'builtin:daily_standup' })
    );
    await waitFor(() =>
      expect(useMeetingRecorderStore.getState().recording?.templateRef).toBe(
        'builtin:daily_standup'
      )
    );
    expect(toast.success).toHaveBeenCalledWith('meetings.banner.format_saved');
  });

  it('shows the remembered choice on the trigger', () => {
    useMeetingRecorderStore.getState().setTemplateRef('builtin:daily_standup');
    renderWithProviders(<MeetingRecordingBanner lng="en" recorder={recorder()} />);
    expect(
      screen.getByRole('combobox', { name: 'meetings.banner.format_label' })
    ).toHaveTextContent('Daily standup');
  });

  it('hides the format once the recording is no longer live', () => {
    renderWithProviders(
      <MeetingRecordingBanner
        lng="en"
        recorder={recorder({ phase: 'processing', isCapturing: false, isLive: false })}
      />
    );
    expect(
      screen.queryByRole('combobox', { name: 'meetings.banner.format_label' })
    ).not.toBeInTheDocument();
  });

  it('names a refused change and keeps the previous format', async () => {
    const { ApiError } = await import('@/lib/api-client');
    api.patch.mockRejectedValueOnce(
      new ApiError('locked', 409, { detail: { code: 'template_locked' } })
    );
    const { user } = renderWithProviders(<MeetingRecordingBanner lng="en" recorder={recorder()} />);
    await user.click(screen.getByRole('combobox', { name: 'meetings.banner.format_label' }));
    await user.click(await screen.findByRole('option', { name: 'Daily standup' }));
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith('meetings.errors.template_locked')
    );
    expect(useMeetingRecorderStore.getState().recording?.templateRef ?? null).toBeNull();
    expect(
      screen.getByRole('combobox', { name: 'meetings.banner.format_label' })
    ).toHaveTextContent('meetings.banner.format_auto');
  });
});
