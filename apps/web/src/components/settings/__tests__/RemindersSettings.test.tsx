/**
 * RemindersSettings — the screen the domain refused until 2026-09-06.
 *
 * The reversal is deliberate and its contract is pinned here: creating,
 * editing and deleting a reminder, plus the two things the reversal did NOT
 * change — an empty list means "nothing is coming", never "nothing was ever
 * sent", and a poll must never unmount the section under the reader.
 *
 * The last class is the point of the whole recurrence programme: this screen
 * mounts `RecurrenceEditor` with a reminder's own ceilings and nothing else.
 */

import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { describe, it, expect, vi, beforeEach } from 'vitest';
import userEvent from '@testing-library/user-event';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';
import type { Reminder } from '@/hooks/useReminders';
import type { RecurrenceSpec } from '@/types/recurrence';

const { useReminders } = vi.hoisted(() => ({ useReminders: vi.fn() }));
vi.mock('@/hooks/useReminders', () => ({ useReminders }));
const { toast } = vi.hoisted(() => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('sonner', () => ({ toast }));

import { RemindersSettings } from '../RemindersSettings';

function spec(over: Partial<RecurrenceSpec> = {}): RecurrenceSpec {
  return {
    freq: 'daily',
    interval: 1,
    anchor_date: '2026-09-06',
    byweekday: [],
    bymonthday: [],
    nth_weekday: null,
    bymonth: [],
    times: { mode: 'at', at: [{ hour: 8, minute: 0 }], step_minutes: null, start: null, end: null },
    end: { kind: 'never', on_date: null, after_count: null },
    ...over,
  };
}

function reminder(over: Partial<Reminder> = {}): Reminder {
  return {
    id: 'r1',
    content: 'prendre les vitamines',
    trigger_at: '2026-09-07T06:00:00Z',
    user_timezone: 'Europe/Paris',
    recurrence: spec(),
    schedule_display: 'Tous les jours, à 08:00',
    times_of_day: ['08:00'],
    runs_per_day: 1,
    next_occurrences: ['2026-09-07T06:00:00Z'],
    created_at: '2026-09-01T10:00:00Z',
    ...over,
  };
}

type Hook = ReturnType<typeof import('@/hooks/useReminders').useReminders>;

function hook(over: Partial<Hook> = {}): Hook {
  return {
    reminders: [],
    total: 0,
    loading: false,
    initialLoading: false,
    error: null,
    refetch: vi.fn(),
    createReminder: vi.fn().mockResolvedValue(reminder()),
    updateReminder: vi.fn().mockResolvedValue(reminder()),
    deleteReminder: vi.fn().mockResolvedValue(undefined),
    creating: false,
    updating: false,
    deleting: false,
    ...over,
  } as Hook;
}

beforeEach(() => {
  vi.clearAllMocks();
  useReminders.mockReturnValue(hook());
});

describe('the list', () => {
  it('says nothing is COMING, not that nothing was ever sent', () => {
    renderWithProviders(<RemindersSettings lng="fr" />);
    // A reminder is deleted the moment it has no future, so an empty list can
    // only mean the future is empty.
    expect(screen.getByText('reminders.empty')).toBeInTheDocument();
    expect(screen.getByText('reminders.empty_hint')).toBeInTheDocument();
  });

  it('shows the sentence the SERVER composed, never one built here', () => {
    useReminders.mockReturnValue(hook({ reminders: [reminder()], total: 1 }));
    renderWithProviders(<RemindersSettings lng="fr" />);

    expect(screen.getByText('Tous les jours, à 08:00')).toBeInTheDocument();
  });

  it('states how many times a day a busy reminder fires', () => {
    useReminders.mockReturnValue(
      hook({ reminders: [reminder({ runs_per_day: 3 })], total: 1 })
    );
    renderWithProviders(<RemindersSettings lng="fr" />);

    expect(screen.getByText('recurrence.summary_per_day')).toBeInTheDocument();
  });

  it('does not repeat the per-day line for a once-a-day reminder', () => {
    useReminders.mockReturnValue(hook({ reminders: [reminder()], total: 1 }));
    renderWithProviders(<RemindersSettings lng="fr" />);

    expect(screen.queryByText('recurrence.summary_per_day')).not.toBeInTheDocument();
  });

  it('spins on the FIRST load only', () => {
    useReminders.mockReturnValue(hook({ initialLoading: true }));
    const { container } = renderWithProviders(<RemindersSettings lng="fr" />);
    expect(container.querySelector('[aria-busy]')).toBeInTheDocument();
    expect(screen.queryByText('reminders.empty')).not.toBeInTheDocument();
  });

  it('keeps the populated list mounted while a refresh runs', () => {
    // `loading` true with data present is a REFRESH. Swapping the list for a
    // spinner here would unmount every row under the reader.
    useReminders.mockReturnValue(
      hook({ reminders: [reminder()], total: 1, loading: true, initialLoading: false })
    );
    renderWithProviders(<RemindersSettings lng="fr" />);

    expect(screen.getByText('prendre les vitamines')).toBeInTheDocument();
  });
});

describe('deleting', () => {
  it('warns that a repeating reminder is a SERIES', async () => {
    const user = userEvent.setup();
    useReminders.mockReturnValue(hook({ reminders: [reminder()], total: 1 }));
    renderWithProviders(<RemindersSettings lng="fr" />);

    await user.click(screen.getByRole('button', { name: 'common.delete' }));

    // Deleting removes every future occurrence, not just the next one.
    expect(await screen.findByText('reminders.delete_series_confirm')).toBeInTheDocument();
  });

  it('says simply "this will be deleted" for a single occurrence', async () => {
    const user = userEvent.setup();
    useReminders.mockReturnValue(
      hook({ reminders: [reminder({ recurrence: spec({ freq: 'once' }) })], total: 1 })
    );
    renderWithProviders(<RemindersSettings lng="fr" />);

    await user.click(screen.getByRole('button', { name: 'common.delete' }));

    expect(await screen.findByText('reminders.delete_confirm')).toBeInTheDocument();
  });

  it('asks before it acts', async () => {
    const user = userEvent.setup();
    const deleteReminder = vi.fn().mockResolvedValue(undefined);
    useReminders.mockReturnValue(hook({ reminders: [reminder()], total: 1, deleteReminder }));
    renderWithProviders(<RemindersSettings lng="fr" />);

    await user.click(screen.getByRole('button', { name: 'common.delete' }));
    expect(deleteReminder).not.toHaveBeenCalled();

    await user.click(screen.getByRole('button', { name: 'common.delete', hidden: false }));
    await waitFor(() => expect(deleteReminder).toHaveBeenCalledWith('r1'));
  });
});

describe('creating', () => {
  it('refuses to save an empty reminder without disabling the control', async () => {
    const user = userEvent.setup();
    const createReminder = vi.fn();
    useReminders.mockReturnValue(hook({ createReminder }));
    renderWithProviders(<RemindersSettings lng="fr" />);

    await user.click(screen.getByRole('button', { name: /reminders.create/ }));
    const save = await screen.findByRole('button', { name: 'common.save' });

    // `aria-disabled`, never `disabled`: the latter blurs a focused control
    // and drops it from the tab order.
    expect(save).toHaveAttribute('aria-disabled', 'true');
    await user.click(save);
    expect(createReminder).not.toHaveBeenCalled();
  });

  it('sends the recurrence the editor produced', async () => {
    const user = userEvent.setup();
    const createReminder = vi.fn().mockResolvedValue(reminder());
    useReminders.mockReturnValue(hook({ createReminder }));
    renderWithProviders(<RemindersSettings lng="fr" />);

    await user.click(screen.getByRole('button', { name: /reminders.create/ }));
    await user.type(screen.getByLabelText('reminders.field_content'), 'appeler le medecin');
    await user.click(screen.getByRole('button', { name: 'common.save' }));

    await waitFor(() => expect(createReminder).toHaveBeenCalled());
    const payload = createReminder.mock.calls[0][0];
    expect(payload.content).toBe('appeler le medecin');
    // The column is NOT NULL and the notification prompt reads it: a reminder
    // created here has no conversation behind it, so it says what was typed.
    expect(payload.original_message).toBe('appeler le medecin');
    expect(payload.recurrence).toBeTruthy();
    // NO `trigger_at`: the API derives the armed instant from the recurrence.
    // Sending both would be a second authority on when the reminder fires —
    // the card announcing one time and the notification arriving at another
    // (measured 2026-09-06, before the schema refused it).
    expect(payload.trigger_at).toBeUndefined();
  });
});

describe('the generic editor is reused, not copied', () => {
  const SOURCE = readFileSync(
    join(process.cwd(), 'src/components/settings/RemindersSettings.tsx'),
    'utf8'
  );

  it('mounts the SAME editor the routines mount', () => {
    expect(SOURCE).toContain("from '@/components/recurrence/RecurrenceEditor'");
    expect(SOURCE).toContain('<RecurrenceEditor');
  });

  it('injects a REMINDER ceiling, not the routines one', () => {
    // 48 a day against a routine's 12: same engine, different caller. This is
    // what `RecurrenceLimits` exists for.
    expect(SOURCE).toMatch(/maxTimesPerDay:\s*48/);
    expect(SOURCE).toMatch(/minStepMinutes:\s*5/);
  });

  it('declares no recurrence field of its own', () => {
    // A weekday picker or a clock select copied into this file would mean the
    // editor was the routines' editor wearing a different name.
    for (const forbidden of ['WeekdayPicker', 'ClockSelect', 'MonthDayPicker', 'byweekday']) {
      expect(SOURCE).not.toContain(forbidden);
    }
  });

  it('opens its dialog constrained in dvh and scrolling inside', () => {
    // The editor is tall; without this the save button is unreachable on a
    // phone — the defect found on the routines' dialog on 2026-09-06.
    const dialog = SOURCE.match(/<DialogContent className="([^"]*)"/)?.[1] ?? '';
    expect(dialog).toContain('overflow-y-auto');
    expect(dialog).toMatch(/max-h-\[\d+dvh\]/);
  });
});

describe('a cap is stated, never applied in silence', () => {
  it('says how many it could show when the page is smaller than the total', () => {
    // Reminders have no per-user ceiling, so a busy account can hold more than
    // one page. Rendering an exact total of 120 above 100 rows without saying
    // so is the defect ADR-185 names.
    useReminders.mockReturnValue(
      hook({ reminders: [reminder(), reminder({ id: 'r2' })], total: 120 })
    );
    renderWithProviders(<RemindersSettings lng="fr" />);

    expect(screen.getByText('reminders.settings.capped')).toBeInTheDocument();
  });

  it('stays quiet when the page holds everything', () => {
    useReminders.mockReturnValue(hook({ reminders: [reminder()], total: 1 }));
    renderWithProviders(<RemindersSettings lng="fr" />);

    expect(screen.queryByText('reminders.settings.capped')).not.toBeInTheDocument();
  });
});
