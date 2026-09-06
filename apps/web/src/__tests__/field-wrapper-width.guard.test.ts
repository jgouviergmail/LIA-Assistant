/**
 * A width on a field binds the FIELD; its parent measures the WRAPPER.
 *
 * `Input` and `Textarea` wrap themselves in `FieldFrame`, which is `w-full`
 * (`ui/input.tsx`, `ui/textarea.tsx` — the only two primitives that do). A
 * width put on the control narrows the control and leaves the wrapper
 * claiming the whole row, so anything beside the field — a unit, a caption, a
 * second control — is pushed to the far edge.
 *
 * Measured in the browser 2026-09-06: `week(s)` sat 330 px from an 80 px field
 * whose `w-20` read as perfectly correct in the source. The class that looks
 * wrong is not the one that is, which is why review never caught it.
 *
 * `tsc`, ESLint and jsdom all miss this — jsdom computes no layout at all.
 *
 * The fix, and the only accepted shape:
 *
 *     <div className="w-24 shrink-0">
 *       <Input className="w-full" />
 *     </div>
 *
 * **This guard is tested against a known-bad sample on every run.** Two
 * earlier versions passed while the defect was in the tree: one scanned
 * `[^>]*` from the tag name and stopped at the `>` inside `onChange={e =>`,
 * the other read a capture group that no longer existed. A guard that cannot
 * fail is worse than no guard: it reports safety it never checked.
 */

import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { globSync } from 'tinyglobby';
import { describe, expect, it } from 'vitest';

const SRC = join(process.cwd(), 'src');

/** The two primitives that carry their own `FieldFrame` wrapper. */
const WRAPPED_CONTROL = /<(Input|Textarea)\b/g;

/** Any width that is not `w-full`: `w-20`, `w-[7rem]`, `sm:w-1/2`… */
const NARROWING_WIDTH = /(?:^|\s|:)w-(?!full\b)[\w[\]./%-]+/;

/**
 * The className of one JSX element, whatever the order of its attributes.
 *
 * Scanning `[^>]*` from the tag name looks obvious and is wrong: `onChange={e
 * =>` contains a `>`, so the scan stops there and every attribute written
 * after the handler is invisible.
 */
function classNameOf(source: string, from: number): string | null {
  const end = source.indexOf('/>', from);
  const body = source.slice(from, end === -1 ? from + 900 : end);
  const attribute = /className=\{?["'`]([^"'`]*)/.exec(body);
  return attribute ? attribute[1] : null;
}

/** Every wrapped control in `source` whose own className narrows it. */
export function narrowedControls(source: string): { tag: string; classes: string }[] {
  const found: { tag: string; classes: string }[] = [];
  for (const match of source.matchAll(WRAPPED_CONTROL)) {
    const classes = classNameOf(source, match.index);
    if (classes === null || !NARROWING_WIDTH.test(classes)) continue;
    found.push({ tag: match[1], classes: classes.trim() });
  }
  return found;
}

const BAD_SAMPLE = `
  <div className="flex items-center gap-2">
    <Input
      id="x"
      type="number"
      onChange={e => set(Number(e.target.value))}
      className="w-24"
    />
    <span>unit</span>
  </div>`;

const GOOD_SAMPLE = `
  <div className="flex items-center gap-2">
    <div className="w-24 shrink-0">
      <Input id="x" onChange={e => set(e)} className="w-full" />
    </div>
    <span>unit</span>
  </div>`;

describe('the guard itself', () => {
  it('catches a narrowing width written AFTER the handler', () => {
    // The exact shape both earlier versions walked straight past.
    expect(narrowedControls(BAD_SAMPLE)).toEqual([{ tag: 'Input', classes: 'w-24' }]);
  });

  it('accepts the bounded-wrapper shape', () => {
    expect(narrowedControls(GOOD_SAMPLE)).toEqual([]);
  });
});

describe('a bounded field is bounded on its wrapper', () => {
  it('never puts a narrowing width on a wrapped control', () => {
    const files = globSync(['components/**/*.tsx', 'app/**/*.tsx'], { cwd: SRC });
    // A silent glob miss would make this pass by measuring nothing.
    expect(files.length).toBeGreaterThan(100);

    const offenders: string[] = [];
    for (const relative of files) {
      if (relative.includes('__tests__')) continue;
      const source = readFileSync(join(SRC, relative), 'utf8');
      for (const { tag, classes } of narrowedControls(source)) {
        offenders.push(`${relative} (${tag} → "${classes}")`);
      }
    }

    expect(
      offenders,
      'a width here narrows the control while its `FieldFrame` wrapper still ' +
        'claims the row. Wrap the control in a bounded div and give the ' +
        'control `w-full`'
    ).toEqual([]);
  });
});
