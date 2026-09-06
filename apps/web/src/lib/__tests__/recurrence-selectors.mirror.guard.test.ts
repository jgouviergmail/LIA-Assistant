/**
 * The editor and the API must agree on which selector each frequency reads.
 *
 * `SELECTORS_READ_BY` exists twice — in `core/recurrence/spec.py`, where it is
 * the invariant the API enforces, and in `lib/recurrence.ts`, where it tells
 * the editor what to clear on a frequency change. It cannot be imported across
 * the two languages, so nothing but this test stops the copies drifting.
 *
 * Drift is not cosmetic. If the editor keeps a selector the API refuses, the
 * reader meets a validation error for a choice they made in one click; if it
 * clears one the API needs, the rule they configured is silently discarded.
 * Measured 2026-09-06, before the invariant existed: ticking Monday and
 * Tuesday in weekly and switching to daily sent both, the API stored them, and
 * the schedule fired all seven days.
 */

import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

/** Parse the Python table into the same shape the TypeScript one has. */
function backendTable(): Record<string, string[]> {
  const source = readFileSync(
    join(process.cwd(), '..', 'api', 'src', 'core', 'recurrence', 'spec.py'),
    'utf8'
  );
  const block = source.match(
    /SELECTORS_READ_BY: dict\[str, frozenset\[str\]\] = \{([\s\S]*?)\n\}/
  );
  expect(block, 'SELECTORS_READ_BY not found in spec.py').not.toBeNull();
  const table: Record<string, string[]> = {};
  for (const line of block![1].split('\n')) {
    const row = line.match(/"(\w+)": frozenset\(\{?([^}]*)\}?\)/);
    if (!row) continue;
    const fields = [...row[2].matchAll(/"(\w+)"/g)].map(m => m[1]);
    table[row[1]] = fields.sort();
  }
  return table;
}

/** Parse the TypeScript table the same way, from source rather than import:
 *  the constant is module-private on purpose, and exporting it only for a
 *  test would widen the surface the guard exists to protect. */
function frontendTable(): Record<string, string[]> {
  const source = readFileSync(join(process.cwd(), 'src', 'lib', 'recurrence.ts'), 'utf8');
  const block = source.match(
    /const SELECTORS_READ_BY: Record<RecurrenceFreq, readonly RecurrenceSelector\[\]> = \{([\s\S]*?)\n\};/
  );
  expect(block, 'SELECTORS_READ_BY not found in recurrence.ts').not.toBeNull();
  const table: Record<string, string[]> = {};
  for (const line of block![1].split('\n')) {
    const row = line.match(/(\w+): \[([^\]]*)\]/);
    if (!row) continue;
    const fields = [...row[2].matchAll(/'(\w+)'/g)].map(m => m[1]);
    table[row[1]] = fields.sort();
  }
  return table;
}

describe('the editor reads the same selector table as the API', () => {
  it('names the same frequencies', () => {
    expect(Object.keys(frontendTable()).sort()).toEqual(Object.keys(backendTable()).sort());
  });

  it('gives every frequency the same selectors', () => {
    expect(frontendTable()).toEqual(backendTable());
  });

  it('actually parsed something, so an empty match cannot pass', () => {
    const table = backendTable();
    expect(table.weekly).toEqual(['byweekday']);
    expect(table.monthly).toEqual(['bymonthday', 'nth_weekday']);
    expect(table.daily).toEqual([]);
  });
});
