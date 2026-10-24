/**
 * Files outside the frontend coverage measure, each with its reason (audit AC-040).
 *
 * Fourteen shadcn/ui primitives used to be excluded on the claim that they had no
 * branch and no interaction of their own — and the list was never re-read while
 * dialog.tsx gained a combobox-aware Escape handler, a translated label and a
 * focus return. The claim is now CHECKED: the guard
 * `src/__tests__/coverage-exclusions.guard.test.ts` refuses an excluded file that
 * holds a decision point (a branch, a short-circuit, an optional chain, a default
 * value) or calls a hook. Ten of the fourteen held one and re-entered the
 * measure on 2026-10-23; a primitive that gains logic leaves this list and gets
 * its tests.
 */

/** @type {ReadonlyArray<{ file: string, reason: string }>} */
export const LOGIC_FREE_PRIMITIVES = [
  {
    file: 'src/components/ui/accordion.tsx',
    reason: 'Radix Accordion parts with cn() class merging: no decision, no hook.',
  },
  {
    file: 'src/components/ui/label.tsx',
    reason: 'Radix Label with cn() class merging: no decision, no hook.',
  },
  {
    file: 'src/components/ui/switch.tsx',
    reason: 'Radix Switch with cn() class merging: no decision, no hook.',
  },
  {
    file: 'src/components/ui/tabs.tsx',
    reason: 'Radix Tabs parts with cn() class merging: no decision, no hook.',
  },
];
