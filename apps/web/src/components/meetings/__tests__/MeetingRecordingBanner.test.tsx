/**
 * The banner says the phase, offers the actions the phase allows, and carries
 * the silence prompt and the missing-segments recovery.
 *
 * The global i18n stub returns keys, so names and texts are asserted by key —
 * the six-locale parity gate owns the wording.
 */

import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import type { UseMeetingRecorderReturn } from '@/hooks/useMeetingRecorder';

import { MeetingRecordingBanner } from '../MeetingRecordingBanner';

function recorder(over: Partial<UseMeetingRecorderReturn> = {}): UseMeetingRecorderReturn {
  return {
    phase: 'recording',
    recording: {
      meetingId: 'm1',
      startedAt: '2026-09-02T10:00:00Z',
      audioFormat: 'webm_opus',
      mimeType: 'audio/webm;codecs=opus',
      segmentSeconds: 30,
      nextSequence: 2,
    },
    engine: null,
    limits: {
      segment_seconds: 30,
      segment_max_seconds: 60,
      segment_max_bytes: 1,
      max_duration_minutes: 180,
      silence_prompt_minutes: 10,
    },
    elapsedSeconds: 125,
    level: 0.2,
    uploadedSegments: 2,
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

describe('MeetingRecordingBanner', () => {
  it('renders nothing when idle', () => {
    const { container } = renderWithProviders(
      <MeetingRecordingBanner
        lng="en"
        recorder={recorder({ phase: 'idle', isCapturing: false, isLive: false })}
      />
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('shows the elapsed time, the upload progress and a Stop button while recording', async () => {
    const rec = recorder();
    const { user } = renderWithProviders(<MeetingRecordingBanner lng="en" recorder={rec} />);
    expect(screen.getByRole('status')).toHaveTextContent('meetings.banner.recording');
    expect(screen.getByText('2:05')).toBeInTheDocument();
    expect(screen.getByText(/meetings\.banner\.uploaded/)).toBeInTheDocument();
    expect(screen.getByTestId('meeting-recording-dot')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'meetings.banner.stop' }));
    expect(rec.stop).toHaveBeenCalledTimes(1);
  });

  it('offers Resume, Finalize and Discard when interrupted', async () => {
    const rec = recorder({ phase: 'interrupted', isCapturing: false });
    const { user } = renderWithProviders(<MeetingRecordingBanner lng="en" recorder={rec} />);
    await user.click(screen.getByRole('button', { name: 'meetings.banner.resume' }));
    expect(rec.resume).toHaveBeenCalledTimes(1);
    await user.click(screen.getByRole('button', { name: 'meetings.banner.finalize' }));
    expect(rec.stop).toHaveBeenCalledTimes(1);
    await user.click(screen.getByRole('button', { name: 'meetings.banner.discard' }));
    expect(rec.discard).toHaveBeenCalledTimes(1);
  });

  it('turns Finalize into "finalize anyway" when segments are missing, and hides Resume', async () => {
    const rec = recorder({ phase: 'interrupted', isCapturing: false, missingSegments: [3, 4] });
    const { user } = renderWithProviders(<MeetingRecordingBanner lng="en" recorder={rec} />);
    expect(
      screen.queryByRole('button', { name: 'meetings.banner.resume' })
    ).not.toBeInTheDocument();
    expect(screen.getByText('meetings.banner.missing_segments')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'meetings.banner.finalize_with_gaps' }));
    expect(rec.finalizeWithGaps).toHaveBeenCalledTimes(1);
  });

  it('asks "still recording?" and forwards Continue', async () => {
    const rec = recorder({ silencePrompt: true });
    const { user } = renderWithProviders(<MeetingRecordingBanner lng="en" recorder={rec} />);
    const dialog = screen.getByRole('alertdialog', { name: 'meetings.banner.silence_title' });
    expect(dialog).toHaveTextContent('meetings.banner.silence_body');
    await user.click(screen.getByRole('button', { name: 'meetings.banner.silence_continue' }));
    expect(rec.continueAfterSilence).toHaveBeenCalledTimes(1);
  });

  it('names the error by its stable code and offers Dismiss', async () => {
    const rec = recorder({
      phase: 'error',
      isCapturing: false,
      isLive: false,
      errorCode: 'microphone_denied',
    });
    const { user } = renderWithProviders(<MeetingRecordingBanner lng="fr" recorder={rec} />);
    expect(screen.getByText('meetings.errors.microphone_denied')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'meetings.banner.stop' })).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'meetings.banner.dismiss' }));
    expect(rec.dismiss).toHaveBeenCalledTimes(1);
  });
});
