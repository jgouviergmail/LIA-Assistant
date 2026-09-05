/**
 * `duplicateTitle` — marking a copy without breaking the column bound.
 *
 * `title` is `max_length=200` server-side. Appending a copy marker to an
 * already-long title would produce a form that looks valid and a create the
 * API refuses, so the bound is respected here, before the reader ever presses
 * save.
 */

import { describe, it, expect } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';

import { SCHEDULED_ACTION_TITLE_MAX_LENGTH } from '../constants';
import type { ScheduledAction } from '@/hooks/useScheduledActions';
import {
  buildTimelineGrid,
  chipState,
  duplicateTitle,
  isoWeekdayInZone,
  numberByTriggerTime,
  routineZones,
  rovingTarget,
  timelineKey,
  triggerTimeLabel,
  weekDates,
} from '../scheduled-actions';

describe('duplicateTitle', () => {
  it('appends the marker when there is room', () => {
    expect(duplicateTitle('Morning brief', '(copy)')).toBe('Morning brief (copy)');
  });

  it('trims the TITLE, never the marker, when the pair overflows', () => {
    // Losing the marker would leave two identically-named routines — precisely
    // what the reader is duplicating to avoid.
    const result = duplicateTitle('x'.repeat(SCHEDULED_ACTION_TITLE_MAX_LENGTH), '(copy)');

    expect(result).toHaveLength(SCHEDULED_ACTION_TITLE_MAX_LENGTH);
    expect(result.endsWith('(copy)')).toBe(true);
  });

  it('degrades to the marker alone rather than overflowing on an absurd marker', () => {
    const result = duplicateTitle('anything', 'y'.repeat(250));

    expect(result.length).toBeLessThanOrEqual(SCHEDULED_ACTION_TITLE_MAX_LENGTH);
  });

  it('leaves an empty title usable', () => {
    expect(duplicateTitle('', '(copy)')).toBe(' (copy)');
  });
});

describe('truncating a title that contains characters wider than one code unit', () => {
  // `slice` counts UTF-16 code units. An emoji is two of them, so a cut that
  // lands between them leaves half a character — a lone surrogate, which
  // renders as the replacement glyph and is not valid text to send anywhere.
  // Reproduced with a title whose emoji start at an odd offset.
  const suffix = '(copie)';

  function loneSurrogate(value: string): boolean {
    return /[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/.test(value);
  }

  it('never cuts a surrogate pair in half', () => {
    const title = `A${'🏃'.repeat(120)}`;

    const result = duplicateTitle(title, suffix);

    expect(loneSurrogate(result)).toBe(false);
  });

  it('still respects the column bound', () => {
    const title = `A${'🏃'.repeat(120)}`;

    expect(duplicateTitle(title, suffix).length).toBeLessThanOrEqual(
      SCHEDULED_ACTION_TITLE_MAX_LENGTH
    );
  });

  it('keeps the copy marker, which is the whole point of the trim', () => {
    const title = `A${'🏃'.repeat(120)}`;

    expect(duplicateTitle(title, suffix).endsWith(suffix)).toBe(true);
  });

  it('leaves a title that fits exactly alone, emoji included', () => {
    const title = '🏃 Course';

    expect(duplicateTitle(title, suffix)).toBe(`${title} ${suffix}`);
  });
});

describe('the title bound against the schema that enforces it', () => {
  // `SCHEDULED_ACTION_TITLE_MAX_LENGTH` is a hand-copied mirror of a bound the
  // BACKEND owns. If the column grows and this stays at 200, duplicates get
  // trimmed for no reason; if the column SHRINKS and this stays, the API
  // refuses a create the form declared valid — the failure this constant was
  // introduced to prevent, pointing the other way.
  //
  // Same mechanism as the SSE contract-symmetry test: re-parse the source when
  // the checkout exposes it. Skipped inside the web dev container, which
  // mounts only apps/web; enforced on host checkouts and in CI.
  const schemaPath = path.resolve(process.cwd(), '../api/src/domains/scheduled_actions/schemas.py');

  it.skipIf(!fs.existsSync(schemaPath))('matches the Pydantic max_length', () => {
    const source = fs.readFileSync(schemaPath, 'utf-8');
    // Every `title` Field in that module, with its bound.
    const bounds = [
      ...source.matchAll(/title:[^=]*=\s*Field\((?:[^()]|\([^()]*\))*?max_length=(\d+)/gs),
    ].map(match => Number(match[1]));

    expect(bounds.length, 'no title bound found — the regex or the schema moved').toBeGreaterThan(
      0
    );
    for (const bound of bounds) {
      expect(bound).toBe(SCHEDULED_ACTION_TITLE_MAX_LENGTH);
    }
  });
});

function routine(over: Partial<ScheduledAction> = {}): ScheduledAction {
  return {
    id: 'r',
    user_id: 'u1',
    title: 'Routine',
    action_prompt: 'do',
    days_of_week: [1],
    trigger_hour: 8,
    trigger_minute: 0,
    user_timezone: 'Europe/Paris',
    trigger_kind: 'time',
    condition_config: null,
    requires_approval: false,
    next_trigger_at: '2026-08-03T06:00:00Z',
    is_enabled: true,
    status: 'active',
    last_executed_at: null,
    execution_count: 0,
    consecutive_failures: 0,
    last_error: null,
    schedule_display: 'Mon 08:00',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...over,
  };
}

const ADVERSARIAL = [
  routine({
    id: 'z',
    title: 'Veille IA',
    days_of_week: [1, 3, 5],
    trigger_hour: 19,
    trigger_minute: 30,
  }),
  routine({ id: 'b', title: 'météo', days_of_week: [1, 2, 3, 4, 5, 6, 7], trigger_hour: 8 }),
  routine({
    id: 'a',
    title: 'Mails',
    days_of_week: [1, 2, 3, 4, 5],
    trigger_hour: 8,
    is_enabled: false,
  }),
  routine({ id: 'c', title: 'Mails', days_of_week: [6, 7, 7], trigger_hour: 8 }),
  routine({ id: 'd', title: 'Minuit', days_of_week: [7], trigger_hour: 0 }),
  routine({
    id: 'e',
    title: 'Tard',
    days_of_week: [5],
    trigger_hour: 23,
    trigger_minute: 55,
    user_timezone: 'Asia/Tokyo',
  }),
  routine({ id: 'f', title: 'Routine 10', days_of_week: [2], trigger_hour: 8, trigger_minute: 5 }),
  routine({ id: 'g', title: 'Routine 2', days_of_week: [2], trigger_hour: 8, trigger_minute: 5 }),
];

describe('numberByTriggerTime', () => {
  it('orders by hour, minute, then title (numeric, accent-insensitive), then id', () => {
    const ids = numberByTriggerTime(ADVERSARIAL, 'fr').map(n => n.action.id);
    expect(ids).toEqual(['d', 'a', 'c', 'b', 'g', 'f', 'z', 'e']);
  });

  it('numbers from one, paused routines included', () => {
    const numbered = numberByTriggerTime(ADVERSARIAL, 'fr');
    expect(numbered.map(n => n.number)).toEqual([1, 2, 3, 4, 5, 6, 7, 8]);
    expect(numbered[1]?.action.is_enabled).toBe(false);
  });

  it('does not depend on the order the API returned the rows in', () => {
    const forward = numberByTriggerTime(ADVERSARIAL, 'fr').map(n => n.action.id);
    const backward = numberByTriggerTime([...ADVERSARIAL].reverse(), 'fr').map(n => n.action.id);
    expect(backward).toEqual(forward);
  });

  it('keeps every rank when a routine is toggled', () => {
    const toggled = ADVERSARIAL.map(a => (a.id === 'b' ? { ...a, is_enabled: false } : a));
    expect(numberByTriggerTime(toggled, 'fr').map(n => n.action.id)).toEqual(
      numberByTriggerTime(ADVERSARIAL, 'fr').map(n => n.action.id)
    );
  });

  it('renumbers the later routines when an earlier one is created', () => {
    const inserted = [...ADVERSARIAL, routine({ id: 'h', title: 'Nouvelle', trigger_hour: 7 })];
    const numbered = numberByTriggerTime(inserted, 'fr');
    expect(numbered.find(n => n.action.id === 'h')?.number).toBe(2);
    expect(numbered.find(n => n.action.id === 'b')?.number).toBe(5);
  });

  it('never mutates its input', () => {
    const input = [...ADVERSARIAL];
    numberByTriggerTime(input, 'fr');
    expect(input.map(a => a.id)).toEqual(ADVERSARIAL.map(a => a.id));
  });
});

describe('triggerTimeLabel', () => {
  it('pads both halves', () => {
    expect(triggerTimeLabel({ trigger_hour: 8, trigger_minute: 5 })).toBe('08:05');
    expect(triggerTimeLabel({ trigger_hour: 23, trigger_minute: 55 })).toBe('23:55');
  });
});

describe('buildTimelineGrid', () => {
  const numbered = numberByTriggerTime(ADVERSARIAL, 'fr');

  it('places one chip per configured day at the hour row, duplicates collapsed', () => {
    const grid = buildTimelineGrid(numbered, null);
    const total = [...grid.values()].reduce((sum, entries) => sum + entries.length, 0);
    expect(total).toBe(21); // 3+7+5+2+1+1+1+1
    expect(grid.get(timelineKey(7, 8))?.map(e => e.number)).toEqual([3, 4]);
  });

  it('keeps the chronological order inside a cell', () => {
    const grid = buildTimelineGrid(numbered, null);
    expect(grid.get(timelineKey(2, 8))?.map(e => e.number)).toEqual([2, 4, 5, 6]);
  });

  it('attaches the week cell of the routine for that day', () => {
    const week = {
      actions: [
        {
          id: 'b',
          timezone: 'Europe/Paris',
          week_start: '2026-08-03',
          today: 3,
          cells: [
            {
              day: 1,
              date: '2026-08-03',
              slot_at: '2026-08-03T06:00:00Z',
              outcome: 'success' as const,
              run_at: '2026-08-03T06:00:05Z',
              error: null,
              manual: false,
            },
          ],
        },
      ],
      generated_at: '2026-08-05T10:00:00Z',
    };
    const grid = buildTimelineGrid(numbered, week);
    const monday = grid.get(timelineKey(1, 8))?.find(e => e.action.id === 'b');
    const tuesday = grid.get(timelineKey(2, 8))?.find(e => e.action.id === 'b');
    expect(monday?.cell?.outcome).toBe('success');
    expect(tuesday?.cell).toBeNull();
  });

  it('skips a day or an hour out of range instead of crashing', () => {
    const broken = numberByTriggerTime(
      [routine({ id: 'x', days_of_week: [0, 8, 3] }), routine({ id: 'y', trigger_hour: 24 })],
      'fr'
    );
    const grid = buildTimelineGrid(broken, null);
    expect([...grid.keys()]).toEqual([timelineKey(3, 8)]);
  });
});

describe('chipState', () => {
  const cell = (outcome: ScheduledAction['status'] | string | null) => ({
    day: 1,
    date: '2026-08-03',
    slot_at: '2026-08-03T06:00:00Z',
    outcome: outcome as never,
    run_at: null,
    error: null,
    manual: null,
  });

  it('paused outranks every outcome', () => {
    expect(chipState(routine({ is_enabled: false }), cell('success'))).toEqual({
      tone: 'paused',
      reason: null,
      executing: false,
    });
  });

  it.each([
    ['success', 'success'],
    ['failure', 'failure'],
    ['proposed', 'proposed'],
  ])('%s colours the chip %s', (outcome, tone) => {
    expect(chipState(routine(), cell(outcome)).tone).toBe(tone);
  });

  it.each(['skipped_condition', 'skipped_hitl'])('%s stays idle but says why', reason => {
    expect(chipState(routine(), cell(reason))).toEqual({
      tone: 'idle',
      reason,
      executing: false,
    });
  });

  it('is idle with no reason when nothing served the slot, or the week is unknown', () => {
    expect(chipState(routine(), cell(null)).tone).toBe('idle');
    expect(chipState(routine(), null)).toEqual({ tone: 'idle', reason: null, executing: false });
  });

  it('reports a routine running right now', () => {
    expect(chipState(routine({ status: 'executing' }), null).executing).toBe(true);
  });
});

describe('routineZones', () => {
  it('lists distinct zones, first seen first', () => {
    expect(routineZones(ADVERSARIAL)).toEqual(['Europe/Paris', 'Asia/Tokyo']);
  });
});

describe('isoWeekdayInZone', () => {
  it('reads the weekday in the zone, not in the runtime', () => {
    // Sunday 14:00 UTC: Sunday in Paris, Monday in Auckland.
    const instant = new Date('2026-08-09T14:00:00Z');
    expect(isoWeekdayInZone(instant, 'Europe/Paris')).toBe(7);
    expect(isoWeekdayInZone(instant, 'Pacific/Auckland')).toBe(1);
  });

  it('answers null on an unknown zone rather than throwing', () => {
    expect(isoWeekdayInZone(new Date(), 'Mars/Olympus')).toBeNull();
  });
});

describe('weekDates', () => {
  it('lists the seven dates from the Monday, across a month boundary', () => {
    expect(weekDates('2026-08-31')).toEqual([
      '2026-08-31',
      '2026-09-01',
      '2026-09-02',
      '2026-09-03',
      '2026-09-04',
      '2026-09-05',
      '2026-09-06',
    ]);
  });

  it('is empty on a malformed start', () => {
    expect(weekDates('yesterday')).toEqual([]);
  });
});

describe('rovingTarget', () => {
  const keys = ['a:1', 'a:3', 'b:2'];

  it('walks the reading order and wraps at both ends', () => {
    expect(rovingTarget(keys, 'a:1', 'ArrowRight')).toBe('a:3');
    expect(rovingTarget(keys, 'a:1', 'ArrowDown')).toBe('a:3');
    expect(rovingTarget(keys, 'b:2', 'ArrowRight')).toBe('a:1');
    expect(rovingTarget(keys, 'a:1', 'ArrowLeft')).toBe('b:2');
    expect(rovingTarget(keys, 'a:3', 'ArrowUp')).toBe('a:1');
  });

  it('jumps to the extremes', () => {
    expect(rovingTarget(keys, 'a:3', 'Home')).toBe('a:1');
    expect(rovingTarget(keys, 'a:3', 'End')).toBe('b:2');
  });

  it('restarts from the first chip when the current one left the grid', () => {
    expect(rovingTarget(keys, 'gone:9', 'ArrowRight')).toBe('a:1');
    expect(rovingTarget(keys, null, 'ArrowLeft')).toBe('a:1');
  });

  it('leaves every other key to the browser, and an empty grid alone', () => {
    expect(rovingTarget(keys, 'a:1', 'Tab')).toBeNull();
    expect(rovingTarget(keys, 'a:1', 'Enter')).toBeNull();
    expect(rovingTarget([], null, 'ArrowRight')).toBeNull();
  });
});
