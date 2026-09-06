# Generic Recurrence — Lot 2B: the routines studio (frontend)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task, **inline** (owner directive: no subagents). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The routines studio reads and writes a `RecurrenceSpec`, through a
**generic** editor a second domain will mount unchanged. The application works
again end to end.

**Architecture:** The browser NEVER materialises a schedule. It renders what
the server computed — `schedule_display`, `times_of_day`, `next_occurrences`,
and week cells that now carry their own local hour. The editor lives in
`components/recurrence/`, its logic in pure helpers in `lib/recurrence.ts`, and
it takes its caps as props so a reminder can mount it with different ones.

**Tech Stack:** Next.js 16 App Router, React 19, TypeScript strict, Tailwind,
react-i18next (6 locales), vitest, Playwright.

**Spec:** `docs/superpowers/specs/2026-09-06-generic-recurrence-design.md` (§5,
§7), and lot 2A (the contract it now serves).

> **Lot 2A left this broken on purpose.** It removed `days_of_week`,
> `trigger_hour` and `trigger_minute` from the API. Until this lot lands, the
> studio cannot render.

## Global Constraints

- **Never `git commit` / `git push`** (owner rule). Every "Commit" step is **"Run the gate"**.
- **No subagents**: execute inline.
- `apps/web/CLAUDE.md` applies in full. In particular:
  - **a11y debt is ZERO** (`.jsx-a11y-baseline.json` → `total: 0`): no new violation is tolerable, unlike complexity which has a baseline.
  - Ratchets are **shrink-only**: `cc`, `a11y`, `react-hooks`. `ScheduledActionsSettings.tsx` is **not** in `.cc-baseline.json` — putting the editor inside it would fail CI.
  - Labelled controls go through `FieldFrame`/`useFieldA11y` (`ui/field.tsx`); the label-to-control gap is `space-y-3` and `Label` is `block`.
  - A title always carries an icon, in `text-primary`, never grey.
  - A grey badge means INACTIVE and nothing else; a live state takes its tone from `lib/status-tone.ts`.
  - `EmptyState`, `RowActions`, `SectionToolbar`, `SettingsDisclosure`, `<Button isLoading>` are the shared primitives — do not re-invent them.
  - **A refresh is not a first load**: never `loading ? <Spinner/> : content`; gate on a monotone first-load flag and announce with `aria-busy`.
  - **A busy control is not a removed one**: `aria-disabled` + a guard in the handler, never `disabled` on a focused control.
  - Components never call `fetch`: `useApiQuery` / `useApiMutation` only.
  - i18n: 6 locales, strict key parity against `en`; `zh` has no CLDR plural — duplicate to `_one`.
- Test stub renders THE KEY (`t: key => key`): assert `'recurrence.freq.weekly'`, never a French label.
- Runtime validation goes through `lia-web-dev`, never a local `pnpm dev`.

## Measured facts this plan rests on (2026-09-06)

| Fact | Measurement |
|---|---|
| The front tests cannot see a contract break | 7 404 tests green while the API had already dropped 3 fields |
| `generate-api` is dead | declared in `package.json`, `src/lib/generated` does not exist, never run by any task |
| `chipKey` collides | `chipKey(id, 1)` twice → `distinct: 1` |
| `cells.find(c => c.day === day)` loses occurrences | returns 08:00, the 18:00 failure is invisible |
| A null trigger renders as 1970 | `new Date(null)` = `1970-01-01`, `isNaN` false, so `renderOccurrences` does not filter it |
| `FrequencyControls` already exists | `MinMaxPerDay` + `HourWindow`, 2 consumers, born from this very duplication |
| a11y debt | `total: 0` |
| The notifications hub already fits | it reads `schedule_display` + `next_trigger_at: string \| null` |

## File Structure

| File | Change |
|---|---|
| `src/lib/recurrence.ts` | **New**: the mirror types + pure helpers (domain-free) |
| `src/components/recurrence/RecurrenceEditor.tsx` | **New**: the generic editor |
| `src/components/recurrence/RecurrenceSummary.tsx` | **New**: the sentence + the next real dates |
| `src/components/settings/FrequencyControls.tsx` | `HourWindow` gains optional minutes |
| `src/hooks/useScheduledActions.ts` | The contract: `recurrence`, `times_of_day`, `runs_per_day`, nullable trigger |
| `src/lib/scheduled-actions.ts` | Ordering and grid read the server's cells |
| `src/lib/schedule-label.ts` | **Deleted**: the sentence comes from the server |
| `src/components/settings/ScheduledActionsSettings.tsx` | Mounts the editor |
| `src/components/settings/ScheduledActionsTimeline.tsx` | One chip per INSTANT |
| `locales/*/translation.json` | `recurrence.*`, six languages |
| `src/__tests__/api-contract.guard.test.ts` | **New**: the front type vs the backend schema |

---

### Task 1: The contract guard — so this never goes unseen again

**Files:**
- Create: `apps/api/tests/unit/api/test_frontend_contract_guard.py`

**Interfaces:**
- Consumes: `ScheduledActionResponse` (lot 2A), and the TypeScript source.
- Produces: nothing (a guard).

**Why it lives on the BACKEND side:** a vitest test cannot introspect a
TypeScript type at runtime — types are erased. Python can read the `.ts` file
and compare its declared fields to the Pydantic schema, which is exactly how
`settings-sections.test.ts` already parses source to check a table.

- [ ] **Step 1: Write the failing test**

Create `apps/api/tests/unit/api/test_frontend_contract_guard.py`:

```python
"""The browser's view of a routine matches the schema the API serves.

Measured 2026-09-06: lot 2A removed three fields from
``ScheduledActionResponse`` and the frontend suite stayed green — 7 404 tests,
none of which could see it. The mocks fabricate the payload and the TypeScript
interface is written by hand, so neither side was checked against the other.

A vitest test cannot do this: TypeScript types are erased at runtime. Python
reads the interface as SOURCE and compares its fields to the schema, the same
way `settings-sections.test.ts` parses components to validate a table.
"""

import re
from pathlib import Path

import pytest

from src.domains.scheduled_actions.schemas import ScheduledActionResponse

HOOK = (
    Path(__file__).resolve().parents[4]
    / "web"
    / "src"
    / "hooks"
    / "useScheduledActions.ts"
)

#: Fields the browser deliberately ignores. Each entry is a decision, not an
#: oversight, so the list is short and justified.
NOT_RENDERED: frozenset[str] = frozenset(
    {
        "user_id",  # the session already scopes every read
        "condition_config",  # the studio edits it through its own flattened form
    }
)


def _declared_fields(source: str, interface: str) -> set[str]:
    """The field names of one exported TypeScript interface.

    Args:
        source: The file's text.
        interface: The interface name.

    Returns:
        Every property name it declares, optional ones included.

    Raises:
        AssertionError: When the interface is absent — a rename must fail here
            rather than silently checking nothing.
    """
    match = re.search(
        r"export interface " + interface + r"\s*\{(.*?)\n\}", source, re.S
    )
    assert match, f"interface {interface} not found in {HOOK.name}"
    body = match.group(1)
    return {
        m.group(1)
        for m in re.finditer(r"^\s{2}(\w+)\??:", body, re.M)
    }


@pytest.fixture(scope="module")
def hook_source() -> str:
    assert HOOK.is_file(), f"{HOOK} not found"
    return HOOK.read_text(encoding="utf-8")


def test_the_browser_declares_every_field_the_api_serves(hook_source: str) -> None:
    served = set(ScheduledActionResponse.model_json_schema()["properties"])
    declared = _declared_fields(hook_source, "ScheduledAction")
    missing = served - declared - NOT_RENDERED
    assert missing == set(), (
        "the API serves fields the browser does not declare, so a payload "
        f"change would go unnoticed: {sorted(missing)}"
    )


def test_the_browser_declares_nothing_the_api_stopped_serving(hook_source: str) -> None:
    served = set(ScheduledActionResponse.model_json_schema()["properties"])
    declared = _declared_fields(hook_source, "ScheduledAction")
    stale = declared - served
    assert stale == set(), (
        "the browser reads fields the API no longer serves — exactly the break "
        f"that stayed green across 7 404 frontend tests: {sorted(stale)}"
    )


def test_the_write_payloads_agree_too(hook_source: str) -> None:
    for schema, interface in (
        ("ScheduledActionCreate", "ScheduledActionCreate"),
        ("ScheduledActionUpdate", "ScheduledActionUpdate"),
    ):
        from src.domains.scheduled_actions import schemas as module

        served = set(getattr(module, schema).model_json_schema()["properties"])
        declared = _declared_fields(hook_source, interface)
        assert declared <= served, (
            f"{interface} sends fields {schema} does not accept: "
            f"{sorted(declared - served)}"
        )
```

- [ ] **Step 2: Run it — it must FAIL on the real drift**

```bash
cd apps/api && .venv/Scripts/python.exe -m pytest tests/unit/api/test_frontend_contract_guard.py -q --no-cov
```

Expected: FAIL, naming `days_of_week`, `trigger_hour`, `trigger_minute` as
stale and `recurrence`, `times_of_day`, `runs_per_day` as missing. That failure
IS the proof the guard works — it reproduces, in one test, the break 7 404
tests could not see.

- [ ] **Step 3: No implementation yet**

Task 2 turns it green by fixing the hook. Leave it red.

- [ ] **Step 4: Run the gate**

```bash
cd apps/api && .venv/Scripts/python.exe -m black --check tests/unit/api \
  && .venv/Scripts/python.exe -m ruff check tests/unit/api
```

---

### Task 2: The contract in the browser

**Files:**
- Modify: `apps/web/src/hooks/useScheduledActions.ts`
- Test: `apps/web/src/hooks/__tests__/useScheduledActions.test.ts`

**Interfaces:**
- Produces (TypeScript):
  - `RecurrenceFreq = 'once' | 'daily' | 'weekly' | 'monthly' | 'yearly'`
  - `TimeOfDay { hour: number; minute: number }`
  - `DailyTimes { mode: 'at' | 'every'; at?: TimeOfDay[]; step_minutes?: number | null; start?: TimeOfDay | null; end?: TimeOfDay | null }`
  - `SeriesEnd { kind: 'never' | 'on_date' | 'after_count'; on_date?: string | null; after_count?: number | null }`
  - `RecurrenceSpec { freq; times; anchor_date; interval; byweekday; bymonthday; nth_weekday; bymonth; end }`
  - `ScheduledAction` gains `recurrence`, `times_of_day`, `runs_per_day`; `next_trigger_at: string | null`; loses the three cron fields.
  - `ScheduledActionWeekCell` gains `hour`, `minute`.

- [ ] **Step 1: Write the failing test**

Append to `apps/web/src/hooks/__tests__/useScheduledActions.test.ts`:

```typescript
describe('the recurrence contract', () => {
  it('parses a routine that fires several times a day', () => {
    const payload: ScheduledAction = {
      id: 'a',
      user_id: 'u',
      title: 't',
      action_prompt: 'p',
      recurrence: {
        freq: 'daily',
        interval: 1,
        anchor_date: '2026-09-07',
        byweekday: [],
        bymonthday: [],
        bymonth: [],
        nth_weekday: null,
        times: {
          mode: 'at',
          at: [
            { hour: 8, minute: 0 },
            { hour: 19, minute: 0 },
          ],
        },
        end: { kind: 'never', on_date: null, after_count: null },
      },
      user_timezone: 'Europe/Paris',
      trigger_kind: 'time',
      condition_config: null,
      requires_approval: false,
      next_trigger_at: '2026-09-08T06:00:00Z',
      is_enabled: true,
      status: 'active',
      last_executed_at: null,
      execution_count: 0,
      consecutive_failures: 0,
      last_error: null,
      schedule_display: 'Tous les jours à 08:00 et 19:00',
      times_of_day: ['08:00', '19:00'],
      runs_per_day: 2,
      next_occurrences: ['2026-09-08T06:00:00Z'],
      created_at: '2026-09-01T00:00:00Z',
      updated_at: '2026-09-01T00:00:00Z',
    };
    expect(payload.times_of_day).toHaveLength(2);
    expect(payload.runs_per_day).toBe(2);
  });

  it('accepts a finished series, whose trigger is null', () => {
    const trigger: ScheduledAction['next_trigger_at'] = null;
    expect(trigger).toBeNull();
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd apps/web && pnpm exec tsc --noEmit --incremental false
```

Expected: type errors — `recurrence`, `times_of_day`, `runs_per_day` are not on
`ScheduledAction`, and `next_trigger_at` is not nullable.

- [ ] **Step 3: Rewrite the contract**

In `apps/web/src/hooks/useScheduledActions.ts`, replace the three cron fields
of `ScheduledAction`, `ScheduledActionCreate` and `ScheduledActionUpdate` with
the recurrence types above, add `times_of_day` / `runs_per_day`, make
`next_trigger_at` nullable, and add `hour` / `minute` to
`ScheduledActionWeekCell`. Full types:

```typescript
/** How a recurrence walks the calendar. `once` is a recurrence of one. */
export type RecurrenceFreq = 'once' | 'daily' | 'weekly' | 'monthly' | 'yearly';

/** A wall-clock moment inside a day, in the routine's own timezone. */
export interface TimeOfDay {
  hour: number;
  minute: number;
}

/**
 * The moments a served day fires at: explicit, or a step between two bounds.
 *
 * The browser NEVER expands a `mode: 'every'` step itself — the server
 * publishes the result in `times_of_day`. Expanding it here would be a second
 * reading of the schedule, and the two would disagree at the daylight-saving
 * edges.
 */
export interface DailyTimes {
  mode: 'at' | 'every';
  at?: TimeOfDay[];
  step_minutes?: number | null;
  start?: TimeOfDay | null;
  end?: TimeOfDay | null;
}

/** When a series stops: never, on a local date, or after N occurrences. */
export interface SeriesEnd {
  kind: 'never' | 'on_date' | 'after_count';
  /** `YYYY-MM-DD`, the LAST local day, included. */
  on_date?: string | null;
  /** How many INSTANTS, not days. */
  after_count?: number | null;
}

/**
 * A recurrence: which calendar days, and which moments inside them.
 *
 * `anchor_date` is BOTH the day the series starts and the phase of an
 * interval — without it, "every 3 days" resolves to "in 3 days" on every
 * computation (measured server-side).
 */
export interface RecurrenceSpec {
  freq: RecurrenceFreq;
  times: DailyTimes;
  /** `YYYY-MM-DD`. */
  anchor_date: string;
  interval: number;
  /** ISO weekdays, 1 = Monday … 7 = Sunday (weekly). */
  byweekday: number[];
  /** 1..31, or -1 for the last day (monthly / yearly). */
  bymonthday: number[];
  /** `[nth, ISO weekday]`, nth in -1 or 1..5 (monthly). */
  nth_weekday: [number, number] | null;
  /** 1..12 (yearly). */
  bymonth: number[];
  end: SeriesEnd;
}
```

- [ ] **Step 4: Run the tests and the guard**

```bash
cd apps/web && pnpm exec tsc --noEmit --incremental false
cd ../api && .venv/Scripts/python.exe -m pytest tests/unit/api/test_frontend_contract_guard.py -q --no-cov
```

Expected: `tsc` clean; the guard from Task 1 now GREEN — the two sides agree.

- [ ] **Step 5: Run the gate**

```bash
cd apps/web && pnpm exec eslint src/hooks/useScheduledActions.ts
```

---

### Task 3: The pure helpers — `lib/recurrence.ts`

**Files:**
- Create: `apps/web/src/lib/recurrence.ts`
- Create: `apps/web/src/lib/__tests__/recurrence.test.ts`
- Delete: `apps/web/src/lib/schedule-label.ts` and its test

**Interfaces:**
- Produces:
  - `emptyRecurrence(anchor: string): RecurrenceSpec`
  - `WEEKDAY_SETS: { all: number[]; workdays: number[]; weekend: number[] }`
  - `namedDaySet(days: readonly number[]): 'all' | 'workdays' | 'weekend' | null`
  - `materialisedTimes(times: DailyTimes): TimeOfDay[]` — **preview only**, the server stays the authority
  - `runsPerDay(times: DailyTimes): number`
  - `clockLabel(t: TimeOfDay): string`
  - `withFreq(spec, freq): RecurrenceSpec` — switching frequency keeps what the new one can use
  - `recurrenceIsComplete(spec): boolean`

**Why `materialisedTimes` exists at all**, given the rule above: the editor must
show the reader what a step produces BEFORE they save, and no round trip can
answer that while they drag a slider. It is a PREVIEW, never a source of truth —
the rendered card always uses the server's `times_of_day`. The distinction is
stated in the file's docstring and asserted by a test.

- [ ] **Step 1: Write the failing test**

Create `apps/web/src/lib/__tests__/recurrence.test.ts`:

```typescript
/**
 * The recurrence helpers: pure, domain-free, and never the authority on a
 * schedule the server already computed.
 */

import { describe, it, expect } from 'vitest';

import type { DailyTimes, RecurrenceSpec } from '@/hooks/useScheduledActions';
import {
  clockLabel,
  emptyRecurrence,
  materialisedTimes,
  namedDaySet,
  recurrenceIsComplete,
  runsPerDay,
  WEEKDAY_SETS,
  withFreq,
} from '@/lib/recurrence';

const at = (...pairs: [number, number][]): DailyTimes => ({
  mode: 'at',
  at: pairs.map(([hour, minute]) => ({ hour, minute })),
});

describe('named day sets', () => {
  it('recognises the three shapes people actually schedule', () => {
    expect(namedDaySet(WEEKDAY_SETS.all)).toBe('all');
    expect(namedDaySet(WEEKDAY_SETS.workdays)).toBe('workdays');
    expect(namedDaySet(WEEKDAY_SETS.weekend)).toBe('weekend');
  });

  it('returns null for a genuinely irregular pick', () => {
    expect(namedDaySet([1, 3, 5])).toBeNull();
  });

  it('ignores order and duplicates', () => {
    expect(namedDaySet([7, 6, 6])).toBe('weekend');
  });
});

describe('materialised times (preview only)', () => {
  it('expands a step between its bounds', () => {
    const times: DailyTimes = {
      mode: 'every',
      step_minutes: 120,
      start: { hour: 8, minute: 0 },
      end: { hour: 14, minute: 0 },
    };
    expect(materialisedTimes(times).map(clockLabel)).toEqual([
      '08:00',
      '10:00',
      '12:00',
      '14:00',
    ]);
  });

  it('sorts and de-duplicates explicit moments', () => {
    expect(materialisedTimes(at([19, 0], [8, 0], [8, 0])).map(clockLabel)).toEqual([
      '08:00',
      '19:00',
    ]);
  });

  it('counts what a served day fires', () => {
    expect(runsPerDay(at([8, 0], [12, 30], [19, 0]))).toBe(3);
  });

  it('never loops forever on a degenerate step', () => {
    const times: DailyTimes = {
      mode: 'every',
      step_minutes: 0,
      start: { hour: 0, minute: 0 },
      end: { hour: 23, minute: 59 },
    };
    expect(materialisedTimes(times).length).toBeLessThanOrEqual(48);
  });
});

describe('switching frequency', () => {
  it('keeps the weekdays when moving between weekly shapes', () => {
    const weekly: RecurrenceSpec = {
      ...emptyRecurrence('2026-09-07'),
      freq: 'weekly',
      byweekday: [1, 3],
    };
    expect(withFreq(weekly, 'weekly').byweekday).toEqual([1, 3]);
  });

  it('gives a monthly rule a day of month rather than leaving it empty', () => {
    const spec = withFreq(emptyRecurrence('2026-09-07'), 'monthly');
    expect(spec.bymonthday.length).toBeGreaterThan(0);
  });

  it('gives a weekly rule at least one weekday', () => {
    const spec = withFreq(emptyRecurrence('2026-09-07'), 'weekly');
    expect(spec.byweekday.length).toBeGreaterThan(0);
  });

  it('drops the end rule when moving to a single occurrence', () => {
    const repeating: RecurrenceSpec = {
      ...emptyRecurrence('2026-09-07'),
      end: { kind: 'after_count', on_date: null, after_count: 5 },
    };
    expect(withFreq(repeating, 'once').end.kind).toBe('never');
    expect(withFreq(repeating, 'once').interval).toBe(1);
  });
});

describe('completeness', () => {
  it('refuses a weekly rule with no weekday, as the API would', () => {
    const spec: RecurrenceSpec = {
      ...emptyRecurrence('2026-09-07'),
      freq: 'weekly',
      byweekday: [],
    };
    expect(recurrenceIsComplete(spec)).toBe(false);
  });

  it('refuses a day with no moment', () => {
    const spec: RecurrenceSpec = {
      ...emptyRecurrence('2026-09-07'),
      times: { mode: 'at', at: [] },
    };
    expect(recurrenceIsComplete(spec)).toBe(false);
  });

  it('accepts the default a reader starts from', () => {
    expect(recurrenceIsComplete(emptyRecurrence('2026-09-07'))).toBe(true);
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd apps/web && pnpm vitest run src/lib/__tests__/recurrence.test.ts
```

Expected: cannot resolve `@/lib/recurrence`.

- [ ] **Step 3: Write the helpers**

Create `apps/web/src/lib/recurrence.ts`:

```typescript
/**
 * Pure helpers for the generic recurrence editor.
 *
 * Domain-free: nothing here knows about routines or reminders, so a second
 * consumer mounts the editor without touching this file.
 *
 * **These helpers are never the authority on a schedule.** The server computes
 * the instants and publishes them (`times_of_day`, `next_occurrences`,
 * `schedule_display`); a rendered card always reads those. `materialisedTimes`
 * exists for ONE reason: the editor must show what a step produces while the
 * reader is still choosing it, and no round trip can answer that between two
 * keystrokes. It is a preview, and the moment a routine is saved the server's
 * answer replaces it.
 */

import type {
  DailyTimes,
  RecurrenceFreq,
  RecurrenceSpec,
  TimeOfDay,
} from '@/hooks/useScheduledActions';

/** ISO weekdays, Monday first — the picker and the grid agree on this. */
export const ISO_WEEKDAYS = [1, 2, 3, 4, 5, 6, 7] as const;

/** The three day sets that deserve a name instead of a list. */
export const WEEKDAY_SETS = {
  all: [1, 2, 3, 4, 5, 6, 7],
  workdays: [1, 2, 3, 4, 5],
  weekend: [6, 7],
} as const;

/** Most moments a preview will expand, whatever the caller's own cap. */
const PREVIEW_TIMES_CEILING = 48;

/** Smallest step a preview will expand — below it, a day is unbounded. */
const MIN_PREVIEW_STEP_MINUTES = 5;

export type NamedDaySet = keyof typeof WEEKDAY_SETS;

/**
 * The named shape of a weekday selection, or null when it is irregular.
 *
 * @param days - ISO weekdays, any order, duplicates tolerated.
 */
export function namedDaySet(days: readonly number[]): NamedDaySet | null {
  const chosen = [...new Set(days)].sort((a, b) => a - b).join(',');
  for (const [name, set] of Object.entries(WEEKDAY_SETS)) {
    if (set.join(',') === chosen) return name as NamedDaySet;
  }
  return null;
}

/** `HH:MM` — digits, identical in every language. */
export function clockLabel(moment: TimeOfDay): string {
  return `${String(moment.hour).padStart(2, '0')}:${String(moment.minute).padStart(2, '0')}`;
}

const minutesOf = (moment: TimeOfDay) => moment.hour * 60 + moment.minute;

/**
 * The moments of one served day — **a preview**, not an authority.
 *
 * Bounded twice: a step below `MIN_PREVIEW_STEP_MINUTES` would make a day
 * unbounded, and the ceiling stops a long window from building a list no
 * screen can show. The server refuses both anyway; refusing them here is what
 * keeps the editor responsive while the reader is still choosing.
 *
 * @param times - The moments, explicit or as a step.
 * @returns The moments, ascending and de-duplicated.
 */
export function materialisedTimes(times: DailyTimes): TimeOfDay[] {
  let moments: TimeOfDay[] = [];
  if (times.mode === 'at') {
    moments = times.at ?? [];
  } else {
    const step = times.step_minutes ?? 0;
    const start = times.start;
    const end = times.end;
    if (step >= MIN_PREVIEW_STEP_MINUTES && start && end) {
      for (
        let cursor = minutesOf(start);
        cursor <= minutesOf(end) && moments.length < PREVIEW_TIMES_CEILING;
        cursor += step
      ) {
        moments.push({ hour: Math.floor(cursor / 60), minute: cursor % 60 });
      }
    }
  }
  const unique = [...new Set(moments.map(minutesOf))].sort((a, b) => a - b);
  return unique.map(total => ({ hour: Math.floor(total / 60), minute: total % 60 }));
}

/** How many times a served day fires — an upper bound (a clock change moves it). */
export function runsPerDay(times: DailyTimes): number {
  return materialisedTimes(times).length;
}

/**
 * The recurrence a reader starts from: every day, once, at 08:00.
 *
 * @param anchor - `YYYY-MM-DD`, the day the series starts.
 */
export function emptyRecurrence(anchor: string): RecurrenceSpec {
  return {
    freq: 'daily',
    interval: 1,
    anchor_date: anchor,
    byweekday: [],
    bymonthday: [],
    bymonth: [],
    nth_weekday: null,
    times: { mode: 'at', at: [{ hour: 8, minute: 0 }] },
    end: { kind: 'never', on_date: null, after_count: null },
  };
}

/**
 * Move a recurrence to another frequency, keeping what the new one can use.
 *
 * A frequency change must not leave a shape the API refuses — a weekly rule
 * with no weekday, a monthly one with no selector — because the reader would
 * meet a validation error they did not cause. Each branch fills its own
 * selector from what is already there, or from the anchor.
 *
 * @param spec - The current recurrence.
 * @param freq - The frequency to move to.
 * @returns A complete recurrence at the new frequency.
 */
export function withFreq(spec: RecurrenceSpec, freq: RecurrenceFreq): RecurrenceSpec {
  const anchorDay = Number(spec.anchor_date.slice(8, 10)) || 1;
  const anchorMonth = Number(spec.anchor_date.slice(5, 7)) || 1;
  const anchorWeekday = isoWeekdayOf(spec.anchor_date);
  const base: RecurrenceSpec = { ...spec, freq };
  if (freq === 'once') {
    return { ...base, interval: 1, end: { kind: 'never', on_date: null, after_count: null } };
  }
  if (freq === 'weekly') {
    return {
      ...base,
      byweekday: spec.byweekday.length > 0 ? spec.byweekday : [anchorWeekday],
    };
  }
  if (freq === 'monthly') {
    const hasSelector = spec.bymonthday.length > 0 || spec.nth_weekday !== null;
    return { ...base, bymonthday: hasSelector ? spec.bymonthday : [anchorDay] };
  }
  if (freq === 'yearly') {
    return {
      ...base,
      nth_weekday: null,
      bymonth: spec.bymonth.length > 0 ? spec.bymonth : [anchorMonth],
      bymonthday: spec.bymonthday.length > 0 ? spec.bymonthday : [anchorDay],
    };
  }
  return base;
}

/**
 * The ISO weekday of a `YYYY-MM-DD` date, 1 = Monday.
 *
 * Pure calendar arithmetic in UTC: an anchor is a local DATE, so no timezone
 * must ever touch it.
 */
export function isoWeekdayOf(isoDate: string): number {
  const parsed = /^(\d{4})-(\d{2})-(\d{2})$/.exec(isoDate);
  if (!parsed) return 1;
  const [, y, m, d] = parsed;
  const day = new Date(Date.UTC(Number(y), Number(m) - 1, Number(d))).getUTCDay();
  return day === 0 ? 7 : day;
}

/**
 * Whether a recurrence is complete enough for the API to accept it.
 *
 * Mirrors the server's structural rules so the Save button states what will
 * happen instead of letting a request fail. It does NOT mirror the caps —
 * those are injected per consumer and checked by the editor itself.
 */
export function recurrenceIsComplete(spec: RecurrenceSpec): boolean {
  if (runsPerDay(spec.times) === 0) return false;
  if (spec.interval < 1) return false;
  if (spec.freq === 'weekly' && spec.byweekday.length === 0) return false;
  if (spec.freq === 'monthly' && spec.bymonthday.length === 0 && spec.nth_weekday === null) {
    return false;
  }
  if (spec.freq === 'yearly' && (spec.bymonth.length === 0 || spec.bymonthday.length === 0)) {
    return false;
  }
  if (spec.end.kind === 'on_date' && !spec.end.on_date) return false;
  if (spec.end.kind === 'after_count' && !spec.end.after_count) return false;
  return true;
}
```

- [ ] **Step 4: Run the tests**

```bash
cd apps/web && pnpm vitest run src/lib/__tests__/recurrence.test.ts
```

- [ ] **Step 5: Run the gate**

```bash
cd apps/web && pnpm exec eslint src/lib/recurrence.ts src/lib/__tests__/recurrence.test.ts \
  && pnpm exec tsc --noEmit --incremental false
```

---

### Tasks 4-8

Tasks 4 (`RecurrenceEditor` + `RecurrenceSummary`), 5 (i18n in six
languages), 6 (`ScheduledActionsSettings`), 7 (`ScheduledActionsTimeline`) and
8 (the full gate, mobile parity, ratchets) are written after Task 3 lands: the
editor's props follow the helpers' final shape, and writing its JSX before the
helpers exist is how the lot-1 plan acquired five defects.

Their contracts are already fixed:

- **`RecurrenceEditor`** — props `{ value: RecurrenceSpec; onChange: (next: RecurrenceSpec) => void; limits: { maxTimesPerDay: number; minStepMinutes: number; maxSeriesCount: number }; timezone: string; idPrefix: string }`. Two questions in order — *which days*, then *at what time* — never one flat form. Every control through `FieldFrame`; the day picker is a group of `<button aria-pressed>`; the frequency is a `Select`; the anchor shows only when it changes an outcome (`once`, `interval > 1`, or a future start).
- **`RecurrenceSummary`** — props `{ spec; timezone; locale; occurrences?: string[] }`. Renders the sentence, then "up to N times a day" (an upper bound, never an exact count), then the next three real dates when the server has supplied them.
- **i18n** — namespace `recurrence.*`, never `scheduled_actions.*`, so the second consumer inherits no vocabulary from the first.
- **Timeline** — one chip per INSTANT: `chipKey(actionId, day, hour, minute)`, and the grid row comes from the CELL's `hour`, not from a routine field that no longer exists.

## Test plan additions for lot 2B

| # | What it pins | Where |
|---|---|---|
| 39 | The front type and the API schema agree, in both directions | `test_frontend_contract_guard.py` |
| 40 | A routine firing twice a day draws two distinct chips | timeline test |
| 41 | A cell is found by (day, hour), never by day alone | timeline test |
| 42 | A finished series never renders 1970 | settings test |
| 43 | The editor produces every corpus shape and refuses what the API refuses | editor test |
| 44 | Mobile parity: every control reachable at 390 px | editor test + axe |
| 45 | The live summary states an upper bound, never an exact count | summary test |
| 46 | Six-locale parity for `recurrence.*` | i18n parity |
| 47 | The editor names every control (a11y debt stays 0) | `form-control-names.guard` |

## Self-Review

**Spec coverage.** §5 (genericity) → Tasks 3-4, caps as props. §7 (UX) →
Tasks 4, 6, 7. §7.1 R1/R2 → Task 7. §7.1 R3/R4 → Tasks 2 and 6. §4.10 (upper
bound) → Task 4's summary.

**Placeholder scan.** Tasks 4-8 are deliberately deferred rather than sketched:
writing JSX against helpers that do not exist yet is exactly how the lot-1 plan
acquired five defects. Their CONTRACTS are fixed above, which is what a
follow-on task needs.

**Type consistency.** `RecurrenceSpec`, `DailyTimes`, `TimeOfDay`, `SeriesEnd`
are declared in Task 2 and imported by name in Task 3. `materialisedTimes`,
`runsPerDay`, `namedDaySet`, `withFreq`, `recurrenceIsComplete`,
`emptyRecurrence`, `clockLabel`, `isoWeekdayOf`, `WEEKDAY_SETS`, `ISO_WEEKDAYS`
are produced by Task 3 and consumed by Tasks 4, 6, 7.
