/**
 * The destinations have ONE reader of their flags.
 *
 * `visibleDestinations` filters the table by flags; WHICH value a flag takes —
 * what the instance offers now, the operator's switch included — is decided in
 * `offered-destinations.ts` alone. The world's « Application » list called the
 * filter itself with the deployment's ceilings, and kept offering what the
 * operator had switched off. `tsc` cannot see that: the call type-checks, the
 * flags have the right shape. Only a rule about WHO calls the filter does.
 */
import { readdirSync, readFileSync } from 'node:fs';
import { join, relative, resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

const SRC = resolve(__dirname, '../../..');

/** The filter's definition, and the one door that feeds it. */
const DEFINITION = 'lib/dashboard-nav.ts';
const DOOR = 'components/dashboard/offered-destinations.ts';

function sources(folder: string): string[] {
  return readdirSync(folder, { withFileTypes: true }).flatMap(entry => {
    const path = join(folder, entry.name);
    if (entry.isDirectory()) return entry.name === '__tests__' ? [] : sources(path);
    return /\.tsx?$/.test(entry.name) ? [path] : [];
  });
}

describe('the destinations table has one reader of its flags', () => {
  it('lets nothing but the door call the table filter', () => {
    const callers = sources(SRC)
      .filter(path => /\bvisibleDestinations\(/.test(readFileSync(path, 'utf-8')))
      .map(path => relative(SRC, path).replaceAll('\\', '/'));

    // Both are named: a walk that read nothing fails, it does not pass by default.
    expect(callers.sort()).toEqual([DOOR, DEFINITION].sort());
  });
});
