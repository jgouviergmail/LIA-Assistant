/**
 * Deep-freeze helper for reducer tests.
 *
 * Recursively freezes an object graph so that any accidental in-place
 * mutation performed by code under test throws a TypeError (ES modules run
 * in strict mode). Used to prove reducers are genuinely immutable instead of
 * only asserting on the returned value.
 *
 * Not a test file: imported by test files only, and excluded from coverage
 * by the vitest.config.ts exclusion on double-underscore test directories.
 */

export function deepFreeze<T>(value: T): T {
  if (value !== null && typeof value === 'object' && !Object.isFrozen(value)) {
    Object.freeze(value);
    for (const inner of Object.values(value)) {
      deepFreeze(inner);
    }
  }
  return value;
}
