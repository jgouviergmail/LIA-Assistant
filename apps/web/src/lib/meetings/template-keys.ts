/**
 * Stable section keys for the minutes template (ADR-258).
 *
 * The API requires `^[a-z][a-z0-9_]{1,39}$` and unique keys; the user only
 * ever types a heading. The key is derived from it — accents folded, anything
 * else replaced by `_` — and kept once assigned, so renaming a heading later
 * does not orphan the section in the generated minutes.
 */

const MAX_KEY_LENGTH = 40;
const FALLBACK_STEM = 'section';

/**
 * A key candidate from a heading.
 *
 * @param label - The heading the user typed.
 * @returns A slug matching the API pattern (before uniqueness).
 */
export function slugifySectionLabel(label: string): string {
  const folded = label
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
    .replace(/_+/g, '_');
  let slug = /^[a-z]/.test(folded) ? folded : `${FALLBACK_STEM}_${folded}`;
  slug = slug.replace(/_+$/g, '');
  if (slug.length < 2) slug = FALLBACK_STEM;
  return slug.slice(0, MAX_KEY_LENGTH).replace(/_+$/g, '') || FALLBACK_STEM;
}

/**
 * A key not already in `taken`.
 *
 * @param label - The heading.
 * @param taken - Keys already used by other sections.
 * @returns The slug, suffixed `_2`, `_3`… when it collides.
 */
export function uniqueSectionKey(label: string, taken: Iterable<string>): string {
  const used = new Set(taken);
  const base = slugifySectionLabel(label);
  if (!used.has(base)) return base;
  for (let n = 2; ; n++) {
    const suffix = `_${n}`;
    const candidate = `${base.slice(0, MAX_KEY_LENGTH - suffix.length)}${suffix}`;
    if (!used.has(candidate)) return candidate;
  }
}

/**
 * Keys derived afresh from the headings, unique in order — for a template
 * being CREATED, whose keys nothing refers to yet. An existing template keeps
 * its keys through renames (`uniqueSectionKey` at insertion), because the
 * minutes already written carry them.
 */
export function rederiveSectionKeys<T extends { label: string }>(sections: readonly T[]): T[] {
  const taken: string[] = [];
  return sections.map(section => {
    const key = uniqueSectionKey(section.label, taken);
    taken.push(key);
    return { ...section, key };
  });
}
