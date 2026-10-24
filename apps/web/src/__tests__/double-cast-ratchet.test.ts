/**
 * Double-assertion ratchet (audit AC-037): what the counter sees, and what the
 * ratchet decides.
 *
 * `x as unknown as T` lets a test double — or production code — claim any type,
 * so it can drift from the contract it stands in for without a single compiler
 * error. 119 existed on 2026-10-23 (107 in tests, 4 end-to-end, 8 in production)
 * and nothing counted them. The ratchet freezes the count per file: it may only
 * go down.
 */

import { describe, expect, it } from 'vitest';

import { compare, countDoubleCasts, shrink } from '../../scripts/double-cast.mjs';

describe('countDoubleCasts', () => {
  it('counts a double assertion through unknown or any, parenthesised or not', () => {
    const source = [
      'const a = value as unknown as Target;',
      'const b = (value as unknown) as Target;',
      'const c = value as any as Target;',
    ].join('\n');
    expect(countDoubleCasts(source, 'file.ts')).toBe(3);
  });

  it('ignores a single assertion, a comment and a string', () => {
    const source = [
      'const a = value as Target;',
      'const b = value as unknown;',
      '// value as unknown as Target',
      "const c = 'value as unknown as Target';",
    ].join('\n');
    expect(countDoubleCasts(source, 'file.ts')).toBe(0);
  });

  it('reads TSX', () => {
    const source = 'const node = <div>{(props as unknown as { label: string }).label}</div>;';
    expect(countDoubleCasts(source, 'component.tsx')).toBe(1);
  });
});

describe('compare', () => {
  it('fails a file that grew and a file that is new', () => {
    const verdict = compare({ 'a.ts': 3, 'new.ts': 1 }, { 'a.ts': 2 });
    expect(verdict.regressions).toEqual(['a.ts: 3 > 2', 'new.ts: 1 > 0']);
  });

  it('reports a file that improved, and passes', () => {
    const verdict = compare({ 'a.ts': 1 }, { 'a.ts': 2, 'gone.ts': 1 });
    expect(verdict.regressions).toEqual([]);
    expect(verdict.improved).toEqual(['a.ts', 'gone.ts']);
  });
});

describe('shrink', () => {
  it('lowers a count, drops a cleared file, and never adds or raises one', () => {
    expect(shrink({ 'a.ts': 1, 'b.ts': 5, 'new.ts': 2 }, { 'a.ts': 2, 'b.ts': 3, 'c.ts': 1 })).toEqual({
      'a.ts': 1,
      'b.ts': 3,
    });
  });
});
