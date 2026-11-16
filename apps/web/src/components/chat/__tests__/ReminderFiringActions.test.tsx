/**
 * ReminderFiringActions — a reminder that rang, postponed or stopped from its
 * bubble (ADR-268 amendment 2026-11-16).
 *
 * The load-bearing behaviors: the block renders NOTHING (and asks the server
 * nothing) unless the bubble names a recorded occurrence whose window is open;
 * the delays come from the server's configuration; a press posts the choice and
 * its verdict replaces the buttons; a delay the series already covers keeps
 * them and says until when; « stop » asks first; and a press on the toast
 * settles the bubble of the same occurrence.
 */

import { act } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { dataQuery, errorQuery, loadingQuery } from '@/__tests__/api-mocks';
import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';
import {
  recordFiringVerdict,
  resetFiringVerdicts,
  type ReminderFiringState,
} from '@/lib/reminder-firing';

/** `t` that shows its interpolation, so the instants and counts can be read. */
const { i18nStub } = vi.hoisted(() => ({
  i18nStub: {
    t: (key: string, options?: Record<string, unknown>) =>
      options && Object.keys(options).length > 0
        ? `${key}(${Object.values(options).join(',')})`
        : key,
    i18n: { language: 'fr' },
  },
}));
vi.mock('react-i18next', () => ({ useTranslation: () => i18nStub }));

const { useApiQuery } = vi.hoisted(() => ({ useApiQuery: vi.fn() }));
vi.mock('@/hooks/useApiQuery', () => ({ useApiQuery }));

const { mutate } = vi.hoisted(() => ({
  mutate: vi.fn(async (_endpoint: string, _data?: unknown): Promise<unknown> => undefined),
}));
vi.mock('@/hooks/useApiMutation', () => ({
  useApiMutation: () => ({ mutate, loading: false, error: null, reset: vi.fn(), data: null }),
}));

const { confirm } = vi.hoisted(() => ({ confirm: vi.fn() }));
vi.mock('@/components/ui/use-confirm', () => ({
  useConfirm: () => ({ confirm, confirmDialog: null }),
}));

vi.mock('@/hooks/useAuth', () => ({ useAuth: () => ({ user: { timezone: 'Asia/Tokyo' } }) }));

const { toast } = vi.hoisted(() => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));
vi.mock('sonner', () => ({ toast }));

import { ReminderFiringActions } from '../ReminderFiringActions';

const FIRING = 'firing-1';
const IN_A_DAY = new Date(Date.now() + 86_400_000).toISOString();

const metadata = (overrides: Record<string, unknown> = {}) => ({
  type: 'reminder_notification',
  reminder_id: 'reminder-1',
  firing_id: FIRING,
  snoozable_until: IN_A_DAY,
  ...overrides,
});

const state = (overrides: Partial<ReminderFiringState> = {}): ReminderFiringState => ({
  id: FIRING,
  fired_at: new Date().toISOString(),
  snoozable_until: IN_A_DAY,
  snoozed_until: null,
  stoppable: false,
  short_minutes: 10,
  long_minutes: 60,
  ...overrides,
});

beforeEach(() => {
  vi.clearAllMocks();
  useApiQuery.mockReturnValue(dataQuery(state()));
  confirm.mockResolvedValue(true);
});

afterEach(() => {
  act(() => resetFiringVerdicts());
});

describe('scoping', () => {
  it.each([
    ['another notification', { type: 'proactive_interest' }],
    ['a reminder whose occurrence was not recorded', metadata({ firing_id: undefined })],
    ['a closed window', metadata({ snoozable_until: new Date(Date.now() - 1000).toISOString() })],
    ['an unreadable window', metadata({ snoozable_until: 'tomorrow' })],
  ])('renders and reads nothing for %s', (_case, meta) => {
    const { container } = renderWithProviders(<ReminderFiringActions metadata={meta} />);

    expect(container).toBeEmptyDOMElement();
    expect(useApiQuery).not.toHaveBeenCalled();
  });

  it('offers nothing before its state is read, nor when the read fails', () => {
    useApiQuery.mockReturnValue(loadingQuery());
    const loading = renderWithProviders(<ReminderFiringActions metadata={metadata()} />);
    expect(loading.container).toBeEmptyDOMElement();
    loading.unmount();

    useApiQuery.mockReturnValue(errorQuery('Not Found'));
    const failed = renderWithProviders(<ReminderFiringActions metadata={metadata()} />);
    expect(failed.container).toBeEmptyDOMElement();
  });
});

describe('the offer', () => {
  it('names the three delays the server configured, and reads the occurrence once', () => {
    renderWithProviders(<ReminderFiringActions metadata={metadata()} />);

    expect(screen.getByRole('group', { name: 'reminders.firing.actions_label' })).toBeVisible();
    expect(
      screen.getByRole('button', { name: /reminders\.firing\.in_minutes\(10\)/ })
    ).toBeVisible();
    expect(screen.getByRole('button', { name: /reminders\.firing\.in_hours\(1\)/ })).toBeVisible();
    expect(
      screen.getByRole('button', { name: /reminders\.firing\.tomorrow_morning/ })
    ).toBeVisible();
    expect(screen.queryByRole('button', { name: /reminders\.firing\.stop/ })).toBeNull();
    expect(useApiQuery).toHaveBeenCalledWith(`/reminders/firings/${FIRING}`, expect.anything());
  });

  it('offers « stop » for a reminder with a future', () => {
    useApiQuery.mockReturnValue(dataQuery(state({ stoppable: true })));

    renderWithProviders(<ReminderFiringActions metadata={metadata()} />);

    expect(screen.getByRole('button', { name: /reminders\.firing\.stop$/ })).toBeVisible();
  });

  it('says where another device already put it, and offers no delay', () => {
    const back = '2026-11-17T00:00:00Z';
    useApiQuery.mockReturnValue(dataQuery(state({ snoozed_until: back, stoppable: true })));

    renderWithProviders(<ReminderFiringActions metadata={metadata()} />);

    expect(screen.getByRole('status')).toHaveTextContent('reminders.firing.snoozed(');
    expect(screen.getByRole('status')).toHaveTextContent('09:00'); // Tokyo, the account's zone
    expect(screen.queryByRole('button', { name: /in_minutes/ })).toBeNull();
    expect(screen.getByRole('button', { name: /reminders\.firing\.stop$/ })).toBeVisible();
  });
});

describe('a press', () => {
  it('posts the choice and replaces the delays with its verdict', async () => {
    mutate.mockResolvedValueOnce({
      outcome: 'snoozed',
      snoozed_until: '2026-11-17T00:00:00Z',
      next_occurrence_at: null,
    });
    const { user } = renderWithProviders(<ReminderFiringActions metadata={metadata()} />);

    await user.click(screen.getByRole('button', { name: /reminders\.firing\.tomorrow_morning/ }));

    expect(mutate).toHaveBeenCalledWith(`/reminders/firings/${FIRING}/snooze`, {
      choice: 'morning',
      surface: 'chat',
    });
    await waitFor(() =>
      expect(screen.getByRole('status')).toHaveTextContent('reminders.firing.snoozed(')
    );
    expect(screen.queryByRole('button', { name: /tomorrow_morning/ })).toBeNull();
  });

  it('a keyboard press leaves the focus on the verdict, not on the page', async () => {
    mutate.mockResolvedValueOnce({
      outcome: 'snoozed',
      snoozed_until: '2026-11-17T00:00:00Z',
      next_occurrence_at: null,
    });
    const { user } = renderWithProviders(<ReminderFiringActions metadata={metadata()} />);

    await user.tab();
    expect(screen.getByRole('button', { name: /in_minutes/ })).toHaveFocus();
    await user.keyboard('{Enter}');

    await waitFor(() => expect(screen.getByRole('status')).toHaveFocus());
    expect(screen.getByRole('status')).toHaveTextContent('reminders.firing.snoozed(');
  });

  it('keeps the delays when the series already comes back first, and says when', async () => {
    mutate.mockResolvedValueOnce({
      outcome: 'collides',
      snoozed_until: null,
      next_occurrence_at: '2026-11-17T00:00:00Z',
    });
    const { user } = renderWithProviders(<ReminderFiringActions metadata={metadata()} />);

    await user.click(screen.getByRole('button', { name: /reminders\.firing\.tomorrow_morning/ }));

    await waitFor(() =>
      expect(screen.getByRole('status')).toHaveTextContent('reminders.firing.collides(')
    );
    expect(screen.getByRole('status')).toHaveTextContent('09:00');
    expect(screen.getByRole('button', { name: /reminders\.firing\.in_minutes/ })).toBeVisible();
  });

  it('says the window closed and offers no delay any more', async () => {
    mutate.mockResolvedValueOnce({
      outcome: 'expired',
      snoozed_until: null,
      next_occurrence_at: null,
    });
    const { user } = renderWithProviders(<ReminderFiringActions metadata={metadata()} />);

    await user.click(screen.getByRole('button', { name: /reminders\.firing\.in_minutes/ }));

    await waitFor(() =>
      expect(screen.getByRole('status')).toHaveTextContent('reminders.firing.expired')
    );
    expect(screen.queryByRole('button', { name: /in_minutes/ })).toBeNull();
  });

  it('says a failure and keeps the delays', async () => {
    mutate.mockRejectedValueOnce(new Error('network'));
    const { user } = renderWithProviders(<ReminderFiringActions metadata={metadata()} />);

    await user.click(screen.getByRole('button', { name: /reminders\.firing\.in_hours/ }));

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('reminders.firing.failed'));
    expect(screen.getByRole('button', { name: /reminders\.firing\.in_hours/ })).toBeVisible();
  });
});

describe('stop', () => {
  beforeEach(() => {
    useApiQuery.mockReturnValue(dataQuery(state({ stoppable: true })));
  });

  it('asks first, then stops the series', async () => {
    mutate.mockResolvedValueOnce({ outcome: 'stopped' });
    const { user } = renderWithProviders(<ReminderFiringActions metadata={metadata()} />);

    await user.click(screen.getByRole('button', { name: /reminders\.firing\.stop$/ }));

    expect(confirm).toHaveBeenCalledWith(
      expect.objectContaining({ title: 'reminders.firing.stop_title' })
    );
    expect(mutate).toHaveBeenCalledWith(`/reminders/firings/${FIRING}/stop`);
    await waitFor(() =>
      expect(screen.getByRole('status')).toHaveTextContent('reminders.firing.stopped')
    );
    expect(screen.queryByRole('button', { name: /reminders\.firing\.stop$/ })).toBeNull();
  });

  it('a copy postponed before the stop is still announced beside it', async () => {
    useApiQuery.mockReturnValue(
      dataQuery(state({ stoppable: true, snoozed_until: '2026-11-17T00:00:00Z' }))
    );
    mutate.mockResolvedValueOnce({ outcome: 'stopped' });
    const { user } = renderWithProviders(<ReminderFiringActions metadata={metadata()} />);

    await user.click(screen.getByRole('button', { name: /reminders\.firing\.stop$/ }));

    await waitFor(() =>
      expect(screen.getByRole('status')).toHaveTextContent('reminders.firing.stopped')
    );
    expect(screen.getByRole('status')).toHaveTextContent('reminders.firing.snoozed(');
  });

  it('a declined confirmation stops nothing', async () => {
    confirm.mockResolvedValueOnce(false);
    const { user } = renderWithProviders(<ReminderFiringActions metadata={metadata()} />);

    await user.click(screen.getByRole('button', { name: /reminders\.firing\.stop$/ }));

    expect(mutate).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: /reminders\.firing\.stop$/ })).toBeVisible();
  });
});

it('withdraws the delays when the window closes while the page stays open', () => {
  vi.useFakeTimers();
  try {
    const closesSoon = new Date(Date.now() + 60_000).toISOString();
    useApiQuery.mockReturnValue(dataQuery(state({ snoozable_until: closesSoon })));
    renderWithProviders(
      <ReminderFiringActions metadata={metadata({ snoozable_until: closesSoon })} />
    );
    expect(screen.getByRole('button', { name: /reminders\.firing\.in_minutes/ })).toBeVisible();

    act(() => {
      vi.advanceTimersByTime(60_001);
    });

    expect(screen.queryByRole('button', { name: /in_minutes/ })).toBeNull();
    expect(screen.getByRole('status')).toHaveTextContent('reminders.firing.expired');
  } finally {
    vi.useRealTimers();
  }
});

it('follows a press made on the toast of the same occurrence', () => {
  renderWithProviders(<ReminderFiringActions metadata={metadata()} />);

  act(() => recordFiringVerdict(FIRING, { snoozedUntil: '2026-11-17T00:00:00Z' }));

  expect(screen.getByRole('status')).toHaveTextContent('reminders.firing.snoozed(');
  expect(screen.queryByRole('button', { name: /in_minutes/ })).toBeNull();
});
