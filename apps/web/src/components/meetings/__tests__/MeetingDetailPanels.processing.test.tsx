/**
 * The processing panel says where the job stands (ADR-258, amended 2026-09-05):
 * which attempt of the budget is running, why the previous one failed, and —
 * when the worker stopped responding — that the meeting can be deleted.
 */

import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import type { MeetingActions } from '@/components/meetings/useMeetingActions';
import type { MeetingDetail } from '@/types/meetings';

import { ProcessingPanel } from '../MeetingDetailPanels';

function actions(): MeetingActions {
  return {
    save: vi.fn(),
    resetReport: vi.fn(),
    regenerate: vi.fn(),
    reformat: vi.fn(),
    retry: vi.fn(),
    email: vi.fn(),
    deleteTranscript: vi.fn(),
    remove: vi.fn(),
  };
}

function processing(over: Partial<MeetingDetail> = {}): MeetingDetail {
  return {
    id: 'm1',
    status: 'processing',
    stage: 'transcribing',
    started_at: '2026-09-05T09:25:00Z',
    stopped_at: '2026-09-05T09:26:00Z',
    last_segment_at: null,
    client_timezone: 'Europe/Paris',
    audio_format: 'pcm_s16le_16',
    segment_count: 2,
    audio_duration_seconds: 33,
    audio_gaps: 0,
    audio_kept_until: null,
    audio_purged_at: null,
    location_lat: null,
    location_lon: null,
    location_label: null,
    calendar_event_id: null,
    stt_provider: null,
    stt_model: null,
    stt_detected_language: null,
    stt_diarized: false,
    stt_cost_eur: null,
    synthesis_model: null,
    synthesis_tokens_in: 0,
    synthesis_tokens_out: 0,
    synthesis_tokens_cache: 0,
    synthesis_cost_eur: null,
    total_cost_eur: null,
    has_transcript: false,
    report: null,
    report_is_edited: false,
    report_edited_at: null,
    template_snapshot: null,
    index_state: null,
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

describe('ProcessingPanel', () => {
  it('a first attempt shows the progress and the plain hint only', () => {
    renderWithProviders(<ProcessingPanel lng="en" meeting={processing()} actions={actions()} />);
    expect(screen.getByText('meetings.detail.processing_hint')).toBeInTheDocument();
    expect(screen.queryByText(/meetings\.detail\.attempt_of/)).not.toBeInTheDocument();
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('a retry names its attempt of the budget and why the previous one failed', () => {
    renderWithProviders(
      <ProcessingPanel
        lng="en"
        meeting={processing({ attempts: 2, last_error_code: 'synthesis_failed' })}
        actions={actions()}
      />
    );
    expect(screen.getByText(/meetings\.detail\.attempt_of/)).toBeInTheDocument();
    expect(screen.getByText(/meetings\.errors\.synthesis_failed/)).toBeInTheDocument();
  });

  it('a queued row after a first failure names that failure with the attempt spent', () => {
    renderWithProviders(
      <ProcessingPanel
        lng="en"
        meeting={processing({
          status: 'stopped',
          stage: null,
          attempts: 1,
          last_error_code: 'provider_timeout',
        })}
        actions={actions()}
      />
    );
    expect(screen.getByText(/meetings\.detail\.attempt_of/)).toBeInTheDocument();
    expect(screen.getByText(/meetings\.errors\.provider_timeout/)).toBeInTheDocument();
  });

  it('a row released without spending an attempt shows the reason and no counter', () => {
    renderWithProviders(
      <ProcessingPanel
        lng="en"
        meeting={processing({
          status: 'stopped',
          stage: null,
          attempts: 0,
          last_error_code: 'usage_limit',
        })}
        actions={actions()}
      />
    );
    expect(screen.queryByText(/meetings\.detail\.attempt_of/)).not.toBeInTheDocument();
    expect(screen.getByText(/meetings\.errors\.usage_limit/)).toBeInTheDocument();
  });

  it('a stale worker is announced and the meeting can be deleted from there', async () => {
    const acts = actions();
    const { user } = renderWithProviders(
      <ProcessingPanel lng="en" meeting={processing({ worker_stale: true })} actions={acts} />
    );
    expect(screen.getByRole('alert')).toHaveTextContent('meetings.detail.worker_stale_hint');
    expect(screen.queryByText('meetings.detail.processing_hint')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'meetings.detail.delete' }));
    expect(acts.remove).toHaveBeenCalledTimes(1);
  });
});
