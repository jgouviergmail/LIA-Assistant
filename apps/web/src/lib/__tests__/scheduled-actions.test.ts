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
import { makeMultiSlotAction, makeScheduledAction } from '@/__tests__/factories';
import type { ScheduledAction } from '@/hooks/useScheduledActions';
import {
  buildTimelineGrid,
  isConditionRoutine,
  sameCondition,
  chipState,
  duplicateTitle,
  isoWeekdayInZone,
  numberByTriggerTime,
  routineZones,
  rovingTarget,
  timelineKey,
  weatherRuleSentence,
  weekDates,
  chipKey,
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

const ADVERSARIAL = [
  makeScheduledAction({
    id: 'z',
    title: 'Veille IA',
    times_of_day: ['19:30'],
  }),
  makeScheduledAction({ id: 'b', title: 'météo', times_of_day: ['08:00'] }),
  makeScheduledAction({
    id: 'a',
    title: 'Mails',
    times_of_day: ['08:00'],
    is_enabled: false,
  }),
  makeScheduledAction({ id: 'c', title: 'Mails', times_of_day: ['08:00'] }),
  makeScheduledAction({ id: 'd', title: 'Minuit', times_of_day: ['00:00'] }),
  makeScheduledAction({
    id: 'e',
    title: 'Tard',
    times_of_day: ['23:55'],
    user_timezone: 'Asia/Tokyo',
  }),
  makeScheduledAction({ id: 'f', title: 'Routine 10', times_of_day: ['08:05'] }),
  makeScheduledAction({ id: 'g', title: 'Routine 2', times_of_day: ['08:05'] }),
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
    const inserted = [
      ...ADVERSARIAL,
      makeScheduledAction({ id: 'h', title: 'Nouvelle', times_of_day: ['07:00'] }),
    ];
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

describe('buildTimelineGrid', () => {
  const numbered = numberByTriggerTime(ADVERSARIAL, 'fr');

  it('places one chip per INSTANT the routine carries, at that instant hour', () => {
    // Position comes from `week_slots`, computed server-side: one chip per
    // instant, never one per configured day. The shared factory gives each
    // routine a single Monday 08:00 slot.
    const grid = buildTimelineGrid(numbered, null);
    const total = [...grid.values()].reduce((sum, entries) => sum + entries.length, 0);
    expect(total).toBe(ADVERSARIAL.length);
    expect(grid.get(timelineKey(1, 8))).toHaveLength(ADVERSARIAL.length);
  });

  it('keeps the chronological order inside a cell', () => {
    const grid = buildTimelineGrid(numbered, null);
    const numbers = grid.get(timelineKey(1, 8))?.map(e => e.number) ?? [];
    expect(numbers).toEqual([...numbers].sort((a, b) => a - b));
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
              hour: 8,
              minute: 0,
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
    // Matched on the INSTANT, not on the day: that is what lets two chips of
    // one day carry different outcomes.
    expect(monday?.cell?.outcome).toBe('success');
  });

  it('skips a slot whose day or hour is out of range instead of crashing', () => {
    const broken = numberByTriggerTime(
      [
        makeScheduledAction({
          id: 'x',
          week_slots: [
            { day: 0, date: '2026-08-03', slot_at: 'a', hour: 8, minute: 0 },
            { day: 8, date: '2026-08-03', slot_at: 'b', hour: 8, minute: 0 },
            { day: 3, date: '2026-08-05', slot_at: 'c', hour: 8, minute: 0 },
          ],
        }),
        makeScheduledAction({
          id: 'y',
          week_slots: [{ day: 1, date: '2026-08-03', slot_at: 'd', hour: 24, minute: 0 }],
        }),
      ],
      'fr'
    );
    const grid = buildTimelineGrid(broken, null);
    expect([...grid.keys()]).toEqual([timelineKey(3, 8)]);
  });

  it('draws every chip even when the outcomes request never answered', () => {
    // Owner arbitration 2026-09-06: an empty grid is a blocking regression.
    // Position ships with the routine; `/week` only adds colour.
    const numbered = numberByTriggerTime([makeMultiSlotAction({ id: 'm' })], 'fr');
    const grid = buildTimelineGrid(numbered, null);
    expect(grid.get(timelineKey(1, 8))).toHaveLength(1);
    expect(grid.get(timelineKey(1, 18))).toHaveLength(1);
    expect(grid.get(timelineKey(1, 8))?.[0].cell).toBeNull();
  });

  it('gives a routine firing twice a day two chips with distinct keys', () => {
    const numbered = numberByTriggerTime([makeMultiSlotAction({ id: 'm' })], 'fr');
    const grid = buildTimelineGrid(numbered, null);
    const keys = [
      ...(grid.get(timelineKey(1, 8)) ?? []),
      ...(grid.get(timelineKey(1, 18)) ?? []),
    ].map(e => chipKey(e.action.id, e.slot.day, e.slot.hour, e.slot.minute));
    expect(new Set(keys).size).toBe(2);
  });
});

describe('chipState', () => {
  const cell = (outcome: ScheduledAction['status'] | string | null) => ({
    day: 1,
    date: '2026-08-03',
    slot_at: '2026-08-03T06:00:00Z',
    hour: 8,
    minute: 0,
    outcome: outcome as never,
    run_at: null,
    error: null,
    manual: null,
  });

  it('paused outranks every outcome', () => {
    expect(chipState(makeScheduledAction({ is_enabled: false }), cell('success'))).toEqual({
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
    expect(chipState(makeScheduledAction(), cell(outcome)).tone).toBe(tone);
  });

  it.each(['skipped_condition', 'skipped_hitl'])('%s stays idle but says why', reason => {
    expect(chipState(makeScheduledAction(), cell(reason))).toEqual({
      tone: 'idle',
      reason,
      executing: false,
    });
  });

  it('is idle with no reason when nothing served the slot, or the week is unknown', () => {
    expect(chipState(makeScheduledAction(), cell(null)).tone).toBe('idle');
    expect(chipState(makeScheduledAction(), null)).toEqual({
      tone: 'idle',
      reason: null,
      executing: false,
    });
  });

  it('reports a routine running right now', () => {
    expect(chipState(makeScheduledAction({ status: 'executing' }), null).executing).toBe(true);
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

describe('sameCondition (ADR-322)', () => {
  it('reads the same condition whatever order its keys arrive in', () => {
    // The server stores its own key order; a spelling difference must not
    // read as an edit, which would re-arm the routine for nothing.
    expect(
      sameCondition(
        { type: 'mail_match', query: 'devis', until: '2026-10-01' },
        { until: '2026-10-01', query: 'devis', type: 'mail_match' }
      )
    ).toBe(true);
  });

  it('reads the same weather kinds in another order as the same condition', () => {
    // The server stores the kinds as a sorted set: re-sending them in the
    // order they were ticked would start the routine's ledger over.
    expect(
      sameCondition(
        { type: 'weather_change', kinds: ['snow', 'rain'] },
        { type: 'weather_change', kinds: ['rain', 'snow'] }
      )
    ).toBe(true);
  });

  it('tells a moved last day, a new filter or new kinds apart', () => {
    const base = { type: 'weather_change' as const, kinds: ['rain'] };
    expect(sameCondition(base, { ...base, until: '2026-10-01' })).toBe(false);
    expect(sameCondition(base, { ...base, kinds: ['snow'] })).toBe(false);
    expect(
      sameCondition({ type: 'mail_match', query: 'a' }, { type: 'mail_match', query: 'b' })
    ).toBe(false);
  });

  it('holds only for two absent conditions when one is absent', () => {
    expect(sameCondition(null, null)).toBe(true);
    expect(sameCondition(null, { type: 'task_overdue' })).toBe(false);
  });
});

describe('isConditionRoutine', () => {
  it('reads which clock the routine runs on', () => {
    expect(isConditionRoutine({ trigger_kind: 'condition' })).toBe(true);
    expect(isConditionRoutine({ trigger_kind: 'time' })).toBe(false);
  });
});

/**
 * `weatherRuleSentence` — the studio says when a weather routine fires exactly
 * as the server applies it (ADR-322 amendment 2026-09-29): the kinds it
 * watches, the horizon, the STRICT probability floor, the one source.
 */
describe('weatherRuleSentence', () => {
  const RULE = { horizon_hours: 4, min_precipitation_percent: 50, source: 'google_weather' };
  /** An echoing `t` that shows the interpolation, like i18next would. */
  const t = (key: string, options?: Record<string, unknown>) =>
    options ? `${key}|${JSON.stringify(options)}` : key.split('.').pop()!;

  it('names every kind when the routine chose none', () => {
    const sentence = weatherRuleSentence(RULE, null, 'en', t);

    expect(sentence).toBe(
      'scheduled_actions.studio.weather_rule|' +
        JSON.stringify({ kinds: 'rain, drizzle, snow, or thunderstorm', hours: 4, percent: 50 })
    );
  });

  it('names only the kinds the edited weather routine watches, in the studio order', () => {
    const sentence = weatherRuleSentence(
      RULE,
      { type: 'weather_change', kinds: ['snow', 'rain'] },
      'en',
      t
    );

    expect(sentence).toContain('"kinds":"rain or snow"');
  });

  it('ignores the kinds of a routine of another type', () => {
    const sentence = weatherRuleSentence(RULE, { type: 'mail_match', kinds: ['snow'] }, 'en', t);

    expect(sentence).toContain('"kinds":"rain, drizzle, snow, or thunderstorm"');
  });

  it('claims nothing when no kind it knows is watched', () => {
    expect(weatherRuleSentence(RULE, { type: 'weather_change', kinds: ['hail'] }, 'en', t)).toBe(
      null
    );
  });

  it('reads the published figures, never typed ones', () => {
    const sentence = weatherRuleSentence(
      { ...RULE, horizon_hours: 2, min_precipitation_percent: 70 },
      null,
      'en',
      t
    );

    expect(sentence).toContain('"hours":2');
    expect(sentence).toContain('"percent":70');
  });
});
