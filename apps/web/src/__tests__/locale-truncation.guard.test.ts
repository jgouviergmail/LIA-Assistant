// @vitest-environment node
/**
 * Key parity proves a translation EXISTS. It says nothing about what is behind
 * the key — and that gap is where this defect lived.
 *
 * `scripts/i18n/validate_translations.py` (pre-commit + the `code-hygiene` CI
 * job) diffs the key sets of the six locales against `en`. A locale that
 * replaced a 500-character answer with a 150-character summary passes it
 * unchanged, forever. Measured 2026-07-27: **23 strings** across 13 FAQ keys
 * carried between 31 % and 58 % of the content the other locales shipped, some
 * of them for many releases. Two of them were not merely shorter but *wrong* —
 * de and it sent users to "Settings > Appearance > Timezone" (Appearance is the
 * theme section, not a parent) and named a refresh icon for a button that is a
 * trash can.
 *
 * The signal here is deliberately crude and therefore hard to argue with: a
 * string materially shorter than the same string in the other Latin-script
 * locales. It cannot see a faithful-but-wrong translation, and it is not meant
 * to — it catches *abridgement*, which is the recurring failure.
 *
 * `zh` is excluded from the comparison: Chinese carries the same meaning in
 * roughly a third of the characters, so a length ratio says nothing there.
 *
 * ALLOWED is SHRINK-ONLY. Every entry names a string that answers a
 * *different question* in that locale — a section-level permutation, where
 * pasting the reference answer would delete content the locale legitimately
 * carries. Repairing one means re-aligning its whole section, not padding the
 * string; the entry comes out then, and never goes back in.
 */

import { describe, it, expect } from 'vitest';

import deLocale from '../../locales/de/translation.json';
import enLocale from '../../locales/en/translation.json';
import esLocale from '../../locales/es/translation.json';
import frLocale from '../../locales/fr/translation.json';
import itLocale from '../../locales/it/translation.json';

/** Latin-script locales only — see the note on `zh` above. */
const LOCALES: Record<string, unknown> = {
  en: enLocale,
  fr: frLocale,
  de: deLocale,
  es: esLocale,
  it: itLocale,
};

/** Below this, length differences are noise (labels, buttons, short hints). */
const MIN_LENGTH = 150;

/** A string under this share of the median is an abridgement, not a translation. */
const MIN_RATIO = 0.6;

/**
 * SHRINK-ONLY. `key` → locales whose entry answers a different question.
 * Do not add. Re-align the section instead, then delete the line.
 */
const ALLOWED: Record<string, readonly string[]> = {
  // `tool_examples_services` is permuted between {en,fr} and {de,es,it} across
  // q4..q14: en/fr q11-q12 are the Google Drive answers, de/es/it q11-q12 are
  // the Gmail ones. Both sets are complete; only the indices disagree.
  'faq.sections.tool_examples_services.questions.q11.answer': ['de', 'it'],
  'faq.sections.tool_examples_services.questions.q12.answer': ['it'],
  // en/fr/es q6 = "preferences per connector"; de/it q6 = "which Google
  // permissions are requested". Different questions, both answered in full.
  'faq.sections.connectors.questions.q6.answer': ['de', 'it'],
};

interface Finding {
  key: string;
  locale: string;
  length: number;
  median: number;
  ratio: number;
}

function flatten(value: unknown, path = '', out: Map<string, string> = new Map()) {
  if (typeof value === 'string') {
    out.set(path, value);
  } else if (value && typeof value === 'object') {
    for (const [k, v] of Object.entries(value)) {
      flatten(v, path ? `${path}.${k}` : k, out);
    }
  }
  return out;
}

function median(values: number[]): number {
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

const flat = Object.fromEntries(
  Object.entries(LOCALES).map(([lng, doc]) => [lng, flatten(doc)])
) as Record<string, Map<string, string>>;

function findTruncated(): Finding[] {
  const findings: Finding[] = [];
  for (const [key, reference] of flat.en) {
    if (reference.length < MIN_LENGTH) continue;
    const lengths = Object.entries(flat).map(([lng, m]) => [lng, m.get(key)?.length ?? 0] as const);
    const med = median(lengths.map(([, n]) => n));
    if (med === 0) continue;
    for (const [lng, n] of lengths) {
      if (n > 0 && n < MIN_RATIO * med) {
        findings.push({ key, locale: lng, length: n, median: med, ratio: n / med });
      }
    }
  }
  return findings;
}

const truncated = findTruncated();

describe('locale content truncation', () => {
  it('has no abridged translation outside the allowlist', () => {
    const unexpected = truncated
      .filter(f => !(ALLOWED[f.key] ?? []).includes(f.locale))
      .map(
        f =>
          `${f.locale} ${f.key} — ${f.length}/${Math.round(f.median)} chars (${f.ratio.toFixed(2)})`
      );

    expect(
      unexpected,
      'these strings carry materially less content than the same key in the other ' +
        'Latin-script locales. Translate the full text; do NOT pad, and do NOT add an ' +
        `allowlist entry unless the locale answers a genuinely different question:\n  ${unexpected.join('\n  ')}`
    ).toEqual([]);
  });

  it('keeps the allowlist free of entries that no longer apply', () => {
    const live = new Set(truncated.map(f => `${f.key}::${f.locale}`));
    const stale: string[] = [];
    for (const [key, locales] of Object.entries(ALLOWED)) {
      for (const locale of locales) {
        if (!live.has(`${key}::${locale}`)) stale.push(`${locale} ${key}`);
      }
    }

    expect(
      stale,
      `these allowlist entries no longer describe a truncated string — delete them ` +
        `(shrink-only ratchet):\n  ${stale.join('\n  ')}`
    ).toEqual([]);
  });

  it('never lets the allowlist grow beyond what was measured', () => {
    const total = Object.values(ALLOWED).reduce((sum, l) => sum + l.length, 0);

    expect(
      total,
      'the allowlist is shrink-only: 5 entries were open when this guard landed ' +
        '(2026-07-27), all of them section-level permutations awaiting re-alignment.'
    ).toBeLessThanOrEqual(5);
  });
});
