/**
 * The generic recurrence editor.
 *
 * Two questions in order — WHICH DAYS, then AT WHAT TIME — never one flat
 * form. Everything the reader can produce here, the API accepts; everything it
 * refuses, this refuses first, with a reason.
 *
 * The i18n stub renders the KEY, so assertions read keys, never labels.
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import type { RecurrenceSpec } from '@/hooks/useScheduledActions';
import { renderOccurrences } from '@/lib/occurrences';
import { emptyRecurrence } from '@/lib/recurrence';
import { RecurrenceEditor, type RecurrenceLimits } from '../RecurrenceEditor';

const LIMITS: RecurrenceLimits = {
  maxTimesPerDay: 12,
  minStepMinutes: 15,
  maxSeriesCount: 500,
};

function setup(over: Partial<RecurrenceSpec> = {}, limits: RecurrenceLimits = LIMITS) {
  const onChange = vi.fn();
  const value = { ...emptyRecurrence('2026-09-07'), ...over };
  const view = render(
    <RecurrenceEditor
      value={value}
      onChange={onChange}
      limits={limits}
      timezone="Europe/Paris"
      idPrefix="test"
    />
  );
  return { onChange, value, view };
}

describe('the two questions', () => {
  it('asks which days, then at what time — as two named groups', () => {
    setup();
    expect(screen.getByRole('group', { name: 'recurrence.legend_days' })).toBeInTheDocument();
    expect(screen.getByRole('group', { name: 'recurrence.legend_times' })).toBeInTheDocument();
  });
});

describe('every control carries an accessible name', () => {
  it('names the frequency select', () => {
    setup();
    expect(screen.getByRole('combobox', { name: 'recurrence.freq_label' })).toBeInTheDocument();
  });

  it('names each weekday toggle and states whether it is chosen', async () => {
    setup({ freq: 'weekly', byweekday: [1] });
    const monday = screen.getByRole('button', { name: 'scheduled_actions.days.d1' });
    expect(monday).toHaveAttribute('aria-pressed', 'true');
    const tuesday = screen.getByRole('button', { name: 'scheduled_actions.days.d2' });
    expect(tuesday).toHaveAttribute('aria-pressed', 'false');
  });
});

describe('choosing days', () => {
  it('adds a weekday without dropping the others', async () => {
    const user = userEvent.setup();
    const { onChange } = setup({ freq: 'weekly', byweekday: [1] });
    await user.click(screen.getByRole('button', { name: 'scheduled_actions.days.d3' }));
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ byweekday: [1, 3] }));
  });

  it('offers the three named sets as shortcuts', async () => {
    const user = userEvent.setup();
    const { onChange } = setup({ freq: 'weekly', byweekday: [1] });
    await user.click(screen.getByRole('button', { name: 'recurrence.weekday_set.workdays' }));
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ byweekday: [1, 2, 3, 4, 5] })
    );
  });

  it('refuses to leave a weekly rule with no day at all, and says so first', async () => {
    const user = userEvent.setup();
    const { onChange } = setup({ freq: 'weekly', byweekday: [1] });
    const monday = screen.getByRole('button', { name: 'scheduled_actions.days.d1' });
    // Stated BEFORE the click: a control that silently does nothing is worse
    // than one that explains itself. `aria-disabled`, never `disabled`, which
    // would blur the button and drop it from the tab order.
    expect(monday).toHaveAttribute('aria-disabled', 'true');
    // Carried by a visible hint the control points at, not by a `title`:
    // a tooltip never appears under a finger.
    expect(monday).toHaveAttribute(
      'aria-describedby',
      screen.getByText('recurrence.error_no_weekday').id
    );
    await user.click(monday);
    expect(onChange).not.toHaveBeenCalled();
  });

  it('lets the last day be unchecked once another one is checked', async () => {
    const user = userEvent.setup();
    const { onChange } = setup({ freq: 'weekly', byweekday: [1, 3] });
    const monday = screen.getByRole('button', { name: 'scheduled_actions.days.d1' });
    expect(monday).toHaveAttribute('aria-disabled', 'false');
    await user.click(monday);
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ byweekday: [3] }));
  });

  it('shows the day picker only for a weekly rule', () => {
    setup({ freq: 'daily' });
    expect(
      screen.queryByRole('button', { name: 'scheduled_actions.days.d1' })
    ).not.toBeInTheDocument();
  });

  it('shows the day of the month only for a monthly rule', () => {
    setup({ freq: 'monthly', bymonthday: [15] });
    expect(screen.getByRole('combobox', { name: 'recurrence.monthday_label' })).toBeInTheDocument();
  });
});

describe('the anchor is shown only when it changes an outcome', () => {
  it('is hidden for a plain daily rule', () => {
    setup({ freq: 'daily', interval: 1 });
    expect(screen.queryByLabelText('recurrence.anchor_label')).not.toBeInTheDocument();
  });

  it('appears as soon as an interval makes it a phase', () => {
    setup({ freq: 'daily', interval: 3 });
    expect(screen.getByLabelText('recurrence.anchor_label')).toBeInTheDocument();
  });

  it('appears for a single occurrence, where it IS the date', () => {
    setup({ freq: 'once' });
    expect(screen.getByLabelText('recurrence.anchor_label')).toBeInTheDocument();
  });
});

describe('choosing times', () => {
  it('adds a moment to the day', async () => {
    const user = userEvent.setup();
    const { onChange } = setup();
    await user.click(screen.getByRole('button', { name: 'recurrence.time_add' }));
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({
        times: expect.objectContaining({ at: expect.arrayContaining([{ hour: 8, minute: 0 }]) }),
      })
    );
  });

  it('refuses to remove the last moment of a day, and says so first', async () => {
    const user = userEvent.setup();
    const { onChange } = setup({ times: { mode: 'at', at: [{ hour: 8, minute: 0 }] } });
    const remove = screen.getByRole('button', { name: 'recurrence.time_remove' });
    expect(remove).toHaveAttribute('aria-disabled', 'true');
    await user.click(remove);
    expect(onChange).not.toHaveBeenCalled();
  });

  it('states the cap in the error rather than silently clamping', async () => {
    setup(
      {
        times: {
          mode: 'every',
          step_minutes: 30,
          start: { hour: 0, minute: 0 },
          end: { hour: 23, minute: 30 },
        },
      },
      LIMITS
    );
    expect(screen.getByRole('alert')).toHaveTextContent('recurrence.error_too_many');
  });

  it('states the step floor, which the API also enforces', () => {
    setup({
      times: {
        mode: 'every',
        step_minutes: 5,
        start: { hour: 8, minute: 0 },
        end: { hour: 9, minute: 0 },
      },
    });
    expect(screen.getByRole('alert')).toHaveTextContent('recurrence.error_step_too_small');
  });

  it('lets a wider consumer accept what a narrower one refuses', () => {
    // The caps are INJECTED: one editor serves a routine capped at 12 and a
    // reminder capped at 48, with no branch of its own.
    setup(
      {
        times: {
          mode: 'every',
          step_minutes: 30,
          start: { hour: 8, minute: 0 },
          end: { hour: 14, minute: 0 },
        },
      },
      { maxTimesPerDay: 48, minStepMinutes: 5, maxSeriesCount: 1000 }
    );
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });
});

describe('ending a series', () => {
  it('offers the three ways a series can end', () => {
    // The end rule now lives behind "advanced options"; a bounded series opens
    // it by itself, so the test states the shape it is looking at.
    setup({ end: { kind: 'after_count', on_date: null, after_count: 5 } });
    setup();
    expect(screen.getByRole('combobox', { name: 'recurrence.end_label' })).toBeInTheDocument();
  });

  it('has no end rule for a single occurrence', () => {
    setup({ freq: 'once' });
    expect(screen.queryByRole('combobox', { name: 'recurrence.end_label' })).not.toBeInTheDocument();
  });

  it('asks for the count when the series ends after N times', () => {
    setup({ end: { kind: 'after_count', on_date: null, after_count: 10 } });
    expect(screen.getByLabelText('recurrence.end_count_label')).toHaveValue(10);
  });
});

describe('the summary travels with the editor', () => {
  it('always shows what the current shape produces', () => {
    setup();
    expect(screen.getByTestId('recurrence-per-day')).toBeInTheDocument();
  });
});

describe('mobile parity', () => {
  it('renders every control at 390 px — nothing is hidden by width', () => {
    // `hidden lg:flex` amputates a feature on phones and tablets
    // (MemorySettings paid for that one). No control may carry a width gate.
    const { view } = setup({ freq: 'weekly', byweekday: [1, 2] });
    const gated = view.container.querySelectorAll(
      '[class*="hidden sm:"], [class*="hidden md:"], [class*="hidden lg:"], [class*="hidden xl:"]'
    );
    expect(gated).toHaveLength(0);
  });

  it('gives every interactive control a touch target of at least 40 px', () => {
    const { view } = setup({ freq: 'weekly', byweekday: [1] });
    const buttons = within(view.container).getAllByRole('button');
    for (const button of buttons) {
      const classes = button.className;
      // Either an explicit height utility of h-10+ or the default control size.
      expect(classes).not.toMatch(/\bh-[1-7]\b/);
    }
  });
});

describe('the upcoming dates speak the reader language', () => {
  const ISO = '2026-09-07T06:00:00Z';

  it('renders them in the active locale, not a hardcoded one', () => {
    // The editor used to pass `locale="en"`, so every non-English reader saw
    // English dates under a French form. The stub pins the language to `fr`.
    const { container } = render(
      <RecurrenceEditor
        value={emptyRecurrence('2026-09-07')}
        onChange={vi.fn()}
        limits={LIMITS}
        timezone="Europe/Paris"
        idPrefix="locale"
        occurrences={[ISO]}
      />
    );
    const french = renderOccurrences([ISO], 'Europe/Paris', 'fr');
    const english = renderOccurrences([ISO], 'Europe/Paris', 'en');
    expect(french[0].label).not.toEqual(english[0].label);
    const text = container.textContent ?? '';
    expect(text).toContain(french[0].label);
    expect(text).not.toContain(english[0].label);
  });
});

describe('a series with no future says so', () => {
  it('states it rather than showing an empty list', () => {
    // The branch existed in `RecurrenceSummary` but nothing reached it: the
    // editor neither accepted nor forwarded the fact, so a routine whose
    // series was over showed silence where a reader expects an answer.
    render(
      <RecurrenceEditor
        value={emptyRecurrence('2026-09-07')}
        onChange={vi.fn()}
        limits={LIMITS}
        timezone="Europe/Paris"
        idPrefix="over"
        finished
      />
    );
    expect(screen.getByText('recurrence.summary_finished')).toBeInTheDocument();
  });

  it('stays silent about it while the series still has a future', () => {
    setup();
    expect(screen.queryByText('recurrence.summary_finished')).not.toBeInTheDocument();
  });
});

describe('the last remaining weekday explains itself', () => {
  it('names the reason on the control, visibly and programmatically', async () => {
    // A `title` was the only carrier: absent under a finger, unreliable for a
    // screen reader. Unchecking the last day does nothing — the reader must
    // be told why BEFORE the click, per the component's own contract.
    setup({ freq: 'weekly', byweekday: [2] });

    const monday = screen.getByRole('button', { name: 'scheduled_actions.days.d2' });
    expect(monday).toHaveAttribute('aria-disabled', 'true');

    const hint = screen.getByText('recurrence.error_no_weekday');
    expect(hint).toBeInTheDocument();
    expect(monday).toHaveAttribute('aria-describedby', hint.id);
  });

  it('drops the hint as soon as a second day makes unchecking legal', () => {
    setup({ freq: 'weekly', byweekday: [2, 4] });
    expect(screen.queryByText('recurrence.error_no_weekday')).not.toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'scheduled_actions.days.d2' })
    ).toHaveAttribute('aria-disabled', 'false');
  });
});

describe('the last remaining moment explains itself too', () => {
  it('names the reason and refuses to leave a day with no time', async () => {
    const user = userEvent.setup();
    const { onChange } = setup({
      times: { mode: 'at', at: [{ hour: 9, minute: 0 }], step_minutes: null, start: null, end: null },
    });

    const remove = screen.getByRole('button', { name: /recurrence.time_remove/ });
    expect(remove).toHaveAttribute('aria-disabled', 'true');
    expect(remove).toHaveAttribute(
      'aria-describedby',
      screen.getByText('recurrence.error_no_time').id
    );
    await user.click(remove);
    expect(onChange).not.toHaveBeenCalled();
  });

  it('drops the hint once a second moment makes removal legal', () => {
    setup({
      times: {
        mode: 'at',
        at: [
          { hour: 9, minute: 0 },
          { hour: 18, minute: 0 },
        ],
        step_minutes: null,
        start: null,
        end: null,
      },
    });
    expect(screen.queryByText('recurrence.error_no_time')).not.toBeInTheDocument();
  });
});

describe('an end date the reader cleared says why the form is stuck', () => {
  // `recurrenceIsComplete` refuses an empty `on_date` — the column cannot hold
  // one and the API would answer 422 — so the save button goes `aria-disabled`.
  // Without a message, that is a form that stops responding for no stated
  // reason: the reader cleared a date and nothing tells them to put one back.
  // The count field cannot reach this state (its handler floors at 1); the
  // date field can, because a text input is legitimately empty while typing.
  it('names the missing date instead of only disabling the save', () => {
    setup({
      end: { kind: 'on_date', on_date: '', after_count: null },
    });
    expect(screen.getByText('recurrence.error_no_end_date')).toBeInTheDocument();
  });

  it('says nothing once the date is there', () => {
    setup({
      end: { kind: 'on_date', on_date: '2026-12-31', after_count: null },
    });
    expect(screen.queryByText('recurrence.error_no_end_date')).not.toBeInTheDocument();
  });

  it('says nothing when the series never ends', () => {
    setup();
    expect(screen.queryByText('recurrence.error_no_end_date')).not.toBeInTheDocument();
  });
});

describe('an end date before the first day says so, and the control publishes the bound', () => {
  // The API refuses a series that ends before it starts (ADR-268 amendment):
  // it fires nothing at all. A save button that goes quiet with no sentence is
  // the defect the block above exists to prevent, so the rule needs a message
  // of its own — and the date control carries `min` so the native picker
  // refuses the day before it is ever typed (ADR-184: publish what you enforce).

  it('names the reversed dates instead of only disabling the save', () => {
    setup({
      anchor_date: '2026-09-10',
      end: { kind: 'on_date', on_date: '2026-09-01', after_count: null },
    });
    expect(screen.getByText('recurrence.error_end_before_start')).toBeInTheDocument();
  });

  it('says nothing when the end falls on the first day itself', () => {
    setup({
      anchor_date: '2026-09-10',
      end: { kind: 'on_date', on_date: '2026-09-10', after_count: null },
    });
    expect(screen.queryByText('recurrence.error_end_before_start')).not.toBeInTheDocument();
  });

  it('keeps the empty-date message for an empty date', () => {
    setup({
      anchor_date: '2026-09-10',
      end: { kind: 'on_date', on_date: '', after_count: null },
    });
    expect(screen.getByText('recurrence.error_no_end_date')).toBeInTheDocument();
    expect(screen.queryByText('recurrence.error_end_before_start')).not.toBeInTheDocument();
  });

  it('the date control refuses an earlier day natively', () => {
    setup({
      anchor_date: '2026-09-10',
      end: { kind: 'on_date', on_date: '2026-12-31', after_count: null },
    });
    expect(screen.getByLabelText('recurrence.date_label')).toHaveAttribute('min', '2026-09-10');
  });
});

describe('the shape of the day and interval rows (owner arbitration 2026-09-06)', () => {
  it('breaks the weekday row after Friday so the weekend reads as a group', () => {
    setup({ freq: 'weekly', byweekday: [1, 2] });
    const friday = screen.getByRole('button', { name: 'scheduled_actions.days.d5' });
    const saturday = screen.getByRole('button', { name: 'scheduled_actions.days.d6' });
    const row = friday.parentElement!;

    // The separator is a zero-height flex break, not a second container: the
    // seven buttons stay ONE wrapping row, so a narrow screen still reflows
    // them instead of being locked into 5 + 2.
    const children = [...row.children];
    const between = children.slice(children.indexOf(friday) + 1, children.indexOf(saturday));
    expect(between).toHaveLength(1);
    expect(between[0].className).toContain('basis-full');
    expect(between[0]).toHaveAttribute('aria-hidden', 'true');
  });

  it('keeps the unit beside its input rather than at the far edge of the row', () => {
    // `Input` wraps itself in `FieldFrame`, which is `w-full`: inside a flex
    // row that wrapper claims every spare pixel and throws the unit against
    // the right edge — measured in the browser 2026-09-06, "week(s)" sat 330px
    // from a 80px field. Bounding the wrapper is what puts them side by side;
    // jsdom computes no layout, so the class IS the available oracle and the
    // screenshot is the real one.
    setup({ freq: 'weekly', byweekday: [1], interval: 2 });
    const input = screen.getByLabelText('recurrence.interval_label');
    const bounded = input.closest('[data-interval-field]');
    expect(bounded).not.toBeNull();
    expect(bounded!.className).toMatch(/w-\d/);
    expect(bounded!.className).not.toContain('w-full');
  });
});

describe('the stepped window gives each group its own line', () => {
  const stepped = {
    times: { mode: 'every' as const, at: [], step_minutes: 60, start: { hour: 8, minute: 0 }, end: { hour: 18, minute: 0 } },
  };

  it('puts the step on its own line, and the window bounds on the next', () => {
    // Three groups sharing one wrapping row read as one long strip, and on a
    // phone they wrapped at whatever point the widths happened to fall. The
    // step is one question ("how often"), the bounds are another ("between
    // when and when") — one line each (owner arbitration 2026-09-06).
    setup(stepped);
    const step = screen.getByLabelText('recurrence.step_label');
    const from = screen.getByLabelText('recurrence.step_from');

    const stepGroup = step.closest('[data-step-group]');
    const windowGroup = from.closest('[data-window-group]');
    expect(stepGroup).not.toBeNull();
    expect(windowGroup).not.toBeNull();
    // Different groups, and the step's own line is full width.
    expect(stepGroup).not.toBe(windowGroup);
    expect(windowGroup!.contains(step)).toBe(false);
  });

  it('gives the step control room for its longest label', () => {
    // "360 minutes" — "360 Minuten" in German — did not fit the old `w-28`.
    // Now that the step owns its line, the control can hold its whole label.
    setup(stepped);
    const step = screen.getByLabelText('recurrence.step_label');
    const width = /w-(\d+)/.exec(step.className);
    expect(width, `no width class on ${step.className}`).not.toBeNull();
    expect(Number(width![1])).toBeGreaterThanOrEqual(40);
  });
});

describe('the window reads as one phrase (owner arbitration 2026-09-06)', () => {
  const stepped = {
    times: { mode: 'every' as const, at: [], step_minutes: 60, start: { hour: 8, minute: 0 }, end: { hour: 18, minute: 0 } },
  };

  it('drops the "From" caption and puts the joining word between the two clocks', () => {
    setup(stepped);
    // No standalone caption above the first clock any more...
    expect(screen.queryByText('recurrence.step_from')).not.toBeInTheDocument();
    expect(screen.queryByText('recurrence.step_to')).not.toBeInTheDocument();
    // ...the word sits between them instead.
    expect(screen.getByText('recurrence.step_separator')).toBeInTheDocument();
  });

  it('keeps a programmatic name on every clock control', () => {
    // Removing a VISIBLE caption must never remove the accessible name: a
    // screen reader still has to tell the two ends of the window apart.
    setup(stepped);
    expect(screen.getByLabelText('recurrence.step_from')).toBeInTheDocument();
    expect(screen.getByLabelText('recurrence.step_from minutes')).toBeInTheDocument();
    expect(screen.getByLabelText('recurrence.step_to')).toBeInTheDocument();
    expect(screen.getByLabelText('recurrence.step_to minutes')).toBeInTheDocument();
  });

  it('leaves the joining word out of the accessible names', () => {
    setup(stepped);
    // Decorative: the controls already say which end they are.
    expect(screen.getByText('recurrence.step_separator')).toHaveAttribute('aria-hidden', 'true');
  });
});

describe('the rarely-changed settings fold away (owner trial 2026-09-06)', () => {
  it('hides the interval and the end rule behind one disclosure by default', () => {
    setup({ freq: 'weekly', byweekday: [1] });
    expect(screen.queryByLabelText('recurrence.interval_label')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('recurrence.end_label')).not.toBeInTheDocument();
    expect(screen.getByText('recurrence.advanced')).toBeInTheDocument();
  });

  it('keeps the everyday questions on screen', () => {
    // Folding must not cost the reader the answers they came for.
    setup({ freq: 'weekly', byweekday: [1] });
    expect(screen.getByLabelText('recurrence.freq_label')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'scheduled_actions.days.d1' })).toBeInTheDocument();
  });

  it('OPENS itself when a value inside it is not the default', () => {
    // The rule that makes folding safe: a schedule that already says "every
    // other week" or "until 31 December" must never hide that fact. A reader
    // editing such a routine would otherwise see a plain weekly rule and
    // believe the interval had been lost.
    setup({ freq: 'weekly', byweekday: [1], interval: 3 });
    expect(screen.getByLabelText('recurrence.interval_label')).toBeInTheDocument();
  });

  it('opens for a bounded series too', () => {
    setup({
      freq: 'weekly',
      byweekday: [1],
      end: { kind: 'after_count', on_date: null, after_count: 5 },
    });
    expect(screen.getByLabelText('recurrence.end_label')).toBeInTheDocument();
  });

  it('stays folded for a plain weekly rule with no end', () => {
    setup({ freq: 'weekly', byweekday: [1], interval: 1 });
    expect(screen.queryByLabelText('recurrence.interval_label')).not.toBeInTheDocument();
  });
});

describe('folding never hides the field that carries the answer', () => {
  it('shows a single occurrence its own date, unfolded', () => {
    // For `once` the anchor is not a setting, it is WHEN the thing happens.
    setup({ freq: 'once' });
    expect(screen.getByLabelText('recurrence.anchor_label')).toBeInTheDocument();
  });

  it('shows the phase of an interval, because the interval opens the fold', () => {
    setup({ freq: 'daily', interval: 3 });
    expect(screen.getByLabelText('recurrence.anchor_label')).toBeInTheDocument();
    expect(screen.getByLabelText('recurrence.interval_label')).toBeInTheDocument();
  });

  it('shows an end date the reader already chose', () => {
    setup({ end: { kind: 'on_date', on_date: '2026-12-31', after_count: null } });
    expect(screen.getByLabelText('recurrence.end_label')).toBeInTheDocument();
  });
});
