/**
 * One reading of `src/`, shared by every guard that inspects the source tree.
 *
 * Eleven guards look at (nearly) every first-party file: the axios error shape,
 * raw `fetch`, the Tailwind v3 colour idiom, self-hosted fonts, field-wrapper
 * widths, the JSON-LD sink, the `'use client'` prologue, embedded image
 * credentials, form-control names, viewport units and dimmed text. Two rules
 * make such a guard trustworthy, and both were learnt from guards reported red
 * on a clean tree:
 *
 * 1. **The tree is read at COLLECTION, never inside a test.** vitest checks a
 *    synchronous test's budget only AFTER the body returns (`withTimeout` in
 *    `@vitest/runner`: its timer cannot fire while the body blocks), so a
 *    whole-tree read inside `it()` can never be stopped as a hang — its budget
 *    only measures the host. Measured 2026-10-16: a few seconds alone, 49.6 s for
 *    one such file under the full suite with coverage, and four guards red
 *    against the 15 s budget on a clean tree. Collection is not timed: a guard
 *    reads its files at module scope and its tests read memory. `readSources`
 *    refuses to run inside a test, so the rule holds by construction; a hook is
 *    timed too, so no guard reads there either.
 * 2. **Dirent types come from `readdirSync` itself** (no `statSync` per entry),
 *    and each selected file is read once.
 */

import fs from 'node:fs';
import path from 'node:path';

import { TestRunner } from 'vitest';

/** Absolute path of `apps/web/src`. */
export const SRC_ROOT = path.resolve(__dirname, '..');

/** Where a file of `src/` sits: what a guard selects on. */
export interface SourcePath {
  /** Path relative to `src/`, always with forward slashes. */
  readonly relative: string;
  /** Whether the file lives under a `__tests__/` folder. */
  readonly isTest: boolean;
}

/** A selected file, read. */
export interface SourceFile extends SourcePath {
  /** The file's text. */
  readonly text: string;
}

/**
 * Every file of `src/` a guard selects, read — at collection only.
 *
 * @param select - Which files the guard inspects, by their place in the tree.
 * @returns The selected files, in scan order.
 * @throws Error when called inside a running test (rule 1 above).
 */
export function readSources(select: (file: SourcePath) => boolean): SourceFile[] {
  if (TestRunner.getCurrentTest()) {
    throw new Error(
      'readSources() reads the tree at collection: declare the files at module scope. ' +
        "Inside a test, vitest's budget measures the host, never the guard (source-scan.ts)."
    );
  }
  return fs
    .readdirSync(SRC_ROOT, { recursive: true, withFileTypes: true })
    .filter(entry => entry.isFile())
    .map(entry => {
      const absolute = path.join(entry.parentPath, entry.name);
      const segments = path.relative(SRC_ROOT, absolute).split(path.sep);
      const folders = segments.slice(0, -1);
      return {
        absolute,
        folders,
        place: { relative: segments.join('/'), isTest: folders.includes('__tests__') },
      };
    })
    .filter(({ folders, place }) => !folders.includes('node_modules') && select(place))
    .map(({ absolute, place }) => ({ ...place, text: fs.readFileSync(absolute, 'utf8') }));
}

/**
 * Whether a line is pure prose — naming a defect in a doc block is allowed.
 *
 * @param line - A single source line.
 * @returns True when the line opens with a comment marker.
 */
export function isCommentLine(line: string): boolean {
  const trimmed = line.trimStart();
  return trimmed.startsWith('*') || trimmed.startsWith('//') || trimmed.startsWith('/*');
}

/** Which part of the read files a scan looks at. */
export interface ScanScope {
  /**
   * Include `__tests__/` files. Default `false`.
   *
   * A guard about production behaviour (raw `fetch`) must not fire on a test
   * that stubs it. A guard about a defect PATTERN (the axios error shape) must
   * include tests: a fabricated mock of a shape production never emits is how
   * that defect stayed green for months.
   */
  includeTests?: boolean;
  /** Basenames to skip — a guard that spells its own defect out in an oracle. */
  exclude?: readonly string[];
}

/**
 * Files with at least one non-comment line matching `pattern`.
 *
 * @param files - The files the guard read at collection.
 * @param pattern - Regex applied line by line.
 * @param scope - What to look at; see {@link ScanScope}.
 * @returns Relative paths, in scan order.
 */
export function filesMatching(
  files: readonly SourceFile[],
  pattern: RegExp,
  scope: ScanScope = {}
): string[] {
  const excluded = new Set(scope.exclude ?? []);
  return files
    .filter(file => scope.includeTests || !file.isTest)
    .filter(file => !excluded.has(file.relative.split('/').pop() ?? ''))
    .filter(file => file.text.split('\n').some(line => !isCommentLine(line) && pattern.test(line)))
    .map(file => file.relative);
}
