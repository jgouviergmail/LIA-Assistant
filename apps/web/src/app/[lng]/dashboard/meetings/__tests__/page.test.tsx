/**
 * The meetings list page: skeleton on first load, an actionable empty state,
 * one named row per meeting, pagination only past one page.
 */

import { describe, expect, it, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import type { MeetingSummary } from '@/types/meetings';

const list = vi.hoisted(() => ({
  meetings: [] as MeetingSummary[],
  total: 0,
  isLoading: false,
  isUnavailable: false,
}));
vi.mock('@/hooks/useMeetings', () => ({
  useMeetingList: () => ({ ...list, error: null, refetch: vi.fn() }),
}));
vi.mock('@/hooks/useLanguageParam', () => ({ useLanguageParam: () => 'en' }));
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

