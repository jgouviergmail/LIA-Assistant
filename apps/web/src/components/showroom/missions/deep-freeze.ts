/**
 * Deep-freeze helper shared by every showroom mission definition.
 *
 * Definitions are pure static data: freezing at module load turns any
 * accidental mutation into a loud TypeError in dev/tests instead of a
 * silent storyboard drift.
 */

export function deepFreeze<T>(value: T): T {
  if (value !== null && typeof value === 'object') {
    for (const item of Object.values(value)) deepFreeze(item);
    Object.freeze(value);
  }
  return value;
}
