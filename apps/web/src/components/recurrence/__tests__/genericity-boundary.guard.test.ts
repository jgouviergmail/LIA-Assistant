/**
 * The recurrence editor must not know who uses it.
 *
 * Its types lived in `hooks/useScheduledActions.ts` while routines were the
 * only consumer, and the five components read them from there — the generic
 * layer importing its shape from ONE of its users. That is invisible with a
 * single consumer, and becomes absurd with two: the reminders settings screen
 * would describe a reminder in the routines' vocabulary.
 *
 * `tsc` cannot see this: the import resolves, the types are right, everything
 * compiles. Only a rule about WHERE a name comes from catches it, which is why
 * this is a guard and not a type.
 *
 * The mirror of `apps/api/tests/unit/core/recurrence/test_no_domain_import.py`.
 */

import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';
import { globSync } from 'tinyglobby';

const SRC = join(process.cwd(), 'src');

/** The generic recurrence surface: the editor, and the helpers it stands on. */
const GENERIC = ['components/recurrence/*.tsx', 'lib/recurrence.ts', 'types/recurrence.ts'];

/**
 * Import prefixes a generic module may never reach for.
 *
 * A hook is one consumer's data access; a settings component is one consumer's
 * screen. Either one, imported here, makes the editor the property of whoever
 * mounted it first.
 */
const FORBIDDEN = ['@/hooks/', '@/components/settings/', '@/components/dashboard/'];

function importsOf(source: string): string[] {
  const found: string[] = [];
  const pattern = /from\s+['"]([^'"]+)['"]/g;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(source)) !== null) found.push(match[1]);
  return found;
}

describe('the recurrence editor stays generic', () => {
  it('imports nothing from a consumer', () => {
    const files = globSync(GENERIC, { cwd: SRC });
    // A silent glob miss would make this test pass by measuring nothing.
    expect(files.length).toBeGreaterThanOrEqual(6);

    const offenders: string[] = [];
    for (const relative of files) {
      const source = readFileSync(join(SRC, relative), 'utf8');
      for (const specifier of importsOf(source)) {
        if (FORBIDDEN.some(prefix => specifier.startsWith(prefix))) {
          offenders.push(`${relative}: ${specifier}`);
        }
      }
    }

    expect(
      offenders,
      `the recurrence surface must serve consumers it does not know:\n${offenders.join('\n')}`
    ).toEqual([]);
  });

  it('keeps the vocabulary in the neutral module', () => {
    const types = readFileSync(join(SRC, 'types/recurrence.ts'), 'utf8');
    for (const name of ['RecurrenceSpec', 'DailyTimes', 'TimeOfDay', 'SeriesEnd']) {
      expect(types).toContain(`interface ${name}`);
    }
    expect(types).toContain('type RecurrenceFreq');
  });
});
