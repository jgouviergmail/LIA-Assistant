/**
 * ActivityTimeline — the feed of what LIA did proactively.
 *
 * The rules a reader would notice being broken:
 *  - first load shows the skeleton geometry, a refetch NEVER unmounts the
 *    list (aria-busy states it instead);
 *  - emptiness on a whole page carries a way out (the proactivity settings);
 *  - a failed source is STATED (partial-data warning), never silent;
 *  - counts come from the exact totals, and a truncated pool says so;
 *  - events group under local day headings, newest first.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import userEvent from '@testing-library/user-event';

const { useActivityTimeline } = vi.hoisted(() => ({ useActivityTimeline: vi.fn() }));
vi.mock('@/hooks/useActivityTimeline', async importOriginal => ({
  ...(await importOriginal<typeof import('@/hooks/useActivityTimeline')>()),
  useActivityTimeline,
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) =>
      opts && 'count' in opts ? `${key}|${opts.count}` : key,
    i18n: { language: 'fr' },
  }),
}));

import { ActivityTimeline } from '../ActivityTimeline';
import type { ActivityEvent } from '@/types/activity';

function event(over: Partial<ActivityEvent> = {}): ActivityEvent {
  return {
    kind: 'habit_detected',
    ref_id: crypto.randomUUID(),
    occurred_at: '2026-08-19T10:00:00Z',
    text: 'evening_review',
    status: null,
    ...over,
  };
}

function hookState(over: Record<string, unknown> = {}) {
  useActivityTimeline.mockReturnValue({
    events: [],
    totals: [],
    failedKinds: [],
    windowDays: 30,
    hasMore: false,
    firstLoad: false,
    loading: false,
    error: null,
    loadMore: vi.fn(),
    refetch: vi.fn(),
    ...over,
  });
}

beforeEach(() => {
  useActivityTimeline.mockReset();
});

describe('ActivityTimeline', () => {
  it('shows the skeleton geometry on first load, without the list', () => {
    hookState({ events: undefined, firstLoad: true, loading: true });

    renderWithProviders(<ActivityTimeline lng="fr" />);

    expect(screen.queryByRole('list')).not.toBeInTheDocument();
    expect(document.querySelector('[data-slot="activity-skeleton"]')).toBeInTheDocument();
  });

  it('renders events under local day headings with kind labels', () => {
    hookState({
      events: [
        event({ kind: 'heartbeat_notification', text: 'Il pleut demain', ref_id: 'a' }),
        event({
          kind: 'open_loop_closed',
          text: 'rappeler le plombier',
          ref_id: 'b',
          occurred_at: '2026-08-18T09:00:00Z',
        }),
      ],
    });

    renderWithProviders(<ActivityTimeline lng="fr" />);

    expect(screen.getByText('activity.rows.heartbeat_notification')).toBeInTheDocument();
    expect(screen.getByText('Il pleut demain')).toBeInTheDocument();
    expect(screen.getByText('activity.rows.open_loop_closed')).toBeInTheDocument();
    // Two different local days → two day group headings.
    expect(screen.getAllByRole('list')).toHaveLength(2);
  });

  it('summarizes exact totals as chips and flags a truncated pool', () => {
    hookState({
      events: [event({ ref_id: 'a' })],
      totals: [
        { kind: 'habit_detected', total: 3, truncated: false },
        { kind: 'heartbeat_notification', total: 250, truncated: true },
      ],
    });

    renderWithProviders(<ActivityTimeline lng="fr" />);

    expect(screen.getByText('activity.kinds.habit_detected|3')).toBeInTheDocument();
    expect(screen.getByText('activity.kinds.heartbeat_notification|250')).toBeInTheDocument();
    expect(screen.getByText('activity.truncated_hint')).toBeInTheDocument();
  });

  it('states partial data when a source failed', () => {
    hookState({
      events: [event()],
      failedKinds: ['interest_notification'],
    });

    renderWithProviders(<ActivityTimeline lng="fr" />);

    expect(screen.getByText('activity.partial_warning')).toBeInTheDocument();
  });

  it('offers the proactivity settings as the way out of an empty page', () => {
    hookState({ events: [] });

    renderWithProviders(<ActivityTimeline lng="fr" />);

    const action = screen.getByRole('link', { name: 'activity.empty_action' });
    expect(action).toHaveAttribute('href', expect.stringContaining('settings'));
  });

  it('loads more through a labelled button', async () => {
    const loadMore = vi.fn();
    hookState({ events: [event()], hasMore: true, loadMore });

    renderWithProviders(<ActivityTimeline lng="fr" />);
    await userEvent.click(screen.getByRole('button', { name: 'activity.load_more' }));

    expect(loadMore).toHaveBeenCalledTimes(1);
  });

  it('announces a refetch with aria-busy instead of unmounting the feed', () => {
    hookState({ events: [event({ text: 'still visible' })], loading: true });

    renderWithProviders(<ActivityTimeline lng="fr" />);

    expect(screen.getByText('still visible')).toBeInTheDocument();
    expect(document.querySelector('[aria-busy="true"]')).toBeInTheDocument();
  });

  it('surfaces the initial error with a retry', async () => {
    const refetch = vi.fn();
    hookState({ events: undefined, error: new Error('boom'), refetch });

    renderWithProviders(<ActivityTimeline lng="fr" />);
    await userEvent.click(screen.getByRole('button', { name: 'activity.retry' }));

    expect(screen.getByText('activity.error_description')).toBeInTheDocument();
    expect(refetch).toHaveBeenCalledTimes(1);
  });
});
