/**
 * Coverage exclusions are checked, not asserted (audit AC-040).
 *
 * Fourteen shadcn/ui primitives were left out of the coverage measure on the
 * claim that they held no branch and no interaction of their own, and the list
 * was never re-read: dialog.tsx had gained a combobox-aware Escape handler, a
 * translated label and a focus return. An excluded file may now hold no
 * decision point — no branch, short-circuit, optional chain or default value —
 * and call no hook; a primitive that gains logic re-enters the measure and gets
 * its tests.
 */

import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

import { LOGIC_FREE_PRIMITIVES } from '../../coverage-exclusions.mjs';
import { decisionPoints } from '../../scripts/decision-points.mjs';

const WEB_DIR = join(__dirname, '..', '..');

describe('decisionPoints', () => {
  it('names every kind of decision a coverage tool counts', () => {
    const source = [
      'export function Probe({ size = 4, items }: { size?: number; items?: string[] }) {',
      '  if (size > 2) return items?.length ?? 0;',
      '  return size > 1 ? (items && items[0]) || null : null;',
      '}',
    ].join('\n');
    const { decisions, hooks } = decisionPoints(source, 'probe.tsx');
    expect(decisions.map(d => d.split('@')[0]).sort()).toEqual(
      ['&&', '?.', '??', '?:', 'default', 'if', '||'].sort()
    );
    expect(hooks).toEqual([]);
  });

  it('names a hook call', () => {
    const { hooks } = decisionPoints('const { t } = useTranslation();', 'probe.ts');
    expect(hooks).toEqual(['useTranslation@1']);
  });

  it('finds nothing in a plain re-export with class merging', () => {
    const source = "export const Part = (props: object) => <Root className={cn('a', 'b')} {...props} />;";
    expect(decisionPoints(source, 'part.tsx')).toEqual({ decisions: [], hooks: [] });
  });
});

describe('coverage exclusions', () => {
  it('give every excluded file a reason, once, in order', () => {
    const files = LOGIC_FREE_PRIMITIVES.map(entry => entry.file);
    expect(files).toEqual([...new Set(files)].sort());
    for (const entry of LOGIC_FREE_PRIMITIVES) expect(entry.reason.trim(), entry.file).not.toBe('');
  });

  it('exclude only files that exist and hold no logic of their own', () => {
    const offenders: string[] = [];
    for (const { file } of LOGIC_FREE_PRIMITIVES) {
      const path = join(WEB_DIR, file);
      if (!existsSync(path)) {
        offenders.push(`${file}: missing`);
        continue;
      }
      const { decisions, hooks } = decisionPoints(readFileSync(path, 'utf8'), file);
      if (decisions.length || hooks.length) {
        offenders.push(`${file}: ${[...decisions, ...hooks].join(' ')}`);
      }
    }
    expect(offenders, 'move these files back into the measure and test them').toEqual([]);
  });
});
