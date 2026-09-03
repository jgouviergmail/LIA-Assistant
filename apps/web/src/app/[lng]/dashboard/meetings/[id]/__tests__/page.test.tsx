/**
 * The meeting page: skeleton, not-found, the progress while the server works,
 * the failure with its recoveries, and the READY minutes with every action —
 * edit/save, restore, rebuild, PDF, email, transcript, delete.
 */

import { describe, expect, it, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';
import type { MeetingDetail, MeetingReport } from '@/types/meetings';

const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock('sonner', () => ({ toast }));

const state = vi.hoisted(() => ({
  meeting: null as MeetingDetail | null,
  isLoading: false,
  isNotFound: false,
  isActing: false,
  patch: vi.fn(),
  resetReport: vi.fn(),
  regenerate: vi.fn(),
  reformat: vi.fn(),
  retry: vi.fn(),
  email: vi.fn(),
  deleteTranscript: vi.fn(),
  remove: vi.fn(),
  refetch: vi.fn(),
}));
vi.mock('@/hooks/useMeetings', () => ({
  useMeeting: () => ({ ...state, error: null }),
}));
vi.mock('@/hooks/useMeetingTemplates', () => ({
  useMeetingTemplates: () => ({
    templates: [
      {
        ref: 'builtin:default_minutes',
        name: 'Meeting minutes',
        description: null,
        category: 'meeting',
        builtin: true,
        sections_count: 6,
        auto_selectable: true,
      },
    ],
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
vi.mock('@/hooks/useLanguageParam', () => ({ useLanguageParam: () => 'en' }));
const push = vi.fn();
vi.mock('@/hooks/useLocalizedRouter', () => ({
  useLocalizedRouter: () => ({ push, replace: vi.fn(), back: vi.fn() }),
}));
const confirm = vi.hoisted(() => ({ answer: true, calls: [] as unknown[] }));
vi.mock('@/components/ui/use-confirm', () => ({
  useConfirm: () => ({
    confirm: async (options: unknown) => {
      confirm.calls.push(options);
      return confirm.answer;
    },
    confirmDialog: null,
  }),
}));

import MeetingPage from '../page';

function report(over: Partial<MeetingReport> = {}): MeetingReport {
  return {
    title: 'Point projet',
    participants: [
      { label: 'S1', name: 'Claire', role: 'chef de projet' },
      { label: 'S2', name: null, role: null },
    ],
    sections: [
      {
        key: 'summary',
        label: 'Résumé',
        kind: 'paragraph',
        paragraph: 'La migration est terminée.',
        bullets: [],
        topics: [],
        action_items: [],
        transcript: [],
      },
      {
        key: 'action_items',
        label: 'Actions',
        kind: 'action_items',
        paragraph: null,
        bullets: [],
        topics: [],
        action_items: [
          { description: 'Préparer la bascule', owner: 'Marc', due_date: '2026-09-09' },
        ],
        transcript: [],
      },
    ],
    ...over,
  };
}

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
    audio_purged_at: '2026-09-02T11:05:00Z',
    location_lat: null,
    location_lon: null,
    location_label: 'Salle Ada',
    calendar_event_id: null,
    stt_provider: 'openai',
    stt_model: 'gpt-4o-transcribe-diarize',
    stt_detected_language: 'fr',
    stt_diarized: true,
    stt_cost_eur: 0.36,
    synthesis_model: 'gpt-4.1',
    synthesis_tokens_in: 1200,
    synthesis_tokens_out: 300,
    synthesis_tokens_cache: 0,
    synthesis_cost_eur: 0.012,
    total_cost_eur: 0.372,
    has_transcript: true,
    report: report(),
    report_is_edited: false,
    report_edited_at: null,
    template_snapshot: null,
    index_state: 'indexed',
    indexed_at: '2026-09-02T11:06:00Z',
    email_sent_at: null,
    last_error_code: null,
    last_error_message: null,
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

// `use(params)` reads a settled thenable synchronously when it carries React's
// fulfilled marker; a bare resolved Promise would suspend the first render.
const ROUTE = { lng: 'en', id: 'm1' };
const params = Object.assign(Promise.resolve(ROUTE), { status: 'fulfilled', value: ROUTE });

beforeEach(() => {
  vi.clearAllMocks();
  confirm.answer = true;
  confirm.calls = [];
  state.meeting = detail();
  state.isLoading = false;
  state.isNotFound = false;
  state.isActing = false;
  state.patch.mockResolvedValue(detail());
  state.resetReport.mockResolvedValue(detail());
  state.regenerate.mockResolvedValue(undefined);
  state.reformat.mockResolvedValue({
    id: 'm9',
    status: 'ready',
    stage: 'synthesizing',
    source_meeting_id: 'm1',
  });
  state.retry.mockResolvedValue(undefined);
  state.email.mockResolvedValue(detail());
  state.deleteTranscript.mockResolvedValue(detail({ has_transcript: false }));
  state.remove.mockResolvedValue(true);
});

describe('MeetingPage — loading and absence', () => {
  it('announces the first load', async () => {
    state.isLoading = true;
    state.meeting = null;
    renderWithProviders(<MeetingPage params={params} />);
    expect(await screen.findByRole('status')).toBeInTheDocument();
  });

  it('offers the way back when the meeting does not exist', async () => {
    state.isNotFound = true;
    state.meeting = null;
    const { user } = renderWithProviders(<MeetingPage params={params} />);
    expect(screen.getByText('meetings.detail.not_found')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'meetings.detail.back' }));
    expect(push).toHaveBeenCalledWith('/dashboard/meetings');
  });
});

describe('MeetingPage — while the server works or failed', () => {
  it('shows the progression and the untitled header while processing', () => {
    state.meeting = detail({ status: 'processing', stage: 'transcribing', report: null });
    renderWithProviders(<MeetingPage params={params} />);
    expect(screen.getByText('meetings.detail.progress_title')).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('meetings.list.untitled');
    expect(screen.queryByText('meetings.detail.minutes_title')).not.toBeInTheDocument();
  });

  it('explains a failure and offers retry while the audio still exists', async () => {
    state.meeting = detail({
      status: 'failed',
      report: null,
      audio_purged_at: null,
      last_error_code: 'provider_rate_limited',
    });
    const { user } = renderWithProviders(<MeetingPage params={params} />);
    expect(screen.getByText('meetings.errors.provider_rate_limited')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'meetings.detail.retry' }));
    expect(state.retry).toHaveBeenCalledTimes(1);
  });

  it('hides retry once the audio is gone, keeps delete', () => {
    state.meeting = detail({ status: 'failed', report: null, last_error_code: 'no_speech' });
    renderWithProviders(<MeetingPage params={params} />);
    expect(screen.queryByRole('button', { name: 'meetings.detail.retry' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'meetings.detail.delete' })).toBeInTheDocument();
  });
});

describe('MeetingPage — READY minutes', () => {
  it('renders the header facts, the minutes and the PDF link', () => {
    renderWithProviders(<MeetingPage params={params} />);
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Point projet');
    expect(screen.getByText('Salle Ada')).toBeInTheDocument();
    expect(screen.getByText('1:00:00')).toBeInTheDocument();
    // The cost fact states the total with its two paid units (the stub echoes the key).
    expect(screen.getByText('meetings.detail.cost_breakdown')).toBeInTheDocument();
    expect(screen.getByText('La migration est terminée.')).toBeInTheDocument();
    expect(screen.getByText('Préparer la bascule · Marc · 2026-09-09')).toBeInTheDocument();
    expect(screen.getByText('meetings.detail.generated_badge')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'meetings.detail.pdf' })).toHaveAttribute(
      'href',
      expect.stringContaining('/meetings/m1/pdf')
    );
  });

  it('states the gaps and the missing speaker names', () => {
    state.meeting = detail({
      audio_gaps: 2,
      report: report({ participants: [{ label: 'S1', name: null, role: null }] }),
    });
    renderWithProviders(<MeetingPage params={params} />);
    expect(screen.getByText('meetings.detail.gaps_notice')).toBeInTheDocument();
    expect(screen.getByText('meetings.detail.no_names_notice')).toBeInTheDocument();
  });

  it('edits the title locally, then saves the whole draft', async () => {
    const { user } = renderWithProviders(<MeetingPage params={params} />);
    await user.click(screen.getByRole('button', { name: 'meetings.detail.edit' }));
    const title = screen.getByLabelText('meetings.detail.title_label');
    await user.clear(title);
    await user.type(title, 'Point projet (revu)');
    await user.click(screen.getByRole('button', { name: 'common.save' }));
    await waitFor(() => expect(state.patch).toHaveBeenCalledTimes(1));
    expect(state.patch.mock.calls[0][0]).toMatchObject({ title: 'Point projet (revu)' });
    expect(toast.success).toHaveBeenCalledWith('meetings.detail.saved');
    // The editor closes after the save.
    expect(screen.queryByLabelText('meetings.detail.title_label')).not.toBeInTheDocument();
  });

  it('cancel drops the draft without a request', async () => {
    const { user } = renderWithProviders(<MeetingPage params={params} />);
    await user.click(screen.getByRole('button', { name: 'meetings.detail.edit' }));
    await user.click(screen.getByRole('button', { name: 'common.cancel' }));
    expect(state.patch).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'meetings.detail.edit' })).toBeInTheDocument();
  });

  it('offers restore only once edited, and asks before restoring', async () => {
    renderWithProviders(<MeetingPage params={params} />);
    expect(screen.queryByRole('button', { name: 'meetings.detail.reset' })).not.toBeInTheDocument();
    state.meeting = detail({ report_is_edited: true });
    const { user } = renderWithProviders(<MeetingPage params={params} />);
    await user.click(screen.getByRole('button', { name: 'meetings.detail.reset' }));
    await waitFor(() => expect(state.resetReport).toHaveBeenCalledTimes(1));
    expect(confirm.calls).toHaveLength(1);
  });

  it('a declined confirmation rebuilds nothing', async () => {
    confirm.answer = false;
    const { user } = renderWithProviders(<MeetingPage params={params} />);
    await user.click(screen.getByRole('button', { name: 'meetings.detail.regenerate' }));
    expect(confirm.calls).toHaveLength(1);
    expect(state.regenerate).not.toHaveBeenCalled();
  });

  it('rebuild is refused without a transcript and while a rebuild runs', () => {
    state.meeting = detail({ has_transcript: false });
    renderWithProviders(<MeetingPage params={params} />);
    expect(screen.getByRole('button', { name: 'meetings.detail.regenerate' })).toHaveAttribute(
      'aria-disabled',
      'true'
    );
    state.meeting = detail({ stage: 'synthesizing' });
    renderWithProviders(<MeetingPage params={params} />);
    expect(
      screen.getAllByRole('button', { name: 'meetings.detail.regenerate' }).at(-1)
    ).toHaveAttribute('aria-disabled', 'true');
  });

  it('emails the minutes and reports the relay refusal code', async () => {
    const { ApiError } = await import('@/lib/api-client');
    state.email.mockRejectedValueOnce(
      new ApiError('refused', 502, { detail: { code: 'email_send_failed' } })
    );
    const { user } = renderWithProviders(<MeetingPage params={params} />);
    await user.click(screen.getByRole('button', { name: 'meetings.detail.email' }));
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith('meetings.errors.email_send_failed')
    );
  });

  it('shows the transcript on demand and deletes it after confirmation', async () => {
    state.meeting = detail({
      transcript: [{ speaker: 'S1', start: 0, end: 4, text: 'Bonjour à tous.' }],
    });
    const { user } = renderWithProviders(<MeetingPage params={params} />);
    await user.click(screen.getByRole('button', { name: 'meetings.detail.transcript_show' }));
    expect(screen.getByText('Bonjour à tous.')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'meetings.detail.delete_transcript' }));
    await waitFor(() => expect(state.deleteTranscript).toHaveBeenCalledTimes(1));
  });

  it('deletes the meeting after confirmation and goes back to the list', async () => {
    const { user } = renderWithProviders(<MeetingPage params={params} />);
    await user.click(screen.getByRole('button', { name: 'meetings.detail.delete' }));
    await waitFor(() => expect(state.remove).toHaveBeenCalledTimes(1));
    expect(toast.success).toHaveBeenCalledWith('meetings.detail.deleted');
    expect(push).toHaveBeenCalledWith('/dashboard/meetings');
  });
});

describe('MeetingPage — cost fact', () => {
  it('omits the cost fact while nothing priced was spent', () => {
    state.meeting = detail({ stt_cost_eur: null, synthesis_cost_eur: null, total_cost_eur: null });
    renderWithProviders(<MeetingPage params={params} />);
    expect(screen.queryByText('meetings.detail.cost_breakdown')).not.toBeInTheDocument();
    expect(screen.queryByText('meetings.detail.cost')).not.toBeInTheDocument();
  });
});

describe('MeetingPage — format and derived minutes (ADR-259)', () => {
  const formatted = () =>
    detail({
      template_ref: 'builtin:default_minutes',
      template_name: 'Meeting minutes',
      template_selection: 'auto',
      template_selection_reason: 'A project status with decisions.',
    });

  it('states the format, how it was chosen and why', () => {
    state.meeting = formatted();
    renderWithProviders(<MeetingPage params={params} />);
    expect(screen.getByText('meetings.detail.format')).toBeInTheDocument();
    expect(screen.getByText('Meeting minutes')).toBeInTheDocument();
    expect(screen.getByText('meetings.detail.format_selection.auto')).toBeInTheDocument();
    expect(screen.getByText('A project status with decisions.')).toBeInTheDocument();
  });

  it('opens the format dialog and, on new minutes, goes to the new row', async () => {
    state.meeting = formatted();
    const { user } = renderWithProviders(<MeetingPage params={params} />);
    await user.click(screen.getByRole('button', { name: 'meetings.detail.change_format' }));
    const dialog = await screen.findByRole('dialog', { name: 'meetings.detail.reformat.title' });
    expect(dialog).toBeInTheDocument();
    await user.click(screen.getByRole('radio', { name: 'meetings.detail.reformat.mode_new' }));
    await user.click(screen.getByRole('button', { name: 'meetings.detail.reformat.submit' }));
    await waitFor(() =>
      expect(state.reformat).toHaveBeenCalledWith({
        template_ref: 'builtin:default_minutes',
        mode: 'new',
      })
    );
    expect(toast.success).toHaveBeenCalledWith('meetings.detail.reformat.started_new');
    expect(push).toHaveBeenCalledWith('/dashboard/meetings/m9');
  });

  it('links the source transcript and counts the minutes derived from this one', async () => {
    state.meeting = detail({ source_meeting_id: 'm0', derived_count: 2 });
    const { user } = renderWithProviders(<MeetingPage params={params} />);
    expect(screen.getByText('meetings.detail.derived_count')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'meetings.detail.derived_from' }));
    expect(push).toHaveBeenCalledWith('/dashboard/meetings/m0');
  });

  it('shows the pending panel for READY minutes not written yet, and the retry after a failure', async () => {
    state.meeting = detail({ stage: 'synthesizing', report: null, template_ref: 'builtin:x' });
    renderWithProviders(<MeetingPage params={params} />);
    expect(screen.getByText('meetings.detail.pending_title')).toBeInTheDocument();
    expect(screen.queryByText('meetings.detail.minutes_title')).not.toBeInTheDocument();

    state.meeting = detail({
      report: null,
      last_error_code: 'synthesis_failed',
      template_ref: 'builtin:x',
    });
    const { user } = renderWithProviders(<MeetingPage params={params} />);
    await user.click(screen.getByRole('button', { name: 'meetings.detail.try_again' }));
    await waitFor(() =>
      expect(state.reformat).toHaveBeenCalledWith({ template_ref: 'builtin:x', mode: 'replace' })
    );
    expect(toast.success).toHaveBeenCalledWith('meetings.detail.reformat.started_replace');
  });
});
