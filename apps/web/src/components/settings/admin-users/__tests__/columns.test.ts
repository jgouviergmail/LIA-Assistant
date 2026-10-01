/**
 * The switches the table renders are the switches the backend serves.
 *
 * Two copies of one list in two languages: a switch added to
 * `admin_columns.ADMIN_USER_SWITCHES` alone is a field the API sends and no
 * column shows; one added here alone is a column that reads `undefined`.
 */

import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

import { ADMIN_USER_SWITCHES, ADMIN_USER_SWITCH_ICONS } from '../columns';

const ADMIN_COLUMNS = readFileSync(
  join(process.cwd(), '../api/src/domains/users/admin_columns.py'),
  'utf8'
);

function pythonTuple(name: string): string[] {
  const block = ADMIN_COLUMNS.slice(ADMIN_COLUMNS.indexOf(`${name}: Final[tuple[str, ...]] = (`));
  const body = block.slice(block.indexOf('('), block.indexOf(')'));
  return [...body.matchAll(/"([a-z_]+)"/g)].map(match => match[1]);
}

describe('the admin switch columns', () => {
  it('are the backend switches, in the same order', () => {
    expect(pythonTuple('ADMIN_USER_SWITCHES')).toEqual([...ADMIN_USER_SWITCHES]);
  });

  it('each carry a distinct glyph, so no two columns look alike', () => {
    const icons = ADMIN_USER_SWITCHES.map(key => ADMIN_USER_SWITCH_ICONS[key]);
    expect(new Set(icons).size).toBe(icons.length);
  });
});
