/**
 * ScheduledActionsTimeline — the weekly grid (ADR-265).
 *
 * What is pinned: the table semantics a screen reader walks (seven column
 * headers, twenty-four row headers, a caption naming the zone), one chip per
 * configured day carrying a full accessible name, the five colours by DATA
 * attribute rather than by class, the chronological order inside a cell, the
 * column of today read in the routines' zone, the honest "unavailable" line
 * when the week could not be read, and the navigation to the card.
 *
 * `t` here interpolates, unlike the global stub: the chip's name is the one
 * string in this component where the wording matters to the assertion.
 */

import { describe, it, expect, vi } from 'vitest';

import { renderWithProviders, screen, within } from '@/__tests__/test-utils';

/** The keys whose interpolation an assertion reads; every other key echoes. */
const TEMPLATES: Record<string, string> = {
  'scheduled_actions.timeline.chip_aria': '{{n}}, {{title}}, {{time}}, {{state}}',
  'scheduled_actions.timeline.caption': 'caption {{zone}}',
  'scheduled_actions.timeline.hours_in_zone': 'hours_in_zone {{zone}}',
  'scheduled_actions.timeline.run_at': 'run_at {{when}}',
};

vi.mock('@/i18n/client', () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) =>
      Object.entries(options ?? {}).reduce(
        (text, [name, value]) => text.replaceAll(`{{${name}}}`, String(value)),
        TEMPLATES[key] ?? key
      ),
    i18n: { language: 'en', changeLanguage: vi.fn() },
  }),
}));

import type { ScheduledAction, ScheduledActionWeekResponse } from '@/hooks/useScheduledActions';
import { numberByTriggerTime } from '@/lib/scheduled-actions';

import { ScheduledActionsTimeline } from '../ScheduledActionsTimeline';

function routine(over: Partial<ScheduledAction> = {}): ScheduledAction {
  return {
    id: 'r',
    user_id: 'u1',
    title: 'Morning brief',
    action_prompt: 'do',
    days_of_week: [1, 3],
    trigger_hour: 8,
    trigger_minute: 5,
    user_timezone: 'Europe/Paris',
    trigger_kind: 'time',
    condition_config: null,
    requires_approval: false,
    next_trigger_at: '2026-08-03T06:05:00Z',
    is_enabled: true,
    status: 'active',
    last_executed_at: null,
    execution_count: 0,
    consecutive_failures: 0,
    last_error: null,
    schedule_display: 'Mon, Wed 08:05',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...over,
  };
}

/** Wednesday 5 August 2026, 12:00 Paris. */
const NOW = new Date('2026-08-05T10:00:00Z');

function week(over: Partial<ScheduledActionWeekResponse['actions'][number]> = {}) {
  return {
    actions: [
      {
        id: 'r',
        timezone: 'Europe/Paris',
        week_start: '2026-08-03',
        today: 3,
        cells: [
          {
            day: 1,
            date: '2026-08-03',
            slot_at: '2026-08-03T06:05:00Z',
            outcome: 'success' as const,
            run_at: '2026-08-03T06:05:04Z',
            error: null,
            manual: false,
          },
          {
            day: 3,
            date: '2026-08-05',
            slot_at: '2026-08-05T06:05:00Z',
            outcome: null,
            run_at: null,
            error: null,
            manual: null,
          },
        ],
        ...over,
      },
    ],
    generated_at: '2026-08-05T10:00:00Z',
  };
}

function render(
  actions: ScheduledAction[],
  weekData: ScheduledActionWeekResponse | null,
  onSelect = vi.fn()
) {
  const numbered = numberByTriggerTime(actions, 'en');
  const utils = renderWithProviders(
    <ScheduledActionsTimeline
      lng="en"
      numbered={numbered}
      week={weekData}
      onSelect={onSelect}
      now={NOW}
    />
  );
  return { ...utils, onSelect };
}

const chip = (name: RegExp) => screen.getByRole('button', { name });

describe('ScheduledActionsTimeline — the table', () => {
  it('is a real table with seven day columns and twenty-four hour rows', () => {
    render([routine()], week());

    const table = screen.getByRole('table');
    expect(within(table).getAllByRole('columnheader')).toHaveLength(8);
    expect(within(table).getAllByRole('rowheader')).toHaveLength(24);
    expect(within(table).getByText('scheduled_actions.days.d1')).toBeInTheDocument();
    expect(within(table).getByText('scheduled_actions.days.d7')).toBeInTheDocument();
    expect(within(table).getByText('08')).toBeInTheDocument();
    expect(within(table).getByText('23')).toBeInTheDocument();
  });

  it('names the zone in its caption and beside the grid', () => {
    render([routine()], week());

    expect(screen.getByRole('table', { name: /Europe\/Paris/ })).toBeInTheDocument();
    expect(screen.getByText('hours_in_zone Europe/Paris')).toBeInTheDocument();
  });

  it('says so when the routines live in several zones', () => {
    render([routine(), routine({ id: 's', user_timezone: 'Asia/Tokyo' })], null);

    expect(screen.getByText('scheduled_actions.timeline.zones_mixed')).toBeInTheDocument();
  });

  it('shows the dates of the week under the day names', () => {
    render([routine()], week());

    // 3 to 9 August under Monday to Sunday.
    const headers = screen.getAllByRole('columnheader');
    expect(headers[1]).toHaveTextContent('3');
    expect(headers[7]).toHaveTextContent('9');
  });
});

describe('ScheduledActionsTimeline — the chips', () => {
  it('renders one chip per configured day, named with rank, title, time and state', () => {
    render([routine()], week());

    // Two configured days, two chips, both named the same way.
    expect(screen.getAllByRole('button', { name: /^1, Morning brief, 08:05, / })).toHaveLength(2);
  });

  it('never renders the title as visible text — the card owns it', () => {
    render([routine()], week());

    expect(screen.queryByText('Morning brief')).not.toBeInTheDocument();
  });

  it('colours the chip of a served slot green and leaves the pending one idle', () => {
    render([routine()], week());

    const monday = chip(/scheduled_actions.timeline.state.success$/);
    const wednesday = chip(/scheduled_actions.timeline.state.idle$/);
    expect(monday).toHaveAttribute('data-tone', 'success');
    expect(wednesday).toHaveAttribute('data-tone', 'idle');
  });

  it.each([
    ['failure', 'failure'],
    ['proposed', 'proposed'],
  ])('paints a %s outcome %s', (outcome, tone) => {
    const data = week();
    data.actions[0]!.cells[0]!.outcome = outcome as 'failure' | 'proposed';
    render([routine()], data);

    expect(chip(new RegExp(`state\\.${outcome}$`))).toHaveAttribute('data-tone', tone);
  });

  it('greys a paused routine whatever its history', () => {
    render([routine({ is_enabled: false })], week());

    const chips = screen.getAllByRole('button', { name: /state\.paused$/ });
    expect(chips).toHaveLength(2);
    chips.forEach(c => expect(c).toHaveAttribute('data-tone', 'paused'));
  });

  it('keeps a skipped slot idle but says why', () => {
    const data = week();
    data.actions[0]!.cells[0]!.outcome = 'skipped_condition';
    render([routine()], data);

    expect(chip(/state\.skipped_condition$/)).toHaveAttribute('data-tone', 'idle');
  });

  it('says a routine is running now', () => {
    render([routine({ status: 'executing' })], week());

    expect(screen.getAllByRole('button', { name: /state\.executing$/ })).toHaveLength(2);
  });

  it('orders the chips of one cell chronologically', () => {
    render(
      [
        routine({ id: 'late', title: 'Late', trigger_minute: 30, days_of_week: [1] }),
        routine({ id: 'early', title: 'Early', trigger_minute: 0, days_of_week: [1] }),
      ],
      null
    );

    const names = screen.getAllByRole('button').map(b => b.getAttribute('aria-label'));
    expect(names).toEqual([
      expect.stringMatching(/^1, Early, 08:00/),
      expect.stringMatching(/^2, Late, 08:30/),
    ]);
  });

  it('marks a condition routine on its chip', () => {
    render(
      [routine({ trigger_kind: 'condition', condition_config: { type: 'task_overdue' } })],
      null
    );

    const [first] = screen.getAllByRole('button', { name: /Morning brief/ });
    expect(first?.querySelector('[data-kind]')).toHaveAttribute('data-kind', 'condition');
  });

  it('takes the reader to the card when a chip is activated', async () => {
    const { user, onSelect } = render([routine()], week());

    const [first] = screen.getAllByRole('button', { name: /^1, Morning brief/ });
    await user.click(first as HTMLElement);

    expect(onSelect).toHaveBeenCalledWith('r');
  });
});

describe('ScheduledActionsTimeline — today', () => {
  it('highlights the column of today in the routines zone, from the week read', () => {
    render([routine()], week());

    const wednesday = screen.getAllByRole('columnheader')[3];
    expect(wednesday).toHaveAttribute('aria-current', 'date');
    expect(
      screen.getAllByRole('columnheader').filter(h => h.hasAttribute('aria-current'))
    ).toHaveLength(1);
  });

  it('falls back to the zone name when the week is unavailable', () => {
    // NOW is Wednesday in Paris; a routine in Auckland reads Wednesday 22:00, still Wednesday.
    render([routine({ user_timezone: 'Pacific/Auckland' })], null);

    expect(screen.getAllByRole('columnheader')[3]).toHaveAttribute('aria-current', 'date');
  });

  it('highlights nothing when the routines disagree on what day it is', () => {
    render([routine(), routine({ id: 's', user_timezone: 'Asia/Tokyo' })], null);

    expect(screen.getAllByRole('columnheader').some(h => h.hasAttribute('aria-current'))).toBe(
      false
    );
  });
});

describe('ScheduledActionsTimeline — when the week cannot be read', () => {
  it('still draws the schedule, every chip idle, and says the states are unavailable', () => {
    render([routine()], null);

    expect(screen.getByRole('status')).toHaveTextContent('scheduled_actions.timeline.unavailable');
    screen.getAllByRole('button').forEach(c => expect(c).toHaveAttribute('data-tone', 'idle'));
  });

  it('is silent about availability once the week is there', () => {
    render([routine()], week());

    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });
});

describe('ScheduledActionsTimeline — the legend', () => {
  it('lists every tone and the condition marker', () => {
    render([routine()], week());

    const legend = screen.getByRole('list', { name: 'scheduled_actions.timeline.legend_title' });
    expect(within(legend).getAllByRole('listitem')).toHaveLength(6);
    expect(within(legend).getByText('scheduled_actions.timeline.state.paused')).toBeInTheDocument();
    expect(
      within(legend).getByText('scheduled_actions.timeline.condition_kind')
    ).toBeInTheDocument();
  });
});

describe('ScheduledActionsTimeline — the grid is one tab stop', () => {
  const two = () => [
    routine({ id: 'early', title: 'Early', trigger_minute: 0, days_of_week: [1, 3] }),
    routine({ id: 'late', title: 'Late', trigger_hour: 19, days_of_week: [5] }),
  ];

  it('puts only the first chip in the tab order', () => {
    render(two(), null);

    const chips = screen.getAllByRole('button');
    expect(chips.map(c => c.tabIndex)).toEqual([0, -1, -1]);
  });

  it('walks the chips with the arrows, in reading order, wrapping at the end', async () => {
    const { user } = render(two(), null);
    const [first, second, third] = screen.getAllByRole('button');

    await user.tab();
    expect(document.activeElement).toBe(first);
    await user.keyboard('{ArrowRight}');
    expect(document.activeElement).toBe(second);
    await user.keyboard('{ArrowDown}');
    expect(document.activeElement).toBe(third);
    await user.keyboard('{ArrowRight}');
    expect(document.activeElement).toBe(first);
    await user.keyboard('{End}');
    expect(document.activeElement).toBe(third);
    await user.keyboard('{Home}');
    expect(document.activeElement).toBe(first);
  });

  it('hands the tab stop to the chip the reader last visited', async () => {
    const { user } = render(two(), null);
    const [first, second] = screen.getAllByRole('button');

    await user.tab();
    await user.keyboard('{ArrowRight}');
    expect(document.activeElement).toBe(second);

    // Leaving the grid and coming back lands on the visited chip, not the first.
    expect(second?.tabIndex).toBe(0);
    expect(first?.tabIndex).toBe(-1);
  });

  it('still activates a chip with the keyboard', async () => {
    const { user, onSelect } = render(two(), null);

    await user.tab();
    await user.keyboard('{ArrowRight}{Enter}');

    expect(onSelect).toHaveBeenCalledWith('early');
  });
});
