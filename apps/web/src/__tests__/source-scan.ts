/**
 * One filesystem scan of `src/`, shared by the source-level ratchets.
 *
 * Two guards (the axios-shape reader and the raw-fetch allowlist) need to look
 * at every first-party file. Done naively — `readdirSync` + `statSync` per
 * entry + `readFileSync` — that is ~2 s of BLOCKING I/O per guard inside a
 * jsdom worker, and under coverage instrumentation it starved the worker's
 * event loop badly enough for vitest's teardown watchdog to kill it. A killed
 * worker reports no result at all, which reads as a failing guard.
 *
 * So: dirent types come from `readdirSync` itself (no `statSync`), each file is
 * read once, and the result is memoised per worker.
 */

import fs from 'node:fs';
import path from 'node:path';

/** Absolute path of `apps/web/src`. */
export const SRC_ROOT = path.resolve(__dirname, '..');

export interface SourceFile {
  /** Path relative to `src/`, always with forward slashes. */
  relative: string;
  /** Whether the file lives under a `__tests__/` folder. */
  isTest: boolean;
  /** Lines of the file, in order. */
  lines: string[];
}

let cache: SourceFile[] | null = null;

/**
 * Every first-party `.ts`/`.tsx` file under `src/`, tests included.
 *
 * @returns The scanned files, read once per worker.
 */
export function sourceFiles(): SourceFile[] {
  if (cache === null) {
    cache = fs
      .readdirSync(SRC_ROOT, { recursive: true, withFileTypes: true })
      .filter(entry => entry.isFile() && /\.(ts|tsx)$/.test(entry.name))
      .map(entry => {
        const absolute = path.join(entry.parentPath, entry.name);
        const relative = path.relative(SRC_ROOT, absolute).split(path.sep).join('/');
        return {
          relative,
          isTest: relative.includes('__tests__/'),
          lines: fs.readFileSync(absolute, 'utf8').split('\n'),
        };
      });
  }
  return cache;
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

/** Which part of the tree a scan looks at. */
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
 * @param pattern - Regex applied line by line.
 * @param scope - What to look at; see {@link ScanScope}.
 * @returns Relative paths, in scan order.
 */
export function filesMatching(pattern: RegExp, scope: ScanScope = {}): string[] {
  const excluded = new Set(scope.exclude ?? []);
  return sourceFiles()
    .filter(file => scope.includeTests || !file.isTest)
    .filter(file => !excluded.has(file.relative.split('/').pop() ?? ''))
    .filter(file => file.lines.some(line => !isCommentLine(line) && pattern.test(line)))
    .map(file => file.relative);
}
