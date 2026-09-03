/**
 * The meetings list page: skeleton on first load, an actionable empty state,
 * one named row per meeting, pagination only past one page.
 */

import { describe, expect, it, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';
import type { MeetingSummary } from '@/types/meetings';

const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }));
vi.mock('sonner', () => ({ toast }));

const list = vi.hoisted(() => ({
  meetings: [] as MeetingSummary[],
  total: 0,
  isLoading: false,
  isUnavailable: false,
  isDeleting: false,
  bulkDelete: vi.fn(),
  refetch: vi.fn(),
}));
vi.mock('@/hooks/useMeetings', () => ({
  useMeetingList: () => ({ ...list, error: null }),
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
vi.mock('@/hooks/useLanguageParam', () => ({ useLanguageParam: () => 'en' }));
const recorder = vi.hoisted(() => ({
  value: null as { start: () => Promise<void>; isLive: boolean; phase: string } | null,
}));
vi.mock('@/components/meetings/MeetingRecorderProvider', () => ({
  useMeetingRecorderContext: () => recorder.value,
}));
const push = vi.fn();
vi.mock('@/hooks/useLocalizedRouter', () => ({
  useLocalizedRouter: () => ({ push, replace: vi.fn(), back: vi.fn() }),
}));

import MeetingsPage from '../page';

function summary(over: Partial<MeetingSummary> = {}): MeetingSummary {
  return {
    id: 'm1',
    status: 'ready',
    stage: null,
    title: 'Point projet',
    started_at: '2026-09-02T10:00:00Z',
    stopped_at: '2026-09-02T11:00:00Z',
    audio_duration_seconds: 3600,
    participants_count: 3,
    action_items_count: 2,
    index_state: 'indexed',
    stt_provider: 'elevenlabs',
    total_cost_eur: null,
    last_error_code: null,
    template_ref: null,
    template_name: null,
    template_selection: null,
    source_meeting_id: null,
    ...over,
  };
}

const params = Promise.resolve({ lng: 'en' });

beforeEach(() => {
  vi.clearAllMocks();
  list.meetings = [];
  list.total = 0;
  list.isLoading = false;
  list.isUnavailable = false;
  list.isDeleting = false;
  list.bulkDelete.mockResolvedValue({ deleted: [], skipped: [] });
  confirm.answer = true;
  confirm.calls = [];
});

describe('MeetingsPage', () => {
  it('announces the first load', () => {
    list.isLoading = true;
    renderWithProviders(<MeetingsPage params={params} />);
    expect(screen.getByRole('status')).toBeInTheDocument();
  });

  it('offers the chat when there is no meeting yet', async () => {
    const { user } = renderWithProviders(<MeetingsPage params={params} />);
    expect(screen.getByText('meetings.list.empty_title')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'meetings.list.empty_action' }));
    expect(push).toHaveBeenCalledWith('/dashboard/chat');
  });

  it('names every row after its meeting and opens it', async () => {
    list.meetings = [
      summary(),
      summary({ id: 'm2', title: null, status: 'processing', stage: 'transcribing' }),
    ];
    list.total = 2;
    const { user } = renderWithProviders(<MeetingsPage params={params} />);
    expect(screen.getByText('meetings.list.total')).toBeInTheDocument();
    await user.click(screen.getAllByRole('button', { name: 'meetings.list.open' })[0]);
    expect(push).toHaveBeenCalledWith('/dashboard/meetings/m1');
    expect(screen.getByText('meetings.list.untitled')).toBeInTheDocument();
    expect(screen.getByText('meetings.stage.transcribing')).toBeInTheDocument();
    expect(screen.queryByRole('navigation')).not.toBeInTheDocument();
  });

  it('paginates only when the total exceeds one page', () => {
    list.meetings = [summary()];
    list.total = 45;
    renderWithProviders(<MeetingsPage params={params} />);
    const nav = screen.getByRole('navigation', { name: 'common.pagination' });
    expect(nav).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'common.previous' })).toHaveAttribute(
      'aria-disabled',
      'true'
    );
    expect(screen.getByRole('button', { name: 'common.next' })).toHaveAttribute(
      'aria-disabled',
      'false'
    );
  });
});

describe('MeetingsPage — cost in the row', () => {
  it('appends what a meeting cost when anything priced was spent, nothing otherwise', () => {
    list.meetings = [summary({ total_cost_eur: 0.0167 }), summary({ id: 'm2', title: 'Free' })];
    list.total = 2;
    renderWithProviders(<MeetingsPage params={params} />);
    expect(screen.getByText(/€0\.0167/)).toBeInTheDocument();
    expect(screen.getAllByText(/€/)).toHaveLength(1);
  });
});

describe('MeetingsPage — selection and bulk delete (ADR-259)', () => {
  it('offers a named checkbox per row and refuses to select an in-flight row', async () => {
    list.meetings = [
      summary(),
      summary({ id: 'm2', title: 'Daily', status: 'processing', stage: 'transcribing' }),
    ];
    list.total = 2;
    const { user } = renderWithProviders(<MeetingsPage params={params} />);
    const boxes = screen.getAllByRole('checkbox', { name: 'meetings.list.select_row' });
    expect(boxes).toHaveLength(2);
    expect(boxes[1]).toHaveAttribute('aria-disabled', 'true');
    await user.click(boxes[1]);
    expect(boxes[1]).not.toBeChecked();
    expect(screen.queryByRole('button', { name: 'meetings.list.delete_selected' })).toBeNull();
  });

  it('shows the selection bar, confirms and deletes the selected ids, then clears', async () => {
    list.meetings = [summary(), summary({ id: 'm2', title: 'Daily' })];
    list.total = 2;
    list.bulkDelete.mockResolvedValue({ deleted: ['m1', 'm2'], skipped: [] });
    const { user } = renderWithProviders(<MeetingsPage params={params} />);
    const boxes = screen.getAllByRole('checkbox', { name: 'meetings.list.select_row' });
    await user.click(boxes[0]);
    await user.click(boxes[1]);
    expect(screen.getByText('meetings.list.selected_count')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'meetings.list.delete_selected' }));
    expect(confirm.calls).toHaveLength(1);
    await waitFor(() => expect(list.bulkDelete).toHaveBeenCalledWith(['m1', 'm2']));
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('meetings.list.bulk_deleted'));
    expect(screen.queryByText('meetings.list.selected_count')).toBeNull();
  });

  it('selects every selectable row of the page at once and reports the skipped ones', async () => {
    list.meetings = [
      summary(),
      summary({ id: 'm2', title: 'Daily' }),
      summary({ id: 'm3', title: 'Live', status: 'recording' }),
    ];
    list.total = 3;
    list.bulkDelete.mockResolvedValue({
      deleted: ['m1'],
      skipped: [{ id: 'm2', code: 'meeting_in_progress' }],
    });
    const { user } = renderWithProviders(<MeetingsPage params={params} />);
    await user.click(screen.getAllByRole('checkbox', { name: 'meetings.list.select_row' })[0]);
    await user.click(screen.getByRole('checkbox', { name: 'meetings.list.select_all_page' }));
    const boxes = screen.getAllByRole('checkbox', { name: 'meetings.list.select_row' });
    expect(boxes[0]).toBeChecked();
    expect(boxes[1]).toBeChecked();
    expect(boxes[2]).not.toBeChecked();
    await user.click(screen.getByRole('button', { name: 'meetings.list.delete_selected' }));
    await waitFor(() => expect(list.bulkDelete).toHaveBeenCalledWith(['m1', 'm2']));
    await waitFor(() => expect(toast.info).toHaveBeenCalledWith('meetings.list.bulk_skipped'));
  });

  it('does nothing when the confirmation is declined', async () => {
    list.meetings = [summary()];
    list.total = 1;
    confirm.answer = false;
    const { user } = renderWithProviders(<MeetingsPage params={params} />);
    await user.click(screen.getByRole('checkbox', { name: 'meetings.list.select_row' }));
    await user.click(screen.getByRole('button', { name: 'meetings.list.delete_selected' }));
    expect(list.bulkDelete).not.toHaveBeenCalled();
    expect(screen.getByRole('checkbox', { name: 'meetings.list.select_row' })).toBeChecked();
  });

  it('steps back a page when the deletion empties a page that is not the first', async () => {
    list.meetings = [summary()];
    list.total = 21;
    list.bulkDelete.mockResolvedValue({ deleted: ['m1'], skipped: [] });
    const { user } = renderWithProviders(<MeetingsPage params={params} />);
    await user.click(screen.getByRole('button', { name: 'common.next' }));
    await user.click(screen.getByRole('checkbox', { name: 'meetings.list.select_row' }));
    await user.click(screen.getByRole('button', { name: 'meetings.list.delete_selected' }));
    await waitFor(() => expect(list.bulkDelete).toHaveBeenCalledWith(['m1']));
    // Back on the first page: « previous » is disabled again.
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'common.previous' })).toHaveAttribute(
        'aria-disabled',
        'true'
      )
    );
  });
});

describe('MeetingsPage — toolbar and format (ADR-259)', () => {
  it('records from the toolbar when the recorder is mounted, and reaches the templates', async () => {
    const start = vi.fn().mockResolvedValue(undefined);
    recorder.value = { start, isLive: false, phase: 'idle' };
    list.meetings = [summary()];
    list.total = 1;
    const { user } = renderWithProviders(<MeetingsPage params={params} />);
    await user.click(screen.getByRole('button', { name: 'meetings.list.record' }));
    expect(start).toHaveBeenCalledTimes(1);
    await user.click(screen.getByRole('button', { name: 'meetings.list.templates' }));
    expect(push).toHaveBeenCalledWith('/dashboard/meetings/templates');
    recorder.value = null;
  });

  it('hides the record CTA without a recorder and states it while live', () => {
    recorder.value = null;
    list.meetings = [summary()];
    list.total = 1;
    renderWithProviders(<MeetingsPage params={params} />);
    expect(screen.queryByRole('button', { name: 'meetings.list.record' })).not.toBeInTheDocument();

    recorder.value = { start: vi.fn(), isLive: true, phase: 'recording' };
    renderWithProviders(<MeetingsPage params={params} />);
    expect(screen.getByRole('button', { name: 'meetings.list.record' })).toHaveAttribute(
      'aria-disabled',
      'true'
    );
    recorder.value = null;
  });

  it('names the format of a meeting in its row', () => {
    list.meetings = [summary({ template_name: 'Daily standup' })];
    list.total = 1;
    renderWithProviders(<MeetingsPage params={params} />);
    expect(screen.getByText(/Daily standup/)).toBeInTheDocument();
  });
});
