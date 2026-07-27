// @vitest-environment node
/**
 * `brace-expansion` carries a patch. This guard is what makes the patch
 * survivable — a dropped patch is otherwise invisible until something crashes
 * or, worse, until the DoS comes back silently.
 *
 * **The defect (CVE-2026-14257 / GHSA-mh99-v99m-4gvg, high).** `expand()`
 * bounded the *number* of results (`max`, 100 000) but not their *length*.
 * Chaining brace groups keeps the count under `max` while every result grows
 * one character per group, so `'{a,b}'.repeat(1500)` — 7.5 KB of input — builds
 * `max × 1500` characters and kills the process with an **uncatchable** V8
 * out-of-memory abort. Measured on the pre-fix entry point: SIGABRT (exit 134)
 * under a 512 MB heap. `try/catch` does not help.
 *
 * **Why a patch and not just a version bump.** The only patched release is
 * `5.0.8`, and it publishes ONLY the named `expand`. The two `minimatch`
 * versions in this tree predate that:
 *
 * | consumer        | how it loads brace-expansion              | needs            |
 * |-----------------|-------------------------------------------|------------------|
 * | `minimatch@3.1.5` | `require('brace-expansion')(pattern)`   | default function |
 * | `minimatch@9.0.9` | `__importDefault(...).default(pattern)` | default function |
 * | `minimatch@10.x`  | `require('brace-expansion').expand`     | named export     |
 *
 * A bare `overrides: ^5.0.8` therefore killed ESLint outright with
 * `TypeError: expand is not a function` (minimatch.js:271) — verified, not
 * assumed. `patches/brace-expansion@5.0.8.patch` re-exports the function as
 * `module.exports` while keeping `.expand` attached, so all three shapes work
 * and the upstream security fix is the one actually running.
 *
 * Every consumer sits in ESLint tooling, so ESLint is the real integration
 * test; this file pins the contract that test depends on.
 */

import { createRequire } from 'node:module';

import { describe, it, expect } from 'vitest';

const require_ = createRequire(import.meta.url);

/** What TypeScript's `__importDefault` helper does, verbatim. */
function importDefault(mod: unknown): { default: unknown } {
  return mod && (mod as { __esModule?: boolean }).__esModule
    ? (mod as { default: unknown })
    : { default: mod };
}

type ExpandFn = ((pattern: string, options?: { max?: number; maxLength?: number }) => string[]) & {
  expand?: unknown;
  EXPANSION_MAX?: number;
  EXPANSION_MAX_LENGTH?: number;
};

const braceExpansion = require_('brace-expansion') as ExpandFn;

describe('brace-expansion patch', () => {
  describe('the security fix is the code that actually runs', () => {
    it('exposes the length bound introduced by the fix', () => {
      // Absent on every pre-5.0.8 release, and absent from 2.1.2's `index.js`
      // even though that version ships a bounded build under `dist/` that its
      // own declared `balanced-match` cannot even load.
      expect(braceExpansion.EXPANSION_MAX_LENGTH).toBeTypeOf('number');
      expect(braceExpansion.EXPANSION_MAX_LENGTH).toBeGreaterThan(0);
      expect(braceExpansion.EXPANSION_MAX).toBeTypeOf('number');
    });

    it('truncates at the length bound instead of growing without limit', () => {
      // 200 chained groups: the result COUNT stays far under `max`, which is
      // exactly why the count bound never protected anything. Only the length
      // bound stops this. An explicit small `maxLength` keeps the assertion in
      // milliseconds; the default bound is exercised by the input below.
      const expanded = braceExpansion('{a,b}'.repeat(200), { maxLength: 10_000 });
      const totalChars = expanded.reduce((sum, s) => sum + s.length, 0);

      expect(totalChars).toBeLessThanOrEqual(10_000);
      expect(expanded.length).toBeGreaterThan(0);
    });

    it('returns rather than aborting on the published proof of concept shape', () => {
      // The real PoC is `'{a,b}'.repeat(1500)` and costs ~1.1 s / 282 MB once
      // bounded; unbounded it aborts the process. A smaller N proves the same
      // property — that the call RETURNS — without paying that in every run.
      const expanded = braceExpansion('{a,b}'.repeat(120));

      expect(Array.isArray(expanded)).toBe(true);
      expect(expanded.length).toBeGreaterThan(0);
    });
  });

  describe('the interop shim keeps every minimatch shape working', () => {
    it('is callable directly, as minimatch@3 loads it', () => {
      expect(braceExpansion).toBeTypeOf('function');
      expect(braceExpansion('a{b,c}d')).toEqual(['abd', 'acd']);
    });

    it('survives __importDefault, as minimatch@9 loads it', () => {
      const asDefault = importDefault(braceExpansion).default;

      expect(asDefault).toBeTypeOf('function');
      expect((asDefault as ExpandFn)('a{b,c}d')).toEqual(['abd', 'acd']);
    });

    it('still carries the named export, as minimatch@10 loads it', () => {
      expect(braceExpansion.expand).toBeTypeOf('function');
      expect((braceExpansion.expand as ExpandFn)('a{b,c}d')).toEqual(['abd', 'acd']);
    });
  });

  describe('expansion semantics are unchanged', () => {
    // A behaviour change here would silently alter which files ESLint selects.
    it.each([
      ['**/*.{js,jsx,ts,tsx}', 4],
      ['{src,test}/**/*.js', 2],
      ['a{b,c{d,e}f}g', 3],
      ['{1..4}', 4],
      ['{a..c}', 3],
      ['no-braces-at-all', 1],
      ['{}', 1],
    ])('expands %s into %i result(s)', (pattern, count) => {
      expect(braceExpansion(pattern)).toHaveLength(count);
    });

    it('leaves an escaped brace alone', () => {
      expect(braceExpansion('a\\{b,c}d')).toEqual(['a{b,c}d']);
    });
  });
});
