/**
 * Accessible-name guard for design-system form controls.
 *
 * ## Why this exists
 *
 * `jsx-a11y` was the obvious home for this check, and it does not work here.
 * Mapping `Input`/`Textarea` to their native elements was measured on
 * 2026-08-05 and produced 96 findings whose sampled cases were all CORRECT
 * code: the rule analyses each element in isolation, so a `<Label htmlFor="x">`
 * sitting next to an `<Input id="x">` reads as an unlabelled control. That
 * pattern is this codebase's norm, so the rule can only cry wolf. The repo
 * already documents the same limitation inline in `login-form.tsx`
 * ("static analysis cannot resolve it across elements").
 *
 * So the check is narrowed to what static analysis CAN decide without guessing:
 * a control that carries **no naming mechanism at all** — no `label` prop, no
 * `aria-label`, no `aria-labelledby`, and no `id` for an external
 * `<Label htmlFor>` to target — cannot be named by anything. There is no
 * context in which that is correct, so there is no false positive to weigh.
 *
 * A `placeholder` is deliberately NOT accepted as a name: it disappears as soon
 * as the user types, and it is advisory text, not a label (WCAG 3.3.2).
 *
 * ## Ratchet
 *
 * `ALLOWED` freezes the debt PER FILE, shrink-only, like the other ratchets in
 * this repo. A file may only decrease; a file absent from the map must be at
 * zero. Never raise an entry to absorb a regression — name the control instead.
 */

import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';
import { describe, it, expect } from 'vitest';

const SRC = join(process.cwd(), 'src');

/** Controls whose accessible name this guard can reason about. */
const CONTROL = /<(Input|Textarea)\b/g;

/** Any of these makes a name possible; `placeholder` is not among them.
 *
 * `{...controlProps}` counts: it is the object `useFieldA11y` returns, and it
 * carries the very `id` an external `<Label htmlFor>` targets — the design
 * system's own naming mechanism. Without it here, every correct use of the
 * field primitive outside `ui/` reads as an unnamed control, which would push
 * callers to hand-roll ARIA instead of using the hook. Same failure mode as
 * the `jsx-a11y` mapping this guard replaced, one layer up. */
const NAMING_ATTRS = ['label=', 'aria-label', 'aria-labelledby', 'id=', '{...controlProps}'];

/**
 * Per-file count of controls with no naming mechanism, frozen at the audited
 * value. Shrink-only: lower an entry as the file is fixed, never raise one.
 */
const ALLOWED: Record<string, number> = {};

function walk(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) {
      if (entry === '__tests__') continue;
      out.push(...walk(full));
    } else if (entry.endsWith('.tsx')) {
      out.push(full);
    }
  }
  return out;
}

/** Extract the opening tag starting at `from`, brace-aware. */
function openingTag(source: string, from: number): string {
  let depth = 0;
  for (let i = from; i < source.length; i += 1) {
    const char = source[i];
    if (char === '{') depth += 1;
    else if (char === '}') depth -= 1;
    else if (char === '>' && depth === 0) return source.slice(from, i);
  }
  return source.slice(from, from + 600);
}

function unnamedControlsPerFile(): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const file of walk(SRC)) {
    const source = readFileSync(file, 'utf8');
    let match: RegExpExecArray | null;
    CONTROL.lastIndex = 0;
    while ((match = CONTROL.exec(source)) !== null) {
      const tag = openingTag(source, match.index);
      if (NAMING_ATTRS.some(attr => tag.includes(attr))) continue;
      const key = relative(process.cwd(), file).replaceAll('\\', '/');
      counts[key] = (counts[key] ?? 0) + 1;
    }
  }
  return counts;
}

describe('design-system form controls carry a naming mechanism', () => {
  it('sees the source tree — a scan that finds nothing proves nothing', () => {
    expect(walk(SRC).length).toBeGreaterThan(300);
  });

  it('detects a control with no naming mechanism', () => {
    // The detector must actually fire, or the guard is decoration.
    const tag = openingTag('<Input value={x} placeholder="p" />', 0);
    expect(NAMING_ATTRS.some(attr => tag.includes(attr))).toBe(false);
  });

  it('accepts every naming mechanism', () => {
    for (const named of [
      '<Input label="Email" />',
      '<Input aria-label="Email" />',
      '<Input aria-labelledby="x" />',
      '<Input id="email" />',
    ]) {
      const tag = openingTag(named, 0);
      expect(NAMING_ATTRS.some(attr => tag.includes(attr))).toBe(true);
    }
  });

  it('no file exceeds its frozen count of unnamed controls', () => {
    const current = unnamedControlsPerFile();
    const regressions = Object.entries(current)
      .filter(([file, count]) => count > (ALLOWED[file] ?? 0))
      .map(([file, count]) => `${file}: ${count} > ${ALLOWED[file] ?? 0}`);
    expect(regressions).toEqual([]);
  });

  it('every frozen entry still has the debt it claims — otherwise remove it', () => {
    const current = unnamedControlsPerFile();
    const stale = Object.keys(ALLOWED).filter(file => (current[file] ?? 0) === 0);
    expect(stale).toEqual([]);
  });
});
